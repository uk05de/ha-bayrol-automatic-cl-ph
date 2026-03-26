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
    transform_value, evaluate_binary,
)

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

        # Build register lookup for fast message routing
        self._sensor_by_register = {}
        for s in SENSORS:
            self._sensor_by_register[s["register"]] = ("sensor", s)
        for s in BINARY_SENSORS:
            self._sensor_by_register[s["register"]] = ("binary_sensor", s)

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
        self._local_host = config["mqtt_host"]
        self._local_port = config["mqtt_port"]

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

        # Extract register from topic: d02/DEVICE_ID/v/X.Y -> X.Y
        parts = topic.split("/")
        if len(parts) < 4 or parts[2] != "v":
            return

        register = parts[3]

        # Parse payload
        try:
            data = json.loads(payload)
            raw_value = data.get("v")
            if raw_value is None:
                return
        except (json.JSONDecodeError, TypeError):
            return

        # Route to sensor
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

        elif component == "binary_sensor":
            is_on = evaluate_binary(sensor, raw_value)
            state_topic = f"{TOPIC_PREFIX}/binary_sensor/{sensor['unique_id']}/state"
            self._local.publish(state_topic, "ON" if is_on else "OFF", retain=True)
            log.debug("Published %s = %s", sensor["name"], "ON" if is_on else "OFF")

        # Update availability
        self._local.publish(f"{TOPIC_PREFIX}/availability", "online", retain=True)

    def _on_bayrol_disconnect(self, client, userdata, rc, properties=None):
        if rc != 0:
            log.warning("Bayrol cloud disconnected unexpectedly (rc=%d), will reconnect", rc)
        else:
            log.info("Bayrol cloud disconnected")

    # --- Local MQTT callbacks ---

    def _on_local_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Local MQTT broker connected")
            self._discovery_sent = False
            self.send_discovery()
        else:
            log.error("Local MQTT connection failed with code %d", rc)

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

        self._discovery_sent = True
        # Publish initial availability so entities appear in HA
        self._local.publish(f"{TOPIC_PREFIX}/availability", "online", retain=True)
        log.info("MQTT Discovery published (%d sensors, %d binary sensors)",
                 len(SENSORS), len(BINARY_SENSORS))

    # --- Refresh ---

    def _trigger_refresh(self):
        """Send empty messages to /g/ topics to trigger Bayrol data refresh."""
        log.info("Triggering data refresh from Bayrol cloud...")
        all_registers = [s["register"] for s in SENSORS] + \
                        [s["register"] for s in BINARY_SENSORS]
        for register in all_registers:
            topic = f"d02/{self.device_id}/g/{register}"
            self._bayrol.publish(topic, "", qos=0)
        self._last_refresh = time.monotonic()
        log.info("Refresh triggered for %d registers", len(all_registers))

    def check_refresh(self):
        """Check if it's time to trigger a refresh."""
        if time.monotonic() - self._last_refresh >= self.refresh_interval:
            self._trigger_refresh()
