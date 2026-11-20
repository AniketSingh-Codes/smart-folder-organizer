"""Safe File Operations Engine for Smart Folder Organizer.

Handles destination path resolution, name conflict resolution,
verification of open files, atomic moves, cross-device compatibility,
and dry-run simulations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Callable, Dict, List, Optional


@dataclass
class MoveItem:
    """Represents a planned file move operation."""

    source_path: Path
    dest_dir: Path
    dest_path: Path
    category: str
    subcategory: Optional[str]
    reason: str
    icon_name: str
    size: int
    selected: bool = True
    status: str = "pending"  # pending, done, skipped, error
    error_message: Optional[str] = None

    @property
    def filename(self) -> str:
        return self.source_path.name

    @property
    def formatted_size(self) -> str:
        """User-friendly human readable file size."""
        size_bytes = self.size
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"


@dataclass
class MoveResult:
    """Summary of executed or simulated move operations."""

    total_attempted: int
    success_count: int
    skipped_count: int
    error_count: int
    executed_moves: List[Dict[str, str]]
    errors: List[str]


def get_unique_dest_path(dest_path: Path) -> Path:
    """Resolves name collisions by appending ' (1)', ' (2)', etc. before the extension."""
    if not dest_path.exists():
        return dest_path

    parent = dest_path.parent
    name = dest_path.name

    # Handle composite extensions like .tar.gz
    if name.lower().endswith(".tar.gz"):
        stem = name[:-7]
        suffix = ".tar.gz"
    elif name.lower().endswith(".tar.xz"):
        stem = name[:-7]
        suffix = ".tar.xz"
    elif name.lower().endswith(".tar.bz2"):
        stem = name[:-8]
        suffix = ".tar.bz2"
    else:
        stem = dest_path.stem
        suffix = dest_path.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_file_open(path: Path) -> bool:
    """Checks whether the file is currently opened by another process on Linux."""
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path

    current_pid = os.getpid()
    proc_path = Path("/proc")

    if not proc_path.exists():
        return False

    current_uid = os.getuid()

    try:
        for entry in proc_path.iterdir():
            if not entry.is_dir() or not entry.name.isdigit():
                continue

            pid = int(entry.name)
            if pid == current_pid:
                continue

            # Only inspect processes owned by the same user to avoid permission errors
            try:
                stat_info = entry.stat()
                if stat_info.st_uid != current_uid:
                    continue
            except (PermissionError, FileNotFoundError):
                continue

            fd_dir = entry / "fd"
            try:
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(fd)
                        if target == str(resolved):
                            return True
                    except (PermissionError, FileNotFoundError, OSError):
                        continue
            except (PermissionError, FileNotFoundError):
                continue
    except Exception:
        pass

    return False


class FileMover:
    """Executes safe and previewable file organization operations."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is None:
            self.config_dir = Path.home() / ".config" / "smart-folder-organizer"
        else:
            self.config_dir = Path(config_dir)

    def is_protected_file(self, path: Path) -> bool:
        """Guards against moving app configuration or state files."""
        try:
            resolved = path.resolve()
            # Protect config directory
            if self.config_dir.resolve() in resolved.parents or resolved == self.config_dir.resolve():
                return True
            # Protect data/history directory
            data_dir = (Path.home() / ".local" / "share" / "smart-folder-organizer").resolve()
            if data_dir in resolved.parents or resolved == data_dir:
                return True
        except Exception:
            pass
        return False

    def plan_move(
        self,
        source_path: Path,
        dest_root: Path,
        target_rel_path: str,
        category: str,
        subcategory: Optional[str],
        reason: str,
        icon_name: str
    ) -> Optional[MoveItem]:
        """Creates a MoveItem, calculating unique destination path and safety checks."""
        if self.is_protected_file(source_path):
            return None

        dest_dir = dest_root / target_rel_path
        initial_dest_path = dest_dir / source_path.name

        # If file is already at destination, no move needed
        try:
            if source_path.resolve() == initial_dest_path.resolve():
                return None
        except Exception:
            if source_path == initial_dest_path:
                return None

        # Resolve conflict ahead of time for preview
        unique_dest_path = get_unique_dest_path(initial_dest_path)

        try:
            size = source_path.stat().st_size
        except Exception:
            size = 0

        return MoveItem(
            source_path=source_path,
            dest_dir=dest_dir,
            dest_path=unique_dest_path,
            category=category,
            subcategory=subcategory,
            reason=reason,
            icon_name=icon_name,
            size=size,
            selected=True
        )

    def execute_moves(
        self,
        items: List[MoveItem],
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> MoveResult:
        """Executes the selected moves, handling errors and tracking results."""
        selected_items = [it for it in items if it.selected]
        total = len(selected_items)
        success_count = 0
        skipped_count = 0
        error_count = 0
        executed: List[Dict[str, str]] = []
        errors: List[str] = []

        for index, item in enumerate(selected_items):
            if cancel_check and cancel_check():
                break

            if progress_callback:
                progress_callback(index, total, item.filename)

            # Safety check 1: File existence
            if not item.source_path.exists():
                item.status = "error"
                item.error_message = "Source file no longer exists"
                errors.append(f"{item.filename}: Source file no longer exists")
                error_count += 1
                continue

            # Safety check 2: Is file in active use?
            if is_file_open(item.source_path):
                item.status = "skipped"
                item.error_message = "File is currently in use by another process"
                errors.append(f"{item.filename}: Skipped (file in use)")
                skipped_count += 1
                continue

            # In dry-run mode, simulate without altering disk
            if dry_run:
                item.status = "done"
                success_count += 1
                executed.append({
                    "source": str(item.source_path),
                    "dest": str(item.dest_path)
                })
                continue

            # Real move execution
            try:
                # Ensure destination folder exists
                item.dest_dir.mkdir(parents=True, exist_ok=True)

                # Re-resolve unique path in case new file arrived concurrently
                final_dest = get_unique_dest_path(item.dest_dir / item.source_path.name)
                item.dest_path = final_dest

                # shutil.move handles cross-filesystem/cross-mount boundary moves
                shutil.move(str(item.source_path), str(final_dest))

                item.status = "done"
                success_count += 1
                executed.append({
                    "source": str(item.source_path),
                    "dest": str(final_dest)
                })
            except PermissionError as e:
                item.status = "error"
                msg = f"Permission denied moving {item.filename}: {e}"
                item.error_message = msg
                errors.append(msg)
                error_count += 1
            except OSError as e:
                item.status = "error"
                msg = f"System error moving {item.filename}: {e}"
                item.error_message = msg
                errors.append(msg)
                error_count += 1
            except Exception as e:
                item.status = "error"
                msg = f"Unexpected error moving {item.filename}: {e}"
                item.error_message = msg
                errors.append(msg)
                error_count += 1

        if progress_callback:
            progress_callback(total, total, "Finished")

        return MoveResult(
            total_attempted=total,
            success_count=success_count,
            skipped_count=skipped_count,
            error_count=error_count,
            executed_moves=executed,
            errors=errors
        )
