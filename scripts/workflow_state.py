"""Inspect real artifacts and append stage checkpoints; never write scientific prose."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from reading_common import (ReadingError, load_document, checked_parent_scope, checked_identity,
    safe_path, embedded_images, resolve_image, vault_root)
from validate_reading_links import validate as validate_reading

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'skills/research-vault-knowledge-maintainer/scripts'))
from validate_research_vault_knowledge import validate as validate_knowledge

STAGES = {'identity', 'fulltext', 'analytical', 'personal', 'indexes', 'knowledge', 'validation'}
DECISIONS = {'KNOWLEDGE_UPDATED', 'NO_KNOWLEDGE_CHANGE'}
STATUSES = {'COMPLETE', 'PASSED', 'ALREADY_COMPLETE', 'FULLTEXT_CREATED', 'NOTE_CREATED',
    'NOTE_TEMPLATE_REPAIRED', 'KNOWLEDGE_UPDATED', 'NO_KNOWLEDGE_CHANGE', 'FULLTEXT_DEFERRED',
    'NOTE_DEFERRED', 'PDF_NOT_FOUND', 'KEY_CONFLICT', 'FULLTEXT_FAILED', 'MINERU_FAILED',
    'IMAGES_INVALID', 'VALIDATION_FAILED', 'SCHEMA_REVIEW_REQUIRED', 'MANUAL_REVIEW_REQUIRED',
    'PARTIAL_FULLTEXT_MISSING', 'PARTIAL_NOTE_MISSING', 'PERSONAL_DEFERRED', 'PERMANENTLY_IGNORED'}


def technical_path(root):
    path = root / 'knowledge/.meta/critical-reading/workflow.jsonl'
    if not path.resolve().is_relative_to(root.resolve()):
        raise ReadingError('Workflow log escapes Vault')
    return path


def history(root, key, scope):
    path = technical_path(root)
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ReadingError(f'Invalid workflow JSONL at line {number}; do not discard history') from exc
        if event.get('zotero_key') == key and event.get('scope') == scope:
            records.append(event)
    return records


def inventory(root, key, scope):
    found = {}
    for tree, kind in [('vault', 'literature-note'), ('fulltext', 'literature-fulltext'), ('Notes', 'personal-reading-note')]:
        candidates = []
        for path in (root / tree).rglob('*.md'):
            try:
                doc = load_document(path)
            except ReadingError:
                continue
            if doc.data.get('zotero_key') != key:
                continue
            if checked_parent_scope(doc.data)[1] != scope:
                continue
            safe_path(root, path.relative_to(root).as_posix(), tree)
            if doc.data.get('type') != kind:
                raise ReadingError(f'Matching identity has missing/conflicting type: {path.relative_to(root)}')
            candidates.append(doc)
        if len(candidates) > 1:
            raise ReadingError(f'Duplicate {tree} identity {scope}/{key}')
        if candidates:
            found[tree] = candidates[0]
    return found


def artifact_fingerprints(root, docs, knowledge_pages=()):
    paths = {doc.path for doc in docs.values()}
    for doc in docs.values():
        for target, style in embedded_images(doc.body.decode('utf-8')):
            _, image_path = resolve_image(root, doc.path, target, style)
            if not image_path.is_file():
                raise ReadingError(f'Missing image: {target}')
            paths.add(image_path)
    for relative in knowledge_pages:
        if not isinstance(relative, str) or not relative.startswith('knowledge/') or '/.meta/' in relative:
            raise ReadingError('knowledge_pages must identify human-facing knowledge/ files')
        path = (root / relative).resolve()
        if not path.is_relative_to((root / 'knowledge').resolve()) or not path.is_relative_to(root.resolve()) or path.suffix != '.md' or not path.is_file():
            raise ReadingError(f'Invalid Knowledge page: {relative}')
        paths.add(path)
    template = root / 'templates/critical-reading-template.md'
    paths.add(template if template.is_file() else PACKAGE / 'assets/analytical-note-template.md')
    fingerprints = {}
    for path in paths:
        label = path.relative_to(root).as_posix() if path.is_relative_to(root) else '@skill/analytical-note-template.md'
        fingerprints[label] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(fingerprints.items()))


def inspect(root, key, scope='library'):
    if not re.fullmatch(r'[A-Z0-9]{8}', key) or not re.fullmatch(r'library|groups/[1-9][0-9]*', scope):
        raise ReadingError('Invalid Zotero key/library scope')
    docs = inventory(root, key, scope)
    events = history(root, key, scope)
    previous = next((e for e in reversed(events) if e.get('status') == 'COMPLETE'), None)
    stages = {tree: tree in docs for tree in ('vault', 'fulltext', 'Notes')}
    report = {'status': 'PARTIAL', 'zotero_key': key, 'scope': scope,
        'artifacts': {tree: d.path.relative_to(root).as_posix() for tree, d in docs.items()},
        'stages': stages, 'next_stage': 'identity', 'warnings': [], 'errors': []}
    if 'fulltext' not in docs:
        report.update(status='PARTIAL_FULLTEXT_MISSING', next_stage='fulltext')
        return report
    fulltext = docs['fulltext']
    try:
        checked_identity(fulltext.data, allow_uri_aliases=True)
        if not fulltext.body.strip():
            raise ReadingError('Formal Fulltext body is empty')
        artifact_fingerprints(root, {'fulltext': fulltext})
    except ReadingError as exc:
        report.update(status='FULLTEXT_FAILED', next_stage='fulltext', errors=[str(exc)])
        return report
    if 'vault' not in docs:
        report.update(status='PARTIAL_NOTE_MISSING', next_stage='analytical')
        return report
    if 'Notes' not in docs:
        report.update(status='PERSONAL_DEFERRED', next_stage='personal')
        return report
    validation = validate_reading(root, docs['vault'].path.relative_to(root).as_posix())
    report['warnings'] += validation['warnings']
    if validation['errors']:
        report.update(status='VALIDATION_FAILED', next_stage='validation', errors=validation['errors'])
        return report
    if events:
        latest = events[-1]
        if latest.get('status') in ('PDF_NOT_FOUND', 'FULLTEXT_DEFERRED', 'FULLTEXT_FAILED', 'MINERU_FAILED', 'IMAGES_INVALID'):
            report.update(status=latest['status'], next_stage='fulltext')
            report['warnings'].append(latest.get('reason', 'Source access or archive review remains deferred'))
            if latest.get('knowledge_decision') in DECISIONS:
                report['knowledge_decision'] = latest['knowledge_decision']
            return report
    if previous:
        issues, summary = validate_knowledge(root)
        report['warnings'] += [i['detail'] for i in issues if i['level'] == 'WARN']
        fingerprints = artifact_fingerprints(root, docs, previous.get('knowledge_pages', []))
        if not summary['errors'] and fingerprints == previous.get('fingerprints') and events[-1].get('status') in ('COMPLETE', 'ALREADY_COMPLETE'):
            report.update(status='ALREADY_COMPLETE', next_stage=None, knowledge_decision=previous['knowledge_decision'])
            return report
        report['warnings'].append('Artifacts/template or latest checkpoint changed; content/Knowledge decision must be reconsidered')
    report.update(status='KNOWLEDGE_DECISION_REQUIRED', next_stage='knowledge')
    return report


def record(root, event):
    event = dict(event)
    key, scope = event.get('zotero_key'), event.get('scope', 'library')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Z0-9]{8}', key) or not re.fullmatch(r'library|groups/[1-9][0-9]*', str(scope)):
        raise ReadingError('Event requires verified zotero_key and scope')
    if event.get('stage') not in STAGES or event.get('status') not in STATUSES:
        raise ReadingError('Invalid stage/status')
    if not isinstance(event.get('title'), str) or not event['title'].strip() or not isinstance(event.get('reason'), str):
        raise ReadingError('Event requires title and reason')
    if event['status'] == 'PERMANENTLY_IGNORED' and event.get('user_confirmed_ignore') is not True:
        raise ReadingError('Permanent ignore needs actual explicit user confirmation')
    event.update(scope=scope, timestamp=datetime.now().astimezone().isoformat(timespec='seconds'))
    # Verify existing log is readable before any append.
    history(root, key, scope)
    human_event = None
    if event['status'] == 'ALREADY_COMPLETE' and inspect(root, key, scope)['status'] != 'ALREADY_COMPLETE':
        raise ReadingError('Actual state is not ALREADY_COMPLETE')
    if event['status'] == 'COMPLETE':
        if event.get('stage') != 'validation' or event.get('pdf_access') not in ('local', 'remote') or event.get('knowledge_decision') not in DECISIONS:
            raise ReadingError('Completion requires final validation, verified PDF access and Knowledge decision')
        reviews = event.get('reviews', {})
        if not isinstance(reviews, dict) or any(reviews.get(k) != 'passed' for k in ('template', 'quotes', 'figures', 'knowledge_coverage')):
            raise ReadingError('Completion requires actual template/quote/figure/Knowledge coverage review')
        if not isinstance(event.get('knowledge_pages', []), list):
            raise ReadingError('knowledge_pages must be a list of actual reviewed pages')
        if event['knowledge_decision'] == 'KNOWLEDGE_UPDATED' and not event.get('knowledge_pages'):
            raise ReadingError('KNOWLEDGE_UPDATED requires actual changed Knowledge pages')
        docs = inventory(root, key, scope)
        if set(docs) != {'vault', 'fulltext', 'Notes'} or not docs['fulltext'].body.strip():
            raise ReadingError('Completion requires nonempty Fulltext and all three layer files')
        checked_identity(docs['fulltext'].data, allow_uri_aliases=True)
        report = validate_reading(root, docs['vault'].path.relative_to(root).as_posix())
        issues, summary = validate_knowledge(root)
        if report['errors'] or summary['errors']:
            raise ReadingError('Required validation failed: ' + json.dumps(report['errors'] + [i for i in issues if i['level'] == 'ERROR'], ensure_ascii=False))
        event['fingerprints'] = artifact_fingerprints(root, docs, event.get('knowledge_pages', []))
        event['paths'] = {tree: d.path.relative_to(root).as_posix() for tree, d in docs.items()}
        event['validation'] = {'reading': report, 'knowledge': summary}
        title = docs['vault'].data['title'].replace('\n', ' ').replace('\r', ' ').replace('|', ' ').replace(']', ')')
        ai_relative = event['paths']['vault'][:-3]
        human_event = f"\n- {event['timestamp'][:10]}：[[{ai_relative}|{title}]]；全文已归档、AI精读已审核、个人页已关联；Knowledge：{event['knowledge_decision']}；适用结构校验与内容审核通过。\n"
    human_path = root / 'knowledge/log.md'
    if human_event and not human_path.resolve().is_relative_to(root.resolve()):
        raise ReadingError('Human log escapes Vault')
    log = technical_path(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
    if human_event:
        human_path.parent.mkdir(parents=True, exist_ok=True)
        with human_path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(human_event)
    return {'status': 'recorded', 'log': log.relative_to(root).as_posix(), 'human_log_appended': bool(human_event)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('inspect')
    check.add_argument('--vault', required=True)
    check.add_argument('--key', required=True)
    check.add_argument('--scope', default='library')
    append = sub.add_parser('record')
    append.add_argument('--vault', required=True)
    append.add_argument('--event-file', required=True, type=Path)
    args = parser.parse_args()
    try:
        root = vault_root(args.vault)
        result = inspect(root, args.key, args.scope) if args.command == 'inspect' else record(root, json.loads(args.event_file.read_text(encoding='utf-8-sig')))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('errors') else 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
