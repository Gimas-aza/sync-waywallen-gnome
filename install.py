#!/usr/bin/env python3
"""Install the GNOME scripts for the current user, with a reversible snapshot."""
import ast
import configparser
from contextlib import ExitStack
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
UUID = 'user-theme@gnome-shell-extensions.gcampax.github.com'
EXT = '.local/share/gnome-shell/extensions/' + UUID
ACCENTS_UUID = 'waywallen-accents@gimas.local'
ACCENTS_EXT = '.local/share/gnome-shell/extensions/' + ACCENTS_UUID
SCRIPTS = ('sync-waywallen-colors', 'watch-waywallen.sh', 'waywallen-current.py',
           'waywallen-settings.py')
SETTINGS_BUS = 'org.freedesktop.impl.portal.desktop.waywallen'
FIREFOX_BLOCK = re.compile(rb'^// BEGIN Waywallen accent\r?\n.*?^// END Waywallen accent\r?\n?',
                           re.M | re.S)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def portal_config():
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    directories = [HOME / '.config']
    directories += [Path(p) for p in os.environ.get('XDG_CONFIG_DIRS', '/etc/xdg').split(':') if p]
    directories += [Path('/etc'), HOME / '.local/share']
    directories += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p]
    directories += [Path('/usr/share')]
    for directory in directories:
        for name in ('gnome-portals.conf', 'portals.conf'):
            source = directory / 'xdg-desktop-portal' / name
            if source.is_file():
                config.read(source)
                if not config.has_section('preferred'):
                    raise SystemExit(f'Missing [preferred] in {source}')
                config['preferred']['org.freedesktop.impl.portal.Settings'] = 'waywallen;'
                return config
    raise SystemExit('GNOME portal configuration not found')


def migrate_firefox(profiles):
    with ExitStack() as locks:
        pending = []
        for prefs in profiles:
            user = prefs.with_name('user.js')
            previous = user.read_bytes() if user.exists() else b''
            blocks = FIREFOX_BLOCK.findall(previous)
            if not blocks:
                continue
            lock = locks.enter_context(prefs.with_name('.parentlock').open('a+'))
            try:
                fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit('Close Firefox and rerun install.py to remove its old accent overrides.')
            managed = {line.split(b',', 1)[0] for block in blocks for line in block.splitlines()
                       if re.match(rb'^user_pref\("ui\.(accentcolor|accentcolortext|highlight|highlighttext|selecteditem|selecteditemtext)",', line)}
            content = b''.join(line for line in prefs.read_bytes().splitlines(keepends=True)
                               if line.split(b',', 1)[0] not in managed)
            pending += [(user, FIREFOX_BLOCK.sub(b'', previous)), (prefs, content)]
        for path, content in pending:
            if content != path.read_bytes():
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                    output.write(content)
                Path(output.name).replace(path)


