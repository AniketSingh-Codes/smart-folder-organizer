"""Classification Engine for Smart Folder Organizer.

Provides multi-layer file categorization:
- Layer 1: Extension and MIME type
- Layer 2: Filename keyword patterns
- Layer 3: Content-aware keyword inspection (optional, for text/PDF/DOCX)
"""

from __future__ import annotations

import datetime
import fnmatch
import importlib.resources
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ClassificationResult:
    """Represents the categorization result for a single file."""

    category: str
    subcategory: Optional[str]
    target_rel_path: str
    match_layer: int  # 1: Ext/Mime, 2: Filename keyword, 3: Content keyword
    reason: str
    icon_name: str

    @property
    def display_destination(self) -> str:
        """Formatted destination display string."""
        return self.target_rel_path


class Classifier:
    """Multi-layer file classifier driven by user-customizable rules."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is None:
            self.config_dir = Path.home() / ".config" / "smart-folder-organizer"
        else:
            self.config_dir = Path(config_dir)

        self.rules_path = self.config_dir / "rules.json"
        self.rules: Dict[str, Any] = {}
        self.load_rules()

    def get_default_rules_data(self) -> Dict[str, Any]:
        """Loads default rules packaged alongside the application."""
        pkg_rules = Path(__file__).parent / "rules_default.json"
        if pkg_rules.exists():
            with open(pkg_rules, "r", encoding="utf-8") as f:
                return json.load(f)

        # Fallback minimal schema if file is somehow missing
        return {
            "categories": {
                "Documents": {"extensions": [".pdf", ".docx", ".txt"], "mime_prefixes": ["text/"], "icon": "x-office-document-symbolic"},
                "Images": {"extensions": [".jpg", ".png", ".gif"], "mime_prefixes": ["image/"], "icon": "image-x-generic-symbolic"},
                "Other": {"extensions": [], "mime_prefixes": [], "icon": "folder-symbolic"}
            },
            "keyword_rules": [],
            "content_rules": [],
            "ignored_patterns": [".*", "*.part", "*.crdownload", "*.tmp", "Organized"]
        }

    def load_rules(self) -> None:
        """Loads rules from config directory or initializes defaults."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.rules_path.exists():
            default_data = self.get_default_rules_data()
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2)
            self.rules = default_data
        else:
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)
            except Exception:
                # If corrupt, fallback to defaults
                self.rules = self.get_default_rules_data()

    def reload_rules(self) -> None:
        """Reloads the classification rules from disk."""
        self.load_rules()

    def save_rules(self) -> None:
        """Saves current in-memory rules to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.rules_path, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, indent=2)

    def reset_rules_to_default(self) -> None:
        """Resets the rules configuration back to application defaults."""
        default_data = self.get_default_rules_data()
        self.rules = default_data
        self.save_rules()

    def is_ignored(self, file_path: Path, ignore_hidden: bool = True, ignore_partial: bool = True) -> bool:
        """Determines if a file should be ignored during scanning."""
        name = file_path.name

        # Ignore hidden files
        if ignore_hidden and name.startswith("."):
            return True

        # Ignore partial downloads & temp files
        if ignore_partial:
            lower_name = name.lower()
            if any(lower_name.endswith(ext) for ext in [".part", ".crdownload", ".tmp", ".download", ".swp"]):
                return True

        # Check against custom ignored patterns in rules
        patterns = self.rules.get("ignored_patterns", [])
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

        return False

    def classify_file(
        self,
        file_path: Path,
        content_aware: bool = False,
        date_based: bool = False
    ) -> ClassificationResult:
        """Classifies a single file through layers 1, 2, and 3."""
        name = file_path.name
        stem = file_path.stem.lower()
        suffix = file_path.suffix.lower()

        # Pre-resolve MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # --- Layer 1: Extension & MIME Type Detection ---
        base_category = "Other"
        category_icon = "folder-symbolic"

        categories: Dict[str, Any] = self.rules.get("categories", {})

        # Pass 1: Exact extension match
        if suffix:
            for cat_name, cat_data in categories.items():
                if cat_name == "Other":
                    continue
                exts = [e.lower() for e in cat_data.get("extensions", [])]
                if suffix in exts:
                    base_category = cat_name
                    category_icon = cat_data.get("icon", category_icon)
                    break

        # Pass 2: Fallback to MIME type prefix match
        if base_category == "Other" and mime_type:
            for cat_name, cat_data in categories.items():
                if cat_name == "Other":
                    continue
                prefixes = cat_data.get("mime_prefixes", [])
                if any(mime_type.startswith(p) for p in prefixes):
                    base_category = cat_name
                    category_icon = cat_data.get("icon", category_icon)
                    break

        if base_category == "Other" and "Other" in categories:
            category_icon = categories["Other"].get("icon", "folder-symbolic")

        match_layer = 1
        reason = f"Matched extension '{suffix}'" if suffix else f"MIME type '{mime_type}'"
        subcategory: Optional[str] = None

        # Normalize stem for keyword matching (replace symbols with spaces)
        normalized_stem = stem.replace("_", " ").replace("-", " ").replace(".", " ")

        # --- Layer 2: Filename Keyword Rules ---
        keyword_rules = self.rules.get("keyword_rules", [])
        for rule in keyword_rules:
            rule_keywords = rule.get("keywords", [])
            for kw in rule_keywords:
                kw_lower = kw.lower()
                # Check for word or substring match
                if kw_lower in normalized_stem or kw_lower in stem:
                    # If rule specifies a category, we can adopt or refine it
                    rule_cat = rule.get("category")
                    if rule_cat:
                        base_category = rule_cat
                        if rule_cat in categories:
                            category_icon = categories[rule_cat].get("icon", category_icon)
                    subcategory = rule.get("subcategory")
                    match_layer = 2
                    reason = f"Keyword '{kw}' in filename"
                    break
            if subcategory:
                break

        # --- Layer 3: Content-Aware Keyword Rules ---
        if content_aware and file_path.is_file():
            # Only inspect text-based documents or PDFs
            text_snippet = self._extract_text_snippet(file_path, suffix, mime_type)
            if text_snippet:
                text_lower = text_snippet.lower()
                content_rules = self.rules.get("content_rules", [])
                for rule in content_rules:
                    rule_keywords = rule.get("keywords", [])
                    for kw in rule_keywords:
                        kw_lower = kw.lower()
                        if kw_lower in text_lower:
                            rule_cat = rule.get("category")
                            if rule_cat:
                                base_category = rule_cat
                                if rule_cat in categories:
                                    category_icon = categories[rule_cat].get("icon", category_icon)
                            subcategory = rule.get("subcategory")
                            match_layer = 3
                            reason = f"Content matched '{kw}'"
                            break
                    if match_layer == 3:
                        break

        # --- Build Target Relative Path (with optional Date-based sorting) ---
        path_parts: List[str] = [base_category]

        if date_based:
            try:
                mtime = os.path.getmtime(file_path)
                dt = datetime.datetime.fromtimestamp(mtime)
                year_str = dt.strftime("%Y")
                month_str = dt.strftime("%B")  # e.g., "November"
                path_parts.extend([year_str, month_str])
            except Exception:
                pass

        if subcategory:
            path_parts.append(subcategory)

        target_rel_path = str(Path(*path_parts))

        return ClassificationResult(
            category=base_category,
            subcategory=subcategory,
            target_rel_path=target_rel_path,
            match_layer=match_layer,
            reason=reason,
            icon_name=category_icon
        )

    def _extract_text_snippet(self, file_path: Path, suffix: str, mime_type: Optional[str]) -> Optional[str]:
        """Safely extracts up to ~2000 characters from supported document formats."""
        max_chars = 2000

        # Plain text / Markdown / Source code
        text_suffixes = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".html", ".sh", ".py", ".rst", ".log"}
        if suffix in text_suffixes or (mime_type and mime_type.startswith("text/")):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(max_chars)
            except Exception:
                return None

        # PDF documents via pypdf
        if suffix == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                if reader.pages:
                    first_page_text = reader.pages[0].extract_text() or ""
                    return first_page_text[:max_chars]
            except (ImportError, Exception):
                pass
            return None

        # Word DOCX documents via python-docx
        if suffix == ".docx":
            try:
                import docx
                doc = docx.Document(str(file_path))
                full_text = []
                total_len = 0
                for para in doc.paragraphs:
                    full_text.append(para.text)
                    total_len += len(para.text)
                    if total_len >= max_chars:
                        break
                return "\n".join(full_text)[:max_chars]
            except (ImportError, Exception):
                pass
            return None

        return None
