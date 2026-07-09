#!/usr/bin/env python3
import calendar
import os
import signal
import sys
from ctypes import CDLL
from ctypes.util import find_library
from datetime import date

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


PID_FILE = "/tmp/waybar-calendar-popup.pid"
WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
MONTHS = [
    "",
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
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


class CalendarPopup(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.gabriel.WaybarCalendarPopup")
        self.today = date.today()
        self.year = self.today.year
        self.month = self.today.month
        self.visible = False
        self.window = None
        self.click_shield = None
        self.month_label = None
        self.grid = None

    def do_activate(self):
        self.hold()
        self.install_css()
        self.write_pid()
        GLibUnix.signal_add(
            GLib.PRIORITY_DEFAULT,
            signal.SIGUSR1,
            self.toggle,
        )
        GLibUnix.signal_add(
            GLib.PRIORITY_DEFAULT,
            signal.SIGTERM,
            self.quit_from_signal,
        )

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Calendario")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(360, 380)
        self.window.connect("close-request", self.on_close)
        self.configure_layer_shell()
        self.create_click_shield()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.add_css_class("calendar-shell")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("calendar-header")

        prev_button = Gtk.Button(label="‹")
        prev_button.add_css_class("nav-button")
        prev_button.connect("clicked", self.previous_month)

        self.month_label = Gtk.Label()
        self.month_label.set_hexpand(True)
        self.month_label.add_css_class("month-title")

        next_button = Gtk.Button(label="›")
        next_button.add_css_class("nav-button")
        next_button.connect("clicked", self.next_month)

        header.append(prev_button)
        header.append(self.month_label)
        header.append(next_button)

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        self.grid.add_css_class("calendar-grid")

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.add_css_class("calendar-footer")

        today_button = Gtk.Button(label="Hoje")
        today_button.add_css_class("today-button")
        today_button.connect("clicked", self.go_today)

        hint = Gtk.Label(label=self.today.strftime("%d/%m/%Y"))
        hint.set_hexpand(True)
        hint.set_xalign(0)
        hint.add_css_class("date-hint")

        footer.append(hint)
        footer.append(today_button)

        root.append(header)
        root.append(self.grid)
        root.append(footer)

        self.window.set_child(root)
        self.render_calendar()
        self.show_popup()

    def toggle(self):
        if self.visible:
            self.hide_popup()
        else:
            self.show_popup()
        return True

    def show_popup(self):
        self.visible = True
        if self.click_shield is not None:
            self.click_shield.present()
        self.window.present()

    def hide_popup(self):
        self.visible = False
        if self.click_shield is not None:
            self.click_shield.set_visible(False)
        self.window.set_visible(False)

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
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.LEFT, False)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.RIGHT, False)
        Gtk4LayerShell.set_anchor(self.window, Gtk4LayerShell.Edge.BOTTOM, False)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, 1)
        Gtk4LayerShell.set_keyboard_mode(
            self.window,
            Gtk4LayerShell.KeyboardMode.ON_DEMAND,
        )

    def create_click_shield(self):
        if Gtk4LayerShell is None:
            return

        self.click_shield = Gtk.ApplicationWindow(application=self)
        self.click_shield.set_title("Calendar click shield")
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

    def render_calendar(self):
        child = self.grid.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.grid.remove(child)
            child = next_child

        month_name = MONTHS[self.month]
        self.month_label.set_text(f"{month_name} {self.year}")

        for column, weekday in enumerate(WEEKDAYS):
            label = Gtk.Label(label=weekday)
            label.add_css_class("weekday")
            self.grid.attach(label, column, 0, 1, 1)

        month_matrix = calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month)
        for row, week in enumerate(month_matrix, start=1):
            for column, day in enumerate(week):
                button = Gtk.Button(label=str(day.day))
                button.add_css_class("day")

                if day.month != self.month:
                    button.add_css_class("outside-month")

                if day == self.today:
                    button.add_css_class("today")

                if day.weekday() >= 5:
                    button.add_css_class("weekend")

                self.grid.attach(button, column, row, 1, 1)

    def previous_month(self, _button):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self.render_calendar()

    def next_month(self, _button):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self.render_calendar()

    def go_today(self, _button):
        self.year = self.today.year
        self.month = self.today.month
        self.render_calendar()

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

        .calendar-shell {
            margin: 10px;
            padding: 18px;
            background: alpha(#111318, 0.96);
            color: #f4f6fb;
            border: 1px solid alpha(#ffffff, 0.10);
            border-radius: 18px;
        }

        .calendar-header {
            min-height: 38px;
        }

        .month-title {
            font-size: 18px;
            font-weight: 700;
        }

        .nav-button {
            min-width: 34px;
            min-height: 34px;
            padding: 0;
            border-radius: 999px;
            border: 1px solid alpha(#ffffff, 0.08);
            background: alpha(#ffffff, 0.07);
            color: #f4f6fb;
            font-size: 22px;
        }

        .nav-button:hover,
        .today-button:hover {
            background: alpha(#ffffff, 0.13);
        }

        .calendar-grid {
            margin-top: 2px;
        }

        .weekday {
            color: #9aa4b2;
            font-size: 12px;
            font-weight: 700;
        }

        .day {
            min-width: 40px;
            min-height: 38px;
            padding: 0;
            margin: 2px;
            border: 0;
            border-radius: 12px;
            background: transparent;
            color: #eef2f8;
            font-weight: 600;
        }

        .day:hover {
            background: alpha(#ffffff, 0.09);
        }

        .weekend {
            color: #8fc7ff;
        }

        .outside-month {
            color: #525b68;
        }

        .today {
            background: #d6ff62;
            color: #151712;
        }

        .today:hover {
            background: #e1ff83;
        }

        .calendar-footer {
            margin-top: 2px;
        }

        .date-hint {
            color: #9aa4b2;
            font-size: 13px;
        }

        .today-button {
            min-height: 32px;
            padding: 0 14px;
            border-radius: 999px;
            border: 1px solid alpha(#ffffff, 0.08);
            background: alpha(#ffffff, 0.07);
            color: #f4f6fb;
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
    app = CalendarPopup()
    exit_code = app.run(sys.argv)
    app.cleanup_pid()
    raise SystemExit(exit_code)
