"""Create/link a personal page without generating or rewriting reading analysis."""
from __future__ import annotations

import argparse
import copy
from datetime import date
import os
from pathlib import Path
import re
import tempfile

from reading_common import (
    Document, ReadingError, SCHEMA, SHARED_FIELDS, QUALITY_FIELDS, RELATION_FIELDS,
    checked_identity, emit_result, load_document, markdown_path, safe_path, useful, vault_root,
    embedded_images, resolve_image,
    checked_parent_scope,
)

START = "<!-- critical-reading:personal-link:start -->"
END = "<!-- critical-reading:personal-link:end -->"


def default_personal_path(title):
    name = re.sub(r'[<>:"/\\|?*#^\[\]\x00-\x1f]', "-", title).strip(" .")[:160].rstrip(" .")
    if not name:
        raise ReadingError("Cannot derive a personal filename from an empty title")
    if name.upper() in ("CON", "PRN", "AUX", "NUL") or re.fullmatch(r"(?:COM|LPT)[1-9]", name, re.I):
        name = "paper-" + name
    return f"Notes/{name} — 我的思考.md"


def defaults(today):
    return {
        "authors": [], "year": None, "journal": None, "doi": None, "pmid": None,
        "collection": None, "source_format": "Zotero PDF + MinerU Markdown",
        "article_type": [], "research_relevance": None, "research_directions": [], "tags": [],
        "model_system": None, "perturbation": None, "mechanism_axis": None,
        "article_quality": "Dataview 自动计算", "quality_dimensions": {key: 0 for key in QUALITY_FIELDS},
        "zotero_tag_sync": "待同步", "status": "未记录", "date_created": today,
        "date_read": None, "evidence_scope": None, "conclusion_verification": None,
    }


def validate_existing_relations(vault, data):
    for field in RELATION_FIELDS:
        if useful(data.get(field)):
            tree = "fulltext" if field == "fulltext_path" else "Notes" if field == "personal_note_path" else None
            safe_path(vault, data[field], tree, legacy=True)


def reject_duplicate_identity(vault, parent, scope, chosen):
    for tree, expected in (("vault", "literature-note"), ("Notes", "personal-reading-note"), ("fulltext", "literature-fulltext")):
        for path in (vault / tree).rglob("*.md"):
            _, path = safe_path(vault, path.relative_to(vault).as_posix(), tree)
            try:
                candidate = load_document(path)
            except ReadingError:
                if path in chosen:
                    raise
                continue
            if candidate.data.get("zotero_key") == parent and path not in chosen:
                if checked_parent_scope(candidate.data)[1] != scope:
                    continue
                raise ReadingError(f"Duplicate {expected} identity {parent}: {path.relative_to(vault)}")


def link_body(document, personal_relative):
    newline = document.newline.decode()
    block = newline.join((START, "> [!note] 个人思考", f"> [[{personal_relative[:-3]}|打开我的个人笔记]]", "> 个人正文由你自由记录；论文证据以本页与原文为准。", END))
    body = document.body.decode("utf-8")
    start_count, end_count = body.count(START), body.count(END)
    if start_count != end_count or start_count > 1:
        raise ReadingError("Ambiguous or incomplete personal-link marker in AI note")
    if start_count:
        begin, end = body.index(START), body.index(END) + len(END)
        if end < begin:
            raise ReadingError("Personal-link markers are reversed")
        return (body[:begin] + block + body[end:]).encode("utf-8")
    # Existing ordinary personal links are left untouched; add a single managed
    # navigation block so later path changes never rewrite arbitrary prose.
    separator = ("" if not body or body.endswith(newline + newline) else newline if body.endswith(newline) else newline + newline)
    return (body + separator + block + newline).encode("utf-8")


def new_personal_body(ai, ai_relative, fulltext_relative):
    title = str(ai["title"]).replace("\r", " ").replace("\n", " ")
    return (f"# {title} — 我的思考\n\n"
            f"关联阅读：[[{ai_relative[:-3]}|AI 精读笔记]]\n"
            f"原文：[[{fulltext_relative[:-3]}|全文 Markdown]]\n"
            f"Zotero：[条目]({ai['zotero_uri']})\n"
            f"PDF：[打开 PDF]({ai['pdf_uri']})\n\n---\n\n").encode("utf-8")


