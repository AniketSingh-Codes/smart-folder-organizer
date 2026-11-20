"""Main Entry Point for Smart Folder Organizer.

Supports:
1. Full Libadwaita 1.4 / GTK 4.12 Desktop GUI
2. Headless CLI mode for scripting and automated cron runs:
   python3 -m smart_folder_organizer --cli --dry-run ~/Downloads
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import List

from .classifier import Classifier
from .history import HistoryManager
from .mover import FileMover, MoveItem, MoveResult


def run_cli(args: argparse.Namespace) -> int:
    """Headless Command Line Interface mode."""
    print("=" * 60)
    print(" Smart Folder Organizer — CLI Mode")
    print("=" * 60)

    history = HistoryManager()

    # Handle Undo CLI operation
    if args.undo:
        if not history.has_undoable_batch():
            print("[-] No organization history found to undo.")
            return 1
        print("[*] Reversing last organization batch…")
        restored, errors = history.undo_last_batch(
            progress_callback=lambda cur, tot, name: print(f"  Restoring ({cur}/{tot}): {name}", end="\r")
        )
        print()
        print(f"[✓] Successfully restored {restored} files.")
        if errors:
            print("[-] Warnings/Errors during undo:")
            for err in errors:
                print(f"    • {err}")
        return 0

    if not args.folder:
        print("[-] Error: target folder is required unless --undo is specified.")
        print("    Usage: python -m smart_folder_organizer --cli [--dry-run] <folder>")
        return 1

    target_dir = Path(args.folder).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"[-] Error: '{target_dir}' does not exist or is not a directory.")
        return 1

    dest_root = Path(args.dest).expanduser().resolve() if args.dest else target_dir / "Organized"

    print(f"[*] Target Folder     : {target_dir}")
    print(f"[*] Destination Root  : {dest_root}")
    print(f"[*] Content-Aware Scan: {'Enabled' if args.content else 'Disabled'}")
    print(f"[*] Date-Based Sort   : {'Enabled' if args.date_based else 'Disabled'}")
    print(f"[*] Dry-Run Mode      : {'YES (Simulation only)' if args.dry_run else 'NO (Files will be moved)'}")
    print("-" * 60)

    classifier = Classifier()
    mover = FileMover()

    # Discover files
    candidates: List[Path] = []
    if args.include_subfolders:
        for root, dirs, files in os.walk(target_dir):
            root_path = Path(root)
            if dest_root.resolve() in root_path.resolve().parents or root_path.resolve() == dest_root.resolve():
                continue
            for f in files:
                candidates.append(root_path / f)
    else:
        for entry in target_dir.iterdir():
            if entry.is_file():
                candidates.append(entry)

    planned_moves: List[MoveItem] = []
    for file_path in candidates:
        if classifier.is_ignored(file_path):
            continue

        result = classifier.classify_file(
            file_path=file_path,
            content_aware=args.content,
            date_based=args.date_based
        )

        item = mover.plan_move(
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

    if not planned_moves:
        print("[✓] Nothing to organize! Target folder is already clean.")
        return 0

    print(f"[+] Found {len(planned_moves)} candidate files:")
    for item in planned_moves:
        rel_dest = item.dest_path.relative_to(dest_root)
        print(f"  • {item.filename:<32} → {str(rel_dest):<30} [{item.reason}]")

    print("-" * 60)
    print(f"[*] Executing moves (Dry-run: {args.dry_run})…")

    result: MoveResult = mover.execute_moves(
        items=planned_moves,
        dry_run=args.dry_run,
        progress_callback=lambda cur, tot, name: print(f"  Processing ({cur}/{tot}): {name}", end="\r")
    )
    print()

    if not args.dry_run and result.executed_moves:
        history.record_batch(target_dir, result.executed_moves)
        print(f"[✓] Successfully moved {result.success_count} files (Logged to history).")
    elif args.dry_run:
        print(f"[✓] Simulation complete: {result.success_count} files would be moved.")

    if result.skipped_count > 0:
        print(f"[!] Skipped {result.skipped_count} files (in use or protected).")
    if result.error_count > 0:
        print(f"[-] Encountered {result.error_count} errors:")
        for err in result.errors:
            print(f"    • {err}")

    return 0 if result.error_count == 0 else 2


def run_gui(initial_folder: Optional[str] = None) -> int:
    """Launches the GTK 4 / Libadwaita desktop application."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib
    from .window import MainWindow

    class App(Adw.Application):
        def __init__(self) -> None:
            super().__init__(
                application_id="com.aniket.SmartFolderOrganizer",
                flags=Gio.ApplicationFlags.HANDLES_OPEN
            )
            self.main_window: Optional[MainWindow] = None

        def do_startup(self) -> None:
            Adw.Application.do_startup(self)
            # Quit action
            quit_action = Gio.SimpleAction.new("quit", None)
            quit_action.connect("activate", lambda a, p: self.quit())
            self.add_action(quit_action)
            self.set_accels_for_action("app.quit", ["<Primary>q"])

        def do_activate(self) -> None:
            Adw.Application.do_activate(self)
            if not self.main_window:
                self.main_window = MainWindow(self)

            if initial_folder:
                folder_path = Path(initial_folder).expanduser().resolve()
                if folder_path.is_dir():
                    self.main_window.set_target_folder(folder_path)

            self.main_window.present()

        def do_open(self, files: List[Gio.File], n_files: int, hint: str) -> None:
            Adw.Application.do_open(self, files, n_files, hint)
            self.do_activate()
            if files and self.main_window:
                path = files[0].get_path()
                if path:
                    folder_path = Path(path).expanduser().resolve()
                    if folder_path.is_dir():
                        self.main_window.set_target_folder(folder_path)

    app = App()
    return app.run(sys.argv[:1])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart Folder Organizer: Categorize and clean up folders automatically."
    )
    parser.add_argument("folder", nargs="?", help="Target folder to organize")
    parser.add_argument("--downloads", action="store_true", help="Launch directly pointing to Downloads")
    parser.add_argument("--desktop", action="store_true", help="Launch directly pointing to Desktop")
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode")
    parser.add_argument("--dry-run", action="store_true", help="Simulate organization without moving files")
    parser.add_argument("--undo", action="store_true", help="Undo the last organization batch")
    parser.add_argument("--content", action="store_true", default=True, help="Enable content-aware inspection (default: True)")
    parser.add_argument("--no-content", action="store_false", dest="content", help="Disable content-aware inspection")
    parser.add_argument("--date-based", action="store_true", help="Sort files into Year/Month subfolders")
    parser.add_argument("--include-subfolders", action="store_true", help="Scan nested subfolders recursively")
    parser.add_argument("--dest", help="Custom destination root path")

    args = parser.parse_args()

    target_folder = args.folder
    if args.downloads:
        from gi.repository import GLib
        target_folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
    elif args.desktop:
        from gi.repository import GLib
        target_folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)

    if args.cli:
        args.folder = target_folder
        return run_cli(args)
    else:
        return run_gui(initial_folder=target_folder)


if __name__ == "__main__":
    sys.exit(main())
