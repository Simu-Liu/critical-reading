"""Offline integration checks for resumed ingest, Knowledge, collection and indexes."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'skills/research-vault-knowledge-maintainer/scripts'))
from init_vault import initialize
from reading_common import load_document, ReadingError
from link_personal_note import plan_links, commit_changes
from workflow_state import inspect, record
from refresh_literature_indexes import refresh
from validate_research_vault_knowledge import validate as validate_knowledge
from validate_research_vault_literature_links import validate as validate_literature
import zotero_readonly_fetch as fetcher


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'vault'
        initialize(self.root,Path(self.temp.name)/'config.toml')
        self.note=self.root/'vault/Cell/paper.md'
        self.full=self.root/'fulltext/Cell/ABCD1234.md'
        self.note.parent.mkdir(parents=True,exist_ok=True)
        self.full.parent.mkdir(parents=True,exist_ok=True)
        ai=load_document(ROOT/'assets/analytical-note-template.md')
        ai.data.update(title='Synthetic paper',zotero_key='ABCD1234',pdf_key='PDF12345',
            zotero_uri='zotero://select/library/items/ABCD1234',pdf_uri='zotero://open-pdf/library/items/PDF12345',
            note_path='vault/Cell/paper.md',analytical_note_path='vault/Cell/paper.md',
            fulltext_path='fulltext/Cell/ABCD1234.md',personal_note_path=None,
            date_created='2026-10-13',research_directions=['实体瘤CAR-T'])
        self.note.write_bytes(ai.render(body=b'# Synthetic AI\n\nEvidence is qualified.\n'))
        self.full.write_text('---\ntype: literature-fulltext\ntitle: Synthetic paper\nzotero_key: ABCD1234\npdf_key: PDF12345\nzotero_uri: zotero://select/library/items/ABCD1234\npdf_uri: zotero://open-pdf/library/items/PDF12345\nnote_path: vault/Cell/paper.md\n---\n# Original\nLipid supplementation partly restores surface signal.\n',encoding='utf-8')

    def tearDown(self): self.temp.cleanup()

    def link(self):
        report,changes=plan_links(self.root,'vault/Cell/paper.md',today='2026-10-13')
        commit_changes(self.root,changes)
        return self.root/report['personal']

    def event(self,decision='NO_KNOWLEDGE_CHANGE',pages=None):
        return {'zotero_key':'ABCD1234','scope':'library','stage':'validation','status':'COMPLETE',
            'title':'Synthetic paper','reason':'Offline reviewed fixture', 'pdf_access':'remote',
            'knowledge_decision':decision,'knowledge_pages':pages or [],
            'reviews':{k:'passed' for k in ('template','quotes','figures','knowledge_coverage')}}

    def make_page(self,source=None,statement='脂质补充支持部分贡献，尚不能确定受体命运。'):
        import yaml
        path=self.root/'knowledge/关系/受体保留.md'
        path.parent.mkdir(parents=True,exist_ok=True)
        data={'type':'knowledge-relation','title':'脂质与受体保留','aliases':['Receptor retention'],
            'status':'developing','evidence_count':1,'source_notes':[source or '[[vault/Cell/paper|合成论文]]'],
            'related':[],'last_updated':'2026-10-13','evidence_status':'fulltext_verified',
            'subject':'脂质状态','relation':'参与','object':'表面受体信号','agreement':'insufficient'}
        path.write_text('---\n'+yaml.safe_dump(data,allow_unicode=True,sort_keys=False)+'---\n## 证据判断\n'+statement+'\n',encoding='utf-8')
        claim={'claim_id':'REL-LIPID-RETENTION-01','page_path':path.relative_to(self.root).as_posix(),
            'section_heading':'证据判断','normalized_statement':statement,
            'statement_hash':hashlib.sha256(statement.encode()).hexdigest(),'evidence_role':'mechanism',
            'verification_state':'fulltext_verified','source_notes':data['source_notes']}
        sidecar=self.root/'knowledge/.meta/claims/REL-LIPID-RETENTION-01.json'
        sidecar.write_text(json.dumps(claim,ensure_ascii=False),encoding='utf-8')
        return path,sidecar

    def test_resume_no_knowledge_change_and_readonly_inspection(self):
        original_body=load_document(self.full).body
        self.assertEqual(inspect(self.root,'ABCD1234')['next_stage'],'personal')
        self.link()
        self.assertEqual(inspect(self.root,'ABCD1234')['next_stage'],'knowledge')
        record(self.root,self.event())
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(inspect(self.root,'ABCD1234')['status'],'ALREADY_COMPLETE')
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(load_document(self.full).body,original_body)
        log=(self.root/'knowledge/log.md').read_text(encoding='utf-8')
        self.assertNotIn('ABCD1234',log)
        self.assertIn('NO_KNOWLEDGE_CHANGE',log)

    def test_changed_personal_body_invalidates_checkpoint_but_is_preserved(self):
        personal=self.link()
        record(self.root,self.event())
        personal.write_bytes(personal.read_bytes()+b'My new thought?\n')
        body=load_document(personal).body
        self.assertNotEqual(inspect(self.root,'ABCD1234')['status'],'ALREADY_COMPLETE')
        self.assertEqual(load_document(personal).body,body)

    def test_missing_fulltext_only_requests_fulltext_and_does_not_rewrite_ai(self):
        before=self.note.read_bytes()
        self.full.unlink()
        self.assertEqual(inspect(self.root,'ABCD1234')['status'],'PARTIAL_FULLTEXT_MISSING')
        self.assertEqual(self.note.read_bytes(),before)

    def test_completion_rejected_without_reviews_and_writes_nothing(self):
        self.link()
        event=self.event(); event['reviews']={}
        with self.assertRaises(ReadingError): record(self.root,event)
        self.assertFalse((self.root/'knowledge/.meta/critical-reading/workflow.jsonl').exists())

    def test_stage_failure_is_append_only_and_retryable(self):
        event={'zotero_key':'ABCD1234','scope':'library','stage':'fulltext','status':'FULLTEXT_DEFERRED',
            'title':'Synthetic paper','reason':'No accessible converter'}
        record(self.root,event)
        first=(self.root/'knowledge/.meta/critical-reading/workflow.jsonl').read_bytes()
        event['status']='FULLTEXT_CREATED'; record(self.root,event)
        self.assertTrue((self.root/'knowledge/.meta/critical-reading/workflow.jsonl').read_bytes().startswith(first))
        self.assertNotEqual(inspect(self.root,'ABCD1234')['status'],'ALREADY_COMPLETE')

    def test_final_source_deferred_preserves_reason_and_knowledge_decision(self):
        self.link()
        event = self.event()
        event.update(status='FULLTEXT_DEFERRED', pdf_access='unavailable', reason='PDF unavailable')
        record(self.root, event)
        result = inspect(self.root, 'ABCD1234')
        self.assertEqual(result['status'], 'FULLTEXT_DEFERRED')
        self.assertEqual(result['next_stage'], 'fulltext')
        self.assertEqual(result['knowledge_decision'], 'NO_KNOWLEDGE_CHANGE')
        self.assertFalse((self.root/'knowledge/log.md').exists())

    def test_empty_knowledge_update_cannot_complete(self):
        self.link()
        with self.assertRaises(ReadingError): record(self.root, self.event('KNOWLEDGE_UPDATED'))
        self.assertFalse((self.root/'knowledge/.meta/critical-reading/workflow.jsonl').exists())

    def test_knowledge_update_trace_and_drift(self):
        self.link()
        page,claim=self.make_page()
        issues,summary=validate_knowledge(self.root)
        self.assertEqual(summary['errors'],0,issues)
        record(self.root,self.event('KNOWLEDGE_UPDATED',[page.relative_to(self.root).as_posix()]))
        self.assertEqual(inspect(self.root,'ABCD1234')['status'],'ALREADY_COMPLETE')
        page.write_bytes(page.read_bytes().replace('部分贡献'.encode(),'确定完整通路'.encode()))
        issues,summary=validate_knowledge(self.root)
        self.assertIn('STATEMENT_DRIFT',{i['code'] for i in issues})
        self.assertNotEqual(inspect(self.root,'ABCD1234')['status'],'ALREADY_COMPLETE')

    def test_personal_page_cannot_be_knowledge_evidence(self):
        personal=self.link()
        self.make_page('[['+personal.relative_to(self.root).as_posix()[:-3]+'|我的idea]]')
        issues,summary=validate_knowledge(self.root)
        self.assertGreater(summary['errors'],0)
        self.assertIn('SOURCE_LINK',{i['code'] for i in issues})

    def test_claim_without_matching_fulltext_not_verified(self):
        self.link(); self.make_page(); self.full.unlink()
        issues,summary=validate_knowledge(self.root)
        self.assertIn('CLAIM_TRACE',{i['code'] for i in issues})

    def test_indexes_preserve_custom_prose_are_idempotent_and_exclude_other_layers(self):
        report=refresh(self.root,True)
        self.assertEqual(len(report['changed']),4)
        self.assertFalse((self.root/'vault/_index/文献索引.md').exists())
        refresh(self.root)
        issues, summary = validate_literature(self.root)
        self.assertEqual(summary['notes_scanned'], 1)
        self.assertEqual(summary['errors'], 0, issues)
        path=self.root/'vault/_index/文献索引.md'
        path.write_bytes(path.read_bytes()+'\n我的索引说明\n'.encode())
        refresh(self.root)
        self.assertIn('我的索引说明',path.read_text(encoding='utf-8'))
        self.assertEqual(refresh(self.root)['changed'],[])
        for p in (self.root/'vault/_index').glob('*.md'):
            text=p.read_text(encoding='utf-8')
            self.assertIn('FROM "vault"',text)
            self.assertIn('type = "literature-note"',text)
            self.assertNotIn('FROM "Notes"',text)

    def test_unmanaged_index_is_not_overwritten(self):
        path=self.root/'vault/_index/文献索引.md'
        path.write_text('My manual index',encoding='utf-8')
        report=refresh(self.root)
        self.assertEqual(path.read_text(encoding='utf-8'),'My manual index')
        self.assertTrue(report['warnings'])


class SQLiteCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.data=Path(self.temp.name)
        db=sqlite3.connect(self.data/'zotero.sqlite')
        db.executescript('''
        CREATE TABLE items(itemID INTEGER PRIMARY KEY,key TEXT,itemTypeID INTEGER,libraryID INTEGER);
        CREATE TABLE libraries(libraryID INTEGER PRIMARY KEY,type TEXT);
        CREATE TABLE groups(groupID INTEGER,libraryID INTEGER);
        CREATE TABLE itemTypes(itemTypeID INTEGER,typeName TEXT);
        CREATE TABLE fields(fieldID INTEGER PRIMARY KEY,fieldName TEXT);
        CREATE TABLE itemData(itemID INTEGER,fieldID INTEGER,valueID INTEGER);
        CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY,value TEXT);
        CREATE TABLE collections(collectionID INTEGER PRIMARY KEY,key TEXT,collectionName TEXT,libraryID INTEGER);
        CREATE TABLE collectionItems(collectionID INTEGER,itemID INTEGER);
        CREATE TABLE itemAttachments(itemID INTEGER,parentItemID INTEGER,path TEXT,contentType TEXT);
        CREATE TABLE itemNotes(itemID INTEGER,parentItemID INTEGER,note TEXT);
        CREATE TABLE deletedItems(itemID INTEGER);
        INSERT INTO libraries VALUES(1,'user'),(2,'group');
        INSERT INTO groups VALUES(42,2);
        INSERT INTO itemTypes VALUES(1,'journalArticle'),(2,'attachment');
        INSERT INTO fields VALUES(1,'title');
        INSERT INTO items VALUES(1,'ABCD1234',1,1),(2,'PDF12345',2,1),(3,'PDF23456',2,1),(4,'ABCD1234',1,2);
        INSERT INTO itemDataValues VALUES(1,'Test paper'),(2,'Group paper');
        INSERT INTO itemData VALUES(1,1,1),(4,1,2);
        INSERT INTO collections VALUES(1,'COLL1234','My collection',1);
        INSERT INTO collectionItems VALUES(1,1),(1,2);
        INSERT INTO itemAttachments VALUES(2,1,'storage:paper.pdf','application/pdf'),(3,1,'storage:paper.pdf','application/pdf');
        ''')
        db.commit(); db.close()
        for key in ('PDF12345','PDF23456'):
            storage=self.data/'storage'/key; storage.mkdir(parents=True)
            (storage/'paper.pdf').write_bytes(b'%PDF-fixture')
            (storage/'.zotero-ft-cache').write_text('original cache',encoding='utf-8')

    def tearDown(self): self.temp.cleanup()

    def run_fetch(self,args):
        out,err=io.StringIO(),io.StringIO()
        before=hashlib.sha256((self.data/'zotero.sqlite').read_bytes()).hexdigest()
        with mock.patch.object(sys,'argv',['fetch','--data-dir',str(self.data),*args]),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=fetcher.main()
        self.assertEqual(before,hashlib.sha256((self.data/'zotero.sqlite').read_bytes()).hexdigest())
        return code,out.getvalue(),err.getvalue()

    def test_collection_direct_parents_and_multpdf_selection(self):
        code,out,err=self.run_fetch(['--collection-key','COLL1234'])
        self.assertEqual(code,0,err)
        result=json.loads(out)
        self.assertEqual(result['item_count'],1)
        self.assertTrue(result['items'][0]['pdf_selection_required'])
        self.assertIsNone(result['items'][0]['pdf_key'])
        code,out,err=self.run_fetch(['--key','ABCD1234'])
        self.assertEqual(code,2)
        code,out,err=self.run_fetch(['--key','ABCD1234','--pdf-key','PDF23456'])
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)['pdf_key'],'PDF23456')
        self.assertTrue(json.loads(out)['cache_found'])

    def test_group_scope_not_merged_and_child_key_rejected(self):
        code,out,err=self.run_fetch(['--key','ABCD1234','--group-id','42'])
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)['scope'],'groups/42')
        self.assertEqual(json.loads(out)['zotero_uri'],'zotero://select/groups/42/items/ABCD1234')
        code,out,err=self.run_fetch(['--key','PDF12345'])
        self.assertEqual(code,2)


if __name__=='__main__': unittest.main()
