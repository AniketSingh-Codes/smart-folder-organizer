"""Unit tests for Safe File Operations and Undo History."""

import sys
from pathlib import Path
import tempfile
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from smart_folder_organizer.history import HistoryManager
from smart_folder_organizer.mover import FileMover, get_unique_dest_path


class TestMoverAndHistory(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.source_dir = self.base_dir / "source"
        self.dest_dir = self.base_dir / "dest"
        self.config_dir = self.base_dir / "config"
        self.data_dir = self.base_dir / "data"

        self.source_dir.mkdir(parents=True)
        self.dest_dir.mkdir(parents=True)

        self.mover = FileMover(config_dir=self.config_dir)
        self.history = HistoryManager(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # --- Conflict Renaming Tests ---

    def test_unique_dest_path_no_conflict(self) -> None:
        target = self.dest_dir / "document.pdf"
        unique = get_unique_dest_path(target)
        self.assertEqual(unique, target)

    def test_unique_dest_path_with_conflicts(self) -> None:
        file1 = self.dest_dir / "document.pdf"
        file1.touch()

        # Next should be (1)
        unique1 = get_unique_dest_path(file1)
        self.assertEqual(unique1, self.dest_dir / "document (1).pdf")

        # Create (1), next should be (2)
        unique1.touch()
        unique2 = get_unique_dest_path(file1)
        self.assertEqual(unique2, self.dest_dir / "document (2).pdf")

    def test_composite_extension_conflict(self) -> None:
        archive = self.dest_dir / "backup.tar.gz"
        archive.touch()

        unique = get_unique_dest_path(archive)
        self.assertEqual(unique, self.dest_dir / "backup (1).tar.gz")

    # --- Dry-Run Simulation Tests ---

    def test_dry_run_simulation(self) -> None:
        src_file = self.source_dir / "photo.jpg"
        src_file.write_text("dummy image data")

        item = self.mover.plan_move(
            source_path=src_file,
            dest_root=self.dest_dir,
            target_rel_path="Images",
            category="Images",
            subcategory=None,
            reason="Matched extension",
            icon_name="image-x-generic"
        )
        self.assertIsNotNone(item)

        result = self.mover.execute_moves([item], dry_run=True)
        self.assertEqual(result.success_count, 1)

        # File should still be in source and NOT in dest
        self.assertTrue(src_file.exists())
        self.assertFalse((self.dest_dir / "Images" / "photo.jpg").exists())

    # --- Real Move & Collision Safety Tests ---

    def test_real_move_with_existing_destination_file(self) -> None:
        # Create an existing file at destination
        target_dir = self.dest_dir / "Documents"
        target_dir.mkdir(parents=True)
        existing = target_dir / "invoice.pdf"
        existing.write_text("original invoice")

        # Source file with identical name
        src_file = self.source_dir / "invoice.pdf"
        src_file.write_text("new incoming invoice")

        item = self.mover.plan_move(
            source_path=src_file,
            dest_root=self.dest_dir,
            target_rel_path="Documents",
            category="Documents",
            subcategory=None,
            reason="Matched",
            icon_name="document"
        )
        self.assertIsNotNone(item)

        result = self.mover.execute_moves([item], dry_run=False)
        self.assertEqual(result.success_count, 1)

        # Source should be moved
        self.assertFalse(src_file.exists())

        # Original invoice must be untouched
        self.assertEqual(existing.read_text(), "original invoice")

        # New invoice must have been renamed to avoid overwrite
        renamed = target_dir / "invoice (1).pdf"
        self.assertTrue(renamed.exists())
        self.assertEqual(renamed.read_text(), "new incoming invoice")

    # --- History Logging & Undo Tests ---

    def test_history_logging_and_undo(self) -> None:
        src_file = self.source_dir / "report.pdf"
        src_file.write_text("annual report content")

        item = self.mover.plan_move(
            source_path=src_file,
            dest_root=self.dest_dir,
            target_rel_path="Documents/Reports",
            category="Documents",
            subcategory="Reports",
            reason="Test",
            icon_name="document"
        )
        self.assertIsNotNone(item)

        result = self.mover.execute_moves([item], dry_run=False)
        self.assertEqual(result.success_count, 1)

        # Record in history
        batch_id = self.history.record_batch(self.source_dir, result.executed_moves)
        self.assertIsNotNone(batch_id)
        self.assertTrue(self.history.has_undoable_batch())

        # Execute Undo
        restored_count, errors = self.history.undo_last_batch()
        self.assertEqual(restored_count, 1)
        self.assertEqual(len(errors), 0)

        # Verify file is restored at source path
        self.assertTrue(src_file.exists())
        self.assertEqual(src_file.read_text(), "annual report content")

        # Verify empty destination folder was cleaned up
        self.assertFalse((self.dest_dir / "Documents" / "Reports").exists())


if __name__ == "__main__":
    unittest.main()
