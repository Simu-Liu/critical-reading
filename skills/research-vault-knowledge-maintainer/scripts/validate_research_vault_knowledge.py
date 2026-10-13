#!/usr/bin/env python3
"""Validate frozen Knowledge schema, real AI sources and claim/gap sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE / 'scripts'))
from reading_common import ReadingError, load_document, checked_parent_scope, safe_path

PAGE_TYPES = {'knowledge-theme','knowledge-concept','knowledge-method','knowledge-relation','knowledge-controversy','knowledge-synthesis'}
STATUSES = {'emerging','developing','established','conditional','contested'}
EVIDENCE = {'fulltext_verified','note_only','mixed'}
AGREEMENT = {'strong','mixed','conflicting','insufficient'}
EVIDENCE_ROLE = {'direct','mechanism','conditional','contextual','related'}
VERIFICATION = {'fulltext_verified','note_supported','interpretation'}
GAP_PROVENANCE = {'evidence-backed','interpretive'}
CLAIM_ID = re.compile(r'^(REL|CON|SYN)-[A-Z0-9]+(?:-[A-Z0-9]+)+-\d{2}$')
REQUIRED = {'type','title','aliases','status','evidence_count','source_notes','related','last_updated','evidence_status'}
LINK = re.compile(r'^\[\[([^\]|]+)(?:\|[^\]]*)?\]\]$')


def resolve_knowledge(root, raw):
    if not isinstance(raw,str) or not raw.startswith('knowledge/') or '/.meta/' in raw or '..' in raw.split('/'):
        raise ReadingError('Expected human-facing knowledge/ path')
    path = (root/raw).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_relative_to((root/'knowledge').resolve()) or path.suffix != '.md':
        raise ReadingError('Knowledge path escapes its layer')
    return path


def source_document(root, raw):
    if not isinstance(raw,str):
        raise ReadingError('source_notes entries must be Wiki links or real note paths')
    match = LINK.fullmatch(raw)
    value = match.group(1) if match else raw
    if value.startswith('02vault/'):
        value = value.removeprefix('02')
    if not value.endswith('.md'):
        value += '.md'
    _, path = safe_path(root,value,'vault')
    doc = load_document(path)
    if doc.data.get('type') != 'literature-note' or doc.data.get('note_origin') == 'user':
        raise ReadingError('Source is not a formal AI Analytical Note')
    # Old canonical notes sometimes have only a key; require valid key and use
    # verified scope when URI exists, retaining read compatibility otherwise.
    key=doc.data.get('zotero_key')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Z0-9]{8}',key):
        raise ReadingError('Source Analytical Note has invalid Zotero key')
    scope=checked_parent_scope(doc.data)[1] if doc.data.get('zotero_uri') or doc.data.get('zotero_item') else 'unverified'
    return doc, (scope,key)


def validate(vault):
    vault=Path(vault).resolve()
    issues=[]
    def add(level,code,path,detail):
        issues.append({'level':level,'code':code,'path':str(path),'detail':detail})
    knowledge=vault/'knowledge'
    if not knowledge.is_dir() or not knowledge.resolve().is_relative_to(vault):
        add('ERROR','KNOWLEDGE_ROOT',knowledge,'missing/unsafe knowledge directory')
        return issues, {'pages':0,'errors':1,'warnings':0}
    pages={}
    aliases={}
    for path in knowledge.rglob('*.md'):
        if '.meta' in path.relative_to(knowledge).parts:
            continue
        if not path.resolve().is_relative_to(knowledge.resolve()):
            add('ERROR','PATH_ESCAPE',path,'Knowledge symlink escapes its layer'); continue
        try:
            doc=load_document(path)
        except (OSError,ReadingError) as exc:
            if path.name not in ('index.md','log.md') and path.read_text(encoding='utf-8-sig').startswith('---'):
                add('ERROR','YAML',path,str(exc))
            continue
        data=doc.data
        if data.get('type') not in PAGE_TYPES:
            continue
        pages[path.resolve()]=doc
        missing=REQUIRED-set(data)
        if missing: add('ERROR','SCHEMA_REQUIRED',path,'missing: '+', '.join(sorted(missing)))
        if data.get('status') not in STATUSES: add('ERROR','SCHEMA_STATUS',path,str(data.get('status')))
        if data.get('evidence_status') not in EVIDENCE: add('ERROR','SCHEMA_EVIDENCE_STATUS',path,str(data.get('evidence_status')))
        count=data.get('evidence_count')
        if isinstance(count,bool) or not isinstance(count,int) or count<0: add('ERROR','EVIDENCE_COUNT',path,'non-negative integer required')
        if data['type']=='knowledge-relation' and not {'subject','relation','object','agreement'}<=set(data): add('ERROR','RELATION_REQUIRED',path,'relation properties missing')
        if data['type'] in ('knowledge-relation','knowledge-controversy') and data.get('agreement') not in AGREEMENT: add('ERROR','AGREEMENT',path,str(data.get('agreement')))
        for name in ('source_notes','related','aliases'):
            if not isinstance(data.get(name),list): add('ERROR','SCHEMA_LIST',path,f'{name} must be a list')
        names=[data.get('title')]+(data.get('aliases') if isinstance(data.get('aliases'),list) else [])
        for name in names:
            if isinstance(name,str) and name.strip(): aliases.setdefault(name.strip().casefold(),set()).add(path.resolve())
        text=doc.body.decode('utf-8')
        if '{{' in text or '[[]]' in text or '待填写' in text: add('ERROR','UNFILLED_TEMPLATE',path,'formal page contains placeholders')
        if re.search(r'(?is)<!--\s*(?:claim_id|evidence_role|verification_state|gap_provenance)\s*:',text): add('ERROR','EMBEDDED_MACHINE_METADATA',path,'use .meta sidecars')
        sources=data.get('source_notes',[])
        distinct=set()
        if isinstance(sources,list):
            for raw in sources:
                try:
                    _,identity=source_document(vault,raw)
                    distinct.add(identity)
                except (ReadingError,OSError) as exc: add('ERROR','SOURCE_LINK',path,f'{raw}: {exc}')
            if isinstance(count,int) and not isinstance(count,bool) and count!=len(distinct): add('ERROR','SOURCE_COUNT',path,f'evidence_count={count}, distinct real papers={len(distinct)}')
    for name, paths in aliases.items():
        if len(paths)>1: add('ERROR','ALIAS_CONFLICT',knowledge,name+': '+', '.join(p.relative_to(vault).as_posix() for p in paths))
    meta=knowledge/'.meta'
    for path in (meta/'claims').glob('*.json') if (meta/'claims').is_dir() else ():
        try:
            if not path.resolve().is_relative_to(meta.resolve()): raise ValueError('sidecar path escape')
            record=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(record,dict): raise ValueError('claim must be an object')
        except (OSError,ValueError) as exc: add('ERROR','CLAIM_JSON',path,str(exc)); continue
        required={'claim_id','page_path','section_heading','normalized_statement','statement_hash','evidence_role','verification_state','source_notes'}
        if not required<=set(record): add('ERROR','CLAIM_REQUIRED',path,'missing: '+str(sorted(required-set(record))))
        if not CLAIM_ID.fullmatch(str(record.get('claim_id',''))): add('ERROR','CLAIM_ID',path,'invalid permanent claim id')
        if record.get('evidence_role') not in EVIDENCE_ROLE: add('ERROR','EVIDENCE_ROLE',path,str(record.get('evidence_role')))
        if record.get('verification_state') not in VERIFICATION: add('ERROR','VERIFICATION_STATE',path,str(record.get('verification_state')))
        try:
            page=resolve_knowledge(vault,record.get('page_path'))
            if page not in pages: raise ReadingError('claim page is missing/not formal')
            statement=record.get('normalized_statement','')
            if not isinstance(statement,str) or not statement.strip(): raise ReadingError('normalized_statement missing')
            expected=hashlib.sha256(statement.strip().encode('utf-8')).hexdigest()
            if record.get('statement_hash')!=expected: add('ERROR','STATEMENT_HASH',path,'statement text hash differs')
            heading=record.get('section_heading')
            body=pages[page].body.decode('utf-8')
            if not isinstance(heading,str) or not re.search(r'(?m)^#{1,6}\s+'+re.escape(heading)+r'\s*$',body): add('ERROR','CLAIM_SECTION',path,'claim section missing')
            if statement.strip() not in body: add('ERROR','STATEMENT_DRIFT',path,'statement is not present in current page')
            sources=record.get('source_notes')
            if not isinstance(sources,list) or not sources: raise ReadingError('claim requires real Analytical Note sources')
            page_sources={source_document(vault,s)[1] for s in pages[page].data.get('source_notes',[])}
            for raw in sources:
                source,identity=source_document(vault,raw)
                if identity not in page_sources: add('ERROR','CLAIM_SOURCE',path,'claim source absent from page source_notes')
                if record.get('verification_state')=='fulltext_verified':
                    _,fullpath=safe_path(vault,source.data.get('fulltext_path'),'fulltext',legacy=True)
                    full=load_document(fullpath)
                    if full.data.get('type')!='literature-fulltext' or full.data.get('zotero_key')!=source.data.get('zotero_key') or full.data.get('pdf_key')!=source.data.get('pdf_key') or not full.body.strip(): raise ReadingError('fulltext_verified claim lacks matching formal Fulltext')
        except (OSError,ReadingError) as exc: add('ERROR','CLAIM_TRACE',path,str(exc))
    for path in (meta/'gaps').glob('*.json') if (meta/'gaps').is_dir() else ():
        try:
            if not path.resolve().is_relative_to(meta.resolve()): raise ValueError('gap path escape')
            record=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(record,dict): raise ValueError('gap must be an object')
        except (OSError,ValueError) as exc: add('ERROR','GAP_JSON',path,str(exc)); continue
        if record.get('gap_provenance') not in GAP_PROVENANCE: add('ERROR','GAP_PROVENANCE',path,str(record.get('gap_provenance')))
    if not pages: add('WARN','NO_PAGES',knowledge,'no formal pages; structure-only check, not a scientific content audit')
    return issues, {'pages':len(pages),'errors':sum(i['level']=='ERROR' for i in issues),'warnings':sum(i['level']=='WARN' for i in issues)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault',type=Path,required=True)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    issues,summary=validate(args.vault)
    if args.json: print(json.dumps({'summary':summary,'issues':issues},ensure_ascii=False,indent=2))
    else:
        for issue in issues: print(f"{issue['level']} {issue['code']} | {issue['path']} | {issue['detail']}")
        print(f"RESULT: {'FAIL' if summary['errors'] else 'PASS'} ({summary['pages']} pages, {summary['errors']} errors, {summary['warnings']} warnings)")
    return 1 if summary['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
