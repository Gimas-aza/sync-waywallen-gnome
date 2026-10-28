#!/usr/bin/gjs -m
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

const directory = GLib.dir_make_tmp('waywallen-shell-test-XXXXXX');
const root = Gio.File.new_for_uri(import.meta.url).get_parent();
const [, bytes] = root.get_child('waywallen-accents/extension.js').load_contents(null);
const source = new TextDecoder().decode(bytes)
    .replace("import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';", 'class Extension {}')
    .replace("import * as Main from 'resource:///org/gnome/shell/ui/main.js';",
        'const Main = {sessionMode: {isLocked: false}, extensionManager: {lookup() { return null; }}};');
assert(!source.includes('resource:///'), 'Shell imports must be stubbed for the headless test');
GLib.file_set_contents(`${directory}/extension.js`, source);
const {default: Accents} = await import(`file://${directory}/extension.js`);
const accent = Gio.File.new_for_path(`${directory}/accent.css`);
const base = Gio.File.new_for_path(`${directory}/base.css`);
const external = Gio.File.new_for_path(`${directory}/external.css`);
GLib.file_set_contents(base.get_path(), '#base { background-color: #224466; }');
GLib.file_set_contents(external.get_path(), '#external { background-color: #654321; }');

function color(context, id) {
    return St.ThemeNode.new(context, null, context.get_theme(), St.Widget.$gtype,
        id, null, null, '').get_background_color().to_string();
}

for (const applicationAccent of [true, false]) {
    GLib.file_set_contents(accent.get_path(), '#probe { background-color: #123456; }');
    // Standalone St contexts lack a Clutter backend and warn during finalization.
    const context = new St.ThemeContext();
    const theme = new St.Theme({
        application_stylesheet: applicationAccent ? accent : base,
        default_stylesheet: base,
    });
    theme.load_stylesheet(external);
    // Reproduce the duplicate sheets inherited when GNOME replaces a theme.
    theme.load_stylesheet(accent);
    theme.load_stylesheet(accent);
    context.set_theme(theme);
    const extension = new Accents();
    extension._context = context;
    extension._file = accent;
    extension._theme = theme;
    extension._loaded = true;
    let changes = 0;
    const signal = context.connect('changed', () => {
        changes++;
        assert(changes < 10, 'Theme reload must not recurse');
        if (context.get_theme() !== extension._theme)
            extension._reload();
    });
    for (const hex of ['#abcdef', '#4477aa']) {
        GLib.file_set_contents(accent.get_path(), `#probe { background-color: ${hex}; }`);
        extension._reload();
        assert(color(context, 'probe') === `${hex}ff`, 'Shell kept the previous accent');
        assert(color(context, 'base') === '#224466ff', 'Base styles changed');
        assert(color(context, 'external') === '#654321ff', 'Other extension styles changed');
        const copies = context.get_theme().get_custom_stylesheets().filter(file => file.equal(accent));
        assert(copies.length === (applicationAccent ? 0 : 1), 'Duplicate accent styles remain');
    }
    const previous = context.get_theme();
    accent.delete(null);
    extension._reload();
    assert(context.get_theme() === previous, 'Missing CSS must leave the current theme intact');
    context.disconnect(signal);
}

for (const name of ['extension.js', 'base.css', 'external.css'])
    Gio.File.new_for_path(`${directory}/${name}`).delete(null);
Gio.File.new_for_path(directory).delete(null);
print('OK: Shell hot reload, application CSS cache, duplicate sheets, other styles and missing CSS');
