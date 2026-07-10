#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
from ctypes import CDLL
from ctypes.util import find_library

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


PID_FILE = "/tmp/waybar-power-menu.pid"
ACTIONS = [
    ("Desligar", ["systemctl", "poweroff"], "system-shutdown-symbolic", "danger"),
    ("Reiniciar", ["systemctl", "reboot"], "system-reboot-symbolic", None),
    ("Suspender", ["systemctl", "suspend"], "weather-clear-night-symbolic", None),
    ("Bloquear", ["swaylock", "-f"], "changes-prevent-symbolic", None),
    ("Sair", ["niri", "msg", "action", "quit"], "system-log-out-symbolic", None),
]


def toggle_existing_instance():
    if not os.path.exists(PID_FILE):
        return

    try:
        with open(PID_FILE, "r", encoding="utf-8") as pid_file:
            pid = int(pid_file.read().strip())
        os.kill(pid, signal.SIGUSR1)
        sys.exit(0)
    except (OSError, ValueError):
        try:
            os.unlink(PID_FILE)
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

        for label, command, icon_name, style_class in ACTIONS:
            button = Gtk.Button()
            button.add_css_class("power-action")
            if style_class is not None:
                button.add_css_class(style_class)
            button.connect("clicked", self.run_action, command)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_valign(Gtk.Align.CENTER)

            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(26)
            icon.add_css_class("action-icon")

            text = Gtk.Label(label=label)
            text.set_xalign(0)
            text.set_hexpand(True)
            text.add_css_class("action-label")

            row.append(icon)
            row.append(text)
            button.set_child(row)
            root.append(button)

        return root

    def run_action(self, _button, command):
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

    def animate_opacity(self, start, end, done=None):
        duration_ms = 160
        frame_ms = 16
        steps = max(1, duration_ms // frame_ms)
        current_step = 0

        def ease_out_cubic(value):
            return 1 - pow(1 - value, 3)

        def tick():
            nonlocal current_step
            current_step += 1
            progress = min(1.0, current_step / steps)
            eased = ease_out_cubic(progress)
            opacity = start + (end - start) * eased
            self.window.set_opacity(opacity)

            if progress >= 1.0:
                self.animation_source = None
                self.window.set_opacity(end)
                if done is not None:
                    done()
                return False
            return True

        self.animation_source = GLib.timeout_add(frame_ms, tick)

    def quit_from_signal(self):
        self.cleanup_pid()
        self.quit()
        return False

    def configure_layer_shell(self):
        if Gtk4LayerShell is None:
            return

        Gtk4LayerShell.init_for_window(self.window)
        Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, False)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.BOTTOM, False)
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
        for edge in (
            Gtk4LayerShell.Edge.TOP,
            Gtk4LayerShell.Edge.BOTTOM,
            Gtk4LayerShell.Edge.LEFT,
            Gtk4LayerShell.Edge.RIGHT,
        ):
            Gtk4LayerShell.set_anchor(self.click_shield, edge, True)
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

    def on_close(self, _window):
        self.hide_popup()
        return True

    def write_pid(self):
        with open(PID_FILE, "w", encoding="utf-8") as pid_file:
            pid_file.write(str(os.getpid()))

    def cleanup_pid(self):
        try:
            os.unlink(PID_FILE)
        except OSError:
            pass

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
