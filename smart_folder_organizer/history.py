"""Undo & Operation History Manager for Smart Folder Organizer.

Maintains an operation log at ~/.local/share/smart-folder-organizer/history.json
to allow single-click rollback of organized files to their original locations.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from .mover import get_unique_dest_path


class HistoryManager:
    """Logs organization runs and facilitates safe reversal (Undo)."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            self.data_dir = Path.home() / ".local" / "share" / "smart-folder-organizer"
        else:
            self.data_dir = Path(data_dir)

        self.history_file = self.data_dir / "history.json"
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    def load_history(self) -> List[Dict[str, Any]]:
        """Loads all past organization batches."""
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    def record_batch(self, folder: Path, moves: List[Dict[str, str]]) -> Optional[str]:
        """Records an organization operation batch."""
        if not moves:
            return None

        batch_id = str(uuid.uuid4())
        entry = {
            "id": batch_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "folder": str(folder),
            "total": len(moves),
            "moves": moves
        }

        history = self.load_history()
        history.append(entry)
        self._save_history(history)
        return batch_id

    def get_last_batch(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent organization batch if one exists."""
        history = self.load_history()
        return history[-1] if history else None

    def has_undoable_batch(self) -> bool:
        """Checks if there is at least one recorded batch that can be undone."""
        return len(self.load_history()) > 0

    def undo_last_batch(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[int, List[str]]:
        """Restores files from the most recent batch back to original paths."""
        history = self.load_history()
        if not history:
            return 0, ["No operations in history to undo."]

        last_batch = history.pop()
        moves = last_batch.get("moves", [])
        total = len(moves)
        restored = 0
        errors: List[str] = []
        dirs_to_clean: List[Path] = []

        # Iterate in reverse order
        for idx, item in enumerate(reversed(moves)):
            source_str = item.get("source")
            dest_str = item.get("dest")

            if not source_str or not dest_str:
                continue

            orig_source = Path(source_str)
            curr_dest = Path(dest_str)

            if progress_callback:
                progress_callback(idx, total, curr_dest.name)

            if not curr_dest.exists():
                errors.append(f"Cannot restore {curr_dest.name}: File missing at destination.")
                continue

            try:
                # Ensure destination directory exists (original source folder)
                orig_source.parent.mkdir(parents=True, exist_ok=True)

                # Never overwrite if original location now has another file
                safe_target = get_unique_dest_path(orig_source)
                shutil.move(str(curr_dest), str(safe_target))
                restored += 1

                # Track destination folder for empty directory cleanup
                dirs_to_clean.append(curr_dest.parent)
            except Exception as e:
                errors.append(f"Failed to restore {curr_dest.name}: {e}")

        # Clean up any empty folders left behind
        for folder in dirs_to_clean:
            self._cleanup_empty_dirs(folder)

        # Save trimmed history
        self._save_history(history)

        if progress_callback:
            progress_callback(total, total, "Undo complete")

        return restored, errors

    def _cleanup_empty_dirs(self, directory: Path) -> None:
        """Removes a directory and its ancestors if they are completely empty."""
        try:
            curr = directory
            while curr != curr.parent:
                if curr.exists() and curr.is_dir() and not any(curr.iterdir()):
                    curr.rmdir()
                    curr = curr.parent
                else:
                    break
        except Exception:
            pass
