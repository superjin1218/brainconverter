#!/usr/bin/env bash
# Run only after reviewing deploy/brainconverter.service and approving system changes.
# Does not modify cloudflared, DNS, Supabase, accounts, or any existing unit.
set -euo pipefail

project=/home/jinwoo/Desktop/brainconvertoe
unit=brainconverter.service
destination=/etc/systemd/system/brainconverter.service

if [ "$(id -u)" -ne 0 ]; then
    echo "Run: sudo bash deploy/install-systemd.sh"
    exit 1
fi
load_state=$(systemctl show "$unit" -p LoadState --value 2>/dev/null || true)
if [ -e "$destination" ] || [ -L "$destination" ] || [ "$load_state" != "not-found" ]; then
    echo "A brainconverter unit already exists; refusing to overwrite it."
    exit 1
fi
# Assignment fails closed under set -e if ss cannot run. No rg dependency in sudo PATH.
listeners=$(ss -H -ltn 'sport = :3000')
if [ -n "$listeners" ]; then
    echo "Port 3000 is occupied; refusing to replace another process."
    exit 1
fi
cd "$project"
runuser -u jinwoo -- "$project/.venv/bin/python" -m scripts.check_production_config --env-file
systemd-analyze verify "$project/deploy/brainconverter.service"
install -o root -g root -m 0644 "$project/deploy/brainconverter.service" "$destination"
systemctl daemon-reload
systemctl enable --now "$unit"
systemctl is-enabled "$unit"
systemctl is-active "$unit"
