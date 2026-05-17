"""
Victus Fan Control — application entry point.
"""

from __future__ import annotations

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from victus_fan_control.window import MainWindow  # noqa: E402


class VictusFanApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.victus.fancontrol")

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win is None:
            win = MainWindow(application=self)
        win.present()


def main() -> int:
    app = VictusFanApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
