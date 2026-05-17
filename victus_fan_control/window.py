"""
Main application window — GTK 4 + libadwaita.
"""

from __future__ import annotations

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from . import hwmon


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = b"""
/* ---- Temperature level bar ---- */
levelbar.temp-bar block.low  { background-color: #33d17a; border-radius: 4px; }
levelbar.temp-bar block.high { background-color: #e5a50a; border-radius: 4px; }
levelbar.temp-bar block.full { background-color: #e01b24; border-radius: 4px; }
levelbar.temp-bar block      { min-height: 8px; min-width: 5px;
                                border-radius: 4px; margin: 1px; }

/* ---- RPM level bar ---- */
levelbar.rpm-bar block       { background-color: #3584e4;
                                border-radius: 4px; min-height: 6px;
                                min-width: 4px; margin: 1px; }
levelbar.rpm-bar block.high  { background-color: #e5a50a; border-radius: 4px; }
levelbar.rpm-bar block.full  { background-color: #e01b24; border-radius: 4px; }

/* ---- Row prefix icons ---- */
.row-icon { opacity: 0.75; margin-end: 4px; }

/* ---- Temperature value label ---- */
.temp-normal   { color: #33d17a; }
.temp-warning  { color: #e5a50a; }
.temp-critical { color: #e01b24; font-weight: bold; }
.temp-value    { font-feature-settings: "tnum"; font-size: 1.05em; }

/* ---- RPM value label ---- */
.rpm-value   { font-feature-settings: "tnum"; }
.rpm-active  { color: #3584e4; }
.rpm-stopped { color: #9a9996; }

/* ---- Fan status dot ---- */
.dot-active { color: #33d17a; }
.dot-idle   { color: #9a9996; }
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_RPM = 5500.0  # Typical HP Victus max fan RPM


def _temp_icon(label: str) -> str:
    l = label.lower()
    if "cpu" in l:                    return "computer-symbolic"
    if "gpu" in l or "nvidia" in l:   return "video-display-symbolic"
    if "nvme" in l or "drive" in l:   return "drive-harddisk-symbolic"
    return "temperature-symbolic"


def _fan_icon(label: str) -> str:
    l = label.lower()
    if "cpu" in l: return "computer-symbolic"
    if "gpu" in l: return "video-display-symbolic"
    return "emblem-synchronizing-symbolic"


def _make_icon(icon_name: str) -> Gtk.Image:
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_icon_size(Gtk.IconSize.NORMAL)
    img.set_valign(Gtk.Align.CENTER)
    img.add_css_class("row-icon")
    return img


def _subtitle(raw: str, device: str) -> str:
    if raw and raw != device:
        return f"{raw}  \u00b7  {device}"
    return device


# ---------------------------------------------------------------------------
# Temperature rows
# ---------------------------------------------------------------------------

class TempRow(Adw.ActionRow):
    _WARN_C = 70.0
    _CRIT_C = 85.0
    _MAX_C  = 100.0

    def __init__(self, sensor: hwmon.TempSensor, device_name: str) -> None:
        super().__init__()
        self._sensor = sensor
        self.set_title(sensor.label)
        self.set_subtitle(_subtitle(sensor.raw_label, device_name))
        self.add_prefix(_make_icon(_temp_icon(sensor.label)))

        self._bar = Gtk.LevelBar()
        self._bar.add_css_class("temp-bar")
        self._bar.set_min_value(0)
        self._bar.set_max_value(self._MAX_C)
        self._bar.set_size_request(120, -1)
        self._bar.set_valign(Gtk.Align.CENTER)
        self._bar.remove_offset_value("low")
        self._bar.remove_offset_value("high")
        self._bar.remove_offset_value("full")
        self._bar.remove_offset_value("middle")
        self._bar.add_offset_value("low",  self._WARN_C)
        self._bar.add_offset_value("high", self._CRIT_C)
        self._bar.add_offset_value("full", self._MAX_C)

        self._lbl = Gtk.Label()
        self._lbl.set_width_chars(9)
        self._lbl.set_xalign(1.0)
        self._lbl.add_css_class("temp-value")

        suffix = Gtk.Box(spacing=10)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.append(self._bar)
        suffix.append(self._lbl)
        self.add_suffix(suffix)
        self.update()

    def update(self) -> None:
        c = self._sensor.celsius
        self._lbl.set_text(f"{c:.1f} \u00b0C")
        self._bar.set_value(min(c, self._MAX_C))
        for cls in ("temp-normal", "temp-warning", "temp-critical"):
            self._lbl.remove_css_class(cls)
        if c >= self._CRIT_C:
            self._lbl.add_css_class("temp-critical")
        elif c >= self._WARN_C:
            self._lbl.add_css_class("temp-warning")
        else:
            self._lbl.add_css_class("temp-normal")


class NvidiaTempRow(Adw.ActionRow):
    _WARN_C = 70.0
    _CRIT_C = 85.0
    _MAX_C  = 100.0

    def __init__(self, sensor: hwmon.NvidiaSensor) -> None:
        super().__init__()
        self._sensor = sensor
        self.set_title("NVIDIA GPU Temp")
        self.set_subtitle("GPU Temperature  \u00b7  NVIDIA")
        self.add_prefix(_make_icon("video-display-symbolic"))

        self._bar = Gtk.LevelBar()
        self._bar.add_css_class("temp-bar")
        self._bar.set_min_value(0)
        self._bar.set_max_value(self._MAX_C)
        self._bar.set_size_request(120, -1)
        self._bar.set_valign(Gtk.Align.CENTER)
        self._bar.remove_offset_value("low")
        self._bar.remove_offset_value("high")
        self._bar.remove_offset_value("full")
        self._bar.remove_offset_value("middle")
        self._bar.add_offset_value("low",  self._WARN_C)
        self._bar.add_offset_value("high", self._CRIT_C)
        self._bar.add_offset_value("full", self._MAX_C)

        self._lbl = Gtk.Label()
        self._lbl.set_width_chars(9)
        self._lbl.set_xalign(1.0)
        self._lbl.add_css_class("temp-value")

        suffix = Gtk.Box(spacing=10)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.append(self._bar)
        suffix.append(self._lbl)
        self.add_suffix(suffix)
        self.update()

    def update(self) -> None:
        c = self._sensor.celsius
        self._lbl.set_text(f"{c:.1f} \u00b0C")
        self._bar.set_value(min(c, self._MAX_C))
        for cls in ("temp-normal", "temp-warning", "temp-critical"):
            self._lbl.remove_css_class(cls)
        if c >= self._CRIT_C:
            self._lbl.add_css_class("temp-critical")
        elif c >= self._WARN_C:
            self._lbl.add_css_class("temp-warning")
        else:
            self._lbl.add_css_class("temp-normal")


# ---------------------------------------------------------------------------
# Fan rows
# ---------------------------------------------------------------------------

def _rpm_dot(rpm: int) -> tuple[str, str]:
    return "\u25cf", "dot-active" if rpm > 0 else "dot-idle"


class FanDisplayRow(Adw.ActionRow):
    """Fan row without any control (read-only RPM display)."""

    def __init__(self, fan: hwmon.FanSensor, device_name: str) -> None:
        super().__init__()
        self._fan = fan
        self.set_title(fan.label)
        self.set_subtitle(_subtitle(fan.raw_label, device_name))
        self.add_prefix(_make_icon(_fan_icon(fan.label)))

        self._dot = Gtk.Label()
        self._dot.set_valign(Gtk.Align.CENTER)

        self._bar = Gtk.LevelBar()
        self._bar.add_css_class("rpm-bar")
        self._bar.set_min_value(0)
        self._bar.set_max_value(_MAX_RPM)
        self._bar.set_size_request(100, -1)
        self._bar.set_valign(Gtk.Align.CENTER)
        self._bar.remove_offset_value("low")
        self._bar.remove_offset_value("high")
        self._bar.remove_offset_value("full")
        self._bar.remove_offset_value("middle")
        self._bar.add_offset_value("high", 4000)
        self._bar.add_offset_value("full", _MAX_RPM)

        self._rpm_lbl = Gtk.Label()
        self._rpm_lbl.add_css_class("rpm-value")
        self._rpm_lbl.set_width_chars(11)
        self._rpm_lbl.set_xalign(1.0)

        suffix = Gtk.Box(spacing=8)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.append(self._dot)
        suffix.append(self._bar)
        suffix.append(self._rpm_lbl)
        self.add_suffix(suffix)
        self.update()

    def update(self) -> None:
        rpm = self._fan.rpm
        self._rpm_lbl.set_text(f"{rpm:,} RPM")
        self._bar.set_value(min(rpm, _MAX_RPM))
        dot_char, dot_cls = _rpm_dot(rpm)
        self._dot.set_text(dot_char)
        for cls in ("dot-active", "dot-idle"):
            self._dot.remove_css_class(cls)
        self._dot.add_css_class(dot_cls)
        for cls in ("rpm-active", "rpm-stopped"):
            self._rpm_lbl.remove_css_class(cls)
        self._rpm_lbl.add_css_class("rpm-active" if rpm > 0 else "rpm-stopped")


class FanTargetRow(Adw.ExpanderRow):
    """
    Fan row with HP-style target-RPM control.
    Uses fan{idx}_target (RPM value) and a shared pwm1_enable (auto/manual).
    """

    def __init__(self, fan: hwmon.FanSensor, device_name: str) -> None:
        super().__init__()
        self._fan = fan
        self._guard = False

        self.set_title(fan.label)
        self.set_subtitle(_subtitle(fan.raw_label, device_name))
        self.set_show_enable_switch(False)
        self.add_prefix(_make_icon(_fan_icon(fan.label)))

        self._dot = Gtk.Label()
        self._dot.set_valign(Gtk.Align.CENTER)

        self._bar = Gtk.LevelBar()
        self._bar.add_css_class("rpm-bar")
        self._bar.set_min_value(0)
        self._bar.set_max_value(fan.fan_max or _MAX_RPM)
        self._bar.set_size_request(100, -1)
        self._bar.set_valign(Gtk.Align.CENTER)
        self._bar.remove_offset_value("low")
        self._bar.remove_offset_value("high")
        self._bar.remove_offset_value("full")
        self._bar.remove_offset_value("middle")
        self._bar.add_offset_value("high", (fan.fan_max or _MAX_RPM) * 0.72)
        self._bar.add_offset_value("full", fan.fan_max or _MAX_RPM)

        self._rpm_lbl = Gtk.Label()
        self._rpm_lbl.add_css_class("rpm-value")
        self._rpm_lbl.set_width_chars(11)
        self._rpm_lbl.set_xalign(1.0)

        suffix = Gtk.Box(spacing=8)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.append(self._dot)
        suffix.append(self._bar)
        suffix.append(self._rpm_lbl)
        self.add_suffix(suffix)

        self._build_controls()
        self.update()

    def _build_controls(self) -> None:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            margin_start=16,
            margin_end=16,
            margin_top=12,
            margin_bottom=12,
        )

        # Auto / Manual toggle
        mode_box = Gtk.Box(spacing=10)
        mode_box.set_halign(Gtk.Align.CENTER)

        auto_lbl   = Gtk.Label(label="Automatic")
        manual_lbl = Gtk.Label(label="Manual")
        auto_lbl.add_css_class("dim-label")
        manual_lbl.add_css_class("dim-label")

        self._mode_switch = Gtk.Switch()
        self._mode_switch.set_tooltip_text(
            "OFF \u2192 BIOS controls both fans automatically\n"
            "ON  \u2192 set a target RPM with the slider below"
        )
        self._mode_switch.set_valign(Gtk.Align.CENTER)

        mode_box.append(auto_lbl)
        mode_box.append(self._mode_switch)
        mode_box.append(manual_lbl)
        box.append(mode_box)

        # Target RPM slider
        max_rpm = self._fan.fan_max or 5000
        slider_row = Gtk.Box(spacing=10)
        speed_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        speed_icon.set_valign(Gtk.Align.CENTER)
        speed_icon.add_css_class("dim-label")

        self._slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, max_rpm, 100
        )
        self._slider.set_hexpand(True)
        self._slider.set_draw_value(True)
        self._slider.set_format_value_func(lambda _s, v: f"{v:.0f} RPM")
        step = max_rpm // 4
        for mark in range(0, max_rpm + 1, step):
            self._slider.add_mark(mark, Gtk.PositionType.BOTTOM, str(mark))

        slider_row.append(speed_icon)
        slider_row.append(self._slider)
        box.append(slider_row)

        # Note about shared control
        note = Gtk.Label()
        note.set_text("\u2139  Both fans switch Auto/Manual together (hardware limitation).")
        note.set_xalign(0)
        note.add_css_class("caption")
        note.add_css_class("dim-label")
        box.append(note)

        # Permission warning
        self._warn_lbl = Gtk.Label()
        self._warn_lbl.set_wrap(True)
        self._warn_lbl.set_xalign(0)
        self._warn_lbl.add_css_class("caption")
        self._warn_lbl.add_css_class("warning")
        box.append(self._warn_lbl)

        inner = Gtk.ListBoxRow()
        inner.set_child(box)
        inner.set_activatable(False)
        inner.set_selectable(False)
        self.add_row(inner)

        self._mode_switch.connect("notify::active", self._on_mode_toggled)
        self._slider.connect("value-changed", self._on_speed_changed)

    def _on_mode_toggled(self, switch: Gtk.Switch, _pspec) -> None:
        if self._guard:
            return
        if switch.get_active():
            self._fan.set_manual_target()
        else:
            self._fan.set_auto_target()
        self._refresh_sensitivity()

    def _on_speed_changed(self, scale: Gtk.Scale) -> None:
        if self._guard:
            return
        self._fan.set_target(int(scale.get_value()))

    def _refresh_sensitivity(self) -> None:
        is_manual    = self._fan.pwm_enable == 1
        can_write    = self._fan.target_writable
        enable_ok    = bool(self._fan.enable_path
                            and os.access(self._fan.enable_path, os.W_OK))

        self._slider.set_sensitive(is_manual and can_write)
        self._mode_switch.set_sensitive(enable_ok)

        if not can_write or not enable_ok:
            self._warn_lbl.set_text(
                "\u26a0  No write permission for fan control files.\n"
                "Run install.sh as root to enable fan control."
            )
            self._warn_lbl.set_visible(True)
        else:
            self._warn_lbl.set_visible(False)

    def update(self) -> None:
        rpm = self._fan.rpm
        self._rpm_lbl.set_text(f"{rpm:,} RPM")
        self._bar.set_value(min(rpm, self._fan.fan_max or _MAX_RPM))
        dot_char, dot_cls = _rpm_dot(rpm)
        self._dot.set_text(dot_char)
        for cls in ("dot-active", "dot-idle"):
            self._dot.remove_css_class(cls)
        self._dot.add_css_class(dot_cls)
        for cls in ("rpm-active", "rpm-stopped"):
            self._rpm_lbl.remove_css_class(cls)
        self._rpm_lbl.add_css_class("rpm-active" if rpm > 0 else "rpm-stopped")

        self._guard = True
        is_manual = self._fan.pwm_enable == 1
        if self._mode_switch.get_active() != is_manual:
            self._mode_switch.set_active(is_manual)
        if self._fan.target_rpm >= 0:
            self._slider.set_value(self._fan.target_rpm)
        self._guard = False
        self._refresh_sensitivity()


class FanControlRow(Adw.ExpanderRow):
    """Fan row with standard sysfs PWM control (pwm{idx})."""

    def __init__(self, fan: hwmon.FanSensor, device_name: str) -> None:
        super().__init__()
        self._fan = fan
        self._guard = False

        self.set_title(fan.label)
        self.set_subtitle(_subtitle(fan.raw_label, device_name))
        self.set_show_enable_switch(False)
        self.add_prefix(_make_icon(_fan_icon(fan.label)))

        self._dot = Gtk.Label()
        self._dot.set_valign(Gtk.Align.CENTER)

        self._bar = Gtk.LevelBar()
        self._bar.add_css_class("rpm-bar")
        self._bar.set_min_value(0)
        self._bar.set_max_value(_MAX_RPM)
        self._bar.set_size_request(100, -1)
        self._bar.set_valign(Gtk.Align.CENTER)
        self._bar.remove_offset_value("low")
        self._bar.remove_offset_value("high")
        self._bar.remove_offset_value("full")
        self._bar.remove_offset_value("middle")
        self._bar.add_offset_value("high", 4000)
        self._bar.add_offset_value("full", _MAX_RPM)

        self._rpm_lbl = Gtk.Label()
        self._rpm_lbl.add_css_class("rpm-value")
        self._rpm_lbl.set_width_chars(11)
        self._rpm_lbl.set_xalign(1.0)

        suffix = Gtk.Box(spacing=8)
        suffix.set_valign(Gtk.Align.CENTER)
        suffix.append(self._dot)
        suffix.append(self._bar)
        suffix.append(self._rpm_lbl)
        self.add_suffix(suffix)

        self._build_controls()
        self.update()

    def _build_controls(self) -> None:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            margin_start=16,
            margin_end=16,
            margin_top=12,
            margin_bottom=12,
        )

        # Mode toggle
        mode_box = Gtk.Box(spacing=10)
        mode_box.set_halign(Gtk.Align.CENTER)

        auto_lbl   = Gtk.Label(label="Automatic")
        manual_lbl = Gtk.Label(label="Manual")
        auto_lbl.add_css_class("dim-label")
        manual_lbl.add_css_class("dim-label")

        self._mode_switch = Gtk.Switch()
        self._mode_switch.set_tooltip_text(
            "OFF \u2192 system controls fan speed automatically\n"
            "ON  \u2192 set fan speed manually with the slider"
        )
        self._mode_switch.set_valign(Gtk.Align.CENTER)

        mode_box.append(auto_lbl)
        mode_box.append(self._mode_switch)
        mode_box.append(manual_lbl)
        box.append(mode_box)

        # Speed slider
        slider_row = Gtk.Box(spacing=10)
        speed_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        speed_icon.set_valign(Gtk.Align.CENTER)
        speed_icon.add_css_class("dim-label")

        self._slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._slider.set_hexpand(True)
        self._slider.set_draw_value(True)
        self._slider.set_format_value_func(lambda _s, v: f"{v:.0f} %")
        for mark in (0, 25, 50, 75, 100):
            self._slider.add_mark(mark, Gtk.PositionType.BOTTOM, f"{mark} %")

        slider_row.append(speed_icon)
        slider_row.append(self._slider)
        box.append(slider_row)

        # Warning label
        self._warn_lbl = Gtk.Label()
        self._warn_lbl.set_wrap(True)
        self._warn_lbl.set_xalign(0)
        self._warn_lbl.add_css_class("caption")
        self._warn_lbl.add_css_class("warning")
        box.append(self._warn_lbl)

        inner = Gtk.ListBoxRow()
        inner.set_child(box)
        inner.set_activatable(False)
        inner.set_selectable(False)
        self.add_row(inner)

        self._mode_switch.connect("notify::active", self._on_mode_toggled)
        self._slider.connect("value-changed", self._on_speed_changed)

    def _on_mode_toggled(self, switch: Gtk.Switch, _pspec) -> None:
        if self._guard:
            return
        if switch.get_active():
            self._fan.set_manual()
        else:
            self._fan.set_auto()
        self._refresh_sensitivity()

    def _on_speed_changed(self, scale: Gtk.Scale) -> None:
        if self._guard:
            return
        self._fan.set_pwm(int((scale.get_value() / 100.0) * 255))

    def _refresh_sensitivity(self) -> None:
        is_manual = self._fan.pwm_enable == 1
        can_write = self._fan.pwm_writable
        self._slider.set_sensitive(is_manual and can_write)
        self._mode_switch.set_sensitive(can_write)
        if not can_write:
            self._warn_lbl.set_text(
                "\u26a0  No write permission for PWM files.\n"
                "Run install.sh as root to enable fan control."
            )
            self._warn_lbl.set_visible(True)
        else:
            self._warn_lbl.set_visible(False)

    def update(self) -> None:
        rpm = self._fan.rpm
        self._rpm_lbl.set_text(f"{rpm:,} RPM")
        self._bar.set_value(min(rpm, _MAX_RPM))
        dot_char, dot_cls = _rpm_dot(rpm)
        self._dot.set_text(dot_char)
        for cls in ("dot-active", "dot-idle"):
            self._dot.remove_css_class(cls)
        self._dot.add_css_class(dot_cls)
        for cls in ("rpm-active", "rpm-stopped"):
            self._rpm_lbl.remove_css_class(cls)
        self._rpm_lbl.add_css_class("rpm-active" if rpm > 0 else "rpm-stopped")

        self._guard = True
        is_manual = self._fan.pwm_enable == 1
        if self._mode_switch.get_active() != is_manual:
            self._mode_switch.set_active(is_manual)
        self._slider.set_value(self._fan.pwm_percent)
        self._guard = False
        self._refresh_sensitivity()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application)
        self.set_title("Victus Fan Control")
        self.set_default_size(600, 760)

        self._devices: list[hwmon.HwmonDevice] = []
        self._nvidia:  hwmon.NvidiaSensor | None = None
        self._temp_rows: list[TempRow | NvidiaTempRow] = []
        self._fan_rows:  list[FanDisplayRow | FanControlRow] = []
        self._groups:    list[Adw.PreferencesGroup] = []

        self._apply_css()
        self._build_skeleton()
        self._load_hardware()
        GLib.timeout_add_seconds(2, self._tick)

    def _apply_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_skeleton(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self._spinner = Gtk.Spinner()
        header.pack_end(self._spinner)

        btn = Gtk.Button(icon_name="view-refresh-symbolic")
        btn.set_tooltip_text("Refresh now")
        btn.connect("clicked", lambda _: self._do_refresh())
        header.pack_end(btn)

        self._banner = Adw.Banner(
            title="Fan control requires elevated permissions \u2014 run install.sh first.",
            button_label="Dismiss",
        )
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked",
                             lambda _b: self._banner.set_revealed(False))
        toolbar_view.add_top_bar(self._banner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar_view.set_content(scroll)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        scroll.set_child(self._stack)

        empty = Adw.StatusPage()
        empty.set_title("No Sensors Detected")
        empty.set_description(
            "No hwmon sensors were found.\n\n"
            "Install lm-sensors and run:\n"
            "    sudo sensors-detect\n"
            "then reboot and relaunch this application."
        )
        empty.set_icon_name("dialog-warning-symbolic")
        self._stack.add_named(empty, "empty")

        self._page = Adw.PreferencesPage()
        self._stack.add_named(self._page, "content")

    def _load_hardware(self) -> None:
        self._devices, self._nvidia = hwmon.discover()
        self._populate_ui()

    def _populate_ui(self) -> None:
        self._temp_rows.clear()
        self._fan_rows.clear()
        for grp in self._groups:
            self._page.remove(grp)
        self._groups.clear()

        has_content = False
        needs_permission_banner = False

        # Temperatures
        temp_items: list[tuple[str, hwmon.TempSensor | hwmon.NvidiaSensor]] = []
        for dev in self._devices:
            for t in dev.temps:
                temp_items.append((dev.name, t))
        if self._nvidia and self._nvidia.available:
            temp_items.append(("NVIDIA", self._nvidia))

        if temp_items:
            has_content = True
            grp = Adw.PreferencesGroup()
            grp.set_title("Temperatures")
            grp.set_description(
                "Bar colour: Green = normal  \u2022  Yellow = warm (70 \u00b0C+)  \u2022  Red = critical (85 \u00b0C+)"
            )
            self._page.add(grp)
            self._groups.append(grp)
            for dev_name, sensor in temp_items:
                if isinstance(sensor, hwmon.NvidiaSensor):
                    row: TempRow | NvidiaTempRow = NvidiaTempRow(sensor)
                else:
                    row = TempRow(sensor, dev_name)
                grp.add(row)
                self._temp_rows.append(row)

        # Fans
        fan_items: list[tuple[str, hwmon.FanSensor]] = []
        for dev in self._devices:
            for f in dev.fans:
                fan_items.append((dev.name, f))

        if fan_items:
            has_content = True
            grp = Adw.PreferencesGroup()
            grp.set_title("Fans")
            grp.set_description(
                "\u25cf Green = spinning  \u25cf Gray = stopped (normal at low load)  \u2014  "
                "Expand a row to control speed manually."
            )
            self._page.add(grp)
            self._groups.append(grp)
            for dev_name, fan in fan_items:
                if fan.has_pwm:
                    frow: FanDisplayRow | FanControlRow | FanTargetRow = FanControlRow(fan, dev_name)
                    if not fan.pwm_writable:
                        needs_permission_banner = True
                elif fan.has_target:
                    frow = FanTargetRow(fan, dev_name)
                    if not fan.target_writable:
                        needs_permission_banner = True
                else:
                    frow = FanDisplayRow(fan, dev_name)
                grp.add(frow)
                self._fan_rows.append(frow)

        self._stack.set_visible_child_name("content" if has_content else "empty")
        self._banner.set_revealed(needs_permission_banner)

    def _do_refresh(self) -> None:
        self._spinner.start()
        for dev in self._devices:
            dev.refresh()
        if self._nvidia:
            self._nvidia.refresh()
        for row in self._temp_rows:
            row.update()
        for row in self._fan_rows:
            row.update()
        GLib.timeout_add(300, lambda: (self._spinner.stop(), False)[1])

    def _tick(self) -> bool:
        self._do_refresh()
        return GLib.SOURCE_CONTINUE
