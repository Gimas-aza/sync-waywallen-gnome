#!/usr/bin/env python3
"""Run the copy in the backup folder to undo this installation."""
import fcntl
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

base = Path(__file__).resolve().parent
manifest = json.loads((base / 'manifest.json').read_text())
home = Path.home()
for path in manifest.get('firefox_prefs', {}):
    lock = (home / path).with_name('.parentlock')
    if lock.exists():
        with lock.open('r+') as handle:
            try:
                fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit('Close Firefox before restoring its saved colors.')
subprocess.run(['systemctl', '--user', 'disable', '--now', 'waywallen-colors.service'], check=True)
if 'portal' in manifest:
    subprocess.run(['systemctl', '--user', 'stop', 'waywallen-settings.service'], check=True)
subprocess.run(['gnome-extensions', 'disable',
                'user-theme@gnome-shell-extensions.gcampax.github.com'], check=False)
subprocess.run(['gnome-extensions', 'disable', 'waywallen-accents@gimas.local'], check=False)
for setting, value in manifest['settings'].items():
    schema, key = setting.split('/')
    subprocess.run(['gsettings', 'set', schema, key, value], check=True)
for path, existed in manifest['paths'].items():
    target = home / path
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.exists() or target.is_symlink():
        target.unlink()
    if existed:
        source = base / 'files' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
for path, saved in manifest.get('firefox_prefs', {}).items():
    prefs = home / path
    if prefs.exists():
        content = re.sub(r'^user_pref\("ui\.(accentcolor|accentcolortext|highlight|highlighttext|selecteditem|selecteditemtext)",[^\n]*\n?',
                         '', prefs.read_text(), flags=re.M)
        content += ('\n' if content and not content.endswith('\n') else '') + '\n'.join(saved)
        if saved:
            content += '\n'
        with tempfile.NamedTemporaryFile(mode='w', dir=prefs.parent, delete=False) as output:
            output.write(content)
        Path(output.name).replace(prefs)
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
if 'portal' in manifest:
    if manifest['portal']['waywallen-settings.service']:
        subprocess.run(['systemctl', '--user', 'start', 'waywallen-settings.service'], check=True)
    subprocess.run(['systemctl', '--user',
                    'restart' if manifest['portal']['xdg-desktop-portal.service'] else 'stop',
                    'xdg-desktop-portal.service'], check=True)
if manifest['service']['is-enabled']:
    subprocess.run(['systemctl', '--user', 'enable', 'waywallen-colors.service'], check=True)
if manifest['service']['is-active']:
    subprocess.run(['systemctl', '--user', 'start', 'waywallen-colors.service'], check=True)
print('Restored the saved files and GNOME settings. Reopen applications to refresh CSS.')
