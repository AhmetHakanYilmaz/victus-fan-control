"""
Hardware monitoring backend.

Reads fan RPM and temperatures from the Linux hwmon sysfs interface
(/sys/class/hwmon/hwmon*) and optionally from nvidia-smi for NVIDIA GPUs.
"""

from __future__ import annotations

import glob
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional

HWMON_BASE = "/sys/class/hwmon"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _read(path: str) -> Optional[str]:
    """Read a sysfs attribute file. Returns None on any error."""
    try:
        with open(path, "r") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _write(path: str, value: str) -> bool:
    """Write a sysfs attribute file. Returns True on success."""
    try:
        with open(path, "w") as fh:
            fh.write(value)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Friendly label mapping
# ---------------------------------------------------------------------------

_TEMP_LABEL_MAP: dict[str, str] = {
    # Intel CPU
    "package id 0":  "CPU Package",
    "package id 1":  "CPU Package #2",
    "core 0":        "CPU Core 0",
    "core 1":        "CPU Core 1",
    "core 2":        "CPU Core 2",
    "core 3":        "CPU Core 3",
    "core 4":        "CPU Core 4",
    "core 5":        "CPU Core 5",
    "core 6":        "CPU Core 6",
    "core 7":        "CPU Core 7",
    "core 8":        "CPU Core 8",
    "core 9":        "CPU Core 9",
    "core 10":       "CPU Core 10",
    "core 11":       "CPU Core 11",
    # AMD CPU
    "tctl":          "CPU Control Temp",
    "tdie":          "CPU Die Temp",
    "tccd1":         "CPU Core Complex #1",
    "tccd2":         "CPU Core Complex #2",
    # AMD / generic GPU
    "edge":          "GPU Edge Temp",
    "junction":      "GPU Hotspot",
    "hotspot":       "GPU Hotspot",
    "mem":           "GPU Memory Temp",
    "vrmem":         "GPU Memory VRM",
    # NVMe
    "composite":     "NVMe Drive Temp",
    "sensor 1":      "NVMe Sensor 1",
    "sensor 2":      "NVMe Sensor 2",
    # ITE / Nuvoton (HP Victus)
    "systin":        "System Board Temp",
    "cputin":        "CPU Input Temp",
    "auxtin0":       "Auxiliary Temp 1",
    "auxtin1":       "Auxiliary Temp 2",
    "auxtin2":       "Auxiliary Temp 3",
    "auxtin3":       "Auxiliary Temp 4",
    # ACPI
    "acpitz":        "ACPI Thermal Zone",
}


def _friendly_temp_label(raw: str, device_name: str) -> str:
    mapped = _TEMP_LABEL_MAP.get(raw.lower())
    if mapped:
        return mapped
    # Numeric fallback
    if raw.lower().startswith("temp"):
        rest = raw[4:].strip()
        return f"Temperature {rest}" if rest else "Temperature"
    return raw.title()


def _friendly_fan_label(index: int, raw: str, device_name: str) -> str:
    """HP Victus convention: fan1 = CPU fan, fan2 = GPU fan."""
    raw_lower = raw.lower()
    # If the kernel already gave a meaningful (non-generic) label, use it
    generic = {f"fan {index}", f"fan{index}"}
    if raw_lower not in generic:
        if "cpu" in raw_lower:
            return f"CPU Fan"
        if "gpu" in raw_lower:
            return f"GPU Fan"
        return raw.title()
    _FAN_NAMES = {1: "CPU Fan", 2: "GPU Fan"}
    return _FAN_NAMES.get(index, f"System Fan {index}")


@dataclass
class TempSensor:
    hwmon_path: str
    index: int
    label: str
    raw_label: str = ""
    celsius: float = 0.0

    def refresh(self) -> None:
        raw = _read(f"{self.hwmon_path}/temp{self.index}_input")
        if raw is not None:
            self.celsius = int(raw) / 1000.0


