# Smart Folder Organizer

A native Linux desktop application built for **Fedora Workstation (GNOME 45+)** using **Python 3**, **GTK 4.12**, and **Libadwaita 1.4**.

Smart Folder Organizer analyzes files in any chosen directory (such as `Downloads` or `Desktop`) and automatically sorts them into neatly structured subfolders. It is built strictly around **safety**, **previewability**, and **undoability**.

---

## Highlights & Features

- **Multi-Layer Classification Engine**:
  - **Layer 1 (Extension & MIME)**: Sorts into primary categories (Images, Videos, Audio, Documents, Spreadsheets, Presentations, Archives, Code, Installers, ISOs, Fonts, Other).
  - **Layer 2 (Filename Keywords)**: Intelligently detects patterns like `invoice`, `receipt`, `resume`, `screenshot`, `ticket`, `assignment` and groups them into specialized subfolders (e.g. `Documents/Invoices`, `Images/Screenshots`).
  - **Layer 3 (Content-Aware Inspection)**: Safely inspects the first ~2,000 characters of text files, Markdown, PDFs, and Word documents in a background thread to identify context (financial terms, resume headers, academic abstracts).
  - **Customizable Rules**: Saved in `~/.config/smart-folder-organizer/rules.json`.
- **Preview Before Moving**:
  - Interactive file list grouped by category.
  - Checkboxes allow selecting or deselecting specific files before running.
  - Live summary of selected files, file sizes, and destination counts.
- **Strictly Safe Operations**:
  - **Never Overwrites**: On filename collisions, appends incremental counters like `report (1).pdf` and `report (2).pdf`.
  - **Process Locks**: Scans `/proc` to verify files are not currently open in other processes.
  - **Protected Paths**: Self-protects application configuration and state files.
  - **Dry-Run Mode**: Simulates operations with complete safety.
- **One-Click Undo**:
  - Every batch operation is logged to `~/.local/share/smart-folder-organizer/history.json`.
  - The UI presents an instant "Undo" toast and header bar button to restore files to their exact original locations and remove empty created folders.
- **Native GNOME HIG Design**:
  - Libadwaita 1.4 widgets: `Adw.ApplicationWindow`, `Adw.ToolbarView`, `Adw.HeaderBar`, `Adw.PreferencesWindow`, `Adw.ActionRow`, `Adw.StatusPage`, `Adw.ToastOverlay`.
  - Responsive layouts, light/dark style management, and symbolic icons.
  - Modern `Gtk.FileDialog` (GTK 4.10+) folder selection.
- **Headless CLI Mode**:
  - Full CLI interface for terminal power users, scripts, and automated cron jobs.

---

## Project Structure

```text
smart-folder-organizer/
├── smart_folder_organizer/
│   ├── __init__.py           # Package initialization & version
│   ├── __main__.py           # python3 -m smart_folder_organizer runner
│   ├── main.py               # Application entry point & CLI parser
│   ├── window.py             # GTK 4 / Libadwaita main application window
│   ├── classifier.py         # 3-layer classification engine
│   ├── mover.py              # Safe file moves, conflict renamer & safety checks
│   ├── history.py            # Batch operation logging & Undo manager
│   ├── settings.py           # Preferences window & configuration manager
│   └── rules_default.json    # Default category & keyword definitions
├── data/
│   ├── com.aniket.SmartFolderOrganizer.desktop        # GNOME desktop launcher
│   ├── com.aniket.SmartFolderOrganizer.metainfo.xml   # AppStream metadata
│   └── icons/
│       └── hicolor/scalable/apps/
│           ├── com.aniket.SmartFolderOrganizer.svg          # Application icon
│           └── com.aniket.SmartFolderOrganizer-symbolic.svg # Symbolic icon
├── tests/
│   ├── __init__.py
│   ├── test_classifier.py    # Unit tests for 3-layer classifier & date sorting
│   └── test_mover.py         # Unit tests for conflict renaming, dry-run, & undo
├── install.sh                # Fedora dnf installer & desktop integrator
├── pyproject.toml            # PEP 517 / 621 packaging metadata
├── requirements.txt          # Python dependencies
└── README.md
```

---

## Installation (Fedora 40 / 41 / 45 Workstation)

### Step 1: Install System Dependencies
Install the required GNOME and PyGObject development libraries via DNF:

```bash
sudo dnf install python3-gobject gtk4 libadwaita
```

### Step 2: Run Installer
Run the provided automated installer script to install the desktop launcher, icons, CLI binary, and optional PDF/Word dependencies:

```bash
cd smart-folder-organizer
./install.sh
```

