#!/usr/bin/env bash
# install.sh — Install Victus Fan Control
# Must be run as root:  sudo bash install.sh [username]
#
# What this script does:
#   1. Installs required system packages (PyGObject, GTK4, libadwaita).
#   2. Creates a 'fancontrol' group and adds the target user to it.
#   3. Installs the permissions helper and a systemd service that sets
#      hwmon PWM file ownership on every boot.
#   4. Copies app files to /usr/local/lib/victus-fan-control/.
#   5. Creates the /usr/local/bin/victus-fan-control launcher.
#   6. Installs the .desktop entry so the app appears in GNOME apps menu.
#   7. Starts the permissions service immediately (no reboot needed).
set -euo pipefail

# ---- privilege check -------------------------------------------------------
if [[ "$(id -u)" -ne 0 ]]; then
    echo "Error: this script must be run as root (sudo bash install.sh)." >&2
    exit 1
fi

# ---- determine target user -------------------------------------------------
if [[ $# -ge 1 ]]; then
    TARGET_USER="$1"
else
    # Default to SUDO_USER if available; otherwise ask.
    TARGET_USER="${SUDO_USER:-}"
    if [[ -z "$TARGET_USER" ]]; then
        read -rp "Enter the username to grant fan control access: " TARGET_USER
    fi
fi

if ! id "$TARGET_USER" &>/dev/null; then
    echo "Error: user '$TARGET_USER' does not exist." >&2
    exit 1
fi

echo "==> Installing Victus Fan Control for user: $TARGET_USER"

# ---- install system packages -----------------------------------------------
echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    lm-sensors \
    2>/dev/null

# ---- fancontrol group ------------------------------------------------------
echo "==> Setting up 'fancontrol' group..."
if ! getent group fancontrol &>/dev/null; then
    groupadd fancontrol
    echo "    Created group 'fancontrol'."
else
    echo "    Group 'fancontrol' already exists."
fi

if id -nG "$TARGET_USER" | grep -qw fancontrol; then
    echo "    User '$TARGET_USER' already in group 'fancontrol'."
else
    usermod -aG fancontrol "$TARGET_USER"
    echo "    Added '$TARGET_USER' to group 'fancontrol'."
fi

# ---- permissions helper ----------------------------------------------------
echo "==> Installing permissions helper..."
install -m 0755 scripts/victus-fan-permissions /usr/local/sbin/victus-fan-permissions

# ---- systemd service -------------------------------------------------------
echo "==> Installing systemd service..."
install -m 0644 scripts/victus-fan-permissions.service \
    /etc/systemd/system/victus-fan-permissions.service
systemctl daemon-reload
systemctl enable victus-fan-permissions.service
systemctl start  victus-fan-permissions.service
echo "    Service started — PWM permissions applied."

# ---- copy application files ------------------------------------------------
APP_DIR="/usr/local/lib/victus-fan-control"
echo "==> Copying application to $APP_DIR..."
mkdir -p "$APP_DIR"
cp -r victus_fan_control "$APP_DIR/"
cp    main.py             "$APP_DIR/"

# ---- launcher --------------------------------------------------------------
echo "==> Installing launcher..."
install -m 0755 victus-fan-control /usr/local/bin/victus-fan-control

# ---- desktop entry ---------------------------------------------------------
echo "==> Installing desktop entry..."
install -m 0644 com.victus.fancontrol.desktop \
    /usr/share/applications/com.victus.fancontrol.desktop
update-desktop-database /usr/share/applications 2>/dev/null || true

# ---- done ------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Installation complete!"
echo ""
echo " Launch the app:"
echo "   • From the GNOME apps grid: search 'Victus Fan Control'"
echo "   • From terminal: victus-fan-control"
echo ""
echo " IMPORTANT: Log out and back in so your group membership"
echo " ($TARGET_USER -> fancontrol) takes effect."
echo "============================================================"
