# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Canister Level Tracker
#
# Tracks consumption of pH- and Chlorine canisters based on
# pump capacity, production rate, and dosing rate.
# Persists consumed amounts in HA input_number helpers.
#

import json
import logging
import os
import time
import urllib.request

log = logging.getLogger("bayrol.canister")

SUPERVISOR_API = "http://supervisor/core/api"

# HA helper entity IDs
ENTITY_CONSUMED_PH = "input_number.bayrol_consumed_ph_ml"
ENTITY_CONSUMED_CL = "input_number.bayrol_consumed_cl_ml"
ENTITY_ALERT_PH = "input_boolean.bayrol_ph_alert_sent"
ENTITY_ALERT_CL = "input_boolean.bayrol_cl_alert_sent"


class CanisterTracker:
    """Tracks canister fill levels for pH and Chlorine."""

    def __init__(self, config: dict):
        self.canister_size_cl = config.get("canister_size_cl", 25.0)  # liters
        self.canister_size_ph = config.get("canister_size_ph", 25.0)  # liters
        self.alert_threshold = config.get("alert_threshold", 20)  # percent remaining
        self._token = os.environ.get("SUPERVISOR_TOKEN", "")

        # Current sensor values (updated from bridge)
        self._values = {
            "ph_pump_state": False,
            "ph_pump_capacity": 0,      # ml/h
            "ph_prod_rate": 0,          # % (75/100/125)
            "ph_dosing_rate": 0,        # %
            "cl_pump_state": False,
            "cl_pump_capacity": 0,      # ml/h
            "cl_prod_rate": 0,          # % (75/100/125)
            "cl_dosing_rate": 0,        # %
        }

        # Consumed amounts in ml
        self._consumed_cl_ml = 0.0
        self._consumed_ph_ml = 0.0
        self._last_calc_time = time.monotonic()

        # Alert state (to avoid repeated notifications)
        self._ph_alert_sent = False
        self._cl_alert_sent = False

        # HA state initialized
        self._ha_initialized = False

    # --- HA API helpers ---

    def _ha_api(self, method: str, path: str, data: dict = None):
        """Call Home Assistant API via Supervisor."""
        if not self._token:
            log.warning("No SUPERVISOR_TOKEN available")
            return None

        url = f"{SUPERVISOR_API}{path}"
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
                return None
        except Exception as e:
            log.debug("HA API %s %s failed: %s", method, path, e)
            return None

    def _get_ha_state(self, entity_id: str, default=None):
        """Get current state of an HA entity."""
        result = self._ha_api("GET", f"/states/{entity_id}")
        if result and result.get("state") not in (None, "unknown", "unavailable"):
            try:
                return float(result["state"])
            except (ValueError, TypeError):
                if result["state"] in ("on", "off"):
                    return result["state"] == "on"
        return default

    def _set_ha_state(self, entity_id: str, value):
        """Set state of an HA entity via service call."""
        if entity_id.startswith("input_number"):
            self._ha_api("POST", "/services/input_number/set_value", {
                "entity_id": entity_id,
                "value": value,
            })
        elif entity_id.startswith("input_boolean"):
            service = "turn_on" if value else "turn_off"
            self._ha_api("POST", f"/services/input_boolean/{service}", {
                "entity_id": entity_id,
            })

    def _create_helper(self, entity_id: str, name: str, helper_type: str, **kwargs):
        """Create an HA helper if it doesn't exist."""
        result = self._ha_api("GET", f"/states/{entity_id}")
        if result and result.get("state") != "unavailable":
            log.debug("Helper %s already exists", entity_id)
            return

        if helper_type == "input_number":
            self._ha_api("POST", "/services/input_number/create", {
                "name": name,
                "min": kwargs.get("min", 0),
                "max": kwargs.get("max", 100000),
                "step": kwargs.get("step", 0.01),
                "unit_of_measurement": kwargs.get("unit", "ml"),
                "mode": "box",
                "icon": kwargs.get("icon", "mdi:counter"),
            })
        elif helper_type == "input_boolean":
            self._ha_api("POST", "/services/input_boolean/create", {
                "name": name,
                "icon": kwargs.get("icon", "mdi:alert"),
            })

        log.info("Created helper: %s", entity_id)

    # --- Initialization ---

    def init_ha_helpers(self):
        """Create HA helpers and load persisted state."""
        if not self._token:
            log.warning("No SUPERVISOR_TOKEN, HA persistence disabled")
            return

        # Create helpers if they don't exist
        self._create_helper(
            ENTITY_CONSUMED_PH, "Bayrol pH Verbrauch (ml)",
            "input_number", min=0, max=100000, step=0.01,
            unit="ml", icon="mdi:water-minus",
        )
        self._create_helper(
            ENTITY_CONSUMED_CL, "Bayrol Chlor Verbrauch (ml)",
            "input_number", min=0, max=100000, step=0.01,
            unit="ml", icon="mdi:water-minus",
        )
        self._create_helper(
            ENTITY_ALERT_PH, "Bayrol pH Alert gesendet",
            "input_boolean", icon="mdi:alert",
        )
        self._create_helper(
            ENTITY_ALERT_CL, "Bayrol Chlor Alert gesendet",
            "input_boolean", icon="mdi:alert",
        )

        # Wait for helpers to be available
        time.sleep(2)

        # Load current values from HA
        self._consumed_ph_ml = self._get_ha_state(ENTITY_CONSUMED_PH, 0.0)
        self._consumed_cl_ml = self._get_ha_state(ENTITY_CONSUMED_CL, 0.0)
        self._ph_alert_sent = self._get_ha_state(ENTITY_ALERT_PH, False)
        self._cl_alert_sent = self._get_ha_state(ENTITY_ALERT_CL, False)
        self._ha_initialized = True

        log.info("Loaded canister state from HA: pH %.0f ml, CL %.0f ml consumed",
                 self._consumed_ph_ml, self._consumed_cl_ml)

    def save_state(self):
        """Persist consumed amounts to HA helpers."""
        if not self._ha_initialized:
            return
        self._set_ha_state(ENTITY_CONSUMED_PH, round(self._consumed_ph_ml, 2))
        self._set_ha_state(ENTITY_CONSUMED_CL, round(self._consumed_cl_ml, 2))
        self._set_ha_state(ENTITY_ALERT_PH, self._ph_alert_sent)
        self._set_ha_state(ENTITY_ALERT_CL, self._cl_alert_sent)

    # --- Sensor value updates ---

    def update_value(self, key: str, value):
        """Update a sensor value used for consumption calculation."""
        if key in self._values:
            self._values[key] = value

    # --- Consumption calculation ---

    def calculate(self):
        """Calculate consumption since last call. Call this periodically."""
        now = time.monotonic()
        elapsed_s = now - self._last_calc_time
        self._last_calc_time = now

        if elapsed_s <= 0 or elapsed_s > 3600:
            return

        # pH consumption
        if self._values["ph_pump_state"]:
            ph_flow_ml_h = (
                self._values["ph_pump_capacity"]
                * (self._values["ph_prod_rate"] / 100.0)
                * (self._values["ph_dosing_rate"] / 100.0)
            )
            consumed = ph_flow_ml_h * (elapsed_s / 3600.0)
            self._consumed_ph_ml += consumed
            if consumed > 0:
                log.debug("pH consumed: %.2f ml (flow: %.1f ml/h)", consumed, ph_flow_ml_h)

        # Chlor consumption
        if self._values["cl_pump_state"]:
            cl_flow_ml_h = (
                self._values["cl_pump_capacity"]
                * (self._values["cl_prod_rate"] / 100.0)
                * (self._values["cl_dosing_rate"] / 100.0)
            )
            consumed = cl_flow_ml_h * (elapsed_s / 3600.0)
            self._consumed_cl_ml += consumed
            if consumed > 0:
                log.debug("CL consumed: %.2f ml (flow: %.1f ml/h)", consumed, cl_flow_ml_h)

    # --- Remaining levels ---

    @property
    def ph_remaining_ml(self) -> float:
        remaining = (self.canister_size_ph * 1000) - self._consumed_ph_ml
        return max(0.0, remaining)

    @property
    def cl_remaining_ml(self) -> float:
        remaining = (self.canister_size_cl * 1000) - self._consumed_cl_ml
        return max(0.0, remaining)

    @property
    def ph_remaining_percent(self) -> float:
        return round(self.ph_remaining_ml / (self.canister_size_ph * 1000) * 100, 1)

    @property
    def cl_remaining_percent(self) -> float:
        return round(self.cl_remaining_ml / (self.canister_size_cl * 1000) * 100, 1)

    @property
    def ph_consumed_liters(self) -> float:
        return round(self._consumed_ph_ml / 1000, 2)

    @property
    def cl_consumed_liters(self) -> float:
        return round(self._consumed_cl_ml / 1000, 2)

    # --- Alerts ---

    def check_alerts(self) -> list:
        """Check if any canister is below threshold. Returns list of alert messages."""
        alerts = []

        if self.ph_remaining_percent <= self.alert_threshold and not self._ph_alert_sent:
            self._ph_alert_sent = True
            alerts.append(
                f"pH- Kanister bei {self.ph_remaining_percent}% "
                f"({self.ph_remaining_ml / 1000:.1f}L von {self.canister_size_ph}L). "
                f"Bitte nachbestellen!"
            )
            log.warning("pH canister alert: %.1f%% remaining", self.ph_remaining_percent)

        if self.cl_remaining_percent <= self.alert_threshold and not self._cl_alert_sent:
            self._cl_alert_sent = True
            alerts.append(
                f"Chlor Kanister bei {self.cl_remaining_percent}% "
                f"({self.cl_remaining_ml / 1000:.1f}L von {self.canister_size_cl}L). "
                f"Bitte nachbestellen!"
            )
            log.warning("CL canister alert: %.1f%% remaining", self.cl_remaining_percent)

        return alerts

    # --- Reset ---

    def reset_ph(self):
        """Reset pH canister to full (new canister installed)."""
        log.info("pH canister reset to full (%dL)", self.canister_size_ph)
        self._consumed_ph_ml = 0.0
        self._ph_alert_sent = False
        self.save_state()

    def reset_cl(self):
        """Reset chlorine canister to full (new canister installed)."""
        log.info("CL canister reset to full (%dL)", self.canister_size_cl)
        self._consumed_cl_ml = 0.0
        self._cl_alert_sent = False
        self.save_state()
