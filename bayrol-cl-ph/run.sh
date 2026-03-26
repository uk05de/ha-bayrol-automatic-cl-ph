#!/usr/bin/env bash
set -e

OPTIONS_FILE="/data/options.json"

if [ ! -f "$OPTIONS_FILE" ]; then
    echo "ERROR: Options file not found at $OPTIONS_FILE"
    exit 1
fi

echo "============================================"
echo "  Bayrol Automatic CL/PH Addon"
echo "============================================"
cat "$OPTIONS_FILE" | python3 -c "import sys,json; d=json.load(sys.stdin); d['bayrol_password']='***'; print(json.dumps(d,indent=2))"
echo ""
echo "============================================"

if [ -f "/srv/venv/bin/activate" ]; then
    source /srv/venv/bin/activate
fi

cd /srv/src
exec python3 main.py "$OPTIONS_FILE"
