"""Main Application Window for Smart Folder Organizer.

Built with GTK 4.12 and Libadwaita 1.4 adhering strictly to the GNOME HIG.
Implements non-blocking worker threads, preview-before-moving, undo toasts,
and Gtk.FileDialog for folder selection.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .classifier import ClassificationResult, Classifier
from .history import HistoryManager
from .mover import FileMover, MoveItem, MoveResult
from .settings import SettingsManager, SettingsWindow


class MainWindow(Adw.ApplicationWindow):
    """Primary application window featuring responsive layouts and preview controls."""

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)

        self.settings_manager = SettingsManager()
        self.classifier = Classifier()
        self.mover = FileMover()
        self.history = HistoryManager()

        self.current_folder: Optional[Path] = None
        self.planned_items: List[MoveItem] = []
        self.file_monitor: Optional[Gio.FileMonitor] = None
        self.cancel_requested = False

        self.set_title("Smart Folder Organizer")
        self.set_default_size(920, 680)

        self._build_ui()
        self._setup_actions()
        self._update_undo_state()

    # -------------------------------------------------------------------------
    # UI Construction
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(self.toolbar_view)

        # HeaderBar
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        # Window Title
        self.title_widget = Adw.WindowTitle(
            title="Smart Folder Organizer",
            subtitle="No folder selected"
        )
        self.header_bar.set_title_widget(self.title_widget)

        # Top Bar Left Controls (Quick Folder Buttons)
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Downloads Button
        self.btn_downloads = Gtk.Button(
            icon_name="folder-download-symbolic",
            tooltip_text="Scan Downloads"
        )
        self.btn_downloads.connect("clicked", self._on_quick_downloads_clicked)
        left_box.append(self.btn_downloads)

        # Desktop Button
        self.btn_desktop = Gtk.Button(
            icon_name="user-desktop-symbolic",
            tooltip_text="Scan Desktop"
        )
        self.btn_desktop.connect("clicked", self._on_quick_desktop_clicked)
        left_box.append(self.btn_desktop)

        # Custom Folder Dialog Button
        self.btn_open = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text="Choose Folder… (Ctrl+O)"
        )
        self.btn_open.connect("clicked", self._on_choose_folder_clicked)
        left_box.append(self.btn_open)

        self.header_bar.pack_start(left_box)

        # Top Bar Right Controls (Undo, Rescan, App Menu)
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.btn_undo = Gtk.Button(
            icon_name="edit-undo-symbolic",
            tooltip_text="Undo Last Organization (Ctrl+Z)"
        )
        self.btn_undo.set_sensitive(False)
        self.btn_undo.connect("clicked", self._on_undo_clicked)
        right_box.append(self.btn_undo)

        self.btn_rescan = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Rescan Current Folder (Ctrl+R)"
        )
        self.btn_rescan.set_sensitive(False)
        self.btn_rescan.connect("clicked", lambda b: self._start_scan())
        right_box.append(self.btn_rescan)

        # Primary Menu
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_menu_model(self._create_menu_model())
        right_box.append(menu_button)

        self.header_bar.pack_end(right_box)

        # Main Stack for Different Application Views
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.toolbar_view.set_content(self.stack)

        # 1. Initial Prompt View
        self._build_welcome_view()

        # 2. Scanning Progress View
        self._build_scanning_view()

        # 3. Empty / Nothing to Organize View
        self._build_empty_view()

        # 4. Preview & Confirmation View
        self._build_preview_view()

        # Bottom Action Bar
        self._build_bottom_bar()

    def _create_menu_model(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu.append("Undo Last Operation", "win.undo")
        menu.append("Keyboard Shortcuts", "win.shortcuts")
        menu.append("About Smart Folder Organizer", "win.about")
        return menu

    def _build_welcome_view(self) -> None:
        self.welcome_page = Adw.StatusPage(
            icon_name="folder-saved-search-symbolic",
            title="Organize Your Folders",
            description="Select your Downloads, Desktop, or any custom folder to automatically categorize and clean up your files."
        )

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(16)

        dl_btn = Gtk.Button(label="Scan Downloads")
        dl_btn.add_css_class("suggested-action")
        dl_btn.add_css_class("pill")
        dl_btn.connect("clicked", self._on_quick_downloads_clicked)
        btn_box.append(dl_btn)

        dt_btn = Gtk.Button(label="Scan Desktop")
        dt_btn.add_css_class("pill")
        dt_btn.connect("clicked", self._on_quick_desktop_clicked)
        btn_box.append(dt_btn)

        choose_btn = Gtk.Button(label="Choose Other Folder…")
        choose_btn.add_css_class("pill")
        choose_btn.connect("clicked", self._on_choose_folder_clicked)
        btn_box.append(choose_btn)

        self.welcome_page.set_child(btn_box)
        self.stack.add_named(self.welcome_page, "welcome")

    def _build_scanning_view(self) -> None:
        self.scanning_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER
        )
        self.scanning_box.set_margin_start(40)
        self.scanning_box.set_margin_end(40)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.scanning_box.append(self.spinner)

        self.scan_title_label = Gtk.Label(label="Scanning and Analyzing Files…")
        self.scan_title_label.add_css_class("title-2")
        self.scanning_box.append(self.scan_title_label)

        self.scan_progress_bar = Gtk.ProgressBar()
        self.scan_progress_bar.set_size_request(380, -1)
        self.scan_progress_bar.set_show_text(False)
        self.scanning_box.append(self.scan_progress_bar)

        self.scan_file_label = Gtk.Label(label="Preparing…")
        self.scan_file_label.add_css_class("dim-label")
        self.scan_file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE if hasattr(Gtk, "Pango") else 3)
        self.scanning_box.append(self.scan_file_label)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("pill")
        cancel_btn.set_halign(Gtk.Align.CENTER)
        cancel_btn.connect("clicked", self._on_cancel_operation)
        self.scanning_box.append(cancel_btn)

        self.stack.add_named(self.scanning_box, "scanning")

    def _build_empty_view(self) -> None:
        self.empty_page = Adw.StatusPage(
            icon_name="object-select-symbolic",
            title="Nothing to Organize",
            description="All files in this folder are either already organized, ignored by filters, or the directory is empty."
        )

        rescan_btn = Gtk.Button(label="Rescan Folder")
        rescan_btn.add_css_class("pill")
        rescan_btn.set_halign(Gtk.Align.CENTER)
        rescan_btn.connect("clicked", lambda b: self._start_scan())
        self.empty_page.set_child(rescan_btn)

        self.stack.add_named(self.empty_page, "empty")

    def _build_preview_view(self) -> None:
        self.preview_scrolled = Gtk.ScrolledWindow()
        self.preview_scrolled.set_vexpand(True)
        self.preview_scrolled.set_hexpand(True)

        self.preview_clamp = Adw.Clamp()
        self.preview_clamp.set_maximum_size(900)
        self.preview_clamp.set_tightening_threshold(700)
        self.preview_scrolled.set_child(self.preview_clamp)

        self.preview_content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18
        )
        self.preview_content_box.set_margin_top(16)
        self.preview_content_box.set_margin_bottom(24)
        self.preview_content_box.set_margin_start(16)
        self.preview_content_box.set_margin_end(16)
        self.preview_clamp.set_child(self.preview_content_box)

        self.stack.add_named(self.preview_scrolled, "preview")

    def _build_bottom_bar(self) -> None:
        self.bottom_bar = Gtk.ActionBar()
        self.toolbar_view.add_bottom_bar(self.bottom_bar)
        self.bottom_bar.set_revealed(False)

        # Left: Selection Toggles & Summary Label
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.select_all_btn = Gtk.Button(label="Select All")
        self.select_all_btn.connect("clicked", self._on_select_all_clicked)
        left_box.append(self.select_all_btn)

        self.deselect_all_btn = Gtk.Button(label="Deselect All")
        self.deselect_all_btn.connect("clicked", self._on_deselect_all_clicked)
        left_box.append(self.deselect_all_btn)

        self.summary_label = Gtk.Label()
        self.summary_label.add_css_class("caption")
        left_box.append(self.summary_label)

        self.bottom_bar.pack_start(left_box)

        # Right: Dry Run Switch & Organize Action Button
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        dry_run_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dry_run_label = Gtk.Label(label="Dry Run")
        self.dry_run_switch = Gtk.Switch()
        self.dry_run_switch.set_active(self.settings_manager.get("dry_run", False))
        dry_run_box.append(dry_run_label)
        dry_run_box.append(self.dry_run_switch)
        right_box.append(dry_run_box)

        self.btn_organize = Gtk.Button(label="Organize Files")
        self.btn_organize.add_css_class("suggested-action")
        self.btn_organize.add_css_class("pill")
        self.btn_organize.connect("clicked", self._on_execute_organize)
        right_box.append(self.btn_organize)

        self.bottom_bar.pack_end(right_box)

    # -------------------------------------------------------------------------
    # Actions & Keybindings
    # -------------------------------------------------------------------------

    def _setup_actions(self) -> None:
        # Ctrl+O: Open Folder
        act_open = Gio.SimpleAction.new("open_folder", None)
        act_open.connect("activate", lambda a, p: self._on_choose_folder_clicked(None))
        self.add_action(act_open)
        self.get_application().set_accels_for_action("win.open_folder", ["<Primary>o"])

        # Ctrl+Z: Undo
        act_undo = Gio.SimpleAction.new("undo", None)
        act_undo.connect("activate", lambda a, p: self._on_undo_clicked(None))
        self.add_action(act_undo)
        self.get_application().set_accels_for_action("win.undo", ["<Primary>z"])

        # Ctrl+R / F5: Refresh
        act_refresh = Gio.SimpleAction.new("refresh", None)
        act_refresh.connect("activate", lambda a, p: self._start_scan())
        self.add_action(act_refresh)
        self.get_application().set_accels_for_action("win.refresh", ["<Primary>r", "F5"])

        # Preferences
        act_pref = Gio.SimpleAction.new("preferences", None)
        act_pref.connect("activate", lambda a, p: self._on_preferences_clicked())
        self.add_action(act_pref)
        self.get_application().set_accels_for_action("win.preferences", ["<Primary>comma"])

        # About
        act_about = Gio.SimpleAction.new("about", None)
        act_about.connect("activate", lambda a, p: self._show_about_dialog())
        self.add_action(act_about)

        # Shortcuts
        act_shortcuts = Gio.SimpleAction.new("shortcuts", None)
        act_shortcuts.connect("activate", lambda a, p: self._show_shortcuts_dialog())
        self.add_action(act_shortcuts)

    # -------------------------------------------------------------------------
    # Folder Selection Handling
    # -------------------------------------------------------------------------

    def _on_quick_downloads_clicked(self, button: Gtk.Button) -> None:
        downloads_path = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads_path and os.path.exists(downloads_path):
            self.set_target_folder(Path(downloads_path))
        else:
            self._show_toast("Downloads directory not found on this system.")

    def _on_quick_desktop_clicked(self, button: Gtk.Button) -> None:
        desktop_path = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
        if desktop_path and os.path.exists(desktop_path):
            self.set_target_folder(Path(desktop_path))
        else:
            self._show_toast("Desktop directory not found on this system.")

    def _on_choose_folder_clicked(self, button: Optional[Gtk.Button]) -> None:
        # Gtk.FileDialog (GTK 4.10+ standard API)
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Select Folder to Organize")

        if self.current_folder and self.current_folder.exists():
            file_dialog.set_initial_folder(Gio.File.new_for_path(str(self.current_folder)))

        def on_finish(dlg: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                gfile = dlg.select_folder_finish(result)
                if gfile:
                    path_str = gfile.get_path()
                    if path_str:
                        self.set_target_folder(Path(path_str))
            except GLib.Error:
                pass  # Dismissed by user

        file_dialog.select_folder(self, None, on_finish)

    def set_target_folder(self, folder: Path) -> None:
        """Sets active target folder and triggers scan."""
        self.current_folder = folder
        self.title_widget.set_subtitle(str(folder))
        self.btn_rescan.set_sensitive(True)

        # Setup Gio.FileMonitor if auto-watch is enabled
        self._setup_file_monitor()

        # Start scanning in background
        self._start_scan()

    def _setup_file_monitor(self) -> None:
        if self.file_monitor:
            self.file_monitor.cancel()
            self.file_monitor = None

        if not self.current_folder or not self.settings_manager.get("auto_watch", False):
            return

        try:
            gfile = Gio.File.new_for_path(str(self.current_folder))
            self.file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.file_monitor.connect("changed", self._on_folder_changed_event)
        except Exception:
            pass

    def _on_folder_changed_event(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Optional[Gio.File],
        event_type: Gio.FileMonitorEvent
    ) -> None:
        # Triggered when new file arrives
        if event_type == Gio.FileMonitorEvent.CREATED:
            filename = file.get_basename()
            GLib.idle_add(self._notify_new_file_arrived, filename)

    def _notify_new_file_arrived(self, filename: str) -> None:
        self._show_toast(f"New file detected: {filename}. Click Rescan to include.")

    # -------------------------------------------------------------------------
    # Scanning Engine (Non-blocking Background Thread)
    # -------------------------------------------------------------------------

    def _start_scan(self) -> None:
        if not self.current_folder or not self.current_folder.exists():
            self.stack.set_visible_child_name("welcome")
            self.bottom_bar.set_revealed(False)
            return

        self.cancel_requested = False
        self.scan_title_label.set_text("Scanning and Analyzing Files…")
        self.scan_progress_bar.set_fraction(0.0)
        self.scan_file_label.set_text("Discovering items…")
        self.spinner.start()

        self.stack.set_visible_child_name("scanning")
        self.bottom_bar.set_revealed(False)

        worker = threading.Thread(target=self._scan_worker, daemon=True)
        worker.start()

    def _scan_worker(self) -> None:
        target_dir = self.current_folder
        if not target_dir or not target_dir.exists():
            GLib.idle_add(self._on_scan_completed, [])
            return

        content_aware = self.settings_manager.get("content_aware", True)
        date_based = self.settings_manager.get("date_based_sorting", False)
        include_subs = self.settings_manager.get("include_subfolders", False)
        ignore_hidden = self.settings_manager.get("ignore_hidden", True)
        ignore_partial = self.settings_manager.get("ignore_partial", True)
        dest_mode = self.settings_manager.get("destination_mode", "inside")
        custom_path_str = self.settings_manager.get("custom_destination_path", "")

        # Determine destination root
        if dest_mode == "custom" and custom_path_str:
            dest_root = Path(custom_path_str)
        else:
            dest_root = target_dir / "Organized"

        # Discover candidate files
        candidates: List[Path] = []
        try:
            if include_subs:
                for root, dirs, files in os.walk(target_dir):
                    root_path = Path(root)
                    # Skip destination root itself
                    if dest_root.resolve() in root_path.resolve().parents or root_path.resolve() == dest_root.resolve():
                        continue
                    for f in files:
                        candidates.append(root_path / f)
            else:
                for entry in target_dir.iterdir():
                    if entry.is_file():
                        candidates.append(entry)
        except Exception as e:
            GLib.idle_add(self._show_toast, f"Error reading folder: {e}")
            GLib.idle_add(self._on_scan_completed, [])
            return

        total_files = len(candidates)
        planned_moves: List[MoveItem] = []

        for idx, file_path in enumerate(candidates):
            if self.cancel_requested:
                break

            # Skip ignored files
            if self.classifier.is_ignored(file_path, ignore_hidden=ignore_hidden, ignore_partial=ignore_partial):
                continue

            # Update progress on UI thread
            frac = (idx + 1) / total_files if total_files > 0 else 1.0
            filename = file_path.name
            GLib.idle_add(self._update_scan_progress, frac, filename)

            # Classify
            result: ClassificationResult = self.classifier.classify_file(
                file_path=file_path,
                content_aware=content_aware,
                date_based=date_based
            )

            # Plan Move
            item = self.mover.plan_move(
                source_path=file_path,
                dest_root=dest_root,
                target_rel_path=result.target_rel_path,
                category=result.category,
                subcategory=result.subcategory,
                reason=result.reason,
                icon_name=result.icon_name
            )

            if item:
                planned_moves.append(item)

        GLib.idle_add(self._on_scan_completed, planned_moves)

    def _update_scan_progress(self, fraction: float, filename: str) -> None:
        self.scan_progress_bar.set_fraction(fraction)
        self.scan_file_label.set_text(f"Analyzing: {filename}")

    def _on_scan_completed(self, items: List[MoveItem]) -> None:
        self.spinner.stop()
        self.planned_items = items

        if not items:
            self.stack.set_visible_child_name("empty")
            self.bottom_bar.set_revealed(False)
            return

        self._render_preview_list()
        self.stack.set_visible_child_name("preview")
        self.bottom_bar.set_revealed(True)
        self._update_summary()

    def _on_cancel_operation(self, button: Gtk.Button) -> None:
        self.cancel_requested = True
        self._show_toast("Operation cancelled.")

    # -------------------------------------------------------------------------
    # Preview Rendering
    # -------------------------------------------------------------------------

    def _render_preview_list(self) -> None:
        # Clear existing rows
        while child := self.preview_content_box.get_first_child():
            self.preview_content_box.remove(child)

        # Header Info Card
        header_banner = Adw.PreferencesGroup()
        header_banner.set_title("Ready to Organize")
        header_banner.set_description(
            f"Review the files and destinations below. Deselect any files you wish to keep in place."
        )
        self.preview_content_box.append(header_banner)

        # Group items by Category / Subcategory
        groups: Dict[str, List[MoveItem]] = {}
        for item in self.planned_items:
            key = f"{item.category}/{item.subcategory}" if item.subcategory else item.category
            groups.setdefault(key, []).append(item)

        for group_name, group_items in sorted(groups.items()):
            pref_group = Adw.PreferencesGroup()
            pref_group.set_title(group_name)
            pref_group.set_description(f"{len(group_items)} file{'s' if len(group_items) != 1 else ''}")

            for item in group_items:
                row = Adw.ActionRow()
                row.set_title(item.filename)

                # Subtitle: Destination tag + size + match reason
                dest_display = str(item.dest_path.parent.name)
                row.set_subtitle(f"→ {item.dest_dir.name} • {item.formatted_size} • {item.reason}")

                # Prefix: Checkbox
                check = Gtk.CheckButton()
                check.set_active(item.selected)
                check.set_valign(Gtk.Align.CENTER)
                check.connect("toggled", self._on_item_toggled, item)
                row.add_prefix(check)

                # Category Icon
                icon = Gtk.Image.new_from_icon_name(item.icon_name)
                icon.set_pixel_size(24)
                icon.set_valign(Gtk.Align.CENTER)
                row.add_prefix(icon)

                # Destination Tag Suffix
                badge = Gtk.Label(label=dest_display)
                badge.add_css_class("badge")
                badge.set_valign(Gtk.Align.CENTER)
                row.add_suffix(badge)

                pref_group.add(row)

            self.preview_content_box.append(pref_group)

    def _on_item_toggled(self, check: Gtk.CheckButton, item: MoveItem) -> None:
        item.selected = check.get_active()
        self._update_summary()

    def _on_select_all_clicked(self, button: Gtk.Button) -> None:
        for item in self.planned_items:
            item.selected = True
        self._render_preview_list()
        self._update_summary()

    def _on_deselect_all_clicked(self, button: Gtk.Button) -> None:
        for item in self.planned_items:
            item.selected = False
        self._render_preview_list()
        self._update_summary()

    def _update_summary(self) -> None:
        selected = [it for it in self.planned_items if it.selected]
        count = len(selected)
        total_size = sum(it.size for it in selected)

        # Unique destination folders
        dest_folders = {it.dest_dir for it in selected}
        dest_count = len(dest_folders)

        # Human size
        size_str = self._format_size(total_size)
        self.summary_label.set_text(
            f"{count} of {len(self.planned_items)} files selected ({size_str}) → {dest_count} folders"
        )
        self.btn_organize.set_sensitive(count > 0)

    def _format_size(self, size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    # -------------------------------------------------------------------------
    # Organization Execution (Threaded Safe Moves)
    # -------------------------------------------------------------------------

    def _on_execute_organize(self, button: Gtk.Button) -> None:
        selected_items = [it for it in self.planned_items if it.selected]
        if not selected_items:
            return

        dry_run = self.dry_run_switch.get_active()

        self.cancel_requested = False
        self.scan_title_label.set_text("Organizing Files…" if not dry_run else "Simulating Dry Run…")
        self.scan_progress_bar.set_fraction(0.0)
        self.spinner.start()

        self.stack.set_visible_child_name("scanning")
        self.bottom_bar.set_revealed(False)

        worker = threading.Thread(
            target=self._execute_worker,
            args=(selected_items, dry_run),
            daemon=True
        )
        worker.start()

    def _execute_worker(self, items: List[MoveItem], dry_run: bool) -> None:
        def on_progress(current: int, total: int, filename: str) -> None:
            frac = current / total if total > 0 else 1.0
            GLib.idle_add(self._update_execute_progress, frac, filename)

        result: MoveResult = self.mover.execute_moves(
            items=items,
            dry_run=dry_run,
            progress_callback=on_progress,
            cancel_check=lambda: self.cancel_requested
        )

        GLib.idle_add(self._on_execute_completed, result, dry_run)

    def _update_execute_progress(self, frac: float, filename: str) -> None:
        self.scan_progress_bar.set_fraction(frac)
        self.scan_file_label.set_text(f"Moving: {filename}")

    def _on_execute_completed(self, result: MoveResult, dry_run: bool) -> None:
        self.spinner.stop()

        if dry_run:
            msg = f"Dry Run Complete: {result.success_count} files would be moved ({result.skipped_count} skipped)."
            self._show_toast(msg)
            self._start_scan()
            return

        # Record in history for undo capability
        if result.executed_moves and self.current_folder:
            self.history.record_batch(self.current_folder, result.executed_moves)
            self._update_undo_state()

        # Toast notification with Undo Action Button
        toast_msg = f"Organized {result.success_count} files successfully."
        if result.error_count > 0:
            toast_msg += f" ({result.error_count} errors)"

        toast = Adw.Toast(title=toast_msg)
        toast.set_button_label("Undo")
        toast.connect("button-clicked", lambda t: self._on_undo_clicked(None))
        self.toast_overlay.add_toast(toast)

        # Refresh the current folder view
        self._start_scan()

    # -------------------------------------------------------------------------
    # Undo Logic
    # -------------------------------------------------------------------------

    def _on_undo_clicked(self, button: Optional[Gtk.Button]) -> None:
        if not self.history.has_undoable_batch():
            self._show_toast("No recent operations to undo.")
            return

        self.scan_title_label.set_text("Restoring Files (Undo)…")
        self.scan_progress_bar.set_fraction(0.0)
        self.spinner.start()
        self.stack.set_visible_child_name("scanning")
        self.bottom_bar.set_revealed(False)

        worker = threading.Thread(target=self._undo_worker, daemon=True)
        worker.start()

    def _undo_worker(self) -> None:
        def on_progress(current: int, total: int, filename: str) -> None:
            frac = current / total if total > 0 else 1.0
            GLib.idle_add(self._update_execute_progress, frac, filename)

        restored_count, errors = self.history.undo_last_batch(progress_callback=on_progress)
        GLib.idle_add(self._on_undo_completed, restored_count, errors)

    def _on_undo_completed(self, restored_count: int, errors: List[str]) -> None:
        self.spinner.stop()
        self._update_undo_state()

        msg = f"Restored {restored_count} files to original locations."
        if errors:
            msg += f" ({len(errors)} issues encountered)"
        self._show_toast(msg)

        # Rescan to show restored files
        self._start_scan()

    def _update_undo_state(self) -> None:
        has_undo = self.history.has_undoable_batch()
        self.btn_undo.set_sensitive(has_undo)

    # -------------------------------------------------------------------------
    # Dialogs & Notifications
    # -------------------------------------------------------------------------

    def _show_toast(self, text: str) -> None:
        toast = Adw.Toast(title=text)
        self.toast_overlay.add_toast(toast)

    def _on_preferences_clicked(self) -> None:
        pref_win = SettingsWindow(
            settings_manager=self.settings_manager,
            classifier=self.classifier,
            parent_window=self,
            on_settings_changed=self._on_settings_updated
        )
        pref_win.present()

    def _on_settings_updated(self, key: str, value: Any) -> None:
        if key == "rules_updated":
            self.classifier.reload_rules()
        elif key == "auto_watch":
            self._setup_file_monitor()

        # Rescan if folder is open
        if self.current_folder:
            self._start_scan()

    def _show_about_dialog(self) -> None:
        # Strictly Libadwaita 1.4 compatible (Adw.AboutWindow)
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="Smart Folder Organizer",
            application_icon="com.aniket.SmartFolderOrganizer",
            developer_name="Aniket Singh",
            version="1.0.0",
            copyright="© 2026 Aniket Singh",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/aniket/smart-folder-organizer",
            issue_url="https://github.com/aniket/smart-folder-organizer/issues",
            developers=["Aniket Singh"],
            comments="Safe, content-aware, and previewable folder organization for GNOME."
        )
        about.present()

    def _show_shortcuts_dialog(self) -> None:
        # Built-in Gtk.ShortcutsWindow
        shortcuts = Gtk.ShortcutsWindow(transient_for=self, modal=True)
        section = Gtk.ShortcutsSection()
        group = Gtk.ShortcutsGroup(title="General")

        shortcuts_list = [
            ("Choose Folder", "<Primary>o"),
            ("Undo Last Operation", "<Primary>z"),
            ("Rescan Current Folder", "<Primary>r"),
            ("Preferences", "<Primary>comma"),
            ("Quit", "<Primary>q"),
        ]

        for title, accel in shortcuts_list:
            s_shortcut = Gtk.ShortcutsShortcut(title=title, accelerator=accel)
            group.append(s_shortcut)

        section.append(group)
        shortcuts.append(section)
        shortcuts.present()
