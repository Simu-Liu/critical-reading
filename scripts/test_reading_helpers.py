"""Run with: python -m unittest discover -s scripts -p 'test_*.py' -v."""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from reading_common import Document, ReadingError, SCHEMA, QUALITY_FIELDS, load_document, safe_path
from link_personal_note import commit_changes, main, plan_links
from validate_reading_links import validate


class ReadingHelpersTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="critical-reading-test-")
        self.root = Path(self.temporary.name).resolve()
        self.ai = self.root / "vault/CAR-T/example.md"
        self.full = self.root / "fulltext/CAR-T/ABCDEFGH.md"
        self.image = self.root / "fulltext/CAR-T/images/Fig1.png"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"test-image")
        self.metadata = {
            "title": "Example paper", "authors": ["A Author", "B Author"], "year": 2026,
            "journal": "Example Journal", "doi": "10.0000/example", "pmid": "NR", "collection": "CAR-T",
            "type": "literature-note", "zotero_key": "ABCDEFGH", "pdf_key": "12345678",
            "zotero_uri": "zotero://select/library/items/ABCDEFGH",
            "pdf_uri": "zotero://open-pdf/library/items/12345678",
            "source_format": "Zotero PDF + MinerU Markdown",
            "note_path": "02vault/CAR-T/example.md", "fulltext_path": "03fulltext/CAR-T/ABCDEFGH.md",
            "research_relevance": "相关", "research_directions": ["实体瘤CAR-T"],
            "article_type": ["免疫", "代谢"], "tags": ["paper", "literature-note", "研究方向/实体瘤CAR-T"],
            "quality_dimensions": {key: 4 for key in QUALITY_FIELDS}, "status": "已读",
            "date_created": "2026-10-12", "date_read": "2026-10-13",
            "evidence_scope": "Main text only", "conclusion_verification": "Source checked",
            "AI_custom_field": "AI-only value",
        }
        self.write(self.ai, self.metadata, b"# AI analysis\n\n![[03fulltext/CAR-T/images/Fig1.png]]\n[[INSR]]\n")
        full_data = {"type": "literature-fulltext", "title": "Example paper", "doi": "10.0000/example",
                     "zotero_key": "ABCDEFGH", "pdf_key": "12345678",
                     "note_path": "02vault/CAR-T/example.md", "fulltext_path": "03fulltext/CAR-T/ABCDEFGH.md",
                     "zotero_item": self.metadata["zotero_uri"], "zotero_pdf": self.metadata["pdf_uri"]}
        self.full_body = b"\r\n# Original source\r\n\r\nOriginal source must remain untouched.\r\n"
        self.write(self.full, full_data, self.full_body, b"\r\n", b"\xef\xbb\xbf")

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path, data, body=b"", newline=b"\n", bom=b""):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Document(path, b"", data, body, newline, bom).render())

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def run_plan(self, personal=None):
        report, changes = plan_links(self.root, "vault/CAR-T/example.md", personal, "2026-10-13")
        commit_changes(self.root, changes)
        return report

    def test_new_personal_schema_defaults_and_fulltext_body_preserved(self):
        report = self.run_plan()
        ai = load_document(self.ai)
        person = load_document(self.root / report["personal"])
        full = load_document(self.full)
        self.assertEqual(set(ai.data), set(person.data))
        self.assertTrue(set(SCHEMA) <= set(person.data))
        self.assertEqual(person.data["type"], "personal-reading-note")
        self.assertEqual(person.data["note_origin"], "user")
        self.assertEqual(person.data["research_directions"], ["实体瘤CAR-T"])
        self.assertEqual(person.data["quality_dimensions"], {key: 0 for key in QUALITY_FIELDS})
        self.assertEqual(person.data["status"], "未记录")
        self.assertIsNone(person.data["date_read"])
        self.assertIsNone(person.data["evidence_scope"])
        self.assertIsNone(person.data["AI_custom_field"])
        self.assertNotIn("literature-note", person.data["tags"])
        self.assertEqual(full.body, self.full_body)
        self.assertEqual(full.bom, b"\xef\xbb\xbf")
        self.assertEqual(person.body.rsplit(b"---", 1)[1].strip(), b"")
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)

    def test_existing_personal_body_crlf_bom_scores_and_custom_fields_preserved(self):
        report = self.run_plan()
        path = self.root / report["personal"]
        person = load_document(path)
        person.data.update(research_directions=["肿瘤疫苗"], status="有待讨论", personal_only={"idea": "my own"})
        person.data["quality_dimensions"]["novelty"] = 2
        body = "\r\n# My thought\r\n\r\n这是我自己的idea。\r\n  \r\n".encode("utf-8")
        self.write(path, person.data, body, b"\r\n", b"\xef\xbb\xbf")
        self.run_plan()
        updated = load_document(path)
        self.assertEqual(updated.body, body)
        self.assertEqual(updated.bom, b"\xef\xbb\xbf")
        self.assertEqual(updated.newline, b"\r\n")
        self.assertEqual(updated.data["quality_dimensions"]["novelty"], 2)
        self.assertEqual(updated.data["research_directions"], ["肿瘤疫苗"])
        self.assertEqual(updated.data["status"], "有待讨论")
        self.assertEqual(updated.data["personal_only"], {"idea": "my own"})
        self.assertIsNone(load_document(self.ai).data["personal_only"])
        self.assertEqual(set(updated.data), set(load_document(self.ai).data))

    def test_idempotent_second_run_and_single_callout(self):
        self.run_plan()
        before = self.snapshot()
        report, changes = plan_links(self.root, "vault/CAR-T/example.md", today="2026-10-13")
        self.assertEqual(changes, {})
        self.assertEqual(report["changed"], [])
        commit_changes(self.root, changes)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(load_document(self.ai).body.count(b"critical-reading:personal-link:start"), 1)

    def test_dry_run_creates_nothing(self):
        before = self.snapshot()
        with contextlib.redirect_stdout(io.StringIO()):
            result = main(["--vault", str(self.root), "--note", "vault/CAR-T/example.md", "--date", "2026-10-13", "--dry-run", "--json"])
        self.assertEqual(result, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / "Notes").exists())

    def test_personal_identity_conflict_writes_zero_files(self):
        path = self.root / "Notes/personal.md"
        self.write(path, {"zotero_key": "ZZZZZZZZ", "title": "Example paper"}, b"my thought")
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan("Notes/personal.md")
        self.assertEqual(before, self.snapshot())

    def test_fulltext_identity_conflict_writes_zero_files(self):
        full = load_document(self.full)
        full.data["pdf_key"] = "87654321"
        self.write(self.full, full.data, full.body)
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan()
        self.assertEqual(before, self.snapshot())

    def test_path_escape_absolute_and_wrong_layer_rejected(self):
        for target in ("Notes/../outside.md", "Notes/%2E%2E/outside.md", "C:/outside.md", "/tmp/x.md", "vault/private.md", "Notes/./private.md", "Notes/.. /escape.md", "Notes/CON.md", "Notes/private.md:stream"):
            with self.subTest(target=target), self.assertRaises(ReadingError):
                plan_links(self.root, "vault/CAR-T/example.md", target, "2026-10-13")

    def test_uri_mismatch_not_guessed_or_repaired(self):
        ai = load_document(self.ai)
        ai.data["pdf_uri"] = "zotero://open-pdf/library/items/87654321"
        self.write(self.ai, ai.data, ai.body)
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(validate(self.root, "vault/CAR-T/example.md")["status"], "failed")

    def test_missing_ai_image_detected_when_fulltext_has_no_image_links(self):
        self.run_plan()
        self.image.unlink()
        result = validate(self.root, "vault/CAR-T/example.md")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("Missing embedded image" in error for error in result["errors"]), result)
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan()
        self.assertEqual(before, self.snapshot())

    def test_duplicate_identity_detected_by_linker_and_validator(self):
        self.run_plan()
        duplicate = self.root / "vault/CAR-T/duplicate.md"
        duplicate.write_bytes(self.ai.read_bytes())
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan()
        self.assertEqual(before, self.snapshot())
        result = validate(self.root, "vault/CAR-T/example.md")
        self.assertTrue(any("Duplicate paper identity" in e for e in result["errors"]), result)

    def test_mismatched_property_keys_reported(self):
        report = self.run_plan()
        path = self.root / report["personal"]
        person = load_document(path)
        person.data["private_field"] = "private"
        self.write(path, person.data, person.body)
        result = validate(self.root)
        self.assertTrue(any("property keys differ" in e for e in result["errors"]), result)

    def test_concept_wikilinks_do_not_become_broken_file_links(self):
        self.run_plan()
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)

    def test_unrelated_legacy_notes_do_not_force_personal_page_creation(self):
        self.write(self.root / "vault/old.md", {"type": "literature-note", "title": "Older note"}, b"unrelated")
        self.run_plan()
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)
        self.assertIn("vault/old.md", result["skipped"])

    def test_symlink_outside_vault_or_across_layers_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            link = self.root / "Notes"
            junction = False
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                if os.name != "nt":
                    self.skipTest(f"Symlink creation unavailable: {exc}")
                # Directory junctions exercise the same resolved-path boundary
                # on Windows without requiring symbolic-link privileges.
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), outside], capture_output=True)
                if result.returncode:
                    self.skipTest(f"Symlink/junction creation unavailable: {exc}")
                junction = True
            with self.assertRaises(ReadingError):
                safe_path(self.root, "Notes/secret.md", "Notes")
            link.rmdir() if junction else link.unlink()
            if junction:
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.root / "vault")], capture_output=True)
                self.assertEqual(result.returncode, 0)
            else:
                link.symlink_to(self.root / "vault", target_is_directory=True)
            with self.assertRaises(ReadingError):
                safe_path(self.root, "Notes/secret.md", "Notes")
            link.rmdir() if junction else link.unlink()

    def test_yaml_duplicate_keys_rejected(self):
        self.ai.write_bytes(b"---\ntitle: A\ntitle: B\n---\n")
        with self.assertRaises(ReadingError):
            load_document(self.ai)

    def test_broken_explicit_navigation_detected_but_concepts_are_ignored(self):
        self.run_plan()
        ai = load_document(self.ai)
        self.write(self.ai, ai.data, ai.body + b"\n[[vault/missing|broken navigation]]\n[[Uncreated concept]]\n")
        result = validate(self.root)
        self.assertTrue(any("Missing reading navigation link" in e for e in result["errors"]), result)

    def test_layer_type_confusion_detected(self):
        report = self.run_plan()
        path = self.root / report["personal"]
        person = load_document(path)
        person.data["type"] = "literature-note"
        self.write(path, person.data, person.body)
        result = validate(self.root)
        self.assertTrue(any("must be 'personal-reading-note'" in e for e in result["errors"]), result)

    def test_partial_new_schema_is_not_silently_skipped(self):
        self.run_plan()
        ai = load_document(self.ai)
        ai.data["personal_note_path"] = None
        self.write(self.ai, ai.data, ai.body)
        result = validate(self.root)
        self.assertTrue(any("missing personal_note_path" in e for e in result["errors"]), result)

    def test_unsafe_embedded_image_path_rejected_before_writes(self):
        ai = load_document(self.ai)
        self.write(self.ai, ai.data, ai.body + b"\n![escape](../../outside.png)\n")
        before = self.snapshot()
        with self.assertRaises(ReadingError):
            self.run_plan()
        self.assertEqual(before, self.snapshot())

    def test_markdown_relative_fulltext_image_resolves(self):
        full = load_document(self.full)
        self.write(self.full, full.data, full.body + b"\n![Figure](images/Fig1.png)\n")
        self.run_plan()
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)

    def test_new_personal_sync_state_not_inherited_and_existing_state_preserved(self):
        ai = load_document(self.ai)
        ai.data["zotero_tag_sync"] = "已同步"
        self.write(self.ai, ai.data, ai.body)
        report = self.run_plan()
        path = self.root / report["personal"]
        person = load_document(path)
        self.assertEqual(person.data["zotero_tag_sync"], "待同步")
        self.assertEqual(load_document(self.ai).data["zotero_tag_sync"], "已同步")
        person.data["zotero_tag_sync"] = "用户标记：暂缓"
        self.write(path, person.data, person.body)
        self.run_plan()
        self.assertEqual(load_document(path).data["zotero_tag_sync"], "用户标记：暂缓")

    def test_untyped_personal_verified_parent_prevents_duplicate_default_page(self):
        path = self.root / "Notes/earlier-thought.md"
        self.write(path, {"zotero_key": "ABCDEFGH", "zotero_uri": self.metadata["zotero_uri"]}, b"existing own thought")
        before = self.snapshot()
        with self.assertRaisesRegex(ReadingError, "Duplicate"):
            self.run_plan()
        self.assertEqual(before, self.snapshot())
        result = validate(self.root)
        # With only one Notes page this is not a duplicate yet, but explicitly
        # adding another same-paper untyped page must make inventory fail.
        self.write(self.root / "Notes/second-thought.md", {"zotero_key": "ABCDEFGH", "zotero_uri": self.metadata["zotero_uri"]}, b"second")
        result = validate(self.root)
        self.assertTrue(any("Duplicate paper identity" in e for e in result["errors"]), result)

    def test_explicit_untyped_personal_is_reused_without_body_loss(self):
        path = self.root / "Notes/earlier-thought.md"
        body = b"My own idea\r\n\r\n"
        self.write(path, {"zotero_key": "ABCDEFGH", "zotero_uri": self.metadata["zotero_uri"]}, body)
        report = self.run_plan("Notes/earlier-thought.md")
        self.assertEqual(report["personal"], "Notes/earlier-thought.md")
        self.assertEqual(load_document(path).body, body)
        self.assertIsNone(load_document(path).data["status"])
        self.assertIsNone(load_document(path).data["date_created"])
        self.assertEqual(validate(self.root)["status"], "ok")

    def test_same_parent_key_in_distinct_group_does_not_false_duplicate(self):
        other = self.root / "Notes/group-thought.md"
        self.write(other, {"zotero_key": "ABCDEFGH", "zotero_uri": "zotero://select/groups/42/items/ABCDEFGH"}, b"another library")
        self.run_plan()
        result = validate(self.root)
        self.assertFalse(any("Duplicate paper identity" in e for e in result["errors"]), result)
        self.assertEqual(result["status"], "ok", result)

    def test_conflicting_personal_legacy_uri_alias_is_atomic_failure(self):
        path = self.root / "Notes/personal.md"
        metadata = {key: self.metadata[key] for key in ("title", "zotero_key", "pdf_key", "zotero_uri", "pdf_uri")}
        metadata["zotero_item"] = "zotero://select/library/items/QRSTUVWX"
        self.write(path, metadata, b"own thought")
        before = self.snapshot()
        with self.assertRaisesRegex(ReadingError, "URI"):
            self.run_plan("Notes/personal.md")
        self.assertEqual(before, self.snapshot())

    def test_generated_personal_filename_avoids_wikilink_reserved_chars(self):
        ai, full = load_document(self.ai), load_document(self.full)
        title = "Paper #1 [alpha] ^beta"
        ai.data["title"], full.data["title"] = title, title
        self.write(self.ai, ai.data, ai.body)
        self.write(self.full, full.data, full.body)
        report = self.run_plan()
        self.assertFalse(any(char in report["personal"] for char in "#[]^"))
        self.assertEqual(load_document(self.root / report["personal"]).data["title"], title)
        self.assertEqual(validate(self.root)["status"], "ok")

    def test_explicit_wikilink_reserved_path_is_rejected(self):
        with self.assertRaisesRegex(ReadingError, "wiki-reserved"):
            self.run_plan("Notes/my#thought.md")

    def test_inactive_legacy_fulltext_does_not_crash_pairwise_validation(self):
        self.run_plan()
        full = load_document(self.full)
        for field in ("analytical_note_path", "personal_note_path"):
            full.data.pop(field, None)
        self.write(self.full, full.data, full.body)
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(any("legacy-skipped or invalid" in warning for warning in result["warnings"]), result)

    def test_invalid_pdf_identity_does_not_crash_pairwise_validation(self):
        self.run_plan()
        full = load_document(self.full)
        full.data["zotero_pdf"] = "zotero://open-pdf/library/items/QRSTUVWX"
        self.write(self.full, full.data, full.body)
        result = validate(self.root)
        self.assertEqual(result["status"], "failed", result)
        self.assertTrue(any("URI" in error for error in result["errors"]), result)
        self.assertTrue(any("legacy-skipped or invalid" in warning for warning in result["warnings"]), result)

    def test_legacy_body_navigation_warns_without_rewriting_original_bytes(self):
        self.run_plan()
        full = load_document(self.full)
        body = full.body + b"\r\n[[02vault/CAR-T/example|Analysis]]\r\n"
        self.write(self.full, full.data, body, full.newline, full.bom)
        before = self.full.read_bytes()
        result = validate(self.root)
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(any("Stale Obsidian reading-link prefix" in warning for warning in result["warnings"]), result)
        self.assertEqual(before, self.full.read_bytes())


if __name__ == "__main__":
    unittest.main()
