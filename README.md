# Victus Fan Control

A GTK4/libadwaita desktop application for monitoring and manually controlling fan speeds on the **HP Victus gaming laptop** (and potentially other HP WMI-based laptops) running Ubuntu/Linux.

![Screenshot](docs/screenshot.png)

## Features

- **Real-time temperature monitoring** — CPU (AMD k10temp), GPU (AMD integrated + NVIDIA discrete), NVMe drive, Wi-Fi chip, RAM, and ACPI thermal zones
- **Real-time fan RPM display** — colour-coded level bars and status indicators
- **Manual fan speed control** — set a target RPM for CPU and GPU fans independently
- **Automatic mode** — hands control back to the BIOS fan curve with clean state (no stale targets)
- **Auto-refresh** — all sensors update every 2 seconds
- **GNOME integration** — appears in the apps grid, uses native libadwaita styling

## How It Works

### Hardware interface

HP Victus laptops expose fan control through the `hp_wmi` kernel driver at:

```
/sys/devices/platform/hp-wmi/hwmon/hwmon*/
  fan1_input        — CPU fan RPM (read)
  fan2_input        — GPU fan RPM (read)
  fan1_max          — CPU fan maximum RPM (read)
  fan2_max          — GPU fan maximum RPM (read)
  fan1_target       — CPU fan target RPM (write to control)
  fan2_target       — GPU fan target RPM (write to control)
  pwm1_enable       — mode switch: 1 = manual, 2 = automatic (write)
```

Unlike typical hwmon devices that use PWM duty cycles (0–255), the HP Victus uses **target RPM** values. You write the desired RPM directly to `fan1_target` / `fan2_target`, and the driver translates that to a PWM duty cycle internally.

`pwm1_enable` is **shared** — setting it to `1` (manual) or `2` (automatic) affects both fans simultaneously. This is a hardware limitation of the HP WMI interface.

Temperature and other sensor data comes from the standard Linux hwmon sysfs tree (`/sys/class/hwmon/hwmon*/temp*_input`). NVIDIA GPU temperature is read via `nvidia-smi`.

### Permission model

The `fan*_target` and `pwm1_enable` sysfs files are owned by root. To allow a normal user to control fans **without running the app as root**, the installer:

1. Creates a `fancontrol` system group
2. Adds the target user to that group
3. Installs a **systemd one-shot service** (`victus-fan-permissions.service`) that runs at every boot and sets `root:fancontrol` ownership with `664` permissions on all controllable sysfs files

The app itself runs entirely as a regular user.

### Auto mode and hysteresis

When you switch a fan back to **Automatic**, the app:
1. Writes `0` to `fan1_target` / `fan2_target` (clears any stale manual value)
2. Writes `2` to `pwm1_enable` (hands control to the BIOS)

This prevents a bug where the BIOS would honour the last manual target even after being switched back to auto mode.

**Note:** BIOS fan curves use intentional hysteresis. Fans may spin up to ~5000 RPM at 80 °C and not spin back down until temperatures reach 40–45 °C. This is normal and prevents rapid oscillation.

### Application stack

```
main.py                          — Adw.Application entry point
victus_fan_control/
  hwmon.py                       — Hardware backend (sysfs reads/writes)
  window.py                      — GTK4/Adwaita UI (MainWindow, sensor rows)
```

| Layer | Technology |
|-------|-----------|
| UI toolkit | GTK 4 + libadwaita |
| Language | Python 3 |
| Hardware API | Linux hwmon sysfs + nvidia-smi |
| Fan driver | hp_wmi (kernel built-in) |
| Permission service | systemd one-shot |

## Requirements

- Ubuntu 22.04 or later (or any distro with GTK 4.6+)
- HP Victus laptop (or other HP WMI laptop with `hp_wmi` driver)
- `python3`, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`
- Optional: `nvidia-smi` for NVIDIA GPU temperature

## Installation

```bash
git clone https://github.com/AhmetHakanYilmaz/victus-fan-control.git
cd victus-fan-control
sudo bash install.sh
```

The installer will:
- Install required apt packages
- Create the `fancontrol` group and add your user to it
- Install and start the permissions systemd service
- Copy the app to `/usr/local/lib/victus-fan-control/`
- Create the `/usr/local/bin/victus-fan-control` launcher
- Register the app in the GNOME applications menu

**After installation, log out and back in** so your `fancontrol` group membership takes effect.

## Running

```bash
victus-fan-control          # from terminal
```

Or search for **Victus Fan Control** in the GNOME apps grid.

## Uninstalling

```bash
sudo bash uninstall.sh
```

## File layout (installed)

```
/usr/local/bin/victus-fan-control              — launcher
/usr/local/lib/victus-fan-control/             — application files
/usr/local/sbin/victus-fan-permissions         — permissions helper script
/etc/systemd/system/victus-fan-permissions.service
/usr/share/applications/com.victus.fancontrol.desktop
/usr/share/icons/hicolor/scalable/apps/com.victus.fancontrol.svg
```

## License

MIT