def normalize_fulltext_relations(vault, original, data, ai_relative, personal_relative, fulltext_relative):
    validate_existing_relations(vault, original)
    # Legacy roots may be repaired only after the files' keys are matched.
    for field, expected in (("note_path", ai_relative), ("analytical_note_path", ai_relative), ("fulltext_path", fulltext_relative), ("personal_note_path", personal_relative)):
        if useful(original.get(field)):
            normalized, _ = safe_path(vault, original[field], legacy=True)
            if normalized != expected:
                raise ReadingError(f"Fulltext {field} points to a different paper path: {original[field]}")
        data[field] = expected
    # Repair the old archival navigation property without touching the body.
    if "analytical_note" in data:
        data["analytical_note"] = f"[[{ai_relative[:-3]}|AI 精读笔记]]"


def plan_links(vault, note, personal=None, today=None):
    today = today or date.today().isoformat()
    date.fromisoformat(today)
    ai_relative, ai_path = markdown_path(vault, note, "vault")
    if not ai_path.is_file():
        raise ReadingError(f"AI note is missing: {ai_relative}")
    ai_doc = load_document(ai_path)
    ai_original = ai_doc.data
    if ai_original.get("type") != "literature-note":
        raise ReadingError("--note must be type: literature-note")
    if ai_original.get("note_origin") not in (None, "ai"):
        raise ReadingError("AI note has conflicting note_origin")
    parent, attachment, scope = checked_identity(ai_original)
    if not useful(ai_original.get("title")):
        raise ReadingError("AI note title is missing")
    validate_existing_relations(vault, ai_original)
    fulltext_relative, fulltext_path = markdown_path(vault, ai_original.get("fulltext_path"), "fulltext", legacy=True)
    if not fulltext_path.is_file():
        raise ReadingError(f"Fulltext is missing: {fulltext_relative}")
    fulltext_doc = load_document(fulltext_path)
    if fulltext_doc.data.get("type") != "literature-fulltext":
        raise ReadingError("Fulltext must be type: literature-fulltext")
    if checked_identity(fulltext_doc.data, allow_uri_aliases=True) != (parent, attachment, scope):
        raise ReadingError("Fulltext Zotero/PDF identity differs from AI note")
    for field in ("doi", "title"):
        if useful(fulltext_doc.data.get(field)) and fulltext_doc.data[field] != ai_original.get(field):
            raise ReadingError(f"Fulltext {field} conflicts with AI note")
    recorded_personal = ai_original.get("personal_note_path")
    if personal is None:
        personal = recorded_personal or default_personal_path(str(ai_original["title"]))
    personal_relative, personal_path = markdown_path(vault, personal, "Notes")
    if useful(recorded_personal):
        recorded_relative, _ = markdown_path(vault, recorded_personal, "Notes")
        if personal_relative != recorded_relative:
            raise ReadingError("AI note already links a different personal page; no implicit relocation")
    if useful(ai_original.get("note_path")):
        normalized, _ = safe_path(vault, ai_original["note_path"], "vault", legacy=True)
        if normalized != ai_relative:
            raise ReadingError("AI note_path points to a different analytical note")
    if useful(ai_original.get("analytical_note_path")):
        normalized, _ = safe_path(vault, ai_original["analytical_note_path"], "vault", legacy=True)
        if normalized != ai_relative:
            raise ReadingError("AI analytical_note_path points to a different note")
    personal_doc = load_document(personal_path) if personal_path.exists() else None
    if personal_doc:
        original_personal = personal_doc.data
        if original_personal.get("type") not in (None, "personal-reading-note") or original_personal.get("note_origin") not in (None, "user"):
            raise ReadingError("Existing Notes page has conflicting type or note_origin")
        validate_existing_relations(vault, original_personal)
        for field in SHARED_FIELDS:
            if useful(original_personal.get(field)) and original_personal[field] != ai_original.get(field):
                raise ReadingError(f"Existing personal {field} conflicts with paper metadata")
        for field, expected in (("note_path", personal_relative), ("analytical_note_path", ai_relative), ("personal_note_path", personal_relative), ("fulltext_path", fulltext_relative)):
            if useful(original_personal.get(field)):
                normalized, _ = safe_path(vault, original_personal[field], legacy=True)
                if normalized != expected:
                    raise ReadingError(f"Existing personal {field} points elsewhere")
    reject_duplicate_identity(vault, parent, scope, {ai_path, personal_path, fulltext_path})
    for document in (ai_doc, fulltext_doc, personal_doc):
        if document is None:
            continue
        for target, style in embedded_images(document.body.decode("utf-8")):
            _, destination = resolve_image(vault, document.path, target, style)
            if not destination.is_file():
                raise ReadingError(f"Missing embedded image in {document.path.relative_to(vault)}: {target}")
    ai = copy.deepcopy(ai_original)
    baseline = defaults(today)
    for field in SCHEMA:
        if field not in ai:
            ai[field] = copy.deepcopy(baseline.get(field))
    person = copy.deepcopy(personal_doc.data) if personal_doc else copy.deepcopy(ai)
    if not personal_doc:
        person.update(status="未记录", date_created=today, date_read=None, evidence_scope=None,
                      conclusion_verification=None, zotero_tag_sync="待同步")
        person["quality_dimensions"] = {key: 0 for key in QUALITY_FIELDS}
        person["tags"] = [tag for tag in person.get("tags", []) if tag != "literature-note"]
        if "personal-reading-note" not in person["tags"]:
            person["tags"].append("personal-reading-note")
        # AI-only arbitrary metadata is represented, but not claimed by user.
        for field in set(ai) - set(SCHEMA):
            person[field] = None
    for field in SCHEMA:
        if field not in person:
            person[field] = None if personal_doc and field in ("status", "date_created") else copy.deepcopy(baseline.get(field))
    for field in SHARED_FIELDS:
        person[field] = copy.deepcopy(ai.get(field))
    # Match property names without copying the user's private values into AI.
    for field in set(ai) | set(person):
        ai.setdefault(field, None)
        person.setdefault(field, None)
    for metadata, own_path, kind, origin in ((ai, ai_relative, "literature-note", "ai"), (person, personal_relative, "personal-reading-note", "user")):
        metadata.update(type=kind, note_origin=origin, note_path=own_path,
                        analytical_note_path=ai_relative, personal_note_path=personal_relative,
                        fulltext_path=fulltext_relative)
        metadata["article_quality"] = "Dataview 自动计算"
    # Existing personal pages may have legacy aliases outside the shared schema.
    # Check those as well before rendering or staging a single file.
    checked_identity(person, allow_uri_aliases=True)
    fulltext = copy.deepcopy(fulltext_doc.data)
    normalize_fulltext_relations(vault, fulltext_doc.data, fulltext, ai_relative, personal_relative, fulltext_relative)
    fulltext.update(zotero_uri=ai["zotero_uri"], pdf_uri=ai["pdf_uri"])
    changes = {ai_path: ai_doc.render(ai, link_body(ai_doc, personal_relative)),
               fulltext_path: fulltext_doc.render(fulltext)}
    if personal_doc:
        changes[personal_path] = personal_doc.render(person)
    else:
        changes[personal_path] = Document(personal_path, b"", person, b"").render(body=new_personal_body(ai, ai_relative, fulltext_relative))
    # Renders are byte-stable after the first run; unchanged files stay untouched.
    changes = {path: content for path, content in changes.items() if not path.exists() or path.read_bytes() != content}
    return {"status": "planned", "note": ai_relative, "personal": personal_relative, "fulltext": fulltext_relative,
            "changed": [p.relative_to(vault).as_posix() for p in changes], "warnings": []}, changes


