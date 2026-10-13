"""Read-only validator for the three-layer critical-reading vault."""
from __future__ import annotations

import argparse
import collections
import re

from reading_common import (
    LEGACY_ROOTS, RELATION_FIELDS, SHARED_FIELDS, SCHEMA, QUALITY_FIELDS,
    ReadingError, checked_identity,
    checked_parent_scope,
    embedded_images, load_document, markdown_path, resolve_image, safe_path,
    useful, vault_root, emit_result,
)

TREE_TYPES = {"vault": "literature-note", "Notes": "personal-reading-note", "fulltext": "literature-fulltext"}


def add(report, category, message):
    report[category].append(message)


def check_image(report, root, path, target, style):
    try:
        _, candidate = resolve_image(root, path, target, style)
        if not candidate.is_file():
            add(report, "errors", f"Missing embedded image in {path.relative_to(root)}: {target}")
    except ReadingError as exc:
        add(report, "errors", f"Invalid embedded image in {path.relative_to(root)} ({target}): {exc}")


def check_navigation(report, root, doc):
    text = doc.body.decode("utf-8")
    # Explicit reading-layer paths are navigation; bare [[concept]] entries are
    # knowledge candidates and may legitimately not exist yet.
    for match in re.finditer(r"(?<!!)\[\[([^\]]+)\]\]", text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].replace("\\", "/")
        if target.split("/", 1)[0] not in ("vault", "fulltext", "Notes", *LEGACY_ROOTS):
            continue
        if target.split("/", 1)[0] in LEGACY_ROOTS:
            add(report, "warnings", f"Stale Obsidian reading-link prefix in {doc.path.relative_to(root)}: {target}; target exists only after legacy normalization, body was preserved")
        target = target if target.lower().endswith(".md") else target + ".md"
        try:
            _, linked = safe_path(root, target, legacy=True)
            if not linked.is_file():
                add(report, "errors", f"Missing reading navigation link in {doc.path.relative_to(root)}: {target}")
        except ReadingError as exc:
            add(report, "errors", f"Unsafe reading navigation in {doc.path.relative_to(root)}: {exc}")


