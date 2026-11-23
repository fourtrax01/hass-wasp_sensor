"""Binary sensor platform for Wasp Sensor."""
import logging
import asyncio
from functools import partial

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.core import Event, callback

from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
)

from .const import (
    BINARY_SENSOR,
    BINARY_SENSOR_DEVICE_CLASS,
    DOMAIN,
    SENSOR_CHANGE_DELAY,
    CONF_WASP_SENSORS,
    CONF_WASP_INV_SENSORS,
    CONF_BOX_SENSORS,
    CONF_BOX_INV_SENSORS,
    CONF_TIMEOUT,
    CONF_NAME,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_platform(hass, _, async_add_entities, discovery_info=None):
    """Setup binary_sensor platform."""
    entities = []
    for thing in discovery_info["entities"]:
        entities.append(WaspBinarySensor(hass, thing))

    async_add_entities(entities)
    await discovery_info["registrar"](entities)


class WaspBinarySensor(BinarySensorEntity, RestoreEntity):
    """Wasp binary_sensor class."""

    def __init__(self, hass, config):
        self.hass = hass
        self._config = config

        _LOGGER.debug("%s: startup %s", self._config[CONF_NAME], self._config)

        self._wasp_in_box = False
        self._box_closed = False
        self._wasp_seen = False
        self._timeout_task = None

    async def async_added_to_hass(self):
        """Handle added to Hass."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) :
            _LOGGER.debug("%s: restoring state %s", self._config[CONF_NAME], state)
            self._wasp_in_box = state.attributes.get("wasp_in_box", False)
            self._box_closed = state.attributes.get("box_closed", False)
            self._wasp_seen = state.attributes.get("wasp_seen", False)

        # wait until full HASS Startup before starting event listeners
        if self.hass.is_running:
            await self._startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, self._startup)

    async def _startup(self, _=None):
        await self._evaluate_wasp_sensors()
        await self._evaluate_box_sensors()

        # Wasp Sensor State Changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config[CONF_WASP_SENSORS],
                partial(self._wasp_sensor_change_handler, expected_state="on"),
            )
        )

        # Wasp Inverted Sensor State Changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config[CONF_WASP_INV_SENSORS],
                partial(self._wasp_sensor_change_handler, expected_state="off"),
            )
        )

        # Box Sensor State Changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config[CONF_BOX_SENSORS],
                self._box_sensor_change_handler,
            )
        )

        # Box Inverted Sensor State Changes
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config[CONF_BOX_INV_SENSORS],
                self._box_sensor_change_handler,
            )
        )

    async def _box_sensor_change_handler(self, event: Event):
        this_entity_id = event.data["entity_id"]
        new_state = event.data["new_state"].state

        _LOGGER.debug(
            "%s: %s is now %s",
            self._config[CONF_NAME],
            this_entity_id,
            new_state,
        )

        await self._evaluate_box_sensors()
        self._wasp_in_box = False

        self.async_write_ha_state()

        # Cancel any pending timeout from a previous box-close event
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None

        if not self._box_closed or not self._wasp_seen:
            return

        _LOGGER.debug(
            "%s: box is closed and wasp is seen, waiting %s seconds",
            self._config[CONF_NAME],
            self._config[CONF_TIMEOUT],
        )

        # Fire timeout as a background task so startup is not blocked
        self._timeout_task = self.hass.async_create_task(
            self._box_closed_timeout()
        )

    async def _box_closed_timeout(self):
        """Wait for timeout then confirm wasp is still in box."""
        try:
            await asyncio.sleep(self._config[CONF_TIMEOUT])
        finally:
            self._timeout_task = None

        if self._box_closed and self._wasp_seen:
            _LOGGER.debug(
                "%s: box is still closed and wasp is still seen after %s seconds",
                self._config[CONF_NAME],
                self._config[CONF_TIMEOUT],
            )

            self._wasp_in_box = True
            self.async_write_ha_state()

    async def _evaluate_box_sensors(self):
        for this_box_sensor in self._config[CONF_BOX_SENSORS]:
            this_state = self.hass.states.get(this_box_sensor).state
            if this_state == "on":
                self._box_closed = False
                self._wasp_in_box = False
                return

        for this_box_sensor in self._config[CONF_BOX_INV_SENSORS]:
            this_state = self.hass.states.get(this_box_sensor).state
            if this_state == "off":
                self._box_closed = False
                self._wasp_in_box = False
                return

        self._box_closed = True
        return

    async def _wasp_sensor_change_handler(
        self, event: Event, expected_state: str = "on"
    ):
        this_entity_id = event.data["entity_id"]
        new_state = event.data["new_state"].state

        _LOGGER.debug(
            "%s: waiting for %s, currently %s, for %s seconds",
            self._config[CONF_NAME],
            this_entity_id,
            new_state,
            SENSOR_CHANGE_DELAY,
        )

        # Wait; some sensors send 'on' right before 'off'
        await asyncio.sleep(SENSOR_CHANGE_DELAY)

        this_state = self.hass.states.get(this_entity_id).state

        _LOGGER.debug(
            "%s: %s is %s after %s seconds",
            self._config[CONF_NAME],
            this_entity_id,
            this_state,
            SENSOR_CHANGE_DELAY,
        )

        if this_state == expected_state:
            if self._box_closed:
                self._wasp_in_box = True

        await self._evaluate_wasp_sensors()
        self.async_write_ha_state()

    async def _evaluate_wasp_sensors(self):
        for this_wasp_sensor in self._config[CONF_WASP_SENSORS]:
            this_state = self.hass.states.get(this_wasp_sensor).state
            if this_state == "on":
                self._wasp_seen = True
                return

        for this_wasp_sensor in self._config[CONF_WASP_INV_SENSORS]:
            this_state = self.hass.states.get(this_wasp_sensor).state
            if this_state == "off":
                self._wasp_seen = True
                return

        self._wasp_seen = False
        return

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self._config[CONF_NAME]}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self._config[CONF_NAME],
            "model": BINARY_SENSOR,
            "manufacturer": "Device Manu",
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            # "attribution": f"{DOMAIN} {BINARY_SENSOR}",
            # "id": str(self.unique_id),
            # "integration": DOMAIN,
            "wasp_in_box": self._wasp_in_box,
            "box_closed": self._box_closed,
            "wasp_seen": self._wasp_seen,
        }

    @property
    def name(self):
        """Return the name of the binary_sensor."""
        return f"{DOMAIN}_{self._config[CONF_NAME]}"

    @property
    def device_class(self):
        """Return the class of this binary_sensor."""
        return BINARY_SENSOR_DEVICE_CLASS

    @property
    def is_on(self):
        """Return true if the binary_sensor is on."""
        return self._wasp_in_box
