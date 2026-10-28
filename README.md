# Waywallen Accents for GNOME

Sync GNOME Shell and application accent colors with your selected Waywallen wallpaper.
The project includes a GNOME Shell extension, a wallpaper watcher, GTK color styles,
and a Settings portal backend. **Install the whole project, not just the extension folder.**

Tested on **Fedora 43, GNOME Shell 49.8, Wayland**, using the Flatpak version of Waywallen
with its `waywallen-v2.db` database. Both bundled GNOME extensions declare support for
**GNOME 49 only**. Other GNOME versions are not currently supported by this package.

## What it does

- Uses the color selected in Waywallen (`waywallen.scheme_color`), then the wallpaper's
  `schemecolor`. If neither provides a usable color, it extracts one from the wallpaper preview.
- Generates accent styles for GNOME Shell, GTK 3, and GTK 4 without replacing application backgrounds.
- Publishes the exact RGB accent through the Settings portal for compatible applications,
  including Flatpak applications. Other settings are forwarded to GNOME.
- Keeps the nearest built-in GNOME accent as a fallback for applications that only support presets.
- Checks Waywallen's configuration and database every three seconds and skips unchanged palettes.
- Reloads Shell accent styles automatically after wallpaper changes, while preserving base styles
  and other extensions' styles. Does not force a light/dark mode switch.

