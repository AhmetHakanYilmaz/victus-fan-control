#!/usr/bin/env bash
# uninstall.sh — Remove Victus Fan Control
# Run as root:  sudo bash uninstall.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Error: this script must be run as root (sudo bash uninstall.sh)." >&2
    exit 1
fi

echo "==> Removing Victus Fan Control..."

# Stop and disable systemd service
if systemctl is-active --quiet victus-fan-permissions.service 2>/dev/null; then
    systemctl stop victus-fan-permissions.service
fi
if systemctl is-enabled --quiet victus-fan-permissions.service 2>/dev/null; then
    systemctl disable victus-fan-permissions.service
fi
rm -f /etc/systemd/system/victus-fan-permissions.service
systemctl daemon-reload

# Remove installed files
rm -f  /usr/local/sbin/victus-fan-permissions
rm -f  /usr/local/bin/victus-fan-control
rm -rf /usr/local/lib/victus-fan-control
rm -f  /usr/share/applications/com.victus.fancontrol.desktop

update-desktop-database /usr/share/applications 2>/dev/null || true

echo ""
echo "Uninstall complete. The 'fancontrol' group was left in place."
echo "Remove it manually with:  sudo groupdel fancontrol"
