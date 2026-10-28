# Waywallen Accents for GNOME

Sync GNOME Shell and GTK application accent colors with your selected Waywallen wallpaper.
Compatible applications, including Flatpaks, receive the exact accent through the Settings portal.
Other applications use the nearest built-in GNOME accent. Your light/dark preference is preserved.

Install the whole project, not just the extension folder. It includes a GNOME Shell extension,
a wallpaper watcher, GTK styles, and a Settings portal backend.
[Waywallen](https://github.com/waywallen/waywallen) must be installed separately.

## Requirements

Tested on **Fedora 43, GNOME Shell 49.8, Wayland**. Both bundled extensions support **GNOME 49 only**.
X11 has not been verified.

- Waywallen Flatpak (`org.waywallen.waywallen`) with its v2 database.
- Python 3.11 or newer with PyGObject (`Gio` and `GLib`) available to `/usr/bin/python3`.
- ImageMagick 7 (`magick`), GTK 4.16 or newer, and standard Linux command-line tools.
- GNOME tools: `gsettings`, `glib-compile-schemas`, and `gnome-extensions`.
- A working user systemd instance, session D-Bus, and the GNOME desktop portal backend.

On Fedora 43 with GNOME:

```bash
sudo dnf install git python3 python3-gobject ImageMagick glib2 \
  gnome-shell xdg-desktop-portal xdg-desktop-portal-gnome flatpak
```

Other distributions need equivalent packages and GNOME 49. The installer checks prerequisites
but does not install system packages. No pip dependencies are needed.

The bundled User Themes extension is installed if absent. An existing copy must support GNOME 49.

## Installation

Run these commands as your regular user inside your GNOME session, without `sudo` or a container.

### 1. Prepare Waywallen

With Flathub configured:

```bash
flatpak install flathub org.waywallen.waywallen
flatpak run org.waywallen.waywallen
```

Finish Waywallen's GNOME integration setup and select a wallpaper. The project expects these files:

```text
~/.var/app/org.waywallen.waywallen/config/waywallen/config.toml
~/.var/app/org.waywallen.waywallen/data/waywallen/waywallen-v2.db
```

The selected wallpaper must exist in the database, with readable image or preview files.
AppImage and native installation paths are not detected automatically.

### 2. Download and install

End screen sharing and other portal-dependent operations before installation:
the installer restarts `xdg-desktop-portal`. If it asks you to close an application,
close it and rerun the installer.

```bash
git clone https://github.com/Gimas-aza/sync-waywallen-gnome.git
cd sync-waywallen-gnome
python3 install.py
```

Alternatively, download and extract the repository ZIP, then run `python3 install.py` there.
Keep all project files together, including `user-theme.zip`. No compilation is needed.

The installer saves a backup, installs and enables both extensions, configures the Settings portal,
and starts automatic color updates. Other portal routes are preserved.

### 3. Log out and back in

**A full logout/login is required after the first installation or a Shell extension code update.**
Locking and unlocking is not sufficient. Reopen applications if they still show the old accent.

## Verify and use

```bash
systemctl --user is-active waywallen-colors.service waywallen-settings.service
```

Both services should report `active`. Confirm **Waywallen Accents** and **User Themes** are enabled
in GNOME's Extensions app. Select another wallpaper in Waywallen; colors update within a few seconds.

To force a refresh:

```bash
~/.local/bin/sync-waywallen-colors --force
```

To inspect status and recent logs:

```bash
systemctl --user status waywallen-colors.service waywallen-settings.service
journalctl --user -u waywallen-colors.service -u waywallen-settings.service -n 50 --no-pager
```

## Updates

From the cloned project directory, follow the same portal precautions as during installation:

```bash
git pull --ff-only
python3 install.py
```

Log out and back in if extension code changed. Each installation creates a separate backup.
ZIP users can extract the updated project and run its installer.

## Stop or uninstall

To stop automatic updates while keeping the current colors and integration:

```bash
systemctl --user disable --now waywallen-colors.service
```

To undo an installation, find its backup:

```bash
ls -1 ~/.local/state/waywallen-colors/backups/
```

End portal-dependent operations. Replace `BACKUP_DIRECTORY` with the chosen folder name:

```bash
python3 "$HOME/.local/state/waywallen-colors/backups/BACKUP_DIRECTORY/restore.py"
```

Use the copy of `restore.py` inside that backup. If it asks you to close an application,
close it and rerun the command. Rollback restores saved files, GNOME settings, portal routing,
and service states. **Later changes to managed files or settings can be overwritten.**
Log out and back in, then reopen applications. Keep the backup until you no longer need rollback.

## Troubleshooting

- **`Missing dependency: magick`:** install ImageMagick 7; `convert` alone is insufficient.
- **`No module named gi`:** install PyGObject for `/usr/bin/python3` and use system Python.
- **`GNOME portal configuration not found`:** install the GNOME portal backend and confirm
  its `gnome-portals.conf` or `portals.conf` exists.
- **Wallpaper or database errors:** launch Waywallen, select a wallpaper, and check the paths above.
  Reimport wallpapers if their file paths have changed.
- **Services cannot connect to D-Bus:** run inside your GNOME session as your regular user, without sudo.
- **Shell colors do not change:** verify GNOME 49 and both extensions, log out/in, and check the service logs.
- **An application keeps its own colors:** reopen it. Custom themes, sandbox restrictions, and limited
  portal support can prevent exact matching. Other theme managers can conflict with generated GTK styles.

One shared accent is used across all monitors. The project reads Waywallen's database without modifying it;
wallpaper rendering and hardware setup belong to Waywallen.

## Tests

Tests use temporary files and isolated or mocked services. On Fedora, install the additional dependencies
and run:

```bash
sudo dnf install gtk3 gtk4 gjs dbus-daemon
python3 test.py
```

## License and credits

Project code uses the [MIT license](LICENSE).
The bundled `user-theme.zip` contains GNOME **User Themes 80 for GNOME 49**, distributed separately
under its GPL license, with source and `COPYING` included.
See [GNOME Shell Extensions](https://gitlab.gnome.org/GNOME/gnome-shell-extensions)
and [Waywallen](https://github.com/waywallen/waywallen).
