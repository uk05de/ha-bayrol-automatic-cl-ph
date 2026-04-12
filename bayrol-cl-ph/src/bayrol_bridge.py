# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - MQTT Bridge
#
# Connects to Bayrol PoolAccess cloud MQTT broker (WSS) and bridges
# messages to local MQTT broker with HA Discovery.
#

import json
import logging
import time
import ssl

import paho.mqtt.client as mqtt

from sensors import (
    SENSORS, BINARY_SENSORS,
    WRITABLE_NUMBERS, WRITABLE_SELECTS,
    transform_value, transform_select, evaluate_binary,
)
from canister_tracker import CanisterTracker

log = logging.getLogger("bayrol")

BAYROL_BROKER = "www.bayrol-poolaccess.de"
BAYROL_PORT = 8083
BAYROL_WSS_PATH = "/mqtt"

DISCOVERY_PREFIX = "homeassistant"
TOPIC_PREFIX = "bayrol_cl_ph"


class BayrolBridge:
    """Bridges Bayrol PoolAccess MQTT (WSS) to local MQTT with HA Discovery."""

    def __init__(self, config: dict):
        self.device_id = config["device_id"]
        self.refresh_interval = config.get("refresh_interval", 900)
        self._last_refresh = time.monotonic()  # prevent double refresh on startup
        self._discovery_sent = False

        # --- Shelly integration (optional) ---
        self._shelly_prefix = config.get("shelly_topic_prefix", "").strip()
        self._shelly_rpc_id = 0

        # Build register lookup for fast message routing
        self._sensor_by_register = {}
        for s in SENSORS:
            self._sensor_by_register[s["register"]] = ("sensor", s)
        for s in BINARY_SENSORS:
            self._sensor_by_register[s["register"]] = ("binary_sensor", s)
        for s in WRITABLE_NUMBERS:
            self._sensor_by_register[s["register"]] = ("number", s)
        for s in WRITABLE_SELECTS:
            self._sensor_by_register[s["register"]] = ("select", s)

        # Build command topic lookups for writable entities
        self._number_cmd_topics = {}
        for s in WRITABLE_NUMBERS:
            self._number_cmd_topics[f"{TOPIC_PREFIX}/number/{s['unique_id']}/set"] = s
        self._select_cmd_topics = {}
        for s in WRITABLE_SELECTS:
            self._select_cmd_topics[f"{TOPIC_PREFIX}/select/{s['unique_id']}/set"] = s

        # --- Bayrol Cloud MQTT client (WSS) ---
        self._bayrol = mqtt.Client(
            client_id=f"ha_bayrol_{self.device_id}",
            transport="websockets",
            protocol=mqtt.MQTTv5,
        )
        self._bayrol.ws_set_options(path=BAYROL_WSS_PATH)
        self._bayrol.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self._bayrol.tls_insecure_set(False)

        if config.get("bayrol_username"):
            self._bayrol.username_pw_set(
                config["bayrol_username"],
                config["bayrol_password"],
            )

        self._bayrol.on_connect = self._on_bayrol_connect
        self._bayrol.on_message = self._on_bayrol_message
        self._bayrol.on_disconnect = self._on_bayrol_disconnect

        # --- Local MQTT client (TCP) ---
        self._local = mqtt.Client(
            client_id="bayrol_cl_ph",
            protocol=mqtt.MQTTv311,
        )
        if config.get("mqtt_user"):
            self._local.username_pw_set(
                config["mqtt_user"],
                config["mqtt_password"],
            )

        self._local.on_connect = self._on_local_connect
        self._local.on_message = self._on_local_message
        self._local_host = config["mqtt_host"]
        self._local_port = config["mqtt_port"]

        # --- Canister tracker ---
        self.canister = CanisterTracker(config)

        # Map sensor unique_ids to canister tracker keys
        self._canister_value_map = {
            "ph_pump_capacity": "ph_pump_capacity",
            "ph_prod_rate": "ph_prod_rate",
            "ph_dosing_rate": "ph_dosing_rate",
            "chlor_pump_capacity": "cl_pump_capacity",
            "cl_prod_rate": "cl_prod_rate",
            "chlor_dosing_rate": "cl_dosing_rate",
        }
        self._canister_binary_map = {
            "ph_pump_state": "ph_pump_state",
            "chlor_pump_state": "cl_pump_state",
        }

    # --- Connection ---

    def connect(self):
        """Connect to both MQTT brokers."""
        # Local first
        self._local.connect(self._local_host, self._local_port, keepalive=60)
        self._local.loop_start()
        log.info("Local MQTT connected to %s:%d", self._local_host, self._local_port)

        # Bayrol cloud
        self._bayrol.connect(BAYROL_BROKER, BAYROL_PORT, keepalive=60)
        self._bayrol.loop_start()
        log.info("Connecting to Bayrol cloud at %s:%d...", BAYROL_BROKER, BAYROL_PORT)

    def disconnect(self):
        """Disconnect from both brokers."""
        self._bayrol.loop_stop()
        self._bayrol.disconnect()
        self._local.loop_stop()
        self._local.disconnect()
        log.info("Disconnected from both brokers")

    # --- Bayrol callbacks ---

    def _on_bayrol_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            topic = f"d02/{self.device_id}/#"
            client.subscribe(topic, qos=2)
            log.info("Bayrol cloud connected, subscribed to %s", topic)
            # Trigger initial refresh
            self._trigger_refresh()
        else:
            log.error("Bayrol cloud connection failed with code %d", rc)

    def _on_bayrol_message(self, client, userdata, msg):
        """Handle incoming message from Bayrol cloud."""
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        log.debug("Bayrol: %s = %s", topic, payload)

        # Only process /v/ topics (value messages)
        parts = topic.split("/")
        if len(parts) < 4 or parts[2] != "v":
            return

        # Parse payload
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return

        # Handle both formats:
        # 1. Batch array: [{"t":"4.2","v":71}, {"t":"4.3","v":76}, ...]
        # 2. Single object: {"v": 71}
        if isinstance(data, list):
            for item in data:
                register = str(item.get("t", ""))
                raw_value = item.get("v")
                if register and raw_value is not None:
                    self._process_register(register, raw_value)
        elif isinstance(data, dict):
            register = parts[3]
            raw_value = data.get("v")
            if raw_value is not None:
                self._process_register(register, raw_value)

        # Update availability
        self._local.publish(f"{TOPIC_PREFIX}/availability", "online", retain=True)

    def _process_register(self, register: str, raw_value):
        """Process a single register value."""
        entry = self._sensor_by_register.get(register)
        if entry is None:
            log.debug("Unknown register %s, ignoring", register)
            return

        component, sensor = entry

        if component == "sensor":
            value = transform_value(sensor, raw_value)
            state_topic = f"{TOPIC_PREFIX}/sensor/{sensor['unique_id']}/state"
            self._local.publish(state_topic, str(value), retain=True)
            log.debug("Published %s = %s", sensor["name"], value)
            # Feed canister tracker
            ct_key = self._canister_value_map.get(sensor["unique_id"])
            if ct_key:
                self.canister.update_value(ct_key, value)

        elif component == "number":
            value = transform_value(sensor, raw_value)
            state_topic = f"{TOPIC_PREFIX}/number/{sensor['unique_id']}/state"
            self._local.publish(state_topic, str(value), retain=True)
            log.debug("Published %s = %s", sensor["name"], value)

        elif component == "select":
            display_value = transform_select(sensor, raw_value)
            if display_value:
                state_topic = f"{TOPIC_PREFIX}/select/{sensor['unique_id']}/state"
                self._local.publish(state_topic, display_value, retain=True)
                log.debug("Published %s = %s", sensor["name"], display_value)
                # Feed canister tracker with numeric value (production rates)
                ct_key = self._canister_value_map.get(sensor["unique_id"])
                if ct_key:
                    try:
                        self.canister.update_value(ct_key, int(display_value))
                    except ValueError:
                        pass
            else:
                log.warning("Unknown select code for %s: %s", sensor["name"], raw_value)

        elif component == "binary_sensor":
            is_on = evaluate_binary(sensor, raw_value)
            state_topic = f"{TOPIC_PREFIX}/binary_sensor/{sensor['unique_id']}/state"
            self._local.publish(state_topic, "ON" if is_on else "OFF", retain=True)
            log.debug("Published %s = %s", sensor["name"], "ON" if is_on else "OFF")
            # Feed canister tracker
            ct_key = self._canister_binary_map.get(sensor["unique_id"])
            if ct_key:
                self.canister.update_value(ct_key, is_on)

    def _on_bayrol_disconnect(self, client, userdata, rc, properties=None):
        if rc != 0:
            log.warning("Bayrol cloud disconnected unexpectedly (rc=%d), will reconnect", rc)
        else:
            log.info("Bayrol cloud disconnected")

    # --- Local MQTT callbacks ---

    def _on_local_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Local MQTT broker connected")
            # Subscribe to canister commands
            client.subscribe(f"{TOPIC_PREFIX}/button/reset_ph/set")
            client.subscribe(f"{TOPIC_PREFIX}/button/reset_cl/set")
            client.subscribe(f"{TOPIC_PREFIX}/number/ph_canister_remaining/set")
            client.subscribe(f"{TOPIC_PREFIX}/number/cl_canister_remaining/set")
            # Subscribe to writable entity commands
            for s in WRITABLE_NUMBERS:
                client.subscribe(f"{TOPIC_PREFIX}/number/{s['unique_id']}/set")
            for s in WRITABLE_SELECTS:
                client.subscribe(f"{TOPIC_PREFIX}/select/{s['unique_id']}/set")
            # Subscribe to Shelly status (if configured)
            if self._shelly_prefix:
                client.subscribe(f"{self._shelly_prefix}/status/switch:0")
                client.subscribe(f"{TOPIC_PREFIX}/switch/power/set")
                log.info("Shelly integration enabled: %s", self._shelly_prefix)
            self._discovery_sent = False
            self.send_discovery()
        else:
            log.error("Local MQTT connection failed with code %d", rc)

    def _on_local_message(self, client, userdata, msg):
        """Handle commands from HA (buttons, numbers, selects)."""
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        log.debug("Local MQTT: %s = %s", topic, payload)

        if topic == f"{TOPIC_PREFIX}/button/reset_ph/set" and payload == "PRESS":
            self.canister.reset_ph()
            self.publish_canister_state()
            return

        if topic == f"{TOPIC_PREFIX}/button/reset_cl/set" and payload == "PRESS":
            self.canister.reset_cl()
            self.publish_canister_state()
            return

        if topic == f"{TOPIC_PREFIX}/number/ph_canister_remaining/set":
            try:
                liters = float(payload)
                self.canister.set_ph_remaining(liters)
                self.publish_canister_state()
                log.info("pH canister manually set to %.1f L", liters)
            except ValueError:
                log.warning("Invalid pH canister value: %s", payload)
            return

        if topic == f"{TOPIC_PREFIX}/number/cl_canister_remaining/set":
            try:
                liters = float(payload)
                self.canister.set_cl_remaining(liters)
                self.publish_canister_state()
                log.info("CL canister manually set to %.1f L", liters)
            except ValueError:
                log.warning("Invalid CL canister value: %s", payload)
            return

        # Writable number entities (pH/Redox targets and alerts)
        number_sensor = self._number_cmd_topics.get(topic)
        if number_sensor:
            try:
                display_value = float(payload)
                mqtt_value = int(round(display_value * number_sensor["write_coefficient"]))
                self._write_to_bayrol(number_sensor["register"], mqtt_value)
                state_topic = f"{TOPIC_PREFIX}/number/{number_sensor['unique_id']}/state"
                self._local.publish(state_topic, str(display_value), retain=True)
                log.info("Set %s = %s (MQTT value: %d)", number_sensor["name"], payload, mqtt_value)
            except (ValueError, TypeError) as e:
                log.warning("Invalid value for %s: %s (%s)", number_sensor["name"], payload, e)
            return

        # Writable select entities (production rates, filtration mode, out modes)
        select_sensor = self._select_cmd_topics.get(topic)
        if select_sensor:
            mqtt_code = select_sensor["display_to_mqtt"].get(payload)
            if mqtt_code:
                self._write_to_bayrol(select_sensor["register"], mqtt_code)
                state_topic = f"{TOPIC_PREFIX}/select/{select_sensor['unique_id']}/state"
                self._local.publish(state_topic, payload, retain=True)
                log.info("Set %s = %s (MQTT code: %s)", select_sensor["name"], payload, mqtt_code)
                # Update canister tracker if applicable (production rates)
                ct_key = self._canister_value_map.get(select_sensor["unique_id"])
                if ct_key:
                    try:
                        self.canister.update_value(ct_key, int(payload))
                    except ValueError:
                        pass
            else:
                log.warning("Invalid option for %s: %s", select_sensor["name"], payload)
            return

        # --- Shelly integration ---
        if self._shelly_prefix:
            # Shelly status update (switch:0)
            if topic == f"{self._shelly_prefix}/status/switch:0":
                self._handle_shelly_status(payload)
                return

            # Switch command from HA
            if topic == f"{TOPIC_PREFIX}/switch/power/set":
                self._handle_shelly_command(payload)
                return

    # --- Shelly integration ---

    def _handle_shelly_status(self, payload):
        """Handle Shelly Plus 1 PM status update (Gen2 JSON format)."""
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return

        # Switch state
        output = data.get("output")
        if output is not None:
            state = "ON" if output else "OFF"
            self._local.publish(
                f"{TOPIC_PREFIX}/switch/power/state", state, retain=True)

        # Power measurement
        apower = data.get("apower")
        if apower is not None:
            self._local.publish(
                f"{TOPIC_PREFIX}/sensor/power/state",
                str(round(apower, 1)), retain=True)

        # Voltage
        voltage = data.get("voltage")
        if voltage is not None:
            self._local.publish(
                f"{TOPIC_PREFIX}/sensor/voltage/state",
                str(round(voltage, 1)), retain=True)

        # Current
        current = data.get("current")
        if current is not None:
            self._local.publish(
                f"{TOPIC_PREFIX}/sensor/current/state",
                str(round(current, 3)), retain=True)

        log.debug("Shelly status: output=%s, power=%s W", output, apower)

    def _handle_shelly_command(self, payload):
        """Forward switch command to Shelly via MQTT RPC."""
        turn_on = payload.upper() == "ON"
        self._shelly_rpc_id += 1
        rpc_payload = json.dumps({
            "id": self._shelly_rpc_id,
            "src": "bayrol_cl_ph",
            "method": "Switch.Set",
            "params": {"id": 0, "on": turn_on},
        })
        self._local.publish(f"{self._shelly_prefix}/rpc", rpc_payload)
        # Optimistic state update
        self._local.publish(
            f"{TOPIC_PREFIX}/switch/power/state",
            "ON" if turn_on else "OFF", retain=True)
        log.info("Shelly switch: %s", "ON" if turn_on else "OFF")

    # --- Write to Bayrol ---

    def _write_to_bayrol(self, register, value):
        """Write a value to the Bayrol cloud via /s/ topic."""
        topic = f"d02/{self.device_id}/s/{register}"
        payload = json.dumps({"t": register, "v": value})
        self._bayrol.publish(topic, payload, qos=1)
        log.info("Published to Bayrol: %s = %s", topic, payload)

    # --- Discovery ---

    def send_discovery(self):
        """Publish MQTT Discovery configs for all sensors."""
        if self._discovery_sent:
            return

        device_id_clean = self.device_id.lower().replace("-", "_")
        device_info = {
            "identifiers": [f"bayrol_cl_ph_{device_id_clean}"],
            "name": f"Bayrol Automatic CL/PH ({self.device_id})",
            "manufacturer": "Bayrol",
            "model": "Automatic CL/PH",
        }

        for sensor in SENSORS:
            config = {
                "name": sensor["name"],
                "unique_id": f"bayrol_{sensor['unique_id']}",
                "state_topic": f"{TOPIC_PREFIX}/sensor/{sensor['unique_id']}/state",
                "device": device_info,
                "availability_topic": f"{TOPIC_PREFIX}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if "unit" in sensor:
                config["unit_of_measurement"] = sensor["unit"]
            if "device_class" in sensor:
                config["device_class"] = sensor["device_class"]
            if "state_class" in sensor:
                config["state_class"] = sensor["state_class"]
            if "icon" in sensor:
                config["icon"] = sensor["icon"]
            if "entity_category" in sensor:
                config["entity_category"] = sensor["entity_category"]

            topic = f"{DISCOVERY_PREFIX}/sensor/bayrol/{sensor['unique_id']}/config"
            self._local.publish(topic, json.dumps(config), qos=1, retain=True)

        for sensor in BINARY_SENSORS:
            config = {
                "name": sensor["name"],
                "unique_id": f"bayrol_{sensor['unique_id']}",
                "state_topic": f"{TOPIC_PREFIX}/binary_sensor/{sensor['unique_id']}/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": device_info,
                "availability_topic": f"{TOPIC_PREFIX}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if "device_class" in sensor:
                config["device_class"] = sensor["device_class"]
            if "entity_category" in sensor:
                config["entity_category"] = sensor["entity_category"]

            topic = f"{DISCOVERY_PREFIX}/binary_sensor/bayrol/{sensor['unique_id']}/config"
            self._local.publish(topic, json.dumps(config), qos=1, retain=True)

        # --- Writable number entities ---
        for sensor in WRITABLE_NUMBERS:
            config = {
                "name": sensor["name"],
                "unique_id": f"bayrol_{sensor['unique_id']}",
                "state_topic": f"{TOPIC_PREFIX}/number/{sensor['unique_id']}/state",
                "command_topic": f"{TOPIC_PREFIX}/number/{sensor['unique_id']}/set",
                "min": sensor["min"],
                "max": sensor["max"],
                "step": sensor["step"],
                "mode": "box",
                "device": device_info,
                "availability_topic": f"{TOPIC_PREFIX}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if "unit" in sensor:
                config["unit_of_measurement"] = sensor["unit"]
            if "icon" in sensor:
                config["icon"] = sensor["icon"]
            if "entity_category" in sensor:
                config["entity_category"] = sensor["entity_category"]

            topic = f"{DISCOVERY_PREFIX}/number/bayrol/{sensor['unique_id']}/config"
            self._local.publish(topic, json.dumps(config), qos=1, retain=True)
            # Remove old sensor discovery (migration cleanup)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/{sensor['unique_id']}/config",
                "", qos=1, retain=True)

        # --- Writable select entities ---
        for sensor in WRITABLE_SELECTS:
            config = {
                "name": sensor["name"],
                "unique_id": f"bayrol_{sensor['unique_id']}",
                "state_topic": f"{TOPIC_PREFIX}/select/{sensor['unique_id']}/state",
                "command_topic": f"{TOPIC_PREFIX}/select/{sensor['unique_id']}/set",
                "options": sensor["options"],
                "device": device_info,
                "availability_topic": f"{TOPIC_PREFIX}/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            if "icon" in sensor:
                config["icon"] = sensor["icon"]

            topic = f"{DISCOVERY_PREFIX}/select/bayrol/{sensor['unique_id']}/config"
            self._local.publish(topic, json.dumps(config), qos=1, retain=True)
            # Remove old sensor discovery (migration cleanup)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/{sensor['unique_id']}/config",
                "", qos=1, retain=True)

        # --- Shelly power entities (if configured) ---
        if self._shelly_prefix:
            # Switch: Dosieranlage Ein/Aus
            self._local.publish(
                f"{DISCOVERY_PREFIX}/switch/bayrol/power/config",
                json.dumps({
                    "name": "Dosieranlage",
                    "unique_id": "bayrol_power_switch",
                    "state_topic": f"{TOPIC_PREFIX}/switch/power/state",
                    "command_topic": f"{TOPIC_PREFIX}/switch/power/set",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "icon": "mdi:power",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Sensor: Leistung (W)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/power/config",
                json.dumps({
                    "name": "Leistung",
                    "unique_id": "bayrol_power",
                    "state_topic": f"{TOPIC_PREFIX}/sensor/power/state",
                    "unit_of_measurement": "W",
                    "device_class": "power",
                    "state_class": "measurement",
                    "icon": "mdi:flash",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Sensor: Spannung (V)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/voltage/config",
                json.dumps({
                    "name": "Spannung",
                    "unique_id": "bayrol_voltage",
                    "state_topic": f"{TOPIC_PREFIX}/sensor/voltage/state",
                    "unit_of_measurement": "V",
                    "device_class": "voltage",
                    "state_class": "measurement",
                    "entity_category": "diagnostic",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Sensor: Strom (A)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/current/config",
                json.dumps({
                    "name": "Strom",
                    "unique_id": "bayrol_current",
                    "state_topic": f"{TOPIC_PREFIX}/sensor/current/state",
                    "unit_of_measurement": "A",
                    "device_class": "current",
                    "state_class": "measurement",
                    "entity_category": "diagnostic",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            log.info("Shelly power entities published (switch + 3 sensors)")

        # --- Canister entities ---
        canister_sizes = {"ph": self.canister.canister_size_ph,
                          "cl": self.canister.canister_size_cl}
        for ctype, name in [("ph", "pH-"), ("cl", "Chlor")]:
            size = canister_sizes[ctype]
            # Remaining liters (editable number entity)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/number/bayrol/{ctype}_canister_remaining/config",
                json.dumps({
                    "name": f"{name} Kanister Restmenge",
                    "unique_id": f"bayrol_{ctype}_canister_remaining",
                    "state_topic": f"{TOPIC_PREFIX}/number/{ctype}_canister_remaining/state",
                    "command_topic": f"{TOPIC_PREFIX}/number/{ctype}_canister_remaining/set",
                    "min": 0,
                    "max": size,
                    "step": 0.1,
                    "unit_of_measurement": "L",
                    "icon": "mdi:gauge",
                    "mode": "box",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Remaining percent (read-only sensor)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/{ctype}_canister_level/config",
                json.dumps({
                    "name": f"{name} Kanister Füllstand",
                    "unique_id": f"bayrol_{ctype}_canister_level",
                    "state_topic": f"{TOPIC_PREFIX}/sensor/{ctype}_canister_level/state",
                    "unit_of_measurement": "%",
                    "icon": "mdi:gauge",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Consumed liters (read-only sensor)
            self._local.publish(
                f"{DISCOVERY_PREFIX}/sensor/bayrol/{ctype}_canister_consumed/config",
                json.dumps({
                    "name": f"{name} Kanister Verbrauch",
                    "unique_id": f"bayrol_{ctype}_canister_consumed",
                    "state_topic": f"{TOPIC_PREFIX}/sensor/{ctype}_canister_consumed/state",
                    "unit_of_measurement": "L",
                    "icon": "mdi:water-minus",
                    "state_class": "total_increasing",
                    "device": device_info,
                    "availability_topic": f"{TOPIC_PREFIX}/availability",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }), qos=1, retain=True
            )
            # Reset button
            self._local.publish(
                f"{DISCOVERY_PREFIX}/button/bayrol/reset_{ctype}/config",
                json.dumps({
                    "name": f"{name} Kanister Reset",
                    "unique_id": f"bayrol_reset_{ctype}_canister",
                    "command_topic": f"{TOPIC_PREFIX}/button/reset_{ctype}/set",
                    "payload_press": "PRESS",
                    "icon": "mdi:reload",
                    "entity_category": "config",
                    "device": device_info,
                }), qos=1, retain=True
            )

        self._discovery_sent = True
        # Publish initial availability so entities appear in HA
        self._local.publish(f"{TOPIC_PREFIX}/availability", "online", retain=True)
        # Publish initial canister state
        self.publish_canister_state()
        log.info("MQTT Discovery published (%d sensors, %d binary, %d numbers, %d selects, canister entities)",
                 len(SENSORS), len(BINARY_SENSORS), len(WRITABLE_NUMBERS), len(WRITABLE_SELECTS))

    # --- Canister ---

    def publish_canister_state(self):
        """Publish canister levels to MQTT."""
        # Editable remaining liters
        self._local.publish(
            f"{TOPIC_PREFIX}/number/ph_canister_remaining/state",
            str(round(self.canister.ph_remaining_ml / 1000, 1)), retain=True)
        self._local.publish(
            f"{TOPIC_PREFIX}/number/cl_canister_remaining/state",
            str(round(self.canister.cl_remaining_ml / 1000, 1)), retain=True)
        # Read-only percent
        self._local.publish(
            f"{TOPIC_PREFIX}/sensor/ph_canister_level/state",
            str(self.canister.ph_remaining_percent), retain=True)
        self._local.publish(
            f"{TOPIC_PREFIX}/sensor/cl_canister_level/state",
            str(self.canister.cl_remaining_percent), retain=True)
        # Read-only consumed
        self._local.publish(
            f"{TOPIC_PREFIX}/sensor/ph_canister_consumed/state",
            str(self.canister.ph_consumed_liters), retain=True)
        self._local.publish(
            f"{TOPIC_PREFIX}/sensor/cl_canister_consumed/state",
            str(self.canister.cl_consumed_liters), retain=True)

    def update_canister(self):
        """Calculate consumption, publish state, check alerts. Call periodically."""
        self.canister.calculate()
        self.publish_canister_state()
        self.canister.save_state()
        return self.canister.check_alerts()

    # --- Refresh ---

    def _trigger_refresh(self):
        """Send empty messages to /g/ topics to trigger Bayrol data refresh."""
        log.info("Triggering data refresh from Bayrol cloud...")
        all_registers = [s["register"] for s in SENSORS] + \
                        [s["register"] for s in BINARY_SENSORS] + \
                        [s["register"] for s in WRITABLE_NUMBERS] + \
                        [s["register"] for s in WRITABLE_SELECTS]
        for register in all_registers:
            topic = f"d02/{self.device_id}/g/{register}"
            self._bayrol.publish(topic, "", qos=0)
        self._last_refresh = time.monotonic()
        log.info("Refresh triggered for %d registers", len(all_registers))

    def check_refresh(self):
        """Check if it's time to trigger a refresh."""
        if time.monotonic() - self._last_refresh >= self.refresh_interval:
            self._trigger_refresh()
