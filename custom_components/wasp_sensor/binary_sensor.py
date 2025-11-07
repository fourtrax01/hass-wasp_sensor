"""Binary sensor platform for Wasp Sensor (config entry based)."""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    SENSOR_CHANGE_DELAY,
    CONF_WASP_SENSORS,
    CONF_WASP_INV_SENSORS,
    CONF_BOX_SENSORS,
    CONF_BOX_INV_SENSORS,
    CONF_TIMEOUT,
    CONF_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Wasp binary sensors from a config entry."""
    config = hass.data[DOMAIN][entry.entry_id]  # one group per entry
    async_add_entities([WaspBinarySensor(hass, entry, config)])


class WaspBinarySensor(BinarySensorEntity, RestoreEntity):
    """Implements the 'wasp in a box' logic as an occupancy binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, config: Dict[str, Any]):
        self.hass = hass
        self.entry = entry
        self._config = config

        name = config[CONF_NAME]
        self._attr_name = f"{DOMAIN}_{name}"
        self._attr_unique_id = f"{DOMAIN}_{name}"

        self._wasp_in_box = False
        self._box_closed = False
        self._wasp_seen = False

    @property
    def is_on(self) -> bool:
        return self._wasp_in_box

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "wasp_in_box": self._wasp_in_box,
            "box_closed": self._box_closed,
            "wasp_seen": self._wasp_seen,
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": self._config[CONF_NAME],
            "model": "Wasp Sensor",
            "manufacturer": "Custom",
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if (last := await self.async_get_last_state()):
            self._wasp_in_box = last.attributes.get("wasp_in_box", False)
            self._box_closed = last.attributes.get("box_closed", False)
            self._wasp_seen = last.attributes.get("wasp_seen", False)

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
                self._config.get(CONF_WASP_SENSORS, []),
                partial(self._wasp_sensor_change_handler, expected_state="on"),
            )
        )
        # Inverted Wasp Sensors
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config.get(CONF_WASP_INV_SENSORS, []),
                partial(self._wasp_sensor_change_handler, expected_state="off"),
            )
        )
        # Box Sensors
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config.get(CONF_BOX_SENSORS, []),
                self._box_sensor_change_handler,
            )
        )
        # Inverted Box Sensors
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._config.get(CONF_BOX_INV_SENSORS, []),
                self._box_sensor_change_handler,
            )
        )

    async def _box_sensor_change_handler(self, event: Event):
        this_entity_id = event.data["entity_id"]
        new_state = event.data["new_state"].state
        _LOGGER.debug("%s: %s is now %s", self._config[CONF_NAME], this_entity_id, new_state)

        await self._evaluate_box_sensors()
        self._wasp_in_box = False

        if not self.hass or not hasattr(self, 'entity_id') or self.entity_id is None:
            return
        try:
            await self.async_write_ha_state()
        except (RuntimeError, TypeError) as err:
            _LOGGER.debug("%s: Could not update state (entity likely being removed): %s", self._config[CONF_NAME], err)

        if not self._box_closed or not self._wasp_seen:
            return

        timeout = self._config[CONF_TIMEOUT]
        _LOGGER.debug("%s: box closed & wasp seen; waiting %s sec", self._config[CONF_NAME], timeout)
        await asyncio.sleep(timeout)

        # Check if entity is still valid after sleep
        if not self.hass or not hasattr(self, 'entity_id') or self.entity_id is None:
            return

        if self._box_closed and self._wasp_seen:
            _LOGGER.debug("%s: still closed & wasp still seen; turning on", self._config[CONF_NAME])
            self._wasp_in_box = True
            try:
                await self.async_write_ha_state()
            except (RuntimeError, TypeError) as err:
                _LOGGER.debug("%s: Could not update state (entity likely being removed): %s", self._config[CONF_NAME], err)

    async def _evaluate_box_sensors(self):
        # Any "open" box sensor cancels closed
        for ent in self._config.get(CONF_BOX_SENSORS, []):
            if (st := self.hass.states.get(ent)) and st.state == "on":
                self._box_closed = False
                self._wasp_in_box = False
                return
        for ent in self._config.get(CONF_BOX_INV_SENSORS, []):
            if (st := self.hass.states.get(ent)) and st.state == "off":
                self._box_closed = False
                self._wasp_in_box = False
                return
        self._box_closed = True

    async def _wasp_sensor_change_handler(self, event: Event, expected_state: str = "on"):
        this_entity_id = event.data["entity_id"]
        new_state = event.data["new_state"].state
        _LOGGER.debug(
            "%s: waiting for %s; currently %s; delay=%s",
            self._config[CONF_NAME], this_entity_id, new_state, SENSOR_CHANGE_DELAY
        )
        await asyncio.sleep(SENSOR_CHANGE_DELAY)

        # Check if entity is still valid after sleep
        if not self.hass or not hasattr(self, 'entity_id') or self.entity_id is None:
            return

        current = self.hass.states.get(this_entity_id).state if self.hass.states.get(this_entity_id) else None
        _LOGGER.debug("%s: %s after delay is %s", self._config[CONF_NAME], this_entity_id, current)

        if current == expected_state and self._box_closed:
            self._wasp_in_box = True

        await self._evaluate_wasp_sensors()
        try:
            await self.async_write_ha_state()
        except (RuntimeError, TypeError) as err:
            _LOGGER.debug("%s: Could not update state (entity likely being removed): %s", self._config[CONF_NAME], err)

    async def _evaluate_wasp_sensors(self):
        for ent in self._config.get(CONF_WASP_SENSORS, []):
            if (st := self.hass.states.get(ent)) and st.state == "on":
                self._wasp_seen = True
                return
        for ent in self._config.get(CONF_WASP_INV_SENSORS, []):
            if (st := self.hass.states.get(ent)) and st.state == "off":
                self._wasp_seen = True
                return
        self._wasp_seen = False
