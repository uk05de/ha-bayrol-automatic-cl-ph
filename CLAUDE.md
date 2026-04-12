# Bayrol Automatic CL/PH — CLAUDE.md

## Project
- HA Addon for Bayrol Automatic CL/PH pool dosing system
- Repo: uk05de/ha-bayrol-automatic-cl-ph
- Replaces Node-RED flow that bridged Bayrol WSS → local MQTT

## Architecture
- Python addon with two paho-mqtt connections:
  1. WSS to Bayrol cloud (wss://www.bayrol-poolaccess.de:8083, MQTT v5)
  2. TCP to local Mosquitto (192.168.2.158:1883, MQTT v3.11)
- Subscribes to `d02/{device_id}/#` on Bayrol broker
- Transforms values and publishes via MQTT Discovery to local broker
- Refresh mechanism: publishes empty messages to `/g/` topics every 15 min
- Config via `/data/options.json`

## Key Files
- `bayrol-cl-ph/src/sensors.py` — Sensors, binary sensors, writable numbers, writable selects with register addresses and transformations
- `bayrol-cl-ph/src/bayrol_bridge.py` — MQTT bridge, discovery, canister tracking integration
- `bayrol-cl-ph/src/canister_tracker.py` — Canister level tracking with file persistence
- `bayrol-cl-ph/src/main.py` — Main loop, notifications via HA Supervisor API
- `bayrol-cl-ph/config.yaml` — HA addon config (version here!)
- `bayrol-cl-ph/run.sh` — Startup, masks passwords in log output

## Bayrol Protocol
- Bayrol cloud MQTT broker at wss://www.bayrol-poolaccess.de:8083 (WebSocket Secure)
- MQTT v5, requires username/password (PoolAccess credentials)
- Device ID: `23ACL2-04714` (configurable)
- Topics:
  - `d02/{device_id}/v/{register}` — read values (subscribe)
  - `d02/{device_id}/g/{register}` — refresh/get (publish empty)
  - `d02/{device_id}/s/{register}` — write/set (publish `{"t":"{register}","v":{value}}`)
- **Payload formats (BOTH must be handled!):**
  - Single: `{"t":"4.78","v":78,"status":"17.2"}`
  - Batch array: `[{"t":"4.2","v":71}, {"t":"4.3","v":76}, ...]` on batch topics like `/v/22`
- Transformations: /10 for pH and temp, /100 for min control, *100 for pump capacity
- Production rate mapping: 19.3→25%, 19.4→50%, 19.5→75%, 19.6→100%, 19.7→125%, 19.8→150%, 19.9→200%, 19.10→300%, 19.11→500%, 19.12→1000%
- Binary sensors use string comparison: "19.54"=pump on, "19.17"=automatic on, "19.177"=filtration on, "19.258"=canister empty
- Text-mapped status codes: STATUS_TEXT_MAP for flow/gas/problem sensors, specific maps for filtration/out modes
- Trailing-zero MQTT codes (19.100, 19.330) need both normalized and original keys in lookups
- **Writable entities** (number/select, via `/s/` topic):
  - pH Target (4.2), pH Alert Max (4.3), pH Alert Min (4.4) — coefficient 10
  - Redox Target (4.28), Redox Alert Max (4.26), Redox Alert Min (4.27) — coefficient 1
  - Start Delay (4.37) — coefficient 1, range 1–60 min
  - pH Production Rate (5.3), Chlor Production Rate (5.175) — text-mapped select
  - Filtration Mode (5.184) — select: Low/Med/High/Auto/Smart/Frost/Off
  - Out 1–4 Mode (5.186–5.189) — select: On/Off/Auto

## Canister Tracking
- Consumption formula: `flow_ml_h = pump_capacity × (production_rate/100) × (dosing_rate/100)`
- Persisted in `/data/canister_state.json` (included in HA backups)
- MQTT entities: remaining liters (editable number), fill level %, consumed liters, reset buttons
- Alert via HA Supervisor API notification when threshold reached
- Configurable: canister sizes (default 25L), alert threshold (default 20%), notification target
- HA REST API does NOT support creating input_number helpers programmatically — that's why file persistence

## Device Identity
- Identifier: `bayrol_cl_ph_{device_id_normalized}` (e.g. `bayrol_cl_ph_23acl2_04714`)
- Name includes device ID: "Bayrol Automatic CL/PH (23ACL2-04714)"
- Intentionally different from old mqtt.yaml device ID (`23ACL2-04714`) for parallel operation

## Important Notes
- Bayrol credentials: username looks like MD5 hash, password from PoolAccess account
- MQTT broker requires authentication (user: homeassistant)
- `homeassistant_api: true` is set for notifications
- Mask both `bayrol_password` and `mqtt_password` in run.sh log output
- Always bump version in `config.yaml` with every functional change
- Old Node-RED setup used same MQTT topics (`d02/...`) — can run in parallel during migration
