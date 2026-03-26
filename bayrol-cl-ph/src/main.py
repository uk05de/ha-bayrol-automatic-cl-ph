# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Main Entry Point
#

import json
import logging
import os
import signal
import sys
import time
import urllib.request

from bayrol_bridge import BayrolBridge

log = logging.getLogger("bayrol")

SUPERVISOR_API = "http://supervisor/core/api"


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def send_ha_notification(message: str, target: str):
    """Send a notification via Home Assistant API."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.warning("No SUPERVISOR_TOKEN, cannot send notification")
        return

    service = f"notify.{target}" if not target.startswith("notify.") else target
    url = f"{SUPERVISOR_API}/services/{service.replace('.', '/')}"
    data = json.dumps({
        "message": message,
        "title": "Bayrol Kanister",
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("Notification sent to %s: %s", target, message)
    except Exception as e:
        log.error("Failed to send notification to %s: %s", target, e)


def main():
    if len(sys.argv) < 2:
        print("Usage: main.py /data/options.json")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        config = json.load(f)

    setup_logging(config.get("loglevel", "INFO"))

    log.info("Starting Bayrol Automatic CL/PH Addon")
    log.info("Device ID: %s", config["device_id"])
    log.info("Refresh interval: %ds", config.get("refresh_interval", 900))
    log.info("Local MQTT: %s:%d", config["mqtt_host"], config["mqtt_port"])
    log.info("Canister sizes: CL=%.0fL, pH=%.0fL",
             config.get("canister_size_cl", 25), config.get("canister_size_ph", 25))
    log.info("Alert threshold: %d%%", config.get("alert_threshold", 20))

    notification_target = config.get("notification_target", "")
    if notification_target:
        log.info("Notifications: %s", notification_target)

    bridge = BayrolBridge(config)

    running = True

    def shutdown(sig, frame):
        nonlocal running
        log.info("Signal %s received, shutting down...", sig)
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    bridge.connect()

    try:
        while running:
            bridge.check_refresh()

            # Update canister tracking
            alerts = bridge.update_canister()
            for alert_msg in alerts:
                if notification_target:
                    send_ha_notification(alert_msg, notification_target)
                else:
                    log.warning("Alert (no notification target): %s", alert_msg)

            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.canister.save_state()
        bridge.disconnect()
        log.info("Bayrol addon stopped")


if __name__ == "__main__":
    main()
