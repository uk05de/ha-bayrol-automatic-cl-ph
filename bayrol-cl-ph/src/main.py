# -*- coding: utf-8 -*-
#
# Bayrol Automatic CL/PH - Main Entry Point
#

import json
import logging
import signal
import sys
import time

from bayrol_bridge import BayrolBridge

log = logging.getLogger("bayrol")


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )


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
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.disconnect()
        log.info("Bayrol addon stopped")


if __name__ == "__main__":
    main()
