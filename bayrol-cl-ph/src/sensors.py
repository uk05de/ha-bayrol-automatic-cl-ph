# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Sensor Definitions
#
# All register addresses, transformations, and MQTT discovery configs
# derived from the Bayrol PoolAccess MQTT protocol.
#

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
        "register": "4.2",
        "name": "pH Target",
        "unique_id": "ph_target",
        "transform": lambda v: round(v / 10, 2),
        "unit": "pH",
        "icon": "mdi:target",
    },
    {
        "register": "4.3",
        "name": "pH Alert Max",
        "unique_id": "ph_alert_max",
        "transform": lambda v: round(v / 10, 2),
        "unit": "pH",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.4",
        "name": "pH Alert Min",
        "unique_id": "ph_alert_min",
        "transform": lambda v: round(v / 10, 2),
        "unit": "pH",
        "entity_category": "diagnostic",
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
        "register": "5.3",
        "name": "pH Production Rate",
        "unique_id": "ph_prod_rate",
        "transform": "prod_rate",
        "unit": "%",
        "icon": "mdi:flask",
    },
    {
        "register": "5.95",
        "name": "pH Problem",
        "unique_id": "ph_problem",
        "icon": "mdi:alert-circle",
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
        "register": "4.28",
        "name": "Redox Target",
        "unique_id": "redox_target",
        "unit": "mV",
        "icon": "mdi:target",
    },
    {
        "register": "4.26",
        "name": "Redox Alert Max",
        "unique_id": "redox_alert_max",
        "unit": "mV",
        "entity_category": "diagnostic",
    },
    {
        "register": "4.27",
        "name": "Redox Alert Min",
        "unique_id": "redox_alert_min",
        "unit": "mV",
        "entity_category": "diagnostic",
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
        "register": "5.175",
        "name": "Chlor Production Rate",
        "unique_id": "cl_prod_rate",
        "transform": "prod_rate",
        "unit": "%",
        "icon": "mdi:flask",
    },
    {
        "register": "5.94",
        "name": "Chlor Problem",
        "unique_id": "chlor_problem",
        "icon": "mdi:alert-circle",
    },

    # --- General ---
    {
        "register": "4.98",
        "name": "Temperatur",
        "unique_id": "temperature",
        "transform": lambda v: round(v / 10, 2),
        "unit": "°C",
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
]

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


def transform_value(sensor, raw_value):
    """Apply sensor-specific transformation to raw value."""
    transform = sensor.get("transform")

    if transform is None:
        return round(raw_value, 2) if isinstance(raw_value, float) else raw_value

    if transform == "prod_rate":
        v = float(raw_value)
        if v == 19.5:
            return 75
        elif v == 19.6:
            return 100
        elif v == 19.7:
            return 125
        return 0

    if callable(transform):
        return transform(raw_value)

    return raw_value


def evaluate_binary(sensor, raw_value):
    """Evaluate binary sensor state from raw value."""
    is_match = str(raw_value) == sensor["on_value"]
    if sensor.get("invert", False):
        return not is_match
    return is_match
