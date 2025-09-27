"""Wasp Sensor integration bootstrapping."""
import logging
from typing import Any, Dict, List

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant import config as conf_util

from .const import (
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
    SERVICE_RELOAD,
    DEFAULT_WASP_TIMEOUT,
    CONF_WASP_SENSORS,
    CONF_WASP_INV_SENSORS,
    CONF_BOX_SENSORS,
    CONF_BOX_INV_SENSORS,
    CONF_TIMEOUT,
    CONF_NAME,
)

_LOGGER = logging.getLogger(__name__)

ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_WASP_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_WASP_INV_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_BOX_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_BOX_INV_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_WASP_TIMEOUT): vol.Coerce(int),
    }
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: [ENTRY_SCHEMA]}, extra=vol.ALLOW_EXTRA)

# Where we stash parsed YAML so config_flow can import it
DATA_YAML = f"{DOMAIN}_yaml"


async def async_setup(hass: HomeAssistant, hass_config: Dict[str, Any]) -> bool:
    """Set up via YAML (optional) and register services."""
    _LOGGER.info(STARTUP_MESSAGE)

    # Parse YAML if present and stash for import step
    yaml_entries = hass_config.get(DOMAIN)
    if yaml_entries:
        try:
            validated = CONFIG_SCHEMA({DOMAIN: yaml_entries})[DOMAIN]
            hass.data[DATA_YAML] = validated
            # Kick off an import flow per group
            for group in validated:
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=group,
                    )
                )
        except vol.Invalid as err:
            _LOGGER.error("Invalid %s YAML: %s", DOMAIN, err)
            return False

    async def _handle_reload(_call=None):
        """Re-read YAML and reload entries."""
        try:
            unprocessed = await conf_util.async_hass_config_yaml(hass)
        except HomeAssistantError as err:
            _LOGGER.error("Reload failed reading YAML: %s", err)
            return

        new_yaml = unprocessed.get(DOMAIN, [])
        hass.data[DATA_YAML] = new_yaml

        # Re-import: create flows for new/changed groups (HA will de-duplicate titles)
        for group in new_yaml:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "import"},
                    data=group,
                )
            )

        # Reload existing entries
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _handle_reload)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wasp Sensor from a config entry."""
    # entry.data contains ONE group (name + lists of entity_ids + timeout)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
