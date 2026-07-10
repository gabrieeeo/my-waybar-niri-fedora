#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
from ctypes import CDLL
from ctypes.util import find_library
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import gi

GTK4_LAYER_SHELL_LIB = find_library("gtk4-layer-shell")
if GTK4_LAYER_SHELL_LIB:
    CDLL(GTK4_LAYER_SHELL_LIB)

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gdk, GLib, GLibUnix, Gtk

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
except (ImportError, ValueError):
    Gtk4LayerShell = None


PID_FILE = Path("/tmp/waybar-power-menu.pid")
ANIMATION_DURATION_MS = 160
ANIMATION_FRAME_MS = 16


@dataclass(frozen=True)
class PowerAction:
    label: str
    command: Sequence[str]
    icon_name: str
    css_class: str | None = None


ACTIONS = (
    PowerAction(
        "Desligar",
        ("systemctl", "poweroff"),
        "system-shutdown-symbolic",
        "danger",
    ),
    PowerAction("Reiniciar", ("systemctl", "reboot"), "system-reboot-symbolic"),
    PowerAction(
        "Suspender",
        ("/home/gabriel/.config/waybar/scripts/lock-and-suspend.sh",),
        "weather-clear-night-symbolic",
    ),
    PowerAction(
        "Bloquear",
        ("/home/gabriel/.config/waybar/scripts/lock-screen.sh",),
        "changes-prevent-symbolic",
    ),
    PowerAction("Sair", ("niri", "msg", "action", "quit"), "system-log-out-symbolic"),
)


def toggle_existing_instance():
    if not PID_FILE.exists():
        return

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGUSR1)
        sys.exit(0)
    except (OSError, ValueError):
        remove_pid_file()


def remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class PowerMenu(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.gabriel.WaybarPowerMenu")
        self.visible = False
        self.animation_source = None
        self.window = None
        self.click_shield = None

    def do_activate(self):
        self.hold()
        self.install_css()
        self.write_pid()
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.toggle)
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.quit_from_signal)

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Menu de energia")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(220, 260)
        self.window.connect("close-request", self.on_close)
        self.configure_layer_shell()
        self.create_click_shield()
        self.window.set_child(self.build_menu())
        self.show_popup()

    def build_menu(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.add_css_class("power-shell")

        for action in ACTIONS:
            root.append(self.create_action_button(action))

        return root

    def create_action_button(self, action: PowerAction) -> Gtk.Button:
        button = Gtk.Button()
        button.add_css_class("power-action")
        if action.css_class:
            button.add_css_class(action.css_class)
        button.connect("clicked", self.run_action, action.command)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name(action.icon_name)
        icon.set_pixel_size(26)
        icon.add_css_class("action-icon")

        label = Gtk.Label(label=action.label)
        label.set_xalign(0)
        label.set_hexpand(True)
        label.add_css_class("action-label")

        row.append(icon)
        row.append(label)
        button.set_child(row)
        return button

    def run_action(self, _button: Gtk.Button, command: Sequence[str]) -> None:
        subprocess.Popen(command)
        self.cleanup_pid()
        self.quit()

    def toggle(self):
        if self.visible:
            self.hide_popup()
        else:
            self.show_popup()
        return True

    def show_popup(self):
        self.stop_animation()
        self.visible = True
        if self.click_shield is not None:
            self.click_shield.present()
        self.window.set_opacity(0.0)
        self.window.present()
        self.animate_opacity(0.0, 1.0)

    def hide_popup(self):
        self.stop_animation()
        self.visible = False
        self.animate_opacity(1.0, 0.0, self.finish_hide)

    def finish_hide(self):
        if self.click_shield is not None:
            self.click_shield.set_visible(False)
        self.window.set_visible(False)

    def stop_animation(self):
        if self.animation_source is not None:
            GLib.source_remove(self.animation_source)
            self.animation_source = None

    def animate_opacity(
        self,
        start: float,
        end: float,
        done: Callable[[], None] | None = None,
    ) -> None:
        steps = max(1, ANIMATION_DURATION_MS // ANIMATION_FRAME_MS)
        current_step = 0

        def tick():
            nonlocal current_step
            current_step += 1
            progress = min(1.0, current_step / steps)
            eased = 1 - (1 - progress) ** 3
            opacity = start + (end - start) * eased
            self.window.set_opacity(opacity)

            if progress >= 1.0:
                self.animation_source = None
                self.window.set_opacity(end)
                if done is not None:
                    done()
                return False
            return True

        self.animation_source = GLib.timeout_add(ANIMATION_FRAME_MS, tick)

    def quit_from_signal(self):
        self.cleanup_pid()
        self.quit()
        return False

    def configure_layer_shell(self):
        if Gtk4LayerShell is None:
            return

        Gtk4LayerShell.init_for_window(self.window)
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        self.set_anchors(self.window, top=True, right=True)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, 1)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.RIGHT, 8)
        Gtk4LayerShell.set_keyboard_mode(
            self.window,
            Gtk4LayerShell.KeyboardMode.ON_DEMAND,
        )

    def create_click_shield(self):
        if Gtk4LayerShell is None:
            return

        self.click_shield = Gtk.ApplicationWindow(application=self)
        self.click_shield.set_title("Power menu click shield")
        self.click_shield.set_decorated(False)
        self.click_shield.add_css_class("click-shield")

        Gtk4LayerShell.init_for_window(self.click_shield)
        Gtk4LayerShell.set_layer(self.click_shield, Gtk4LayerShell.Layer.TOP)
        self.set_anchors(
            self.click_shield,
            top=True,
            right=True,
            bottom=True,
            left=True,
        )
        Gtk4LayerShell.set_exclusive_zone(self.click_shield, -1)
        Gtk4LayerShell.set_keyboard_mode(
            self.click_shield,
            Gtk4LayerShell.KeyboardMode.NONE,
        )

        shield_area = Gtk.Box()
        shield_area.set_hexpand(True)
        shield_area.set_vexpand(True)

        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_args: self.hide_popup())
        shield_area.add_controller(click)

        self.click_shield.set_child(shield_area)
        self.click_shield.set_visible(False)

    @staticmethod
    def set_anchors(window, **anchors: bool) -> None:
        edges = {
            "top": Gtk4LayerShell.Edge.TOP,
            "right": Gtk4LayerShell.Edge.RIGHT,
            "bottom": Gtk4LayerShell.Edge.BOTTOM,
            "left": Gtk4LayerShell.Edge.LEFT,
        }
        for name, edge in edges.items():
            Gtk4LayerShell.set_anchor(window, edge, anchors.get(name, False))

    def on_close(self, _window):
        self.hide_popup()
        return True

    def write_pid(self):
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    def cleanup_pid(self):
        remove_pid_file()

    def install_css(self):
        css = b"""
        window {
            background: transparent;
        }

        .click-shield {
            background: alpha(#000000, 0.01);
        }

        .power-shell {
            margin: 10px;
            padding: 10px;
            background: alpha(#18181b, 0.94);
            color: #f5f5f7;
            border: 1px solid alpha(#ffffff, 0.10);
            border-radius: 16px;
        }

        .power-action {
            min-width: 180px;
            min-height: 38px;
            padding: 0 12px;
            border: 0;
            border-radius: 11px;
            background: transparent;
            color: #f5f5f7;
        }

        .power-action:hover {
            background: alpha(#ffffff, 0.10);
        }

        .power-action.danger {
            color: #ff453a;
        }

        .power-action.danger:hover {
            background: alpha(#ff453a, 0.18);
            color: #ffffff;
        }

        .action-icon {
            color: inherit;
        }

        .action-label {
            color: inherit;
            font-size: 14px;
            font-weight: 700;
        }
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

if __name__ == "__main__":
    toggle_existing_instance()
    app = PowerMenu()
    exit_code = app.run(sys.argv)
    app.cleanup_pid()
    raise SystemExit(exit_code)
