#!/usr/bin/env python3
import fcntl
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import signal
import shutil

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('current', ROOT / 'waywallen-current.py')
current = importlib.util.module_from_spec(spec)
spec.loader.exec_module(current)

with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    (base / 'config/waywallen').mkdir(parents=True)
    (base / 'data/waywallen').mkdir(parents=True)
    config = base / 'config/waywallen/config.toml'
    config.write_text('[global]\nlast_wallpaper="222"\n')
    image = base / 'preview space.png'
    subprocess.run(['magick', '-size', '64x64', 'xc:#4477aa', str(image)], check=True)
    with sqlite3.connect(base / 'data/waywallen/waywallen-v2.db') as conn:
        conn.executescript('CREATE TABLE library(id INTEGER, path TEXT);'
                           'CREATE TABLE item(id INTEGER,library_id INTEGER,preview_path TEXT,path TEXT,user_property_overrides TEXT);')
        conn.execute('INSERT INTO library VALUES(1,?)', (str(base),))
        conn.execute('INSERT INTO item VALUES(222,1,?,?,?)', (image.name, 'missing.mp4', '{"schemecolor":"0.2 0.4 0.6"}'))
    assert current.current_image(base) == image
    scheme = base / 'scheme.ppm'
    assert current.current_image(base, scheme) == scheme
    assert scheme.read_bytes() == b'P6\n1 1\n255\n\x33\x66\x99'
    with sqlite3.connect(base / 'data/waywallen/waywallen-v2.db') as conn:
        conn.execute('UPDATE item SET user_property_overrides=? WHERE id=222',
                     ('{"waywallen.scheme_color":"1.0000 0.0000 0.0000",'
                      '"schemecolor":"0.2 0.4 0.6"}',))
    assert current.current_image(base, scheme) == scheme
    assert scheme.read_bytes() == b'P6\n1 1\n255\n\xff\x00\x00'
    with sqlite3.connect(base / 'data/waywallen/waywallen-v2.db') as conn:
        conn.execute('UPDATE item SET user_property_overrides=? WHERE id=222',
                     ('{"schemecolor":"0.2 0.4 0.6"}',))
    config.write_text('[global]\nlast_wallpaper="999"\n')
    try:
        current.current_image(base)
        raise AssertionError('Missing wallpaper accepted')
    except ValueError:
        pass
    (base / '.local/bin').mkdir(parents=True)
    firefox_profile = base / '.var/app/org.mozilla.firefox/config/mozilla/firefox/test.default'
    firefox_profile.mkdir(parents=True)
    firefox_prefs = firefox_profile / 'prefs.js'
    original_prefs = ('user_pref("ui.accentcolor", "#123456");\nuser_pref("test.keep", true);\n'
                      'user_pref("ui.accentcolortext", "#112233");\n')
    firefox_prefs.write_text(original_prefs)
    firefox_user = firefox_profile / 'user.js'
    personal_settings = b'// Personal settings\nuser_pref("test.personal", true);\n'
    firefox_user.write_bytes(personal_settings)
    settings = base / '.local/bin/gsettings'
    settings.write_text('#!/bin/sh\nexit 0\n')
    settings.chmod(0o755)
    env = dict(os.environ, HOME=str(base), XDG_RUNTIME_DIR=str(base),
               WAYWALLEN_BASE=str(base), WALLUST_TEMPLATES='0')
    run = lambda *args: subprocess.run(['bash', str(ROOT / 'sync-waywallen-colors'), *args],
                                      env=env, text=True, capture_output=True)
    first = run(str(image))
    assert first.returncode == 0, first.stdout + first.stderr
    gtk4 = base / '.config/gtk-4.0/waywallen-colors.css'
    gtk3 = base / '.config/gtk-3.0/waywallen-colors.css'
    assert '--accent-bg-color:' in gtk4.read_text()
    assert ':root' not in gtk3.read_text() and '@define-color' in gtk3.read_text()
    assert '@define-color accent_bg_color #4477aa;' in gtk3.read_text()
    assert firefox_user.read_bytes() == personal_settings
    assert firefox_prefs.read_text() == original_prefs
    accent = base / '.local/state/waywallen-colors/accent'
    assert accent.read_text() == '#4477aa\n'
    shell_css = (base / '.local/share/themes/Waywallen/gnome-shell/gnome-shell.css').read_text()
    assert '#4477aa' in shell_css and '-st-accent-color' not in shell_css
    assert 'Skipping reapplication' in run(str(image)).stdout
    firefox_before = firefox_user.read_bytes()
    assert run('--force', str(image)).returncode == 0
    assert firefox_user.read_bytes() == firefox_before
    assert run(str(base / 'missing.png')).returncode != 0
    broken = base / 'broken.png'
    broken.write_text('not an image')
    previous = gtk4.read_bytes()
    assert run(str(broken)).returncode != 0
    assert gtk4.read_bytes() == previous
    assert firefox_user.read_bytes() == firefox_before
    assert accent.read_text() == '#4477aa\n'
    for version, path in [('3.0', gtk3), ('4.0', gtk4)]:
        code = ('import gi;gi.require_version("Gtk",'+repr(version)+');'
                'from gi.repository import Gtk; p=Gtk.CssProvider(); errors=[];'
                'p.connect("parsing-error",lambda *args: errors.append(str(args[-1])));'
                'p.load_from_path('+repr(str(path))+');assert not errors,errors')
        subprocess.run(['/usr/bin/python3', '-c', code], check=True)
    assert run().returncode != 0, 'Missing selection must not fall back to another wallpaper'
    assert gtk4.read_bytes() == previous
    config.write_text('[global]\nlast_wallpaper="222"\n')
    automatic = run('--force')
    assert automatic.returncode == 0, automatic.stdout + automatic.stderr
    assert accent.read_text() == '#336699\n'
    for name, code in {
        'systemctl': '#!/bin/sh\ncase "$*" in *waywallen-settings.service*)\ncase "$*" in *restart*|*start*) touch "$HOME/settings-started";; *is-active*) test -f "$HOME/settings-started"; exit $?;; *stop*) rm -f "$HOME/settings-started";; esac;;\n*xdg-desktop-portal.service*) exit 0;;\n*is-active*|*is-enabled*) test -f "$HOME/service-started"; exit $?;; *enable*) touch "$HOME/service-started";; esac\nexit 0\n',
        'gsettings': '#!/bin/sh\nif [ "$1" = get ]; then\ncase "$3" in enabled-extensions|disabled-extensions) echo "@as []";; *) echo "\\x27blue\\x27";; esac\nfi\nexit 0\n',
        'gnome-extensions': '#!/bin/sh\nexit 0\n',
    }.items():
        target = base / '.local/bin' / name
        target.write_text(code)
        target.chmod(0o755)
    env.update(PATH=str(base / '.local/bin') + ':' + os.environ['PATH'])
    firefox_user.write_bytes(personal_settings + b'// BEGIN Waywallen accent\n'
                             b'user_pref("ui.accentcolor", "#4477aa");\n'
                             b'user_pref("ui.highlight", "#4477aa");\n// END Waywallen accent\n')
    firefox_prefs.write_text(original_prefs + 'user_pref("ui.highlight", "#4477aa");\n')
    portal_config = base / '.config/xdg-desktop-portal/gnome-portals.conf'
    portal_config.parent.mkdir(parents=True)
    portal_config.write_text('[preferred]\ndefault=gnome;gtk;\n'
                             'org.freedesktop.impl.portal.Secret=gnome-keyring;\n'
                             'org.freedesktop.impl.portal.FileChooser=gtk;\n')
    extension = base / '.local/share/gnome-shell/extensions/waywallen-accents@gimas.local'
    extension.mkdir(parents=True)
    (extension / 'extension.js').write_text('// Previous installed watcher\n')
    (extension / 'metadata.json').write_text('{"version": 2}\n')
    saved = {p: p.read_bytes() for p in (gtk3, gtk4, gtk3.with_name('gtk.css'), gtk4.with_name('gtk.css'),
                                        firefox_user, accent, portal_config,
                                        extension / 'extension.js', extension / 'metadata.json')}
    with (firefox_profile / '.parentlock').open('w') as lock:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = ('import install; from pathlib import Path; '
                'install.migrate_firefox([Path(' + repr(str(firefox_prefs)) + ')])')
        busy = subprocess.run(['/usr/bin/python3', '-c', code], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        assert busy.returncode != 0 and 'Close Firefox' in busy.stderr
        assert firefox_user.read_bytes() == saved[firefox_user]
    installed = subprocess.run(['/usr/bin/python3', str(ROOT / 'install.py')], env=env,
                               capture_output=True, text=True)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert firefox_user.read_bytes() == personal_settings
    assert firefox_prefs.read_text() == original_prefs.split('\n', 1)[1]
    assert accent.read_text() == '#336699\n'
    assert 'org.freedesktop.impl.portal.Settings=waywallen;' in portal_config.read_text()
    assert 'org.freedesktop.impl.portal.FileChooser=gtk;' in portal_config.read_text()
    assert 'org.freedesktop.impl.portal.Secret=gnome-keyring;' in portal_config.read_text()
    assert 'default=gnome;gtk;' in portal_config.read_text()
    assert (extension / 'extension.js').read_bytes() == (ROOT / 'waywallen-accents/extension.js').read_bytes()
    restore = next((base / '.local/state/waywallen-colors/backups').glob('*/restore.py'))
    # Simulate Firefox saving the managed colors and an unrelated setting after installation.
    firefox_prefs.write_text('user_pref("ui.accentcolor", "#336699");\n'
                             'user_pref("ui.highlight", "#336699");\n'
                             'user_pref("test.keep", true);\nuser_pref("test.new", 42);\n')
    with (firefox_profile / '.parentlock').open('w') as lock:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        busy = subprocess.run(['/usr/bin/python3', str(restore)], env=env,
                              capture_output=True, text=True)
        assert busy.returncode != 0 and 'Close Firefox' in busy.stderr
    restored = subprocess.run(['/usr/bin/python3', str(restore)], env=env,
                              capture_output=True, text=True)
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert all(p.read_bytes() == contents for p, contents in saved.items())
    assert 'user_pref("ui.accentcolor", "#123456");' in firefox_prefs.read_text()
    assert 'user_pref("ui.highlight", "#4477aa");' in firefox_prefs.read_text()
    assert 'user_pref("test.new", 42);' in firefox_prefs.read_text()
    assert not (base / '.local/bin/waywallen-current.py').exists()
    assert not (base / '.local/bin/waywallen-settings.py').exists()
    assert not (base / '.config/systemd/user/waywallen-settings.service').exists()
    assert not (base / '.local/share/xdg-desktop-portal/portals/waywallen.portal').exists()
    assert not (base / '.local/share/dbus-1/services/org.freedesktop.impl.portal.desktop.waywallen.service').exists()
    watcher = base / 'watcher'
    watcher.mkdir()
    shutil.copy2(ROOT / 'watch-waywallen.sh', watcher / 'watch-waywallen.sh')
    stub = watcher / 'sync-waywallen-colors'
    stub.write_text('#!/bin/sh\necho sync >> "$HOME/sync-events"\n')
    stub.chmod(0o755)
    process = subprocess.Popen(['bash', str(watcher / 'watch-waywallen.sh')],
                               env=env, start_new_session=True)
    try:
        events = base / 'sync-events'
        for expected in (1, 2, 3):
            deadline = time.monotonic() + 6
            while not events.exists() or len(events.read_text().splitlines()) < expected:
                assert time.monotonic() < deadline, 'Watcher missed a change'
                time.sleep(0.1)
            if expected == 1:
                config.write_text('[global]\nlast_wallpaper="999"\n')
            elif expected == 2:
                with sqlite3.connect(base / 'data/waywallen/waywallen-v2.db') as conn:
                    conn.execute('UPDATE item SET user_property_overrides=? WHERE id=222',
                                 ('{"waywallen.scheme_color":"1.0000 0.0000 0.0000"}',))
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
subprocess.run(['/usr/bin/python3', str(ROOT / 'test-portal.py')], check=True)
shell_env = dict(os.environ, GSETTINGS_BACKEND='memory')
libraries = [str(path) for root in (Path('/usr/lib64'), Path('/usr/lib'))
             for path in (root / 'gnome-shell', *root.glob('mutter-*')) if path.is_dir()]
for key in ('GI_TYPELIB_PATH', 'LD_LIBRARY_PATH'):
    shell_env[key] = ':'.join(libraries + ([os.environ[key]] if os.environ.get(key) else []))
subprocess.run(['gjs', '-m', str(ROOT / 'test-shell.js')], env=shell_env, check=True)
print('OK: selection, palette, GTK parsing, Firefox migration, cache, invalid images, install, rollback and watcher')
