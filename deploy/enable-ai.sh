#!/usr/bin/env bash
# Operator-approved activation. No inference, migrations, or ledger resets.
set -euo pipefail
project=/home/jinwoo/Desktop/brainconvertoe
unit=/etc/systemd/system/brainconverter.service
backup=/etc/systemd/system/brainconverter.service.pre-ai
paused_hash=b6d0256c37ce4d543e2ce4febc77988a63f3fd6bc3f88dcb511f3ede6756792c

if [ "$(id -u)" -ne 0 ]; then
    echo "Run: sudo bash deploy/enable-ai.sh"
    exit 1
fi
read -r current_hash ignored < <(sha256sum "$unit")
if [ "$current_hash" != "$paused_hash" ]; then
    echo "Installed service differs from the reviewed paused unit; refusing to overwrite."
    exit 1
fi
if [ -n "$(systemctl show brainconverter.service -p DropInPaths --value)" ]; then
    echo "Service overrides exist; review them before activation."
    exit 1
fi
if [ -e "$backup" ] || [ -L "$backup" ]; then
    echo "A previous backup exists; review it before activation."
    exit 1
fi
cd "$project"
runuser -u jinwoo -- "$project/.venv/bin/python" - <<'PY'
import asyncio, os
import httpx
from dotenv import load_dotenv
from scripts.check_production_config import validate
from backend.app.openai_provider import OpenAIProvider
try:
    load_dotenv('.env.local', override=True)
    os.environ['CONVERSIONS_ENABLED'] = 'true'
    validate()
    report = asyncio.run(OpenAIProvider().check_connection())
    if report.get('status') != 'ok' or not report.get('modelAvailable'):
        raise ValueError()
    response = httpx.get(
        os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/rpc/brain_openai_budget_ready',
        headers={'apikey': os.environ['SUPABASE_SECRET_KEY']}, timeout=10,
    )
    data = response.json()
    if response.status_code != 200 or data.get('ready') is not True:
        raise ValueError()
    if data.get('allowanceKrw') != 34 or data.get('limitKrw') != 20000:
        raise ValueError()
except Exception:
    print('AI activation preflight failed. No changes made; credentials omitted.')
    raise SystemExit(1) from None
print('AI activation preflight OK: key, model and budget policy; no inference requested.')
PY
systemd-analyze verify "$project/deploy/brainconverter.service"
install -o root -g root -m 0644 "$unit" "$backup"

set_ai_flag() {
    runuser -u jinwoo -- "$project/.venv/bin/python" - "$1" <<'PY'
import sys
from dotenv import set_key
set_key('.env.local', 'CONVERSIONS_ENABLED', sys.argv[1])
PY
}
rollback() {
    trap - ERR
    set +e
    set_ai_flag false
    install -o root -g root -m 0644 "$backup" "$unit"
    systemctl daemon-reload
    systemctl restart brainconverter.service
    echo "Activation failed; restored the paused service. Review its journal."
    exit 1
}
trap rollback ERR
install -o root -g root -m 0644 "$project/deploy/brainconverter.service" "$unit"
set_ai_flag true
systemctl daemon-reload
systemctl restart brainconverter.service
runuser -u jinwoo -- "$project/.venv/bin/python" - <<'PY'
import time
import httpx
for _ in range(20):
    try:
        r = httpx.get('http://127.0.0.1:3000/api/health', timeout=2)
        if r.status_code == 200 and r.json().get('conversionsEnabled') is True:
            print('AI enabled. Approved members can request paid conversions; no inference tested.')
            break
    except (httpx.HTTPError, ValueError):
        pass
    time.sleep(0.5)
else:
    raise SystemExit(1)
PY
systemctl is-active brainconverter.service
trap - ERR
