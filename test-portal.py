#!/usr/bin/env python3
"""Exercise the real portal frontend on a private D-Bus session."""
from fnmatch import fnmatchcase
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('settings', ROOT / 'waywallen-settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)
PUBLIC = 'org.freedesktop.portal.Desktop'
PUBLIC_INTERFACE = 'org.freedesktop.portal.Settings'


def mock_gnome():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    values = {
        settings.APPEARANCE: {'accent-color': GLib.Variant('(ddd)', (0.1, 0.2, 0.3)),
                              'color-scheme': GLib.Variant('u', 1)},
        'org.gnome.desktop.interface': {'font-name': GLib.Variant('s', 'Adwaita Sans 11')},
    }
    xml = settings.XML.replace('</interface>', '''
      <method name="Change"><arg type="s" direction="in"/><arg type="s" direction="in"/>
        <arg type="v" direction="in"/></method></interface>''')
    info = Gio.DBusNodeInfo.new_for_xml(xml)

    def method(bus, sender, path, interface, name, parameters, invocation):
        args = parameters.unpack()
        if name == 'ReadAll':
            namespaces = args[0]
            result = {ns: entries for ns, entries in values.items() if not namespaces or any(
                not pattern or fnmatchcase(ns, pattern) for pattern in namespaces)}
            invocation.return_value(GLib.Variant('(a{sa{sv}})', (result,)))
        elif name == 'Change':
            namespace, key, _ = args
            values.setdefault(namespace, {})[key] = parameters.get_child_value(2).get_variant()
            bus.emit_signal(None, settings.OBJECT, settings.INTERFACE, 'SettingChanged', parameters)
            invocation.return_value(None)
        else:
            namespace, key = args
            if key in values.get(namespace, {}):
                invocation.return_value(GLib.Variant('(v)', (values[namespace][key],)))
            else:
                invocation.return_dbus_error('org.freedesktop.portal.Error.NotFound', 'Unknown setting')

    connection.register_object(settings.OBJECT, info.interfaces[0], method,
                               lambda *args: GLib.Variant('u', 0), None)
    Gio.bus_own_name_on_connection(connection, settings.GNOME, Gio.BusNameOwnerFlags.NONE, None, None)
    GLib.MainLoop().run()


def session_test():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(bus, method, signature, args, interface=PUBLIC_INTERFACE):
        return connection.call_sync(bus, settings.OBJECT, interface, method,
                                    GLib.Variant(signature, args), None,
                                    Gio.DBusCallFlags.NONE, 3000, None)

    def wait_for(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError('Timed out waiting for portal')

    def owned(name):
        return connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                    'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', (name,)),
                                    None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]

    with tempfile.TemporaryDirectory(prefix='waywallen-portal-') as folder:
        base = Path(folder)
        runtime = base / 'runtime'
        runtime.mkdir(mode=0o700)
        portals = base / 'portals'
        portals.mkdir()
        (portals / 'waywallen.portal').write_bytes((ROOT / 'waywallen.portal').read_bytes())
        (portals / 'gnome-portals.conf').write_text(
            '[preferred]\ndefault=none\norg.freedesktop.impl.portal.Settings=waywallen;\n')
        env = dict(os.environ, HOME=str(base), XDG_RUNTIME_DIR=str(runtime),
                   XDG_DESKTOP_PORTAL_DIR=str(portals), XDG_CURRENT_DESKTOP='GNOME')
        processes = []
        with (base / 'portal.log').open('w+') as log:
            def start(*args):
                process = subprocess.Popen(args, env=env, stdout=log, stderr=log)
                processes.append(process)
                return process

            try:
                start(sys.executable, __file__, '--mock')
                wait_for(lambda: owned(settings.GNOME))
                backend = start(sys.executable, str(ROOT / 'waywallen-settings.py'))
                wait_for(lambda: owned(settings.BUS))
                start('/usr/libexec/xdg-desktop-portal')
                wait_for(lambda: owned(PUBLIC))
                read = lambda key='accent-color': call(
                    PUBLIC, 'ReadOne', '(ss)', (settings.APPEARANCE, key)).unpack()[0]
                assert read() == (0.1, 0.2, 0.3), 'Missing accent must fall back to GNOME'
                events = []
                connection.signal_subscribe(PUBLIC, PUBLIC_INTERFACE, 'SettingChanged',
                                            settings.OBJECT, None, Gio.DBusSignalFlags.NONE,
                                            lambda *args: events.append(args[5].unpack()))
                connection.flush_sync(None)
                accent = base / '.local/state/waywallen-colors/accent'

                def write(value):
                    temporary = accent.with_suffix('.tmp')
                    temporary.write_text(value)
                    temporary.replace(accent)

                expected = tuple(int(value, 16) / 255 for value in ('6e', '67', '5e'))
                write('#6e675e\n')
                wait_for(lambda: any(event == (settings.APPEARANCE, 'accent-color', expected)
                                     for event in events))
                assert read() == expected
                assert call(PUBLIC, 'Read', '(ss)', (settings.APPEARANCE, 'accent-color')).unpack()[0] == expected
                for namespaces in ([], [''], ['org.freedesktop.*']):
                    result = call(PUBLIC, 'ReadAll', '(as)', (namespaces,))
                    values = result.get_child_value(0).lookup_value(settings.APPEARANCE, None)
                    assert values.lookup_value('accent-color', None).unpack() == expected
                    assert values.lookup_value('color-scheme', None).get_type_string() == 'u'
                result = call(PUBLIC, 'ReadAll', '(as)', (['org.gnome.desktop.interface'],)).unpack()[0]
                assert result == {'org.gnome.desktop.interface': {'font-name': 'Adwaita Sans 11'}}
                assert call(PUBLIC, 'ReadAll', '(as)', (['unknown.*'],)).unpack()[0] == {}
                try:
                    read('missing')
                    raise AssertionError('Unknown setting accepted')
                except GLib.Error as error:
                    assert Gio.DBusError.get_remote_error(error) == 'org.freedesktop.portal.Error.NotFound'

                call(settings.GNOME, 'Change', '(ssv)',
                     (settings.APPEARANCE, 'color-scheme', GLib.Variant('u', 2)), settings.INTERFACE)
                wait_for(lambda: (settings.APPEARANCE, 'color-scheme', 2) in events)
                assert read('color-scheme') == 2
                count = len(events)
                call(settings.GNOME, 'Change', '(ssv)', (settings.APPEARANCE, 'accent-color',
                     GLib.Variant('(ddd)', (1.0, 0.0, 0.0))), settings.INTERFACE)
                write('invalid\n')
                deadline = time.monotonic() + 0.2
                while time.monotonic() < deadline:
                    GLib.MainContext.default().iteration(False)
                    time.sleep(0.01)
                assert len(events) == count and read() == expected

                backend.terminate()
                backend.wait(timeout=3)
                wait_for(lambda: not owned(settings.BUS))
                start(sys.executable, str(ROOT / 'waywallen-settings.py'))
                wait_for(lambda: owned(settings.BUS))
                assert read() == (1.0, 0.0, 0.0), 'Invalid saved accent must fall back to GNOME'
                write('#000000\n')
                wait_for(lambda: read() == (0.0, 0.0, 0.0))
                write('#ffffff\n')
                wait_for(lambda: read() == (1.0, 1.0, 1.0))
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read()[-6000:], file=sys.stderr)
                raise
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=3)
    print('OK: portal RGB, typed ReadAll, namespace filters, GNOME forwarding, errors, signals and restart')


if __name__ == '__main__':
    if sys.argv[1:] == ['--mock']:
        mock_gnome()
    elif sys.argv[1:] == ['--session']:
        session_test()
    else:
        with tempfile.TemporaryDirectory(prefix='waywallen-bus-') as folder:
            config = Path(folder) / 'bus.conf'
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                              '<policy context="default"><allow own="*"/>'
                              '<allow send_destination="*"/><allow receive_sender="*"/>'
                              '</policy></busconfig>')
            env = dict(os.environ, HOME=folder, XDG_RUNTIME_DIR=folder, GIO_USE_VFS='local',
                       XDG_DATA_HOME=folder + '/.local/share', XDG_CONFIG_HOME=folder + '/.config')
            subprocess.run(['dbus-run-session', '--config-file=' + str(config), '--',
                            sys.executable, __file__, '--session'],
                           env=env, check=True)