def main():
    for cmd in ('python3', 'magick', 'gsettings', 'systemctl', 'glib-compile-schemas'):
        if not shutil.which(cmd):
            raise SystemExit(f'Missing dependency: {cmd}')
    run('systemctl', '--user', 'show-environment', stdout=subprocess.DEVNULL)
    run('python3', '-c', 'from gi.repository import Gio, GLib')
    config = portal_config()
    paths = ['.local/bin/' + name for name in SCRIPTS]
    paths += ['.config/systemd/user/waywallen-colors.service',
              '.config/systemd/user/waywallen-settings.service',
              '.local/share/themes/Waywallen', EXT, ACCENTS_EXT,
              '.local/state/waywallen-colors/accent',
              '.local/share/xdg-desktop-portal/portals/waywallen.portal',
              f'.local/share/dbus-1/services/{SETTINGS_BUS}.service',
              '.config/xdg-desktop-portal/gnome-portals.conf']
    paths += [f'.config/gtk-{v}.0/{name}' for v in (3, 4)
              for name in ('gtk.css', 'waywallen-colors.css')]
    firefox_prefs = {}
    profiles = []
    firefox = HOME / '.var/app/org.mozilla.firefox'
    for folder in (firefox / 'config/mozilla/firefox', firefox / '.mozilla/firefox'):
        for prefs in folder.glob('*/prefs.js'):
            profiles.append(prefs)
            paths.append(str(prefs.with_name('user.js').relative_to(HOME)))
            firefox_prefs[str(prefs.relative_to(HOME))] = [
                line for line in prefs.read_text().splitlines()
                if re.match(r'^user_pref\("ui\.(accentcolor|accentcolortext|highlight|highlighttext|selecteditem|selecteditemtext)",', line)]
    backup = HOME / '.local/state/waywallen-colors/backups' / datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    backup.chmod(0o700)
    manifest = {'paths': {}, 'settings': {}, 'service': {}, 'firefox_prefs': firefox_prefs}
    manifest['portal'] = {name: subprocess.run(
        ['systemctl', '--user', 'is-active', name], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode == 0
        for name in ('waywallen-settings.service', 'xdg-desktop-portal.service')}
    for path in paths:
        source = HOME / path
        exists = source.exists() or source.is_symlink()
        manifest['paths'][path] = exists
        if exists:
            target = backup / 'files' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
    for schema, key in [('org.gnome.desktop.interface', 'accent-color'),
                        ('org.gnome.shell', 'enabled-extensions'),
                        ('org.gnome.shell', 'disabled-extensions')]:
        manifest['settings'][schema + '/' + key] = run(
            'gsettings', 'get', schema, key, capture_output=True).stdout.strip()
    for flag in ('is-active', 'is-enabled'):
        manifest['service'][flag] = subprocess.run(
            ['systemctl', '--user', flag, 'waywallen-colors.service'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    shutil.copy2(ROOT / 'restore.py', backup / 'restore.py')
    print(f'Backup: {backup}', flush=True)
    for name in SCRIPTS:
        target = HOME / '.local/bin' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
        target.chmod(0o755)
    for name in ('waywallen-colors.service', 'waywallen-settings.service'):
        target = HOME / '.config/systemd/user' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    target = HOME / '.local/share/xdg-desktop-portal/portals/waywallen.portal'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / target.name, target)
    target = HOME / f'.local/share/dbus-1/services/{SETTINGS_BUS}.service'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f'[D-BUS Service]\nName={SETTINGS_BUS}\n'
                      f'Exec=/usr/bin/python3 {shlex.quote(str(HOME / ".local/bin/waywallen-settings.py"))}\n'
                      'SystemdService=waywallen-settings.service\n')
    target = HOME / '.config/xdg-desktop-portal/gnome-portals.conf'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w') as output:
        config.write(output, space_around_delimiters=False)
    if not (HOME / EXT).exists():
        with zipfile.ZipFile(ROOT / 'user-theme.zip') as archive:
            archive.extractall(HOME / EXT)
        run('glib-compile-schemas', str(HOME / EXT / 'schemas'))
    (HOME / ACCENTS_EXT).mkdir(parents=True, exist_ok=True)
    for name in ('extension.js', 'metadata.json'):
        shutil.copy2(ROOT / 'waywallen-accents' / name, HOME / ACCENTS_EXT / name)
    run('systemctl', '--user', 'daemon-reload')
    run('bash', str(HOME / '.local/bin/sync-waywallen-colors'), '--force')
    run('systemctl', '--user', 'restart', 'waywallen-settings.service')
    run('systemctl', '--user', 'restart', 'xdg-desktop-portal.service')
    run('systemctl', '--user', 'is-active', 'waywallen-settings.service')
    run('systemctl', '--user', 'is-active', 'xdg-desktop-portal.service')
    migrate_firefox(profiles)
    for uuid in (UUID, ACCENTS_UUID):
        result = subprocess.run(['gnome-extensions', 'enable', uuid], capture_output=True, text=True)
        if result.returncode:
            enabled = ast.literal_eval(run('gsettings', 'get', 'org.gnome.shell',
                                           'enabled-extensions', capture_output=True).stdout.removeprefix('@as '))
            if uuid not in enabled:
                run('gsettings', 'set', 'org.gnome.shell', 'enabled-extensions', repr(enabled + [uuid]))
            print(f'{uuid} will load after signing out and signing back in.')
    run('systemctl', '--user', 'enable', '--now', 'waywallen-colors.service')
    run('systemctl', '--user', 'restart', 'waywallen-colors.service')
    run('systemctl', '--user', 'is-active', 'waywallen-colors.service')


if __name__ == '__main__':
    main()
