# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Canister Level Tracker
#
# Tracks consumption of pH- and Chlorine canisters based on
# pump capacity, production rate, and dosing rate.
# Persists state in /data/canister_state.json (included in HA backups).
#

import json
import logging
import os
import time

log = logging.getLogger("bayrol.canister")

STATE_FILE = "/data/canister_state.json"


class CanisterTracker:
    """Tracks canister fill levels for pH and Chlorine."""

    def __init__(self, config: dict):
        self.canister_size_cl = config.get("canister_size_cl", 25.0)  # liters
        self.canister_size_ph = config.get("canister_size_ph", 25.0)  # liters
        self.alert_threshold = config.get("alert_threshold", 20)  # percent remaining

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

        # Load persisted state
        self._load_state()

    # --- State persistence ---

    def _load_state(self):
        """Load consumed amounts from persistent storage."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                self._consumed_cl_ml = state.get("consumed_cl_ml", 0.0)
                self._consumed_ph_ml = state.get("consumed_ph_ml", 0.0)
                self._ph_alert_sent = state.get("ph_alert_sent", False)
                self._cl_alert_sent = state.get("cl_alert_sent", False)
                log.info("Loaded canister state: CL %.0f ml, pH %.0f ml consumed",
                         self._consumed_cl_ml, self._consumed_ph_ml)
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Failed to load canister state: %s", e)

    def save_state(self):
        """Persist consumed amounts to disk."""
        state = {
            "consumed_cl_ml": round(self._consumed_cl_ml, 2),
            "consumed_ph_ml": round(self._consumed_ph_ml, 2),
            "ph_alert_sent": self._ph_alert_sent,
            "cl_alert_sent": self._cl_alert_sent,
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
        except IOError as e:
            log.error("Failed to save canister state: %s", e)

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
