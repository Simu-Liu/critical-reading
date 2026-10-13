"""Shared path, YAML and identity primitives for critical-reading helpers."""
from __future__ import annotations

import json
import ntpath
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required. Use a Python environment with PyYAML installed.") from exc


class ReadingError(ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous frontmatter instead of silently losing duplicate keys."""


def _unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ReadingError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)

SCHEMA = (
    "title", "authors", "year", "journal", "doi", "pmid", "collection",
    "type", "note_origin", "zotero_key", "pdf_key", "zotero_uri", "pdf_uri",
    "source_format", "note_path", "analytical_note_path", "personal_note_path",
    "fulltext_path", "article_type", "research_relevance", "research_directions",
    "tags", "model_system", "perturbation", "mechanism_axis", "article_quality",
    "quality_dimensions", "zotero_tag_sync", "status", "date_created", "date_read",
    "evidence_scope", "conclusion_verification",
)
SHARED_FIELDS = (
    "title", "authors", "year", "journal", "doi", "pmid", "collection",
    "zotero_key", "pdf_key", "source_format", "zotero_uri", "pdf_uri",
)
QUALITY_FIELDS = ("novelty", "evidence_chain", "methodological_rigor", "reproducibility", "transferability")
RELATION_FIELDS = ("note_path", "analytical_note_path", "personal_note_path", "fulltext_path")
LEGACY_ROOTS = {"02vault": "vault", "03fulltext": "fulltext"}
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
SELECT_RE = re.compile(r"^zotero://select/(library|groups/[0-9]+)/items/([A-Z0-9]{8})$")
PDF_RE = re.compile(r"^zotero://open-pdf/(library|groups/[0-9]+)/items/([A-Z0-9]{8})(?:\?page=[1-9][0-9]*(?:&annotation=[A-Z0-9]{8})?)?$")


@dataclass
class Document:
    path: Path
    original: bytes
    data: dict
    body: bytes
    newline: bytes = b"\n"
    bom: bytes = b""

    def render(self, data=None, body=None):
        metadata = self.data if data is None else data
        content = self.body if body is None else body
        serialized = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False, width=160).rstrip("\n")
        header = serialized.replace("\n", self.newline.decode()).encode("utf-8")
        return self.bom + b"---" + self.newline + header + self.newline + b"---" + self.newline + content


def load_document(path):
    path = Path(path)
    raw = path.read_bytes()
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    payload = raw[len(bom):]
    lines = payload.splitlines(keepends=True)
    if not lines or lines[0].rstrip(b"\r\n") != b"---":
        raise ReadingError(f"Missing YAML frontmatter: {path}")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip(b"\r\n") == b"---"), None)
    if end is None:
        raise ReadingError(f"Unclosed YAML frontmatter: {path}")
    try:
        data = yaml.load(b"".join(lines[1:end]).decode("utf-8"), Loader=UniqueKeyLoader)
        body = b"".join(lines[end + 1:])
        body.decode("utf-8")
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ReadingError(f"Invalid UTF-8/YAML in {path}: {exc}") from exc
    if not isinstance(data, dict) or not all(isinstance(k, str) for k in data):
        raise ReadingError(f"Frontmatter must be a mapping of string properties: {path}")
    newline = b"\r\n" if lines[0].endswith(b"\r\n") else b"\n"
    return Document(path, raw, data, body, newline, bom)


def vault_root(raw):
    path = Path(raw)
    if not path.is_absolute():
        raise ReadingError("--vault must be an absolute directory path")
    path = path.resolve()
    if not path.is_dir():
        raise ReadingError(f"Vault does not exist: {path}")
    return path


def safe_path(vault, raw, tree=None, legacy=False):
    if not isinstance(raw, str) or not raw.strip():
        raise ReadingError("Missing relative path")
    value = unquote(raw).replace("\\", "/")
    if ntpath.isabs(value) or ntpath.splitdrive(value)[0] or value.startswith("/"):
        raise ReadingError(f"Absolute paths are not allowed: {raw}")
    parts = value.split("/")
    if any(any(symbol in p for symbol in "#^[]|") for p in parts):
        raise ReadingError(f"Unsupported Obsidian wiki-reserved character in path: {raw}")
    if (any(p in ("..", ".", "") or p.rstrip(" .") != p for p in parts)
            or any(re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts)
            or any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", p.split(".", 1)[0], re.I) for p in parts)):
        raise ReadingError(f"Unsafe relative path: {raw}")
    if legacy and parts[0] in LEGACY_ROOTS:
        parts[0] = LEGACY_ROOTS[parts[0]]
    if parts[0] not in ("vault", "fulltext", "Notes"):
        raise ReadingError(f"Path must be in vault/, fulltext/ or Notes/: {raw}")
    if tree and parts[0] != tree:
        raise ReadingError(f"Path must be in {tree}/: {raw}")
    relative = "/".join(parts)
    path = vault.joinpath(*parts)
    try:
        path.resolve().relative_to(vault.resolve())
    except ValueError as exc:
        raise ReadingError(f"Path or symlink escapes the Vault: {raw}") from exc
    # Even an internal symlink cannot switch evidence/AI/personal layers.
    actual = path.resolve().relative_to(vault.resolve()).parts
    if not actual or actual[0] != parts[0]:
        raise ReadingError(f"Symlink crosses reading layers: {raw}")
    return relative, path


def markdown_path(vault, raw, tree, legacy=False):
    relative, path = safe_path(vault, raw, tree, legacy)
    if path.suffix.lower() != ".md":
        raise ReadingError(f"Expected a Markdown file: {raw}")
    return relative, path


def checked_key(data, field):
    value = data.get(field)
    if not isinstance(value, str) or not KEY_RE.fullmatch(value):
        raise ReadingError(f"Missing or invalid {field}; verify Zotero metadata, do not guess it")
    return value


def checked_uri(value, expected_key, pdf=False):
    pattern = PDF_RE if pdf else SELECT_RE
    match = pattern.fullmatch(str(value or ""))
    if not match or match.group(2) != expected_key:
        raise ReadingError(f"{'PDF' if pdf else 'Zotero'} URI does not match its verified key: {value}")
    return match.group(1)


def checked_identity(data, allow_uri_aliases=False):
    parent, attachment = checked_key(data, "zotero_key"), checked_key(data, "pdf_key")
    item = data.get("zotero_uri")
    pdf = data.get("pdf_uri")
    if allow_uri_aliases:
        item = item or data.get("zotero_item")
        pdf = pdf or data.get("zotero_pdf")
    item_scope = checked_uri(item, parent)
    pdf_scope = checked_uri(pdf, attachment, pdf=True)
    if item_scope != pdf_scope:
        raise ReadingError("Zotero item/PDF URI library scopes do not match")
    for alias, value, key, is_pdf in (("zotero_item", data.get("zotero_item"), parent, False), ("zotero_pdf", data.get("zotero_pdf"), attachment, True)):
        if value is not None:
            if checked_uri(value, key, is_pdf) != item_scope:
                raise ReadingError(f"Conflicting legacy URI alias: {alias}")
    return parent, attachment, item_scope


def checked_parent_scope(data):
    """Verify an existing parent identity even if its PDF metadata is absent."""
    parent = checked_key(data, "zotero_key")
    value = data.get("zotero_uri") or data.get("zotero_item")
    scope = checked_uri(value, parent)
    if useful(data.get("zotero_item")) and checked_uri(data["zotero_item"], parent) != scope:
        raise ReadingError("Conflicting Zotero legacy URI library scope")
    return parent, scope


def useful(value):
    return value not in (None, "", [], {})


def emit_result(value, use_json=False):
    if use_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        print(value.get("status", "unknown"))
        for name in ("errors", "warnings", "changed"):
            for entry in value.get(name, []):
                print(f"{name}: {entry}")


def is_remote(target):
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target)) or target.startswith("data:")


def embedded_images(text):
    """Read Obsidian embeds and usual Markdown image URLs (including angle URLs)."""
    images = []
    for match in re.finditer(r"!\[\[([^\]]+)\]\]", text):
        images.append((match.group(1).split("|", 1)[0].split("#", 1)[0].strip(), "wiki"))
    for match in re.finditer(r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\s*\)", text):
        images.append((match.group(1) or match.group(2), "markdown"))
    return images


def resolve_image(vault, doc_path, target, style):
    value = unquote(target).split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
    if is_remote(value):
        raise ReadingError(f"Remote image is not an archived local asset: {target}")
    if ntpath.isabs(value) or ntpath.splitdrive(value)[0] or value.startswith("/"):
        raise ReadingError(f"Absolute image path is not allowed: {target}")
    if ".." in value.split("/"):
        raise ReadingError(f"Image path traversal is not allowed: {target}")
    first = value.split("/")[0]
    if first in ("fulltext", "vault", "Notes") or first in LEGACY_ROOTS:
        return safe_path(vault, value, legacy=True)
    # MinerU relative images live beside Fulltext; an unqualified Obsidian
    # image filename is accepted only when its local destination is unambiguous.
    sibling = doc_path.parent / value
    rel = sibling.relative_to(vault).as_posix()
    relative, candidate = safe_path(vault, rel)
    if candidate.exists() or style == "markdown" or "/" in value:
        return relative, candidate
    candidates = [p for tree in ("fulltext", "vault", "Notes") for p in (vault / tree).rglob(value) if p.is_file()]
    if len(candidates) == 1:
        return safe_path(vault, candidates[0].relative_to(vault).as_posix())
    if len(candidates) > 1:
        raise ReadingError(f"Ambiguous embedded image filename: {target}")
    return relative, candidate
