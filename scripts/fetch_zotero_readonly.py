#!/usr/bin/env python3
"""Read a verified Zotero parent/PDF and locate existing MinerU output; no writes."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_ORIGIN = "http://127.0.0.1:23119"
PARENT_TYPES = {"journalArticle", "preprint", "conferencePaper"}
KEY_PATTERN = re.compile(r"[A-Z0-9]{8}\Z")


class AcquisitionError(ValueError):
    pass


class LocalAPI:
    """Only the loopback Zotero API is reachable; redirects are disallowed."""

    def __init__(self, group_id: int | None = None, timeout: float = 10):
        library_route = f"groups/{group_id}" if group_id else "users/0"
        self.base = f"{API_ORIGIN}/api/{library_route}/"
        self.timeout = timeout
        self.group_id = group_id

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise AcquisitionError("Local API redirect refused; no external URL is followed")

        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )

    def get(self, route: str, query: dict[str, Any] | None = None) -> Any:
        if not re.fullmatch(r"(?:items(?:/[A-Z0-9]{8}(?:/children)?)?|collections/[A-Z0-9]{8})", route):
            raise AcquisitionError("Unsupported API route")
        url = self.base + route
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.load(response)

    def list(self, route: str, query: dict[str, Any] | None = None) -> list[dict]:
        items = []
        # A finite bound avoids unbounded enumeration; never report an incomplete search as unique.
        for start in range(0, 10000, 100):
            page = self.get(route, {**(query or {}), "limit": 100, "start": start})
            if not isinstance(page, list):
                raise AcquisitionError("API listing was not an array")
            items.extend(page)
            if len(page) < 100:
                return items
        raise AcquisitionError("API search exceeded 10,000 records; use a parent item key")


def data(record: dict) -> dict:
    value = record.get("data")
    if not isinstance(value, dict):
        raise AcquisitionError("Item response has no data object")
    return value


def item_key(record: dict) -> str:
    key = record.get("key") or data(record).get("key")
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
        raise AcquisitionError("Item key is missing or malformed")
    if data(record).get("key", key) != key:
        raise AcquisitionError("Root and data item keys disagree")
    return key


def verified_library(record: dict, group_id: int | None) -> dict:
    library = record.get("library")
    if not isinstance(library, dict) or library.get("type") not in {"user", "group"}:
        raise AcquisitionError("API library type/id is unavailable; do not guess a Zotero URI")
    library_id = library.get("id")
    if isinstance(library_id, bool) or not str(library_id).isdigit() or int(library_id) <= 0:
        raise AcquisitionError("API library id is unavailable or invalid")
    if group_id:
        if library["type"] != "group" or int(library_id) != group_id:
            raise AcquisitionError("Returned item belongs to a different group library")
    elif library["type"] != "user":
        raise AcquisitionError("Personal-library route returned a group item")
    return {"type": library["type"], "id": int(library_id), "name": library.get("name")}


def data_directory(explicit: Path | None, prefs: Path | None) -> tuple[Path | None, str | None]:
    if explicit:
        directory, origin = explicit.expanduser().resolve(), "explicit --data-dir"
    elif prefs:
        settings = {}
        raw = prefs.read_text(encoding="utf-8-sig")
        pattern = r'user_pref\("(extensions\.zotero\.(?:dataDir|useDataDir))",\s*("(?:\\.|[^"\\])*"|true|false)\s*\);'
        for name, encoded in re.findall(pattern, raw):
            settings[name] = json.loads(encoded)
        if settings.get("extensions.zotero.useDataDir") is not True:
            raise AcquisitionError("Specified prefs does not confirm an enabled custom Zotero dataDir; pass --data-dir")
        value = settings.get("extensions.zotero.dataDir")
        if not isinstance(value, str) or not value:
            raise AcquisitionError("Specified prefs has no dataDir string")
        directory, origin = Path(value).expanduser().resolve(), f"verified preference in {prefs.resolve()}"
    else:
        return None, None
    if not directory.is_dir() or not (directory / "storage").is_dir():
        raise AcquisitionError("Zotero data directory/storage does not exist")
    return directory, origin


def attachment_path(record: dict, directory: Path | None) -> dict:
    fields = data(record)
    result = {"pdf_key": item_key(record), "filename": fields.get("filename"),
              "link_mode": fields.get("linkMode"), "pdf_path": None, "pdf_found": False}
    if directory is None:
        result["path_status"] = "data-directory-unverified"
        return result
    if fields.get("linkMode") not in {"imported_file", "imported_url"}:
        result["path_status"] = "external-or-unconfirmed-attachment; not resolved by this helper"
        return result
    filename = fields.get("filename")
    if not isinstance(filename, str) or not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
        result["path_status"] = "attachment-filename-missing-or-not-local"
        return result
    storage_root = (directory / "storage" / result["pdf_key"]).resolve()
    candidate = (storage_root / filename).resolve()
    # The actual resolved file must remain in the verified attachment storage directory.
    if not candidate.is_relative_to(storage_root) or not storage_root.is_relative_to((directory / "storage").resolve()):
        raise AcquisitionError("Attachment path escapes its storage directory")
    if candidate.is_file():
        with candidate.open("rb") as stream:
            if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                result["path_status"] = "file-is-not-a-PDF"
                return result
        result.update(pdf_path=str(candidate), pdf_found=True, path_status="verified-existing-PDF")
    else:
        result["path_status"] = "confirmed-attachment-file-not-accessible"
    return result


def image_targets(markdown: str) -> list[str]:
    targets = re.findall(r"!\[[^\]\n]*\]\(([^\n]*?)\)", markdown)
    targets += re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", markdown, re.I)
    targets += re.findall(r"!\[\[([^\]\n]+)\]\]", markdown)
    cleaned = []
    for target in targets:
        target = target.strip()
        if target.startswith("<") and ">" in target:
            target = target[1:target.index(">")]
        else:
            target = re.split(r'\s+[\"\']', target, maxsplit=1)[0]
        target = target.split("|", 1)[0]
        cleaned.append(target)
    return list(dict.fromkeys(cleaned))


def inspect_mineru(root: Path, source: dict) -> dict:
    markdown_path, manifest_path = root / "full.md", root / "manifest.json"
    info = {"directory": str(root), "source": source, "markdown_path": None,
            "manifest_path": None, "images_directory": str(root / "images") if (root / "images").is_dir() else None,
            "images": [], "issues": [], "ready_for_archive": False}
    if not markdown_path.is_file():
        info["issues"].append("full.md missing")
        return info
    if not manifest_path.is_file():
        info["issues"].append("manifest.json missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
            info["manifest_path"] = str(manifest_path)
            info["manifest_total_pages"] = manifest.get("totalPages")
        except (OSError, ValueError) as exc:
            info["issues"].append(f"manifest.json unreadable: {exc}")
    raw = markdown_path.read_text(encoding="utf-8-sig")
    info["markdown_path"] = str(markdown_path)
    info["body_characters"] = len(raw)
    info["nonempty_body"] = bool(raw.strip())
    if not raw.strip():
        info["issues"].append("full.md empty")
    for target in image_targets(raw):
        url = urllib.parse.urlsplit(target)
        entry = {"reference": target, "path": None, "exists": False}
        # External resources and absolute paths are not fetched, copied, or accepted silently.
        if url.scheme or url.netloc or target.startswith(("/", "\\")):
            entry["issue"] = "nonlocal-or-absolute-image-reference"
        else:
            candidate = (root / urllib.parse.unquote(url.path)).resolve()
            if not candidate.is_relative_to(root.resolve()):
                entry["issue"] = "image-reference-escapes-source"
            else:
                entry.update(path=str(candidate), exists=candidate.is_file())
                if not entry["exists"]:
                    entry["issue"] = "image-file-missing"
        info["images"].append(entry)
        if entry.get("issue"):
            info["issues"].append(f"{target}: {entry['issue']}")
    info["image_links_valid"] = not any(image.get("issue") for image in info["images"])
    info["page_mapping"] = "unknown; verify original PDF before using converter page labels"
    info["ready_for_archive"] = not info["issues"]
    return info


def discover_mineru(directory: Path | None, parent_key: str, pdf_key: str | None) -> dict:
    report = {"status": "data-directory-unverified", "matches": [], "discovery_issues": []}
    if directory is None or pdf_key is None:
        return report
    mineru_root = directory / "llm-for-zotero-mineru"
    if not mineru_root.is_dir():
        report["status"] = "existing-parser-directory-unavailable"
        return report
    for metadata_path in sorted(mineru_root.glob("*/_llm_source.json")):
        try:
            source = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
            if not isinstance(source, dict):
                raise ValueError("source is not an object")
        except (OSError, ValueError) as exc:
            report["discovery_issues"].append(f"{metadata_path}: {exc}")
            continue
        if source.get("parentItemKey") == parent_key and source.get("attachmentKey") == pdf_key:
            report["matches"].append(inspect_mineru(metadata_path.parent.resolve(), source))
    report["status"] = "unique-source" if len(report["matches"]) == 1 else "ambiguous-source" if report["matches"] else "matching-source-not-found"
    # Several matches are alternatives; selecting newest would silently hide provenance ambiguity.
    return report


def fetch(api: LocalAPI, key: str | None, title: str | None, pdf_key: str | None,
          directory: Path | None, directory_origin: str | None) -> dict:
    if key:
        parent = api.get(f"items/{key}")
    else:
        candidates = [record for record in api.list("items", {"q": title, "qmode": "title"})
                      if data(record).get("title") == title and data(record).get("itemType") in PARENT_TYPES]
        if len(candidates) != 1:
            raise AcquisitionError(f"Exact title matched {len(candidates)} supported parent items; use --key. "
                                   + json.dumps([{ "key": item_key(item), "title": data(item).get("title") } for item in candidates], ensure_ascii=False))
        parent = candidates[0]
    parent_key = item_key(parent)
    fields = data(parent)
    if key and parent_key != key:
        raise AcquisitionError("Returned item key does not match requested key")
    if fields.get("itemType") not in PARENT_TYPES:
        raise AcquisitionError("Requested key is not a supported paper parent (journalArticle/preprint/conferencePaper)")
    library = verified_library(parent, api.group_id)
    children = api.list(f"items/{parent_key}/children")
    for child in children:
        if data(child).get("parentItem") != parent_key:
            raise AcquisitionError("Child parentItem disagrees with requested parent")
        if verified_library(child, api.group_id) != library:
            # Display names can differ in responses; identity is type/id only.
            child_library = verified_library(child, api.group_id)
            if (child_library["type"], child_library["id"]) != (library["type"], library["id"]):
                raise AcquisitionError("Child belongs to another library")
    pdfs = [item for item in children if data(item).get("itemType") == "attachment" and data(item).get("contentType") == "application/pdf"]
    if pdf_key:
        selected = [item for item in pdfs if item_key(item) == pdf_key]
        if len(selected) != 1:
            raise AcquisitionError("--pdf-key is not a PDF child of the verified parent")
        selected_pdf = selected[0]
    elif len(pdfs) > 1:
        raise AcquisitionError("Several PDF children found; specify --pdf-key. " + json.dumps([
            {"key": item_key(item), "title": data(item).get("title"), "filename": data(item).get("filename")} for item in pdfs], ensure_ascii=False))
    else:
        selected_pdf = pdfs[0] if pdfs else None
    chosen_key = item_key(selected_pdf) if selected_pdf else None
    annotations = api.list(f"items/{chosen_key}/children") if chosen_key else []
    for annotation in annotations:
        if data(annotation).get("parentItem") != chosen_key:
            raise AcquisitionError("PDF child parentItem disagrees with selected attachment")
        annotation_library = verified_library(annotation, api.group_id)
        if (annotation_library["type"], annotation_library["id"]) != (library["type"], library["id"]):
            raise AcquisitionError("PDF child belongs to another library")
    collection_records = []
    for collection_key in fields.get("collections", []):
        if not KEY_PATTERN.fullmatch(collection_key):
            raise AcquisitionError("Invalid collection key in item metadata")
        collection = api.get(f"collections/{collection_key}")
        collection_records.append({"key": collection_key, "name": data(collection).get("name")})
    prefix = "library" if library["type"] == "user" else f"groups/{library['id']}"
    authors = [creator.get("name") or " ".join(filter(None, [creator.get("firstName"), creator.get("lastName")]))
               for creator in fields.get("creators", []) if creator.get("creatorType") == "author"]
    date = fields.get("date", "")
    year_match = re.search(r"\b(\d{4})\b", date)
    return {
        "zotero_key": parent_key, "pdf_key": chosen_key, "library": library,
        "title": fields.get("title"), "item_type": fields.get("itemType"), "authors": authors,
        "date": date, "year": year_match.group(1) if year_match else None,
        "journal": fields.get("publicationTitle"), "doi": fields.get("DOI"),
        "collections": collection_records, "tags": fields.get("tags", []),
        "zotero_uri": f"zotero://select/{prefix}/items/{parent_key}",
        "pdf_uri": f"zotero://open-pdf/{prefix}/items/{chosen_key}" if chosen_key else None,
        "data_directory": str(directory) if directory else None, "data_directory_source": directory_origin,
        "selected_pdf": attachment_path(selected_pdf, directory) if selected_pdf else None,
        "pdf_attachments": [attachment_path(item, directory) for item in pdfs],
        "annotations": [data(item) for item in annotations if data(item).get("itemType") == "annotation"],
        "annotations_found": any(data(item).get("itemType") == "annotation" for item in annotations),
        "notes": [data(item) for item in children if data(item).get("itemType") == "note"],
        "mineru": discover_mineru(directory, parent_key, chosen_key),
        "raw_parent": parent, "raw_children": children,
        "access_mode": "read-only loopback API GET and read-only local files; no SQLite access or Zotero writes",
    }


def main() -> int:
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, "reconfigure"):
            output.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--key", help="verified parent item key; attachments/notes are rejected")
    identity.add_argument("--title", help="exact case-sensitive title; requires one supported parent")
    parser.add_argument("--pdf-key", help="PDF attachment key; required when more than one PDF exists")
    parser.add_argument("--group-id", type=int, help="group library id; defaults to local personal library")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--data-dir", type=Path, help="explicit verified Zotero data directory")
    location.add_argument("--prefs", type=Path, help="specified Zotero profile prefs.js with enabled custom dataDir")
    parser.add_argument("--timeout", type=float, default=10, help="local API request timeout in seconds (default 10)")
    args = parser.parse_args()
    for label, key in (("--key", args.key), ("--pdf-key", args.pdf_key)):
        if key and not KEY_PATTERN.fullmatch(key):
            parser.error(f"{label} must contain 8 uppercase letters/digits")
    if args.group_id is not None and args.group_id <= 0:
        parser.error("--group-id must be positive")
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than zero and at most 60")
    try:
        directory, origin = data_directory(args.data_dir, args.prefs)
        result = fetch(LocalAPI(args.group_id, args.timeout), args.key, args.title, args.pdf_key, directory, origin)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AcquisitionError, OSError, urllib.error.URLError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "status": "ACQUISITION_DEFERRED",
                          "writes_performed": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