This is an independent integration. Install and configure
[Waywallen](https://github.com/waywallen/waywallen) separately; this project does not render wallpapers.

## Requirements

Run the installer as your regular desktop user, from a terminal inside your GNOME session.
Do not use `sudo python3 install.py` or run it inside a container.

| Requirement | Notes |
| --- | --- |
| GNOME Shell 49 | The tested session is Wayland. X11 has not been verified. |
| Waywallen Flatpak | App ID: `org.waywallen.waywallen`; requires the v2 database layout below. |
| Python 3.11 or newer | The system Python at `/usr/bin/python3` must provide PyGObject with `Gio` and `GLib`. No pip dependencies. |
| ImageMagick 7 | The installer requires the `magick` command; `convert` alone is insufficient. |
| GTK 4.16 or newer | Required for the generated GTK 4 CSS custom properties. GTK 3 styles are generated separately. |
| GNOME tools | `gsettings`, `glib-compile-schemas`, and `gnome-extensions`. |
| Session services | A working user systemd instance and session D-Bus. |
| Desktop portal | `xdg-desktop-portal`, the GNOME backend, and an existing GNOME portal configuration. |
| Standard Linux tools | Bash, coreutils, grep, sed, awk, and find. Git is needed only to clone or update. |

The installer includes **User Themes version 80 for GNOME 49** in `user-theme.zip`.
It installs this extension if absent and enables it alongside Waywallen Accents.
If User Themes is already installed, make sure that copy supports GNOME 49.

Optional: FFmpeg improves GIF frame sampling. Wallust is not required; its template integration
is disabled by default. No extra Flatpak permissions are required to receive the portal accent.
Applications still decide whether and how to use that accent.

### Install dependencies on Fedora 43

On an existing Fedora GNOME desktop:

```bash
sudo dnf install git python3 python3-gobject ImageMagick glib2 \
  gnome-shell xdg-desktop-portal xdg-desktop-portal-gnome flatpak
```

To run the test suite, also install:

```bash
sudo dnf install gtk3 gtk4 gjs dbus-daemon
```

Other distributions need equivalent packages and GNOME 49. Package names may differ.
The installer checks some prerequisites but does not install system packages for you.

## Installation

### 1. Prepare Waywallen

Install Waywallen from [Flathub](https://flathub.org/apps/org.waywallen.waywallen)
or follow its [upstream installation instructions](https://github.com/waywallen/waywallen#quick-start).
With Flathub already configured:

```bash
flatpak install flathub org.waywallen.waywallen
flatpak run org.waywallen.waywallen
```

Finish Waywallen's own GNOME integration setup and select a wallpaper. This project expects:

```text
~/.var/app/org.waywallen.waywallen/config/waywallen/config.toml
~/.var/app/org.waywallen.waywallen/data/waywallen/waywallen-v2.db
```

The configuration must contain `global.last_wallpaper`, and that item must exist in the database.
Wallpaper files or previews referenced by the database must be readable on this computer.
Select or reimport your wallpapers on the new computer rather than copying a database with stale paths.

### 2. Download this project

```bash
git clone https://github.com/Gimas-aza/sync-waywallen-gnome.git
cd sync-waywallen-gnome
```

Alternatively, use GitHub's **Code → Download ZIP**, extract the archive, and open a terminal
in the extracted directory. Keep all project files together, including `user-theme.zip`.
No compilation is needed.

### 3. Test and install

Close Firefox, particularly when upgrading from an earlier version that wrote Firefox color overrides.
End any active screen sharing or other portal-dependent operation: installation restarts
`xdg-desktop-portal`.

```bash
python3 test.py
python3 install.py
```

Tests use temporary files and isolated or mocked services; they do not install into your real home.
They cover wallpaper lookup, color generation, GTK CSS parsing, caching, invalid images,
watcher updates, installation and rollback, Firefox migration, portal behavior, and Shell theme reloads.
A passing suite does not replace checking your actual desktop after installation.

The installer saves a backup before modifying files, installs the scripts and extensions,
configures the Settings portal route, generates the first palette, and enables the watcher.
It leaves other portal routes as configured. Your light/dark preference is preserved.

### 4. Log out and log back in

**A full logout/login is required after the first installation or a Shell extension code update.**
GNOME caches extension code for the session. Locking and unlocking the screen is not sufficient.
After this login, wallpaper changes reload Shell accent styles automatically.
Reopen applications once if they still show the old accent.

## Verify the installation

```bash
systemctl --user is-active waywallen-colors.service waywallen-settings.service
```

Both services should report `active`. Confirm **Waywallen Accents** and **User Themes** are enabled
in GNOME's Extensions app. Then select another wallpaper in Waywallen and wait a few seconds.
Choose wallpapers with different accent colors to see a visible change.

Useful commands:

```bash
# Force a refresh from the current Waywallen selection.
~/.local/bin/sync-waywallen-colors --force

# Test a specific image; the watcher may replace its colors on the next Waywallen change.
~/.local/bin/sync-waywallen-colors --force /absolute/path/to/image.png

# Inspect service status and recent logs.
systemctl --user status waywallen-colors.service waywallen-settings.service
journalctl --user -u waywallen-colors.service -u waywallen-settings.service -n 50 --no-pager
```

No manual color configuration is needed for the standard Flatpak layout.

## Updates

From your cloned project directory:

```bash
git pull --ff-only
python3 test.py
python3 install.py
```

Follow the same Firefox and portal precautions as for the initial installation.
Log out and back in if extension code changed. Each installation creates a separate backup.
ZIP users can download and extract the updated project, then run the same test and install commands.

## Stop or uninstall

To stop automatic wallpaper watching:

```bash
systemctl --user disable --now waywallen-colors.service
```

This leaves the current colors, extensions, and Settings portal integration installed.
For a full rollback, use the backup created by the installation you want to undo:

```bash
ls -1 ~/.local/state/waywallen-colors/backups/
```

Close Firefox and end portal-dependent operations. Replace `BACKUP_DIRECTORY` with the chosen
folder name, usually a timestamp:

```bash
python3 "$HOME/.local/state/waywallen-colors/backups/BACKUP_DIRECTORY/restore.py"
```

Use the copy of `restore.py` inside that backup, not the top-level project copy.
Rollback restores saved files, GNOME extension/accent settings, and portal routing;
removes files that did not exist before installation; and restores previous service states.
Changes you made later to those managed files or settings can be overwritten.
Other Firefox preferences are preserved. Log out and log back in, then reopen applications.
Keep the backup until you no longer need rollback.

## Troubleshooting

- **`Missing dependency: magick`:** install ImageMagick 7. The installer requires this command
  even if your distribution still provides ImageMagick 6's `convert`.
- **`No module named gi`:** install PyGObject for `/usr/bin/python3`. Use system Python,
  not an isolated virtual environment.
- **`GNOME portal configuration not found`:** install your distribution's GNOME portal backend
  and confirm its `gnome-portals.conf` or `portals.conf` exists. Run from a normal GNOME session.
- **No selected wallpaper, missing database, or SQLite errors:** launch Waywallen, select a wallpaper,
  and check the two expected paths above. New Waywallen database schemas may require updating
  `waywallen-current.py`; AppImage/native layouts are not automatically detected.
- **Services cannot connect to the session bus:** run as your logged-in desktop user, without sudo.
  Check `systemctl --user status` and your GNOME session.
- **Shell colors do not change:** check GNOME is version 49 (`gnome-shell --version`), verify both
  extensions are enabled, and log out/in after installation. Inspect the watcher logs above.
- **An application keeps its own colors:** reopen it. Custom themes, fixed application styles,
  sandbox access to GTK CSS, and limited portal support can prevent matching the exact accent.
  The portal does not override an application's own styling decisions.

## Limitations

- Compatibility is tied to GNOME 49 and the Waywallen v2 SQLite schema.
- One global Waywallen selection produces one shared GNOME palette, including on multiple monitors.
- The watcher reads Waywallen's database in read-only mode. It does not migrate or repair that database.
- Live wallpaper rendering and hardware/driver setup belong to Waywallen, not this project.
- Existing GTK CSS imports are preserved, but other theme managers can conflict with the generated colors.
- Exact RGB is available to compatible portal clients; some applications use only GNOME's preset fallback.

## License and credits

Project code is distributed under the [MIT license](LICENSE), retaining the original copyright notice.
The bundled `user-theme.zip` is the official GNOME **User Themes** extension, version 80 for GNOME 49.
It is distributed separately under its GPL license; its source and `COPYING` are included in the archive.
See the [GNOME Shell Extensions upstream project](https://gitlab.gnome.org/GNOME/gnome-shell-extensions).

Waywallen is developed separately by its [upstream contributors](https://github.com/waywallen/waywallen).