def commit_changes(vault, changes):
    staged, originals, committed = {}, {}, []
    try:
        # Recheck every destination before creating any files.
        for path in changes:
            safe_path(vault, path.relative_to(vault).as_posix())
        for path, content in changes.items():
            originals[path] = path.read_bytes() if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".critical-reading-", suffix=".tmp", dir=path.parent)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            staged[path] = Path(temporary)
        for path, staged_path in staged.items():
            os.replace(staged_path, path)
            committed.append(path)
    except Exception:
        for path in reversed(committed):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        raise
    finally:
        for staged_path in staged.values():
            staged_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--note", required=True, help="Vault-relative vault/...md")
    parser.add_argument("--personal", help="Vault-relative Notes/...md")
    parser.add_argument("--date", help="Local calendar date YYYY-MM-DD (defaults to date.today())")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        root = vault_root(arguments.vault)
        report, changes = plan_links(root, arguments.note, arguments.personal, arguments.date)
        if not arguments.dry_run:
            commit_changes(root, changes)
        report["status"] = "dry-run" if arguments.dry_run else "updated" if changes else "unchanged"
        emit_result(report, arguments.json)
        return 0
    except (ReadingError, OSError, ValueError) as exc:
        emit_result({"status": "failed", "errors": [str(exc)], "changed": []}, arguments.json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
