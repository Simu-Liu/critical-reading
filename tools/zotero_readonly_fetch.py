#!/usr/bin/env python3
"""Read Zotero parent records/collections via read-only SQLite, never writing it."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from config import configured_path, load_config

KEY = re.compile(r'^[A-Z0-9]{8}$')
PARENT_TYPES = {'journalArticle', 'preprint', 'conferencePaper'}


def discover_data_dir():
    candidates = [Path.home() / 'Zotero']
    if platform.system() == 'Windows' and os.environ.get('APPDATA'):
        profiles = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles'
        if profiles.is_dir():
            candidates.extend(p / 'zotero' for p in profiles.iterdir() if p.is_dir())
    matches = [p.resolve() for p in candidates if (p / 'zotero.sqlite').is_file()]
    if len(set(matches)) > 1:
        raise ValueError('Several Zotero data directories found; specify --data-dir')
    return matches[0] if matches else None


class Reader:
    def __init__(self, db, directory, group_id=None):
        self.db, self.directory, self.group_id = db, directory, group_id
        self.tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.deleted = {r[0] for r in db.execute('SELECT itemID FROM deletedItems')} if 'deletedItems' in self.tables else set()

    def columns(self, table):
        return {r['name'] for r in self.db.execute(f'PRAGMA table_info({table})')}

    def library_scope(self, row):
        if 'libraryID' not in row.keys():
            if self.group_id is not None:
                raise ValueError('This export cannot verify group-library identity')
            return 'library'
        if 'libraries' not in self.tables:
            raise ValueError('Cannot verify library type for libraryID')
        library = self.db.execute('SELECT * FROM libraries WHERE libraryID=?', (row['libraryID'],)).fetchone()
        if library is None:
            raise ValueError('Library record is missing')
        if library['type'] == 'user':
            return 'library'
        if library['type'] == 'group' and 'groups' in self.tables:
            group = self.db.execute('SELECT groupID FROM groups WHERE libraryID=?', (row['libraryID'],)).fetchone()
            if group:
                return f"groups/{group['groupID']}"
        raise ValueError('Unsupported or unverified library scope')

    def in_scope(self, row):
        expected = 'library' if self.group_id is None else f'groups/{self.group_id}'
        return self.library_scope(row) == expected

    def parent(self, row):
        if row['itemID'] in self.deleted:
            return False
        for table in ('itemAttachments', 'itemNotes', 'itemAnnotations'):
            if table in self.tables and self.db.execute(f'SELECT 1 FROM {table} WHERE itemID=?', (row['itemID'],)).fetchone():
                return False
        if 'itemTypes' in self.tables:
            kind = self.db.execute('SELECT typeName FROM itemTypes WHERE itemTypeID=?', (row['itemTypeID'],)).fetchone()
            if kind is None or kind[0] not in PARENT_TYPES:
                return False
        return self.in_scope(row)

    def values(self, item_id):
        return {r['fieldName']: r['value'] for r in self.db.execute(
            'SELECT f.fieldName,v.value FROM itemData d JOIN fields f USING(fieldID) JOIN itemDataValues v USING(valueID) WHERE d.itemID=?', (item_id,))}

    def authors(self, item_id):
        if not {'creators', 'itemCreators'} <= self.tables:
            return []
        query = 'SELECT c.firstName,c.lastName FROM itemCreators ic JOIN creators c USING(creatorID) '
        if 'creatorTypes' in self.tables and 'creatorTypeID' in self.columns('itemCreators'):
            query += "JOIN creatorTypes ct USING(creatorTypeID) WHERE ic.itemID=? AND ct.creatorType='author' ORDER BY ic.orderIndex"
        else:
            query += 'WHERE ic.itemID=? ORDER BY ic.orderIndex'
        return [' '.join(filter(None, (r['firstName'], r['lastName']))) for r in self.db.execute(query, (item_id,))]

    def attachments(self, row):
        results = []
        if 'itemAttachments' not in self.tables:
            return results
        for child in self.db.execute('SELECT i.*,a.path,a.contentType FROM items i JOIN itemAttachments a USING(itemID) WHERE a.parentItemID=?', (row['itemID'],)):
            if child['itemID'] in self.deleted or child['contentType'] != 'application/pdf':
                continue
            if self.library_scope(child) != self.library_scope(row):
                raise ValueError('PDF child library disagrees with parent')
            attachment_key, path_value = child['key'], child['path'] or ''
            storage = (self.directory / 'storage' / attachment_key).resolve()
            pdf_path = None
            if path_value.startswith('storage:'):
                filename = path_value.split(':', 1)[1]
                candidate = (storage / filename).resolve()
                if not candidate.is_relative_to(storage):
                    raise ValueError('Attachment path escapes its storage directory')
                if candidate.is_file():
                    with candidate.open('rb') as handle:
                        if b'%PDF-' in handle.read(1024):
                            pdf_path = str(candidate)
            caches = sorted(p for p in storage.glob('.zotero-ft-cache*') if p.is_file()) if storage.is_dir() else []
            results.append({'item_id': child['itemID'], 'pdf_key': attachment_key,
                'title': self.values(child['itemID']).get('title'), 'pdf_path': pdf_path,
                'attachment_path_field': path_value, 'fulltext_cache': str(caches[0]) if len(caches) == 1 else None,
                'cache_candidates': [str(p) for p in caches]})
        return results

    def record(self, row, pdf_key=None, allow_unselected=False):
        if not KEY.fullmatch(row['key']):
            raise ValueError('Invalid parent key in database')
        values = self.values(row['itemID'])
        pdfs = self.attachments(row)
        if pdf_key:
            selected = [p for p in pdfs if p['pdf_key'] == pdf_key]
            if len(selected) != 1:
                raise ValueError('--pdf-key is not a PDF child of this parent')
            pdf = selected[0]
        elif len(pdfs) > 1:
            if not allow_unselected:
                raise ValueError('Several PDF children; specify --pdf-key: ' + json.dumps(pdfs, ensure_ascii=False))
            pdf = {}
        else:
            pdf = pdfs[0] if pdfs else {}
        annotations = []
        if pdf and 'itemAnnotations' in self.tables:
            for annotation in self.db.execute('SELECT * FROM itemAnnotations WHERE parentItemID=?', (pdf['item_id'],)):
                if annotation['itemID'] not in self.deleted:
                    annotations.append(dict(annotation))
        notes = []
        if 'itemNotes' in self.tables:
            notes = [r['note'] for r in self.db.execute('SELECT * FROM itemNotes WHERE parentItemID=?', (row['itemID'],)) if r['itemID'] not in self.deleted]
        collections = []
        if {'collections', 'collectionItems'} <= self.tables:
            collections = [r[0] for r in self.db.execute('SELECT c.collectionName FROM collectionItems ci JOIN collections c USING(collectionID) WHERE ci.itemID=?', (row['itemID'],))]
        tags = []
        if {'tags', 'itemTags'} <= self.tables:
            tags = [r[0] for r in self.db.execute('SELECT t.name FROM itemTags it JOIN tags t USING(tagID) WHERE it.itemID=?', (row['itemID'],))]
        scope, key = self.library_scope(row), row['key']
        chosen = pdf.get('pdf_key')
        author_list = self.authors(row['itemID'])
        year = re.search(r'\b(\d{4})\b', values.get('date', ''))
        item_uri = f'zotero://select/{scope}/items/{key}'
        pdf_uri = f'zotero://open-pdf/{scope}/items/{chosen}' if chosen else None
        return {'zotero_key': key, 'pdf_key': chosen, 'scope': scope,
            'title': values.get('title'), 'authors': author_list, 'author': '; '.join(author_list),
            'year': int(year.group(1)) if year else None, 'journal': values.get('publicationTitle'),
            'doi': values.get('DOI'), 'pmid': values.get('PMID'), 'collection': collections, 'tags': tags,
            'annotations': annotations, 'notes': notes, 'pdf_path': pdf.get('pdf_path'),
            'fulltext_cache': pdf.get('fulltext_cache'), 'pdf_attachments': pdfs,
            'pdf_selection_required': len(pdfs) > 1 and not chosen,
            'pdf_found': bool(pdf.get('pdf_path')), 'cache_found': bool(pdf.get('fulltext_cache')),
            'annotations_found': bool(annotations), 'zotero_uri': item_uri, 'pdf_uri': pdf_uri,
            'zotero_item': item_uri, 'zotero_pdf': pdf_uri,
            'database_access': 'read-only SQLite mode=ro/query_only; no writes performed'}

    def find(self, key=None, title=None):
        if key:
            rows = self.db.execute('SELECT * FROM items WHERE key=?', (key,)).fetchall()
        else:
            rows = self.db.execute("SELECT i.* FROM items i JOIN itemData d USING(itemID) JOIN fields f USING(fieldID) JOIN itemDataValues v USING(valueID) WHERE f.fieldName='title' AND v.value=?", (title,)).fetchall()
        matches = [r for r in rows if self.parent(r)]
        if len(matches) != 1:
            raise ValueError(f'Expected one supported live parent in selected library; got {len(matches)}')
        return matches[0]

    def collection(self, key=None, title=None):
        field = 'key' if key else 'collectionName'
        if field not in self.columns('collections'):
            raise ValueError('Collection key cannot be verified in this export; use its unique title')
        rows = self.db.execute(f'SELECT * FROM collections WHERE {field}=?', (key or title,)).fetchall()
        rows = [r for r in rows if self.in_scope(r)]
        if 'deletedCollections' in self.tables:
            deleted = {r[0] for r in self.db.execute('SELECT collectionID FROM deletedCollections')}
            rows = [r for r in rows if r['collectionID'] not in deleted]
        if len(rows) != 1:
            raise ValueError(f'Expected one collection in selected library; got {len(rows)}')
        collection = rows[0]
        members = self.db.execute('SELECT i.* FROM items i JOIN collectionItems ci USING(itemID) WHERE ci.collectionID=? ORDER BY i.key', (collection['collectionID'],)).fetchall()
        items = [self.record(r, allow_unselected=True) for r in members if self.parent(r)]
        return {'collection': dict(collection), 'scope': self.library_scope(collection), 'membership': 'direct-only',
            'items': items, 'item_count': len(items), 'writes_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('--key')
    identity.add_argument('--title')
    identity.add_argument('--collection-key')
    identity.add_argument('--collection-title')
    parser.add_argument('--pdf-key')
    parser.add_argument('--group-id', type=int)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    for key in (args.key, args.pdf_key, args.collection_key):
        if key and not KEY.fullmatch(key):
            parser.error('Zotero keys must contain eight uppercase letters/digits')
    if args.group_id is not None and args.group_id <= 0:
        parser.error('--group-id must be positive')
    if args.pdf_key and (args.collection_key or args.collection_title):
        parser.error('--pdf-key selects a single paper attachment, not a collection')
    db = None
    try:
        settings = load_config(args.config)
        directory = args.data_dir.expanduser().resolve() if args.data_dir else configured_path('zotero_data_dir', settings) or discover_data_dir()
        if directory is None or not (directory / 'zotero.sqlite').is_file():
            raise ValueError('zotero.sqlite unavailable; specify --data-dir or use connector/API/export')
        uri = 'file:' + quote((directory / 'zotero.sqlite').as_posix(), safe=':/') + '?mode=ro'
        db = sqlite3.connect(uri, uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only = ON')
        db.execute('PRAGMA busy_timeout = 5000')
        reader = Reader(db, directory, args.group_id)
        result = reader.collection(args.collection_key, args.collection_title) if args.collection_key or args.collection_title else reader.record(reader.find(args.key, args.title), args.pdf_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'status': 'ACQUISITION_DEFERRED', 'error': str(exc), 'writes_performed': False}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    raise SystemExit(main())
