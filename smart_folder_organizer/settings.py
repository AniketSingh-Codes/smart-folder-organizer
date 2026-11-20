"""Application Preferences and Settings Manager for Smart Folder Organizer.

Provides persistent configuration management and a GNOME HIG compliant
Adw.PreferencesWindow with Libadwaita 1.4 compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk


DEFAULT_SETTINGS: Dict[str, Any] = {
    "destination_mode": "inside",  # "inside" or "custom"
    "custom_destination_path": "",
    "content_aware": True,
    "include_subfolders": False,
    "date_based_sorting": False,
    "ignore_hidden": True,
    "ignore_partial": True,
    "auto_watch": False,
    "dry_run": False,
}


class SettingsManager:
    """Manages application settings stored in ~/.config/smart-folder-organizer/settings.json."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is None:
            self.config_dir = Path.home() / ".config" / "smart-folder-organizer"
        else:
            self.config_dir = Path(config_dir)

        self.settings_file = self.config_dir / "settings.json"
        self.settings: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Loads settings from file or applies defaults."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.settings_file.exists():
            self.settings = dict(DEFAULT_SETTINGS)
            self.save()
        else:
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge defaults for any missing keys
                    self.settings = dict(DEFAULT_SETTINGS)
                    self.settings.update(loaded)
            except Exception:
                self.settings = dict(DEFAULT_SETTINGS)

    def save(self) -> None:
        """Persists current settings to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.save()


class SettingsWindow(Adw.PreferencesWindow):
    """GNOME HIG compliant Preferences Window (Libadwaita 1.4 compatible)."""

    def __init__(
        self,
        settings_manager: SettingsManager,
        classifier: Any,
        parent_window: Gtk.Window,
        on_settings_changed: Optional[Callable[[str, Any], None]] = None
    ) -> None:
        super().__init__()
        self.settings = settings_manager
        self.classifier = classifier
        self.on_settings_changed = on_settings_changed

        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_title("Preferences")
        self.set_default_size(560, 600)

        self._build_general_page()
        self._build_rules_page()

    def _notify_change(self, key: str, value: Any) -> None:
        self.settings.set(key, value)
        if self.on_settings_changed:
            self.on_settings_changed(key, value)

    def _build_general_page(self) -> None:
        page = Adw.PreferencesPage()
        page.set_title("General")
        page.set_icon_name("preferences-system-symbolic")

        # Destination Group
        dest_group = Adw.PreferencesGroup()
        dest_group.set_title("Destination")
        dest_group.set_description("Where organized files and categorized subfolders should be placed")

        self.dest_mode_switch = Adw.SwitchRow()
        self.dest_mode_switch.set_title("Use Custom Destination Directory")
        self.dest_mode_switch.set_subtitle("When off, files are sorted into an 'Organized' folder inside the scanned directory")
        is_custom = self.settings.get("destination_mode") == "custom"
        self.dest_mode_switch.set_active(is_custom)
        self.dest_mode_switch.connect("notify::active", self._on_dest_mode_toggled)
        dest_group.add(self.dest_mode_switch)

        self.custom_path_row = Adw.ActionRow()
        self.custom_path_row.set_title("Custom Folder")
        custom_path = self.settings.get("custom_destination_path", "")
        self.custom_path_row.set_subtitle(custom_path if custom_path else "No folder selected")
        self.custom_path_row.set_sensitive(is_custom)

        choose_btn = Gtk.Button(label="Choose…")
        choose_btn.set_valign(Gtk.Align.CENTER)
        choose_btn.connect("clicked", self._on_choose_custom_dest)
        self.custom_path_row.add_suffix(choose_btn)
        dest_group.add(self.custom_path_row)

        page.add(dest_group)

        # Classification & Sorting Group
        sort_group = Adw.PreferencesGroup()
        sort_group.set_title("Sorting & Inspection")

        self.content_row = Adw.SwitchRow()
        self.content_row.set_title("Content-Aware Classification")
        self.content_row.set_subtitle("Inspect the first 2,000 characters of text, PDF, and DOCX files in the background")
        self.content_row.set_active(self.settings.get("content_aware", True))
        self.content_row.connect("notify::active", lambda row, pspec: self._notify_change("content_aware", row.get_active()))
        sort_group.add(self.content_row)

        self.date_row = Adw.SwitchRow()
        self.date_row.set_title("Date-Based Subfolders")
        self.date_row.set_subtitle("Group categorized files into Year/Month folders (e.g. Images/2026/November)")
        self.date_row.set_active(self.settings.get("date_based_sorting", False))
        self.date_row.connect("notify::active", lambda row, pspec: self._notify_change("date_based_sorting", row.get_active()))
        sort_group.add(self.date_row)

        self.subfolder_row = Adw.SwitchRow()
        self.subfolder_row.set_title("Scan Subfolders Recursively")
        self.subfolder_row.set_subtitle("Search for files inside nested directories within the chosen folder")
        self.subfolder_row.set_active(self.settings.get("include_subfolders", False))
        self.subfolder_row.connect("notify::active", lambda row, pspec: self._notify_change("include_subfolders", row.get_active()))
        sort_group.add(self.subfolder_row)

        page.add(sort_group)

        # File Filter Group
        filter_group = Adw.PreferencesGroup()
        filter_group.set_title("File Exclusions")

        self.hidden_row = Adw.SwitchRow()
        self.hidden_row.set_title("Ignore Hidden Files")
        self.hidden_row.set_subtitle("Skip files and directories beginning with a period (.)")
        self.hidden_row.set_active(self.settings.get("ignore_hidden", True))
        self.hidden_row.connect("notify::active", lambda row, pspec: self._notify_change("ignore_hidden", row.get_active()))
        filter_group.add(self.hidden_row)

        self.partial_row = Adw.SwitchRow()
        self.partial_row.set_title("Ignore Incomplete Downloads")
        self.partial_row.set_subtitle("Skip .part, .crdownload, .tmp, and active download buffers")
        self.partial_row.set_active(self.settings.get("ignore_partial", True))
        self.partial_row.connect("notify::active", lambda row, pspec: self._notify_change("ignore_partial", row.get_active()))
        filter_group.add(self.partial_row)

        page.add(filter_group)

        # Automation Group
        auto_group = Adw.PreferencesGroup()
        auto_group.set_title("Automation")

        self.watch_row = Adw.SwitchRow()
        self.watch_row.set_title("Auto-Watch Current Folder")
        self.watch_row.set_subtitle("Monitor directory with Gio.FileMonitor and send desktop notifications when new files arrive")
        self.watch_row.set_active(self.settings.get("auto_watch", False))
        self.watch_row.connect("notify::active", lambda row, pspec: self._notify_change("auto_watch", row.get_active()))
        auto_group.add(self.watch_row)

        page.add(auto_group)

        self.add(page)

    def _build_rules_page(self) -> None:
        page = Adw.PreferencesPage()
        page.set_title("Rules")
        page.set_icon_name("view-list-symbolic")

        rules_group = Adw.PreferencesGroup()
        rules_group.set_title("Classification Rules")
        rules_group.set_description(f"Rules are stored in {self.classifier.rules_path}")

        # Open in editor action
        edit_row = Adw.ActionRow()
        edit_row.set_title("Edit Rules File")
        edit_row.set_subtitle("Open rules.json in your default text editor")
        edit_btn = Gtk.Button(label="Open File")
        edit_btn.set_valign(Gtk.Align.CENTER)
        edit_btn.connect("clicked", self._on_open_rules_file)
        edit_row.add_suffix(edit_btn)
        rules_group.add(edit_row)

        # Reset rules action
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset Rules to Default")
        reset_row.set_subtitle("Discard custom edits and restore default categorization rules")
        reset_btn = Gtk.Button(label="Reset…")
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_rules)
        reset_row.add_suffix(reset_btn)
        rules_group.add(reset_row)

        page.add(rules_group)

        # Keyword preview group
        preview_group = Adw.PreferencesGroup()
        preview_group.set_title("Active Keyword Rules")

        keyword_rules = self.classifier.rules.get("keyword_rules", [])
        for rule in keyword_rules[:8]:  # Show top rules
            row = Adw.ActionRow()
            row.set_title(rule.get("name", "Rule"))
            kws = ", ".join(rule.get("keywords", []))
            target = f"{rule.get('category')}/{rule.get('subcategory')}"
            row.set_subtitle(f"Keywords: {kws} → {target}")
            preview_group.add(row)

        page.add(preview_group)

        self.add(page)

    def _on_dest_mode_toggled(self, switch_row: Adw.SwitchRow, pspec: Any) -> None:
        is_custom = switch_row.get_active()
        mode = "custom" if is_custom else "inside"
        self._notify_change("destination_mode", mode)
        self.custom_path_row.set_sensitive(is_custom)

    def _on_choose_custom_dest(self, button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Custom Destination Folder")

        def on_folder_selected(dlg: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                gfile = dlg.select_folder_finish(result)
                if gfile:
                    path = gfile.get_path()
                    if path:
                        self.custom_path_row.set_subtitle(path)
                        self._notify_change("custom_destination_path", path)
            except GLib.Error:
                pass  # Cancelled

        dialog.select_folder(self, None, on_folder_selected)

    def _on_open_rules_file(self, button: Gtk.Button) -> None:
        rules_uri = self.classifier.rules_path.as_uri()
        try:
            Gtk.show_uri(self, rules_uri, Gdk.CURRENT_TIME if hasattr(Gtk, "Gdk") else 0)
        except Exception:
            Gio.AppInfo.launch_default_for_uri(rules_uri, None)

    def _on_reset_rules(self, button: Gtk.Button) -> None:
        # Libadwaita 1.4 compatible confirmation dialog
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Reset Rules to Default?",
            body="All custom keyword and category definitions in rules.json will be replaced with defaults."
        )
        dialog.add_response("cancel", "_Cancel")
        dialog.add_response("reset", "_Reset Rules")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(dlg: Adw.MessageDialog, response_id: str) -> None:
            if response_id == "reset":
                self.classifier.reset_rules_to_default()
                self._notify_change("rules_updated", True)

        dialog.connect("response", on_response)
        dialog.present()
