import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export default class WaywallenAccents extends Extension {
    enable() {
        this._file = Gio.File.new_for_path(GLib.build_filenamev([
            GLib.get_home_dir(), '.local/share/themes/Waywallen/gnome-shell/gnome-shell.css',
        ]));
        this._context = St.ThemeContext.get_for_stage(global.stage);
        this._theme = null;
        this._loaded = false;
        this._timer = 0;
        this._restoreSource = 0;
        this._monitorManager = global.backend.get_monitor_manager();
        this._powerSignal = this._monitorManager.connect('power-save-mode-changed', () => {
            if (!this._restoreSource) {
                this._restoreSource = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this._restoreSource = 0;
                    this._restoreWallpaper();
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        this._contextSignal = this._context.connect('changed', () => {
            if (this._context.get_theme() !== this._theme)
                this._reload();
        });
        this._monitor = this._file.get_parent().monitor_directory(Gio.FileMonitorFlags.NONE, null);
        this._monitor.connect('changed', (_monitor, file, otherFile) => {
            if (file.get_basename() !== 'gnome-shell.css' && otherFile?.get_basename() !== 'gnome-shell.css')
                return;
            if (this._timer)
                GLib.Source.remove(this._timer);
            this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
                this._timer = 0;
                this._reload();
                return GLib.SOURCE_REMOVE;
            });
        });
        this._reload();
    }

    _reload() {
        try {
            if (!this._file.query_exists(null))
                return;
            const current = this._context.get_theme();
            // A fresh theme discards cached application CSS and duplicate accent sheets.
            const theme = new St.Theme({
                application_stylesheet: current.application_stylesheet,
                theme_stylesheet: current.theme_stylesheet,
                default_stylesheet: current.default_stylesheet,
            });
            for (const file of current.get_custom_stylesheets()) {
                if (file && !file.equal(this._file))
                    theme.load_stylesheet(file);
            }
            const applicationAccent = theme.application_stylesheet?.equal(this._file) ?? false;
            if (!applicationAccent)
                theme.load_stylesheet(this._file);
            // Set identity before ThemeContext::changed is emitted synchronously.
            this._theme = theme;
            this._loaded = !applicationAccent;
            this._context.set_theme(theme);
        } catch (error) {
            console.error(`Waywallen Accents: ${error.message}`);
        } finally {
            this._restoreWallpaper();
        }
    }

    _restoreWallpaper() {
        if (Main.sessionMode.isLocked)
            return;
        // Style changes can leave GNOME backgrounds without Waywallen's live child.
        const waywallen = Main.extensionManager.lookup('org.waywallen.gnome@waywallen.io');
        if (waywallen?.stateObj?._override) {
            waywallen.stateObj._override._reloadBackgrounds();
        }
    }

    disable() {
        this._monitor?.cancel();
        this._monitorManager?.disconnect(this._powerSignal);
        if (this._restoreSource)
            GLib.Source.remove(this._restoreSource);
        this._restoreSource = 0;
        this._monitorManager = null;
        if (this._timer)
            GLib.Source.remove(this._timer);
        this._context?.disconnect(this._contextSignal);
        if (this._loaded)
            this._theme.unload_stylesheet(this._file);
        this._timer = 0;
        this._loaded = false;
        this._theme = null;
        this._context = null;
        this._restoreWallpaper();
    }
}
