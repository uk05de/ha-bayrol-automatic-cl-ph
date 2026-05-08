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
from datetime import date

log = logging.getLogger("bayrol.canister")

STATE_FILE = "/data/canister_state.json"


class CanisterTracker:
    """Tracks canister fill levels for pH and Chlorine."""

    def __init__(self, config: dict):
        self.canister_size_cl = config.get("canister_size_cl", 25.0)  # liters
        self.canister_size_ph = config.get("canister_size_ph", 25.0)  # liters
        self.alert_threshold = config.get("alert_threshold", 20)  # percent remaining
        # Optional Day-Limits (in ml). Wenn 0 / nicht gesetzt: kein Limit-
        # Tracking. Bayrol Standard ist 1.6 L = 1600 ml für pH-minus.
        self.ph_day_limit_ml = float(config.get("ph_day_limit_ml", 0))
        self.cl_day_limit_ml = float(config.get("cl_day_limit_ml", 0))

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

        # Consumed amounts in ml — Lifetime-Counter
        self._consumed_cl_ml = 0.0
        self._consumed_ph_ml = 0.0
        # Today-Counter (resettet um 00:00 lokal)
        self._consumed_ph_today_ml = 0.0
        self._consumed_cl_today_ml = 0.0
        self._today_date: str = date.today().isoformat()
        self._last_calc_time = time.monotonic()
        # Event-driven ON-time tracking — exact duration zwischen
        # OFF→ON und ON→OFF Transitions. Vermeidet Sampling-Aliasing
        # bei kurzen Pump-Pulsen (z.B. 4.8s ON bei 8% Duty).
        self._ph_pump_on_since: float | None = None
        self._cl_pump_on_since: float | None = None

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
                self._consumed_ph_today_ml = state.get("consumed_ph_today_ml", 0.0)
                self._consumed_cl_today_ml = state.get("consumed_cl_today_ml", 0.0)
                self._today_date = state.get("today_date", date.today().isoformat())
                self._ph_alert_sent = state.get("ph_alert_sent", False)
                self._cl_alert_sent = state.get("cl_alert_sent", False)
                # Wenn nach Restart anderer Tag → Today-Counter zurücksetzen
                self._maybe_reset_today_counters()
                log.info("Loaded canister state: CL %.0f ml, pH %.0f ml consumed (today: pH %.0f, CL %.0f)",
                         self._consumed_cl_ml, self._consumed_ph_ml,
                         self._consumed_ph_today_ml, self._consumed_cl_today_ml)
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Failed to load canister state: %s", e)

    def save_state(self):
        """Persist consumed amounts to disk."""
        state = {
            "consumed_cl_ml": round(self._consumed_cl_ml, 2),
            "consumed_ph_ml": round(self._consumed_ph_ml, 2),
            "consumed_ph_today_ml": round(self._consumed_ph_today_ml, 2),
            "consumed_cl_today_ml": round(self._consumed_cl_today_ml, 2),
            "today_date": self._today_date,
            "ph_alert_sent": self._ph_alert_sent,
            "cl_alert_sent": self._cl_alert_sent,
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
        except IOError as e:
            log.error("Failed to save canister state: %s", e)

    def _maybe_reset_today_counters(self):
        """Wenn lokaler Tag gewechselt hat, Today-Counter zurücksetzen."""
        current_date = date.today().isoformat()
        if current_date != self._today_date:
            log.info(
                "Pool Advisor: Tageswechsel %s → %s — Today-Counter reset (pH war %.0f ml, CL war %.0f ml)",
                self._today_date, current_date,
                self._consumed_ph_today_ml, self._consumed_cl_today_ml,
            )
            self._consumed_ph_today_ml = 0.0
            self._consumed_cl_today_ml = 0.0
            self._today_date = current_date

    # --- Sensor value updates ---

    def update_value(self, key: str, value):
        """Update a sensor value used for consumption calculation.

        Für pump_state-Keys: detect Transitionen und akkumuliere event-driven
        die exakte ON-Dauer (vermeidet Sampling-Aliasing bei kurzen Pulsen).
        """
        if key not in self._values:
            return

        if key in ("ph_pump_state", "cl_pump_state"):
            old_value = self._values[key]
            self._values[key] = value
            if old_value != value:
                self._handle_pump_transition(key, value)
        else:
            self._values[key] = value

    def _handle_pump_transition(self, key: str, new_state: bool) -> None:
        """Behandle pump_state-Transition: bei ON merken wann, bei OFF
        Dauer × Kapazität in Counter rechnen."""
        now = time.monotonic()
        # Tageswechsel-Check vor Akkumulation
        self._maybe_reset_today_counters()

        if key == "ph_pump_state":
            if new_state:
                # OFF→ON
                self._ph_pump_on_since = now
                log.debug("pH pump ON @ %.1f", now)
            else:
                # ON→OFF
                if self._ph_pump_on_since is not None:
                    duration_s = now - self._ph_pump_on_since
                    consumed = self._values["ph_pump_capacity"] * (duration_s / 3600.0)
                    self._consumed_ph_ml += consumed
                    self._consumed_ph_today_ml += consumed
                    log.debug(
                        "pH pump OFF: %.2fs ON → %.2f ml dosed",
                        duration_s, consumed,
                    )
                    self._ph_pump_on_since = None
        elif key == "cl_pump_state":
            if new_state:
                self._cl_pump_on_since = now
                log.debug("CL pump ON @ %.1f", now)
            else:
                if self._cl_pump_on_since is not None:
                    duration_s = now - self._cl_pump_on_since
                    consumed = self._values["cl_pump_capacity"] * (duration_s / 3600.0)
                    self._consumed_cl_ml += consumed
                    self._consumed_cl_today_ml += consumed
                    log.debug(
                        "CL pump OFF: %.2fs ON → %.2f ml dosed",
                        duration_s, consumed,
                    )
                    self._cl_pump_on_since = None

    # --- Consumption calculation ---

    def calculate(self):
        """Periodischer Tick — akkumuliert KEINE pump-Zeiten (das passiert
        event-driven in _handle_pump_transition). Diese Funktion sorgt nur
        für Tageswechsel-Reset und ggf. Live-Update bei aktuell laufender
        Pumpe (damit der Today-Sensor in HA nicht erst beim OFF-Event
        aktualisiert wird).
        """
        now = time.monotonic()
        elapsed_s = now - self._last_calc_time
        self._last_calc_time = now

        if elapsed_s <= 0 or elapsed_s > 3600:
            return

        # Tageswechsel-Check
        self._maybe_reset_today_counters()

        # Live-Update für aktuell laufende Pumpe — wir akkumulieren in der
        # Counter, machen das aber bei der nächsten OFF-Transition rückgängig
        # damit es zur exakten Duration passt. Stattdessen: kein Live-Update,
        # Today-Sensor zeigt erst beim OFF die neue Dosis.
        # → keine Aktion in calculate(). pump-Akkumulation ist 100%
        #   event-driven via _handle_pump_transition.

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

    # --- Tagesverbrauch ---

    @property
    def ph_dosed_today_ml(self) -> float:
        self._maybe_reset_today_counters()
        return round(self._consumed_ph_today_ml, 1)

    @property
    def cl_dosed_today_ml(self) -> float:
        self._maybe_reset_today_counters()
        return round(self._consumed_cl_today_ml, 1)

    @property
    def ph_day_limit_reached(self) -> bool:
        if self.ph_day_limit_ml <= 0:
            return False
        return self._consumed_ph_today_ml >= self.ph_day_limit_ml

    @property
    def cl_day_limit_reached(self) -> bool:
        if self.cl_day_limit_ml <= 0:
            return False
        return self._consumed_cl_today_ml >= self.cl_day_limit_ml

    @property
    def ph_day_limit_remaining_ml(self) -> float:
        if self.ph_day_limit_ml <= 0:
            return 0.0
        remaining = self.ph_day_limit_ml - self._consumed_ph_today_ml
        return max(0.0, round(remaining, 1))

    @property
    def cl_day_limit_remaining_ml(self) -> float:
        if self.cl_day_limit_ml <= 0:
            return 0.0
        remaining = self.cl_day_limit_ml - self._consumed_cl_today_ml
        return max(0.0, round(remaining, 1))

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

    def set_ph_remaining(self, liters: float):
        """Manually set pH canister remaining volume."""
        self._consumed_ph_ml = (self.canister_size_ph * 1000) - (liters * 1000)
        self._consumed_ph_ml = max(0.0, self._consumed_ph_ml)
        # Reset alert if level was corrected above threshold
        if self.ph_remaining_percent > self.alert_threshold:
            self._ph_alert_sent = False
        self.save_state()

    def set_cl_remaining(self, liters: float):
        """Manually set chlorine canister remaining volume."""
        self._consumed_cl_ml = (self.canister_size_cl * 1000) - (liters * 1000)
        self._consumed_cl_ml = max(0.0, self._consumed_cl_ml)
        if self.cl_remaining_percent > self.alert_threshold:
            self._cl_alert_sent = False
        self.save_state()

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
