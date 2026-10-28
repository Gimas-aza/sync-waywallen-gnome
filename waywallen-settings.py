#!/usr/bin/env python3
"""GNOME Settings portal with the exact wallpaper accent."""
from fnmatch import fnmatchcase
from pathlib import Path
import re
import sys

from gi.repository import Gio, GLib

BUS = 'org.freedesktop.impl.portal.desktop.waywallen'
GNOME = 'org.freedesktop.impl.portal.desktop.gnome'
OBJECT = '/org/freedesktop/portal/desktop'
INTERFACE = 'org.freedesktop.impl.portal.Settings'
APPEARANCE = 'org.freedesktop.appearance'
ACCENT = 'accent-color'
XML = '''<node><interface name="org.freedesktop.impl.portal.Settings">
  <method name="Read"><arg type="s" direction="in"/><arg type="s" direction="in"/>
    <arg type="v" direction="out"/></method>
  <method name="ReadAll"><arg type="as" direction="in"/>
    <arg type="a{sa{sv}}" direction="out"/></method>
  <signal name="SettingChanged"><arg type="s"/><arg type="s"/><arg type="v"/></signal>
  <property name="version" type="u" access="read"/>
</interface></node>'''


class Settings:
    def __init__(self, connection):
        self.connection = connection
        self.path = Path.home() / '.local/state/waywallen-colors/accent'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.accent = self.read_accent()
        self.info = Gio.DBusNodeInfo.new_for_xml(XML)
        self.registration = connection.register_object(
            OBJECT, self.info.interfaces[0], self.method,
            lambda *args: GLib.Variant('u', 0), None)
        self.subscription = connection.signal_subscribe(
            GNOME, INTERFACE, 'SettingChanged', OBJECT, None,
            Gio.DBusSignalFlags.NONE, self.gnome_changed)
        self.monitor = Gio.File.new_for_path(str(self.path.parent)).monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.monitor.connect('changed', self.file_changed)

    def read_accent(self):
        try:
            color = self.path.read_text(encoding='ascii').strip()
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('expected #RRGGBB')
            return GLib.Variant('(ddd)', tuple(int(color[i:i+2], 16) / 255 for i in (1, 3, 5)))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, ValueError) as error:
            print(f'Cannot read wallpaper accent: {error}', file=sys.stderr, flush=True)
            return None

    def file_changed(self, monitor, file, other, event):
        if not any(item and item.get_basename() == self.path.name for item in (file, other)):
            return
        accent = self.read_accent()
        # Keep the last valid accent during incomplete writes or temporary file removal.
        if accent is not None and accent != self.accent:
            self.accent = accent
            self.connection.emit_signal(None, OBJECT, INTERFACE, 'SettingChanged',
                                        GLib.Variant('(ssv)', (APPEARANCE, ACCENT, accent)))

    def gnome_changed(self, connection, sender, path, interface, signal, parameters):
        namespace, key, _ = parameters.unpack()
        if self.accent is None or (namespace, key) != (APPEARANCE, ACCENT):
            connection.emit_signal(None, OBJECT, INTERFACE, 'SettingChanged', parameters)

    def overlay(self, result, namespaces):
        if self.accent is None or (namespaces and not any(
                not pattern or fnmatchcase(APPEARANCE, pattern) for pattern in namespaces)):
            return result
        builder = GLib.VariantBuilder.new(GLib.VariantType('a{sa{sv}}'))
        values = result.get_child_value(0)
        found = False
        for i in range(values.n_children()):
            entry = values.get_child_value(i)
            if entry.get_child_value(0).get_string() == APPEARANCE:
                settings = GLib.VariantDict.new(entry.get_child_value(1))
                settings.insert_value(ACCENT, self.accent)
                entry = GLib.Variant.new_dict_entry(GLib.Variant('s', APPEARANCE), settings.end())
                found = True
            builder.add_value(entry)
        if not found:
            builder.add_value(GLib.Variant('{sa{sv}}', (APPEARANCE, {ACCENT: self.accent})))
        return GLib.Variant.new_tuple(builder.end())

    def method(self, connection, sender, path, interface, method, parameters, invocation):
        args = parameters.unpack()
        if method == 'Read' and tuple(args) == (APPEARANCE, ACCENT) and self.accent is not None:
            invocation.return_value(GLib.Variant('(v)', (self.accent,)))
            return

        def done(connection, response):
            try:
                result = connection.call_finish(response)
                if method == 'ReadAll':
                    result = self.overlay(result, args[0])
                invocation.return_value(result)
            except GLib.Error as error:
                invocation.return_gerror(error)

        connection.call(GNOME, OBJECT, INTERFACE, method, parameters, None,
                        Gio.DBusCallFlags.NONE, 5000, None, done)


def main():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    settings = Settings(connection)
    loop = GLib.MainLoop()
    Gio.bus_own_name_on_connection(connection, BUS, Gio.BusNameOwnerFlags.NONE,
                                   None, lambda *args: loop.quit())
    loop.run()
    raise SystemExit('Settings portal lost its D-Bus name')


if __name__ == '__main__':
    main()
