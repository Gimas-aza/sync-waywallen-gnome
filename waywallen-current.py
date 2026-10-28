#!/usr/bin/env python3
"""Resolve the selected Waywallen v2 wallpaper without modifying its database."""
import os
import json
from pathlib import Path
import sqlite3
import sys
import tomllib


def scheme_color(root, source, overrides):
    try:
        overrides = json.loads(overrides or '{}')
        if not isinstance(overrides, dict):
            overrides = {}
        if 'waywallen.scheme_color' in overrides:
            value = overrides['waywallen.scheme_color']
        elif 'schemecolor' in overrides:
            value = overrides['schemecolor']
        else:
            source = Path(root) / source
            directory = source if source.is_dir() else source.parent
            project = json.loads((directory / 'project.json').read_text())
            value = project.get('general', {}).get('properties', {}).get('schemecolor', {}).get('value')
        if not isinstance(value, str):
            return None
        rgb = [float(part) for part in value.split()]
        if len(rgb) != 3 or not all(0 <= channel <= 1 for channel in rgb):
            return None
        rgb = bytes(int(channel * 255 + 0.5) for channel in rgb)
        return rgb if any(rgb) else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def current_image(base, scheme_image=None):
    config = tomllib.loads((base / 'config/waywallen/config.toml').read_text())
    selected = config.get('global', {}).get('last_wallpaper')
    if not selected:
        raise ValueError('Waywallen has no selected wallpaper')
    db = base / 'data/waywallen/waywallen-v2.db'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as conn:
        row = conn.execute('SELECT library.path, item.preview_path, item.path, item.user_property_overrides '
                           'FROM item JOIN library ON library.id=item.library_id '
                           'WHERE item.id=?', (selected,)).fetchone()
    if not row:
        raise ValueError(f'Wallpaper {selected} is missing from the library')
    root, preview, source, overrides = row
    if scheme_image is not None:
        color = scheme_color(root, source, overrides)
        if color is not None:
            scheme_image.write_bytes(b'P6\n1 1\n255\n' + color)
            print(f'[sync] Using wallpaper color scheme: #{color.hex()}', file=sys.stderr)
            return scheme_image
    for value in (preview, source):
        if value:
            path = Path(root) / value
            if path.is_file():
                return path
    raise FileNotFoundError(f'Wallpaper {selected} has no accessible preview or source')


if __name__ == '__main__':
    base = Path(os.environ.get('WAYWALLEN_BASE',
                str(Path.home() / '.var/app/org.waywallen.waywallen')))
    try:
        print(current_image(base, Path(sys.argv[1]) if len(sys.argv) > 1 else None))
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f'[sync] {exc}')
