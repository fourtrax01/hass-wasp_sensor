"""Config flow for Wasp Sensor."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    DEFAULT_WASP_TIMEOUT,
    CONF_WASP_SENSORS,
    CONF_WASP_INV_SENSORS,
    CONF_BOX_SENSORS,
    CONF_BOX_INV_SENSORS,
    CONF_TIMEOUT,
    CONF_NAME,
)

STEP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_WASP_SENSORS, default=""): str,
        vol.Optional(CONF_WASP_INV_SENSORS, default=""): str,
        vol.Optional(CONF_BOX_SENSORS, default=""): str,
        vol.Optional(CONF_BOX_INV_SENSORS, default=""): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_WASP_TIMEOUT): int,
    }
)


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wasp Sensor."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_DATA_SCHEMA)

        data = {
            CONF_NAME: user_input[CONF_NAME],
            CONF_WASP_SENSORS: _split_csv(user_input.get(CONF_WASP_SENSORS, "")),
            CONF_WASP_INV_SENSORS: _split_csv(user_input.get(CONF_WASP_INV_SENSORS, "")),
            CONF_BOX_SENSORS: _split_csv(user_input.get(CONF_BOX_SENSORS, "")),
            CONF_BOX_INV_SENSORS: _split_csv(user_input.get(CONF_BOX_INV_SENSORS, "")),
            CONF_TIMEOUT: user_input.get(CONF_TIMEOUT),
        }

        await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_NAME]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    async def async_step_import(self, import_config):
        """Handle YAML import: one entry per group."""
        data = {
            CONF_NAME: import_config[CONF_NAME],
            CONF_WASP_SENSORS: import_config.get(CONF_WASP_SENSORS, []),
            CONF_WASP_INV_SENSORS: import_config.get(CONF_WASP_INV_SENSORS, []),
            CONF_BOX_SENSORS: import_config.get(CONF_BOX_SENSORS, []),
            CONF_BOX_INV_SENSORS: import_config.get(CONF_BOX_INV_SENSORS, []),
            CONF_TIMEOUT: import_config.get(CONF_TIMEOUT, DEFAULT_WASP_TIMEOUT),
        }

        await self.async_set_unique_id(f"{DOMAIN}_{data[CONF_NAME]}")
        # If already exists, update it
        existing = self._async_current_entries()
        for entry in existing:
            if entry.unique_id == self.unique_id:
                return self.async_update_reload_and_abort(
                    entry=entry, data=data, reason="already_configured"
                )

        return self.async_create_entry(title=data[CONF_NAME], data=data)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Wasp Sensor entries."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is None:
            data = self.entry.data
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Optional(
                            CONF_TIMEOUT, default=data.get(CONF_TIMEOUT, DEFAULT_WASP_TIMEOUT)
                        ): int
                    }
                ),
            )

        # Only timeout is adjustable in options for simplicity
        data = dict(self.entry.data)
        data[CONF_TIMEOUT] = user_input[CONF_TIMEOUT]
        return self.async_create_entry(title="", data=data)
