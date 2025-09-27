"""Constants for Wasp Sensor."""

NAME = "Wasp Sensor"
DOMAIN = "wasp_sensor"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.4"
ISSUE_URL = "https://github.com/dlashua/hass-wasp_sensor/issues"

# Platforms
BINARY_SENSOR = "binary_sensor"
PLATFORMS = [BINARY_SENSOR]

# Services
SERVICE_RELOAD = "reload"

# Defaults
DEFAULT_NAME = DOMAIN

# Config keys
CONF_WASP_SENSORS = "wasp_sensors"
CONF_WASP_INV_SENSORS = "wasp_inv_sensors"
CONF_BOX_SENSORS = "box_sensors"
CONF_BOX_INV_SENSORS = "box_inv_sensors"
CONF_TIMEOUT = "timeout"
CONF_NAME = "name"

# Behavior
SENSOR_CHANGE_DELAY = 1
DEFAULT_WASP_TIMEOUT = 5

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