def validate(root, selected=None):
    report = {"status": "ok", "errors": [], "warnings": [], "checked": [], "skipped": []}
    selected_path, selected_parent = None, None
    if selected:
        raw = selected.replace("\\", "/")
        if raw.startswith("02vault/") or raw.startswith("03fulltext/"):
            add(report, "warnings", f"Legacy path accepted for inspection; use vault/fulltext in new metadata: {selected}")
        try:
            rel, path = safe_path(root, raw, legacy=True)
        except ReadingError as exc:
            add(report, "errors", str(exc)); report["status"] = "failed"; return report
        if not path.is_file():
            add(report, "errors", f"Requested note does not exist: {rel}"); report["status"] = "failed"; return report
        selected_path = path
        try:
            selected_parent = load_document(path).data.get("zotero_key")
        except ReadingError as exc:
            add(report, "errors", str(exc)); report["status"] = "failed"; return report
    paths = [p for tree in TREE_TYPES for p in (root / tree).rglob("*.md") if p.is_file()]
    docs, active = {}, {}
    identity = collections.defaultdict(list)
    for path in paths:
        rel = path.relative_to(root).as_posix()
        tree = rel.split("/", 1)[0]
        try:
            safe_path(root, rel, tree)
            doc = load_document(path)
        except ReadingError as exc:
            if selected_path == path:
                add(report, "errors", f"{rel}: {exc}")
            elif "escapes" in str(exc) or "crosses reading layers" in str(exc):
                add(report, "errors", f"{rel}: {exc}")
            elif not selected:
                report["skipped"].append(rel)
                add(report, "warnings", f"Skipped unrelated or legacy Markdown: {rel}")
            continue
        docs[path] = doc
        data = doc.data
        kind = data.get("type")
        if selected and data.get("zotero_key") != selected_parent:
            continue
        # Inventory verified parent identities before legacy/new-schema routing.
        # An untyped personal page still occupies its paper's Notes slot.
        if useful(data.get("zotero_key")):
            try:
                parent_identity = checked_parent_scope(data)
                identity[parent_identity].append((path, kind, tree))
            except ReadingError:
                pass  # Active checks below report invalid/incomplete identity.
        new_schema = (useful(data.get("analytical_note_path")) or useful(data.get("personal_note_path"))
                      or data.get("note_origin") in ("ai", "user") or kind == "personal-reading-note")
        if not selected and not new_schema:
            report["skipped"].append(rel)
            add(report, "warnings", f"Skipped legacy note without critical-reading links: {rel}")
            continue
        expected = TREE_TYPES[tree]
        # Old notes with no new schema are warnings, not failures; this keeps
        # introducing the validator from requiring mass migration.
        if kind is None and not useful(data.get("zotero_key")):
            report["skipped"].append(rel); continue
        if kind != expected:
            add(report, "errors", f"{rel}: type {kind!r} must be {expected!r} for {tree}/")
        try:
            parent, attachment, scope = checked_identity(data, allow_uri_aliases=(tree == "fulltext"))
            active[path] = (parent, attachment, scope)
        except ReadingError as exc:
            add(report, "errors", f"{rel}: {exc}")
            continue
        report["checked"].append(rel)
        for relation in RELATION_FIELDS:
            if not useful(data.get(relation)):
                add(report, "errors" if new_schema else "warnings", f"{rel}: missing {relation}" + (" (legacy; personal page is not required)" if not new_schema else ""))
                continue
            try:
                relation_tree = "fulltext" if relation == "fulltext_path" else "Notes" if relation == "personal_note_path" or (relation == "note_path" and tree == "Notes") else "vault"
                relation_rel, relation_path = markdown_path(root, data[relation], relation_tree, legacy=True)
                if not relation_path.is_file():
                    add(report, "errors", f"{rel}: missing linked {relation}: {relation_rel}")
            except ReadingError as exc:
                add(report, "errors", f"{rel}: invalid {relation}: {exc}")
        for target, style in embedded_images(doc.body.decode("utf-8")):
            check_image(report, root, path, target, style)
        check_navigation(report, root, doc)
        if tree in ("vault", "Notes") and new_schema:
            missing = set(SCHEMA) - set(data)
            if missing:
                add(report, "errors", f"{rel}: missing schema properties: {sorted(missing)}")
            expected_origin = "ai" if tree == "vault" else "user"
            if data.get("note_origin") != expected_origin:
                add(report, "errors", f"{rel}: note_origin must be {expected_origin}")
            scores = data.get("quality_dimensions")
            if not isinstance(scores, dict) or not all(isinstance(scores.get(k), (int, float)) and not isinstance(scores.get(k), bool) and 0 <= scores[k] <= 5 for k in QUALITY_FIELDS):
                add(report, "errors", f"{rel}: quality_dimensions must contain five scores from 0 to 5")
    for key, entries in identity.items():
        # Fulltext + AI + personal are the expected three distinct documents.
        seen = {tree for _, _, tree in entries}
        if len(entries) > 3 or len(seen) != len(entries):
            names = ", ".join(p.relative_to(root).as_posix() for p, _, _ in entries)
            add(report, "errors", f"Duplicate paper identity {key[0]} ({key[1]}): {names}")
    # Pairwise cross-layer consistency checks for every identity.
    for key, entries in identity.items():
        by_type = {kind: path for path, kind, _ in entries if path in active}
        ai, personal, fulltext = (by_type.get("literature-note"), by_type.get("personal-reading-note"), by_type.get("literature-fulltext"))
        if not ai or not personal or not fulltext:
            if ai or personal or fulltext:
                inactive = [p.relative_to(root).as_posix() for p, _, _ in entries if p not in active]
                add(report, "warnings", f"Incomplete validated three-layer paper identity {key[0]}: missing {set(TREE_TYPES.values()) - set(by_type)}" + (f"; legacy-skipped or invalid: {inactive}" if inactive else ""))
            continue
        ai_data, person_data, full_data = docs[ai].data, docs[personal].data, docs[fulltext].data
        if set(ai_data) != set(person_data):
            add(report, "errors", f"AI/personal property keys differ for {key[0]}")
        for field in SHARED_FIELDS:
            if person_data.get(field) != ai_data.get(field):
                add(report, "errors", f"Cross-layer {field} mismatch: {personal.relative_to(root)} vs {ai.relative_to(root)}")
        if active[ai] != active[personal] or active[ai] != active[fulltext]:
            add(report, "errors", f"AI/personal/fulltext PDF identity or URI scope differs for {key[0]}")
        for field in ("title", "doi"):
            if useful(full_data.get(field)) and full_data[field] != ai_data.get(field):
                add(report, "errors", f"Fulltext {field} mismatch for {key[0]}")
        # Fulltext archives historically use note_path as their analytical-note
        # backlink; preserve that convention while fulltext_path identifies the
        # archive itself. AI and personal pages use note_path for themselves.
        expected_rel = {
            ai: ("vault", ai), personal: ("Notes", personal), fulltext: ("vault", ai),
        }
        for path, (tree, own) in expected_rel.items():
            data = docs[path].data
            try:
                own_rel = own.relative_to(root).as_posix()
                actual, _ = safe_path(root, data.get("note_path"), tree, legacy=True)
                if actual != own_rel:
                    add(report, "errors", f"{path.relative_to(root)}: note_path must identify its own layer file")
            except ReadingError as exc:
                add(report, "errors", f"{path.relative_to(root)}: invalid note_path: {exc}")
        expected_relations = {
            "analytical_note_path": ai.relative_to(root).as_posix(),
            "personal_note_path": personal.relative_to(root).as_posix(),
            "fulltext_path": fulltext.relative_to(root).as_posix(),
        }
        for path in (ai, personal, fulltext):
            for field, expected in expected_relations.items():
                try:
                    actual, _ = safe_path(root, docs[path].data.get(field), legacy=True)
                    if actual != expected:
                        add(report, "errors", f"{path.relative_to(root)}: {field} does not point to paired page")
                except ReadingError as exc:
                    add(report, "errors", f"{path.relative_to(root)}: invalid {field}: {exc}")
    if report["errors"]:
        report["status"] = "failed"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--note", help="Check one vault-relative file; otherwise scan all three trees")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(vault_root(args.vault), args.note)
    except (ReadingError, OSError) as exc:
        result = {"status": "failed", "errors": [str(exc)], "warnings": [], "checked": [], "skipped": []}
    emit_result(result, args.json)
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