@dataclass
class FanSensor:
    hwmon_path: str
    index: int
    label: str
    raw_label: str = ""
    rpm: int = 0
    # --- standard sysfs PWM (pwm{idx}) ---
    has_pwm: bool = False
    pwm_writable: bool = False
    pwm_value: int = 128    # 0–255
    pwm_enable: int = 2     # 0 = disabled, 1 = manual, 2 = auto
    # --- HP-style target-RPM (fan{idx}_target + pwm1_enable) ---
    has_target: bool = False
    target_writable: bool = False
    target_rpm: int = -1    # -1 = auto/not set
    fan_max: int = 5000
    enable_path: str = ""   # shared pwm*_enable path (may cover all fans)

    # ---- read ----

    def refresh(self) -> None:
        raw = _read(f"{self.hwmon_path}/fan{self.index}_input")
        if raw is not None:
            self.rpm = int(raw)
        if self.has_pwm:
            v = _read(f"{self.hwmon_path}/pwm{self.index}")
            if v is not None:
                self.pwm_value = int(v)
            e = _read(f"{self.hwmon_path}/pwm{self.index}_enable")
            if e is not None:
                self.pwm_enable = int(e)
        elif self.has_target:
            tv = _read(f"{self.hwmon_path}/fan{self.index}_target")
            if tv is not None:
                self.target_rpm = int(tv)
            ep = self.enable_path or f"{self.hwmon_path}/pwm1_enable"
            ev = _read(ep)
            if ev is not None:
                self.pwm_enable = int(ev)

    @property
    def pwm_percent(self) -> float:
        return (self.pwm_value / 255.0) * 100.0

    # ---- write: standard PWM ----

    def set_manual(self) -> bool:
        if not self.has_pwm or not self.pwm_writable:
            return False
        ok = _write(f"{self.hwmon_path}/pwm{self.index}_enable", "1")
        if ok:
            self.pwm_enable = 1
        return ok

    def set_auto(self) -> bool:
        if not self.has_pwm or not self.pwm_writable:
            return False
        ok = _write(f"{self.hwmon_path}/pwm{self.index}_enable", "2")
        if ok:
            self.pwm_enable = 2
        return ok

    def set_pwm(self, value: int) -> bool:
        """Write PWM duty cycle (0–255)."""
        if not self.has_pwm or not self.pwm_writable:
            return False
        value = max(0, min(255, value))
        ok = _write(f"{self.hwmon_path}/pwm{self.index}", str(value))
        if ok:
            self.pwm_value = value
        return ok

    # ---- write: HP target-RPM ----

    def set_manual_target(self) -> bool:
        """Switch to manual mode via shared pwm*_enable = 1."""
        if not self.has_target:
            return False
        ep = self.enable_path or f"{self.hwmon_path}/pwm1_enable"
        ok = _write(ep, "1")
        if ok:
            self.pwm_enable = 1
        return ok

    def set_auto_target(self) -> bool:
        """Switch to automatic mode via shared pwm*_enable = 2.
        Also resets fan*_target to 0 so the driver does not keep a stale value.
        """
        if not self.has_target:
            return False
        ep = self.enable_path or f"{self.hwmon_path}/pwm1_enable"
        # Reset target first so the BIOS curve takes over cleanly
        _write(f"{self.hwmon_path}/fan{self.index}_target", "0")
        ok = _write(ep, "2")
        if ok:
            self.pwm_enable = 2
            self.target_rpm = 0
        return ok

    def set_target(self, rpm: int) -> bool:
        """Write a target RPM for this fan (HP hp_wmi driver)."""
        if not self.has_target or not self.target_writable:
            return False
        rpm = max(0, min(rpm, self.fan_max))
        ok = _write(f"{self.hwmon_path}/fan{self.index}_target", str(rpm))
        if ok:
            self.target_rpm = rpm
        return ok


@dataclass
class HwmonDevice:
    path: str
    name: str
    temps: list[TempSensor] = field(default_factory=list)
    fans: list[FanSensor] = field(default_factory=list)

    def refresh(self) -> None:
        for t in self.temps:
            t.refresh()
        for f in self.fans:
            f.refresh()


