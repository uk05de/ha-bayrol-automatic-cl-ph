# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Sensor Definitions
#
# All register addresses, transformations, and MQTT discovery configs
# derived from the Bayrol PoolAccess MQTT protocol.
#

# ---------------------------------------------------------------------------
#  Text mappings for MQTT status codes
# ---------------------------------------------------------------------------

# General status text map for text-mapped sensors (flow, gas, problem, etc.)
# Maps Bayrol MQTT codes to human-readable text.
# String keys to handle both string and float raw values.
STATUS_TEXT_MAP = {
    "19.17": "Yes",
    "19.18": "No",
    "19.54": "Active",
    "19.177": "Active",
    "19.258": "Filled",
    "19.259": "Empty",
}

# Production rate: MQTT code → display percentage
PROD_RATE_MQTT_TO_DISPLAY = {
    "19.3": "25", "19.4": "50", "19.5": "75", "19.6": "100",
    "19.7": "125", "19.8": "150", "19.9": "200",
    "19.1": "300", "19.10": "300",    # 19.10 normalizes to 19.1 as float
    "19.11": "500", "19.12": "1000",
}
PROD_RATE_DISPLAY_TO_MQTT = {
    "25": "19.3", "50": "19.4", "75": "19.5", "100": "19.6",
    "125": "19.7", "150": "19.8", "200": "19.9", "300": "19.10",
    "500": "19.11", "1000": "19.12",
}
PROD_RATE_OPTIONS = ["25", "50", "75", "100", "125", "150", "200", "300", "500", "1000"]

# Filtration mode: MQTT code → display text
FILTRATION_MQTT_TO_DISPLAY = {
    "19.315": "Low", "19.316": "Med", "19.317": "High",
    "19.346": "Auto", "19.33": "Smart", "19.330": "Smart",  # trailing zero
    "19.338": "Frost", "19.312": "Off",
}
FILTRATION_DISPLAY_TO_MQTT = {
    "Low": "19.315", "Med": "19.316", "High": "19.317",
    "Auto": "19.346", "Smart": "19.330", "Frost": "19.338", "Off": "19.312",
}
FILTRATION_OPTIONS = ["Low", "Med", "High", "Auto", "Smart", "Frost", "Off"]

# Output mode: MQTT code → display text
OUT_MODE_MQTT_TO_DISPLAY = {
    "19.311": "On", "19.1": "Off", "19.100": "Off",  # trailing zero
    "19.345": "Auto",
}
OUT_MODE_DISPLAY_TO_MQTT = {
    "On": "19.311", "Off": "19.100", "Auto": "19.345",
}
OUT_MODE_OPTIONS = ["On", "Off", "Auto"]


# ---------------------------------------------------------------------------
#  Read-only sensors
# ---------------------------------------------------------------------------