The script:
1. Validates system packages via DNF.
2. Creates an optional virtual environment in `~/.local/share/smart-folder-organizer/venv` for `pypdf` and `python-docx` (with system site-packages enabled so PyGObject is inherited).
3. Links the `smart-folder-organizer` executable to `~/.local/bin/`.
4. Copies `.desktop` files, icons, and AppStream metadata to `~/.local/share/` and refreshes the desktop database.

---

## Running the Application

### 1. From GNOME Desktop
Search for **Smart Folder Organizer** in the GNOME Application Grid or pin it to your Dash / Dock.

### 2. From Terminal (GUI)
```bash
smart-folder-organizer
```
Or directly point to a directory:
```bash
smart-folder-organizer ~/Downloads
smart-folder-organizer --downloads
smart-folder-organizer --desktop
```

### 3. Headless CLI Mode (Automation & Scripts)
The application includes a powerful CLI mode reusing the same core classification engine:

```bash
# Dry-run simulation on Downloads
python3 -m smart_folder_organizer --cli --dry-run ~/Downloads

# Organize a folder into a custom destination
python3 -m smart_folder_organizer --cli ~/Downloads --dest ~/CleanDownloads

# Organize with date-based subfolders (e.g. Images/2026/November)
python3 -m smart_folder_organizer --cli --date-based ~/Downloads

# Undo the last organization run from the terminal
python3 -m smart_folder_organizer --cli --undo
```

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>O</kbd> | Open / Choose folder dialog |
| <kbd>Ctrl</kbd> + <kbd>Z</kbd> | Undo last organization batch |
| <kbd>Ctrl</kbd> + <kbd>R</kbd> or <kbd>F5</kbd> | Rescan active folder |
| <kbd>Ctrl</kbd> + <kbd>,</kbd> | Open Preferences |
| <kbd>Ctrl</kbd> + <kbd>Q</kbd> | Quit application |

---

## Running Unit Tests

The test suite covers classifier layers, conflict rename resolution, dry-run simulation, and undo recovery:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

Or using `pytest`:
```bash
pytest tests/ -v
```

---

## Packaging as a Flatpak

To package Smart Folder Organizer for Flathub or local Flatpak installation:

1. Install `flatpak-builder`:
   ```bash
   sudo dnf install flatpak-builder
   ```

2. Example manifest `com.aniket.SmartFolderOrganizer.json`:
   ```json
   {
     "app-id": "com.aniket.SmartFolderOrganizer",
     "runtime": "org.gnome.Platform",
     "runtime-version": "45",
     "sdk": "org.gnome.Sdk",
     "command": "smart-folder-organizer",
     "finish-args": [
       "--share=ipc",
       "--socket=fallback-x11",
       "--socket=wayland",
       "--filesystem=xdg-download",
       "--filesystem=xdg-desktop",
       "--filesystem=home"
     ],
     "modules": [
       {
         "name": "python-dependencies",
         "buildsystem": "simple",
         "build-commands": [
           "pip3 install --verbose --exists-action=i --no-index --find-links=\"file://${PWD}\" --prefix=${FLATPAK_DEST} pypdf python-docx"
         ]
       },
       {
         "name": "smart-folder-organizer",
         "buildsystem": "simple",
         "build-commands": [
           "pip3 install --no-deps --prefix=${FLATPAK_DEST} .",
           "install -Dm644 data/com.aniket.SmartFolderOrganizer.desktop ${FLATPAK_DEST}/share/applications/com.aniket.SmartFolderOrganizer.desktop",
           "install -Dm644 data/com.aniket.SmartFolderOrganizer.metainfo.xml ${FLATPAK_DEST}/share/metainfo/com.aniket.SmartFolderOrganizer.metainfo.xml",
           "install -Dm644 data/icons/hicolor/scalable/apps/com.aniket.SmartFolderOrganizer.svg ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/com.aniket.SmartFolderOrganizer.svg",
           "install -Dm644 data/icons/hicolor/scalable/apps/com.aniket.SmartFolderOrganizer-symbolic.svg ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/com.aniket.SmartFolderOrganizer-symbolic.svg"
         ],
         "sources": [
           {
             "type": "dir",
             "path": "."
           }
         ]
       }
     ]
   }
   ```

3. Build and install locally:
   ```bash
   flatpak-builder --user --install --force-clean build-dir com.aniket.SmartFolderOrganizer.json
   flatpak run com.aniket.SmartFolderOrganizer
   ```

---

## License

GNU General Public License v3.0 or later (GPL-3.0-or-later).
