"""Unit tests for the Multi-Layer File Classification Engine."""

import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from smart_folder_organizer.classifier import Classifier


class TestClassifier(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name) / "config"
        self.work_dir = Path(self.temp_dir.name) / "files"
        self.work_dir.mkdir(parents=True)
        self.classifier = Classifier(config_dir=self.config_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # --- Layer 1 Tests: Extension & MIME ---

    def test_layer1_extension_categorization(self) -> None:
        test_cases = [
            ("photo.jpg", "Images"),
            ("song.mp3", "Audio"),
            ("movie.mp4", "Videos"),
            ("notes.txt", "Documents"),
            ("data.csv", "Spreadsheets"),
            ("deck.pptx", "Presentations"),
            ("bundle.zip", "Archives"),
            ("script.py", "Code"),
            ("setup.rpm", "Installers"),
            ("os.iso", "ISOs"),
            ("font.ttf", "Fonts"),
            ("unknown.xyz123", "Other"),
        ]

        for filename, expected_cat in test_cases:
            file_path = self.work_dir / filename
            file_path.touch()
            res = self.classifier.classify_file(file_path, content_aware=False)
            self.assertEqual(res.category, expected_cat, f"Failed for {filename}")
            self.assertEqual(res.match_layer, 1)

    # --- Layer 2 Tests: Filename Keywords ---

    def test_layer2_keyword_matching(self) -> None:
        test_cases = [
            ("invoice_2026_03.pdf", "Documents", "Invoices"),
            ("Client_Bill_Final.pdf", "Documents", "Invoices"),
            ("Software_Engineer_Resume.docx", "Documents", "Resumes"),
            ("Aniket_CV_2026.pdf", "Documents", "Resumes"),
            ("Screenshot from 2026-11-14.png", "Images", "Screenshots"),
            ("Flight_Boarding_Pass.pdf", "Documents", "Travel"),
            ("Math_Assignment_3.pdf", "Documents", "Academic"),
            ("Desktop_Wallpaper_4k.jpg", "Images", "Wallpapers"),
        ]

        for filename, expected_cat, expected_subcat in test_cases:
            file_path = self.work_dir / filename
            file_path.touch()
            res = self.classifier.classify_file(file_path, content_aware=False)
            self.assertEqual(res.category, expected_cat, f"Category mismatch for {filename}")
            self.assertEqual(res.subcategory, expected_subcat, f"Subcategory mismatch for {filename}")
            self.assertEqual(res.match_layer, 2)
            self.assertEqual(res.target_rel_path, f"{expected_cat}/{expected_subcat}")

    # --- Layer 3 Tests: Content-Aware Inspection ---

    def test_layer3_content_inspection(self) -> None:
        # A file with generic name, but invoice keywords inside
        generic_doc = self.work_dir / "document_9812.txt"
        generic_doc.write_text("Hello, please find the tax invoice details below. Total amount due is $450.00.")

        res = self.classifier.classify_file(generic_doc, content_aware=True)
        self.assertEqual(res.category, "Documents")
        self.assertEqual(res.subcategory, "Invoices")
        self.assertEqual(res.match_layer, 3)

        # A file with generic name, but resume keywords inside
        resume_doc = self.work_dir / "profile_summary.txt"
        resume_doc.write_text("Professional Summary:\nCurriculum Vitae of Senior Software Engineer.\nWork Experience:\n5 years.")

        res_resume = self.classifier.classify_file(resume_doc, content_aware=True)
        self.assertEqual(res_resume.category, "Documents")
        self.assertEqual(res_resume.subcategory, "Resumes")
        self.assertEqual(res_resume.match_layer, 3)

    # --- Date-Based Sorting Tests ---

    def test_date_based_sorting_path(self) -> None:
        test_file = self.work_dir / "invoice_march.pdf"
        test_file.touch()

        res = self.classifier.classify_file(test_file, content_aware=False, date_based=True)
        parts = Path(res.target_rel_path).parts
        self.assertEqual(parts[0], "Documents")
        # Second part should be 4-digit year
        self.assertTrue(parts[1].isdigit() and len(parts[1]) == 4)
        # Subcategory should be preserved
        self.assertEqual(parts[-1], "Invoices")

    def test_case_insensitivity_and_dots(self) -> None:
        file1 = self.work_dir / "PHOTO_UPPERCASE.JPG"
        file1.touch()
        self.assertEqual(self.classifier.classify_file(file1).category, "Images")

        file2 = self.work_dir / "my.cv.2026.latest.PDF"
        file2.touch()
        res = self.classifier.classify_file(file2)
        self.assertEqual(res.category, "Documents")
        self.assertEqual(res.subcategory, "Resumes")

    # --- Ignore Filter Tests ---

    def test_ignored_files(self) -> None:
        self.assertTrue(self.classifier.is_ignored(Path(".hidden_config")))
        self.assertTrue(self.classifier.is_ignored(Path("large_iso.iso.crdownload")))
        self.assertTrue(self.classifier.is_ignored(Path("archive.zip.part")))
        self.assertTrue(self.classifier.is_ignored(Path("cache.tmp")))
        self.assertFalse(self.classifier.is_ignored(Path("document.pdf")))


if __name__ == "__main__":
    unittest.main()