@dataclass
class NvidiaSensor:
    """NVIDIA GPU temperature polled via nvidia-smi."""
    label: str = "NVIDIA GPU"
    celsius: float = 0.0
    available: bool = False

    def refresh(self) -> None:
        try:
            result = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                val = result.stdout.strip().splitlines()[0].strip()
                self.celsius = float(val)
                self.available = True
        except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
            self.available = False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _pwm_writable(hwmon_path: str, index: int) -> bool:
    path = f"{hwmon_path}/pwm{index}"
    return os.path.exists(path) and os.access(path, os.W_OK)


def discover() -> tuple[list[HwmonDevice], NvidiaSensor]:
    """
    Scan /sys/class/hwmon and return all devices that expose fans or
    temperatures, plus an NvidiaSensor (queried once on startup).
    """
    devices: list[HwmonDevice] = []

    for hwmon_link in sorted(glob.glob(f"{HWMON_BASE}/hwmon*")):
        real = os.path.realpath(hwmon_link)
        name = _read(f"{real}/name") or os.path.basename(real)
        device = HwmonDevice(path=real, name=name)

        # --- temperature sensors ---
        for tf in sorted(glob.glob(f"{real}/temp*_input")):
            basename = os.path.basename(tf)
            idx = int(basename[4:].replace("_input", ""))
            raw_lbl = _read(f"{real}/temp{idx}_label") or f"Temp {idx}"
            friendly = _friendly_temp_label(raw_lbl, name)
            raw = _read(tf) or "0"
            device.temps.append(
                TempSensor(
                    hwmon_path=real, index=idx,
                    label=friendly, raw_label=raw_lbl,
                    celsius=int(raw) / 1000.0,
                )
            )

        # --- fan sensors ---
        for ff in sorted(glob.glob(f"{real}/fan*_input")):
            basename = os.path.basename(ff)
            idx = int(basename[3:].replace("_input", ""))
            raw_lbl = _read(f"{real}/fan{idx}_label") or f"Fan {idx}"
            label = _friendly_fan_label(idx, raw_lbl, name)
            raw = _read(ff) or "0"

            has_pwm = os.path.exists(f"{real}/pwm{idx}")
            writable = _pwm_writable(real, idx)
            pwm_value, pwm_enable = 128, 2
            if has_pwm:
                pv = _read(f"{real}/pwm{idx}") or "128"
                pwm_value = int(pv)
                pe = _read(f"{real}/pwm{idx}_enable") or "2"
                pwm_enable = int(pe)

            # HP-style target-RPM control (hp_wmi driver: fan*_target)
            has_target = (not has_pwm
                          and os.path.exists(f"{real}/fan{idx}_target"))
            target_writable = (has_target
                               and os.access(f"{real}/fan{idx}_target", os.W_OK))
            target_rpm, fan_max, enable_path = -1, 5000, ""
            if has_target:
                tv = _read(f"{real}/fan{idx}_target") or "-1"
                target_rpm = int(tv)
                mv = _read(f"{real}/fan{idx}_max") or "5000"
                fan_max = int(mv)
                # Shared enable file: try pwm1_enable first (covers all fans)
                for ep_candidate in (
                    f"{real}/pwm1_enable",
                    f"{real}/pwm{idx}_enable",
                ):
                    if os.path.exists(ep_candidate):
                        enable_path = ep_candidate
                        break
                # Read current enable state
                ev = _read(enable_path) if enable_path else None
                if ev is not None:
                    pwm_enable = int(ev)

            device.fans.append(
                FanSensor(
                    hwmon_path=real, index=idx,
                    label=label, raw_label=raw_lbl,
                    rpm=int(raw), has_pwm=has_pwm, pwm_writable=writable,
                    pwm_value=pwm_value, pwm_enable=pwm_enable,
                    has_target=has_target, target_writable=target_writable,
                    target_rpm=target_rpm, fan_max=fan_max,
                    enable_path=enable_path,
                )
            )

        if device.temps or device.fans:
            devices.append(device)

    nvidia = NvidiaSensor()
    nvidia.refresh()
    return devices, nvidia