SENSORS = [
    # --- pH ---
    {
        "register": "4.78",
        "name": "pH",
        "unique_id": "ph",
        "transform": lambda v: round(v / 10, 2),
        "unit": "pH",
        "icon": "mdi:ph",
    },
    {
        "register": "4.34",
        "name": "pH Min Control",
        "unique_id": "min_control_ph",
        "transform": lambda v: round(v / 100, 2),
        "entity_category": "diagnostic",
    },
    {
        "register": "4.89",
        "name": "pH Dosing Rate",
        "unique_id": "ph_dosing_rate",
        "unit": "%",
        "icon": "mdi:pump",
    },
    {
        "register": "4.47",
        "name": "pH Dosing Speed",
        "unique_id": "ph_dosing_speed",
        "unit": "%",
        "icon": "mdi:speedometer",
    },
    {
        "register": "4.38",
        "name": "pH Dosing Cycle",
        "unique_id": "ph_dosing_cycle",
        "unit": "s",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.5",
        "name": "pH Dosage Control Time",
        "unique_id": "ph_dosage_control_time",
        "unit": "min",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.32",
        "name": "pH Pump Capacity",
        "unique_id": "ph_pump_capacity",
        "transform": lambda v: int(v) * 100,
        "unit": "ml/h",
        "icon": "mdi:pump",
    },
    {
        "register": "5.95",
        "name": "pH Problem",
        "unique_id": "ph_problem",
        "icon": "mdi:alert-circle",
        "transform": "text_map",
    },

    # --- Chlor / Redox ---
    {
        "register": "4.204",
        "name": "Redox",
        "unique_id": "redox",
        "unit": "mV",
        "device_class": "voltage",
        "state_class": "measurement",
    },
    {
        "register": "4.90",
        "name": "Chlor Dosing Rate",
        "unique_id": "chlor_dosing_rate",
        "unit": "%",
        "icon": "mdi:pump",
    },
    {
        "register": "4.48",
        "name": "Chlor Dosing Speed",
        "unique_id": "cl_dosing_speed",
        "unit": "%",
        "icon": "mdi:speedometer",
    },
    {
        "register": "4.39",
        "name": "Chlor Dosing Cycle",
        "unique_id": "cl_dosing_cycle",
        "unit": "s",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.29",
        "name": "Chlor Dosage Control Time",
        "unique_id": "cl_dosage_control_time",
        "unit": "min",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.30",
        "name": "Chlor Min Control",
        "unique_id": "min_control_cl",
        "transform": lambda v: round(v / 100, 2),
        "entity_category": "diagnostic",
    },
    {
        "register": "4.33",
        "name": "Chlor Pump Capacity",
        "unique_id": "chlor_pump_capacity",
        "transform": lambda v: int(v) * 100,
        "unit": "ml/h",
        "icon": "mdi:pump",
    },
    {
        "register": "5.94",
        "name": "Chlor Problem",
        "unique_id": "chlor_problem",
        "icon": "mdi:alert-circle",
        "transform": "text_map",
    },

    # --- General ---
    {
        "register": "4.98",
        "name": "Temperatur",
        "unique_id": "temperature",
        "transform": lambda v: round(v / 10, 2),
        "unit": "\u00b0C",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    {
        "register": "4.92",
        "name": "Startup Delay",
        "unique_id": "startup_delay",
        "unit": "min",
        "entity_category": "diagnostic",
    },

    # --- New sensors (from 0xQuantumHome integration) ---
    {
        "register": "4.67",
        "name": "SW Version",
        "unique_id": "sw_version",
        "transform": lambda v: round(v / 100, 2),
        "entity_category": "diagnostic",
        "icon": "mdi:tag",
    },
    {
        "register": "4.68",
        "name": "SW Date",
        "unique_id": "sw_date",
        "entity_category": "diagnostic",
        "icon": "mdi:calendar",
    },
    {
        "register": "4.102",
        "name": "Conductivity",
        "unique_id": "conductivity",
        "transform": lambda v: round(v / 10, 1),
        "unit": "mS/cm",
        "icon": "mdi:flash",
        "state_class": "measurement",
    },
    {
        "register": "4.107",
        "name": "Battery Voltage",
        "unique_id": "battery_voltage",
        "transform": lambda v: round(v / 100, 2),
        "unit": "V",
        "device_class": "voltage",
        "state_class": "measurement",
        "entity_category": "diagnostic",
    },
    {
        "register": "5.28",
        "name": "Flow In Status",
        "unique_id": "flow_in_status",
        "transform": "text_map",
        "icon": "mdi:water-check",
    },
    {
        "register": "5.29",
        "name": "Flow Pump Status",
        "unique_id": "flow_pump_status",
        "transform": "text_map",
        "icon": "mdi:pump",
    },
    {
        "register": "5.37",
        "name": "Gas Sensor",
        "unique_id": "gas_sensor",
        "transform": "text_map",
        "icon": "mdi:gas-cylinder",
    },
]


# ---------------------------------------------------------------------------
#  Writable number entities (settable via Bayrol cloud /s/ topic)
# ---------------------------------------------------------------------------

WRITABLE_NUMBERS = [
    {
        "register": "4.2",
        "name": "pH Target",
        "unique_id": "ph_target",
        "transform": lambda v: round(v / 10, 2),
        "write_coefficient": 10,
        "unit": "pH",
        "icon": "mdi:target",
        "min": 6.2,
        "max": 8.2,
        "step": 0.1,
    },
    {
        "register": "4.3",
        "name": "pH Alert Max",
        "unique_id": "ph_alert_max",
        "transform": lambda v: round(v / 10, 2),
        "write_coefficient": 10,
        "unit": "pH",
        "min": 7.2,
        "max": 8.7,
        "step": 0.1,
        "entity_category": "diagnostic",
    },
    {
        "register": "4.4",
        "name": "pH Alert Min",
        "unique_id": "ph_alert_min",
        "transform": lambda v: round(v / 10, 2),
        "write_coefficient": 10,
        "unit": "pH",
        "min": 5.7,
        "max": 7.2,
        "step": 0.1,
        "entity_category": "diagnostic",
    },
    {
        "register": "4.26",
        "name": "Redox Alert Max",
        "unique_id": "redox_alert_max",
        "write_coefficient": 1,
        "unit": "mV",
        "min": 500,
        "max": 995,
        "step": 5,
        "entity_category": "diagnostic",
    },
    {
        "register": "4.27",
        "name": "Redox Alert Min",
        "unique_id": "redox_alert_min",
        "write_coefficient": 1,
        "unit": "mV",
        "min": 200,
        "max": 850,
        "step": 5,
        "entity_category": "diagnostic",
    },
    {
        "register": "4.28",
        "name": "Redox Target",
        "unique_id": "redox_target",
        "write_coefficient": 1,
        "unit": "mV",
        "icon": "mdi:target",
        "min": 400,
        "max": 950,
        "step": 5,
    },
    {
        "register": "4.37",
        "name": "Start Delay",
        "unique_id": "start_delay",
        "write_coefficient": 1,
        "unit": "min",
        "icon": "mdi:timer-sand",
        "min": 1,
        "max": 60,
        "step": 1,
    },
]


# ---------------------------------------------------------------------------
#  Writable select entities (dropdowns, settable via /s/ topic)
# ---------------------------------------------------------------------------

WRITABLE_SELECTS = [
    {
        "register": "5.3",
        "name": "pH Production Rate",
        "unique_id": "ph_prod_rate",
        "icon": "mdi:flask",
        "unit": "%",
        "options": PROD_RATE_OPTIONS,
        "mqtt_to_display": PROD_RATE_MQTT_TO_DISPLAY,
        "display_to_mqtt": PROD_RATE_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.175",
        "name": "Chlor Production Rate",
        "unique_id": "cl_prod_rate",
        "icon": "mdi:flask",
        "unit": "%",
        "options": PROD_RATE_OPTIONS,
        "mqtt_to_display": PROD_RATE_MQTT_TO_DISPLAY,
        "display_to_mqtt": PROD_RATE_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.184",
        "name": "Filtration Mode",
        "unique_id": "filtration_mode",
        "icon": "mdi:water-pump",
        "options": FILTRATION_OPTIONS,
        "mqtt_to_display": FILTRATION_MQTT_TO_DISPLAY,
        "display_to_mqtt": FILTRATION_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.186",
        "name": "Out 1 Mode",
        "unique_id": "out_1_mode",
        "icon": "mdi:electric-switch",
        "options": OUT_MODE_OPTIONS,
        "mqtt_to_display": OUT_MODE_MQTT_TO_DISPLAY,
        "display_to_mqtt": OUT_MODE_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.187",
        "name": "Out 2 Mode",
        "unique_id": "out_2_mode",
        "icon": "mdi:electric-switch",
        "options": OUT_MODE_OPTIONS,
        "mqtt_to_display": OUT_MODE_MQTT_TO_DISPLAY,
        "display_to_mqtt": OUT_MODE_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.188",
        "name": "Out 3 Mode",
        "unique_id": "out_3_mode",
        "icon": "mdi:electric-switch",
        "options": OUT_MODE_OPTIONS,
        "mqtt_to_display": OUT_MODE_MQTT_TO_DISPLAY,
        "display_to_mqtt": OUT_MODE_DISPLAY_TO_MQTT,
    },
    {
        "register": "5.189",
        "name": "Out 4 Mode",
        "unique_id": "out_4_mode",
        "icon": "mdi:electric-switch",
        "options": OUT_MODE_OPTIONS,
        "mqtt_to_display": OUT_MODE_MQTT_TO_DISPLAY,
        "display_to_mqtt": OUT_MODE_DISPLAY_TO_MQTT,
    },
]


# ---------------------------------------------------------------------------
#  Binary sensors
# ---------------------------------------------------------------------------

BINARY_SENSORS = [
    {
        "register": "5.79",
        "name": "pH Pumpe",
        "unique_id": "ph_pump_state",
        "on_value": "19.54",
        "device_class": "running",
    },
    {
        "register": "5.168",
        "name": "Chlor Pumpe",
        "unique_id": "chlor_pump_state",
        "on_value": "19.54",
        "device_class": "running",
    },
    {
        "register": "5.42",
        "name": "pH Automatik",
        "unique_id": "ph_state",
        "on_value": "19.17",
        "device_class": "power",
    },
    {
        "register": "5.154",
        "name": "Chlor Automatik",
        "unique_id": "chlor_automatic_on_off",
        "on_value": "19.17",
        "device_class": "power",
    },
    {
        "register": "5.98",
        "name": "Filtration",
        "unique_id": "filtration_state",
        "on_value": "19.177",
        "device_class": "running",
    },
    {
        "register": "5.169",
        "name": "Chlor Kanister",
        "unique_id": "chlor_canister_state",
        "on_value": "19.258",
        "invert": True,
        "device_class": "problem",
    },
    {
        "register": "5.80",
        "name": "pH Kanister",
        "unique_id": "ph_canister_state",
        "on_value": "19.258",
        "invert": True,
        "device_class": "problem",
    },
]


# ---------------------------------------------------------------------------
#  Transform functions
# ---------------------------------------------------------------------------

def transform_value(sensor, raw_value):
    """Apply sensor-specific transformation to raw value."""
    transform = sensor.get("transform")

    if transform is None:
        return round(raw_value, 2) if isinstance(raw_value, float) else raw_value

    if transform == "text_map":
        key = str(raw_value)
        result = STATUS_TEXT_MAP.get(key)
        if result is not None:
            return result
        # Try float-normalized key (e.g. 19.100 → "19.1")
        try:
            fkey = str(float(raw_value))
            result = STATUS_TEXT_MAP.get(fkey)
            if result is not None:
                return result
        except (ValueError, TypeError):
            pass
        # Unknown code — return raw value as string
        return key

    if callable(transform):
        return transform(raw_value)

    return raw_value


def transform_select(sensor, raw_value):
    """Convert MQTT code to display text for a select entity."""
    mapping = sensor["mqtt_to_display"]
    key = str(raw_value)
    result = mapping.get(key)
    if result is not None:
        return result
    # Try float-normalized key (handles float precision, e.g. 19.100 → "19.1")
    try:
        fkey = str(float(raw_value))
        return mapping.get(fkey)
    except (ValueError, TypeError):
        return None


def evaluate_binary(sensor, raw_value):
    """Evaluate binary sensor state from raw value."""
    is_match = str(raw_value) == sensor["on_value"]
    if sensor.get("invert", False):
        return not is_match
    return is_match
