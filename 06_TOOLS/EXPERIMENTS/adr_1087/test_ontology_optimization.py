"""Synthetic exact contracts and operation counts; no real corpus/model load."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace as S

import pytest
from conftest import term_glossary
from test_batch_reference_navigation import connected
from test_definition_context import inv, definition_source
from test_ontology_context import configure, bundle, attach
from test_ontology_review_adr1061 import prepare, confirmed_input
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_context as oc, ontology_review as review
from semantic_runtime.legal_agent import ontology_io as io, ontology_input as oi, ontology_compiler as compiler
from semantic_runtime.legal_agent import repository
from semantic_runtime.legal_agent.errors import ContractError, ProposalError

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1079/departure-a2-r1/revisions/rev-002/snapshot/02_BACKEND/semantic_runtime/legal_agent'


def original(module, name):
    tree = ast.parse((BASE / Path(module.__file__).name).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = dict(vars(module))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(BASE), 'exec'), namespace)
    return namespace[name]


def journal(n):
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    db.executescript('CREATE TABLE evidence_unit(evidence_id TEXT PRIMARY KEY,source_id,document_id,text_hash,metadata_json);'
        'CREATE TABLE evidence_span(evidence_id TEXT,ordinal INTEGER,block_id,start_cp,end_cp,text,block_hash,span_hash,PRIMARY KEY(evidence_id,ordinal));')
    for i in range(n):
        ident=f'E{i:04d}'; parts=[f'  원문 {i}\n',f'두번째\t{i}']; text='\n'.join(parts)
        db.execute('INSERT INTO evidence_unit VALUES(?,?,?,?,?)',(ident,'s','d',repository.text_hash(text),'{"version":"v"}'))
        for k in (1,0):
            db.execute('INSERT INTO evidence_span VALUES(?,?,?,?,?,?,?,?)',(ident,k,str(k),0,len(parts[k]),parts[k],'h','h'))
    return db


@pytest.mark.parametrize('n',[0,1,8,80,129,300])
def test_targeted_evidence_batch_count_order_and_exact_equivalence(n):
    db=journal(n+2); repo=S(db=db); ids=[f'E{i:04d}' for i in reversed(range(n))]
    sql=[]; db.set_trace_callback(sql.append)
    before={eid:repository.WorkRepository.evidence(repo,eid) for eid in ids}; before_count=len(sql)
    sql.clear(); after=io.evidence(repo,ids+ids[:1]); after_count=len(sql)
    assert after==before and before_count==2*n and after_count==2*((n+127)//128)
    assert all('WHERE evidence_id IN (' in q for q in sql)
    for table,order in [('evidence_unit','evidence_id'),('evidence_span','evidence_id,ordinal')]:
        plan=[r[3] for r in db.execute(f'EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE evidence_id IN (?,?) ORDER BY {order}',('E0000','E0001'))]
        assert any('SEARCH' in row for row in plan) and not any('TEMP B-TREE' in row for row in plan)
    print('EVIDENCE_SQL',n,before_count,after_count)
    db.close()


def test_missing_and_corrupted_evidence_rejected():
    db=journal(2); repo=S(db=db)
    with pytest.raises(ProposalError): io.evidence(repo,['missing'])
    db.execute("UPDATE evidence_span SET text='changed' WHERE evidence_id='E0001' AND ordinal=0")
    with pytest.raises(ContractError): io.evidence(repo,['E0000','E0001'])
    # Unrequested corrupted rows are not consulted by a selected-ID read.
    assert io.evidence(repo,['E0000'])['E0000']['evidence_id']=='E0000'
    db.close()


def test_receipt_index_returns_only_same_presentation_in_event_order():
    db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)')
    for i in range(1000):
        p={'presentation_id':'current' if i in (17,999) else 'past-'+str(i),'attempt':i}
        db.execute('INSERT INTO event VALUES(?,?,?,?)',(i,'NAVIGATION_INPUT_DELIVERED',json.dumps(p),digest(p)))
    repo=S(db=db); sql=[]; db.set_trace_callback(sql.append)
    rows=list(io.delivery_events(repo,'current'))
    assert [json.loads(r['payload_json'])['attempt'] for r in rows]==[17,999]
    assert len([q for q in sql if q.startswith('CREATE')])==1
    sql.clear(); assert list(io.delivery_events(repo,'absent'))==[]
    assert len(sql)==1 and sql[0].startswith('SELECT')
    plan=[r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT payload_json,payload_hash FROM event WHERE kind='NAVIGATION_INPUT_DELIVERED' AND json_extract(payload_json,'$.presentation_id') IS ? ORDER BY seq",('current',))]
    assert any('SEARCH' in r and io.RECEIPT_INDEX in r for r in plan)
    assert not any('TEMP B-TREE' in r for r in plan)
    # Reopening an object uses existing bytes/index, never rewrites a receipt.
    assert list(io.delivery_events(S(db=db),'current'))==rows
    print('RECEIPT_ROWS',1000,len(rows),'PLAN',plan)
    db.close()


def test_cached_snapshot_checked_on_mutation_and_result_is_detached(inv,monkeypatch):
    i,_=inv; configure(i,[bundle(i.s)],'A1')
    calls=[]; validate=compiler.validate_bundle
    monkeypatch.setattr(compiler,'validate_bundle',lambda b:calls.append(b['bundle_id']) or validate(b))
    first=oc.config(i); second=oc.config(i); assert first==second and len(calls)==1
    first['snapshot']['bundles'][0]['concept']['label']='not shared'
    assert oc.config(i)==second
    i.policy['ontology_context']['snapshot']['bundles'][0]['concept']['label']='changed'
    with pytest.raises(ContractError,match='binding'): oc.config(i)
    snap=i.policy['ontology_context']['snapshot']; i.policy['ontology_context']['snapshot_sha256']=digest(snap)
    assert oc.config(i)['snapshot']==snap and len(calls)==2
    i.policy['ontology_context']['mode']='unsupported'
    with pytest.raises(ContractError): oc.config(i)


@pytest.mark.parametrize('mode',['A1','A2'])
def test_attach_same_full_server_card_without_unused_alternate(inv,monkeypatch,mode):
    i,_,_=prepare(inv,mode); old_attach=original(oc,'attach')
    count=[]; compile_fn=compiler.compile_bundle
    monkeypatch.setattr(compiler,'compile_bundle',lambda *a,**k:count.append(k['mode']) or compile_fn(*a,**k))
    queries=[]; i.s.repo.db.set_trace_callback(queries.append)
    before={'sources':[],'basis':[]}; old_attach(i,before); old_count=len(count)
    sql_before=sum(q.startswith('SELECT * FROM evidence_') for q in queries); queries.clear()
    count.clear(); after=attach(i); new_count=len(count)
    sql_after=sum(q.startswith('SELECT * FROM evidence_') for q in queries)
    i.s.repo.db.set_trace_callback(None)
    assert before==after and (old_count,new_count)==(2,1)
    assert sql_after < sql_before
    print('ATTACH_EVIDENCE_SQL',mode,sql_before,sql_after)
    print('COMPILE_COUNT',mode,old_count,new_count)


@pytest.mark.parametrize('mode',['A1','A2'])
@pytest.mark.parametrize('selection',['all','one','none'])
def test_prompt_reduction_preserves_every_semantic_field_and_source(inv,mode,selection):
    i,b,data=prepare(inv,mode); old_project=original(review,'project')
    selected=None if selection=='all' else data['sources'][:1] if selection=='one' else []
    before=deepcopy(data); after=deepcopy(data)
    old_project(before,sources=selected); review.project(after,sources=selected)
    assert before['sources']==after['sources'] and before['basis']==after['basis']
    # Full proof pages are preserved; only the separately versioned model card changes.
    assert before['ontology_review']==after['ontology_review']
    old=before['ontology_bundles'][0]; new=after['ontology_bundles'][0]
    assert old['presentation']==new['presentation'] and old['connection_scan']==new['connection_scan']
    expected=deepcopy(old['payload']); expected.pop('bundle_sha256')
    def strip(value):
        if isinstance(value,list):
            for row in value: strip(row)
        elif isinstance(value,dict):
            a=value.get('anchor')
            if isinstance(a,dict) and oi.ANCHOR_PROOF<=set(a):
                for k in oi.ANCHOR_PROOF: a.pop(k)
            for child in value.values(): strip(child)
    strip(expected)
    assert new['payload']==expected and new['payload_sha256']==digest(expected)
    chars=lambda x:len(json.dumps(x,ensure_ascii=False))
    assert chars(new)<chars(old)
    assert all(row['anchor']['label'] for row in new['payload']['provisions'])
    print('ONTOLOGY_CARD_CHARS',mode,selection,chars(old),chars(new))


def test_current_event_hash_tamper_still_rejected(inv):
    i,_,data=prepare(inv,'A1'); review.project(data); confirmed_input(i,data)
    db=i.s.repo.db
    for row in list(db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='event'")):
        db.execute('DROP TRIGGER '+row[0])
    db.execute("UPDATE event SET payload_hash=? WHERE kind='NAVIGATION_INPUT_DELIVERED'",('0'*64,))
    with pytest.raises(ContractError,match='event hash'): review.reconcile(i,data)


def test_scope_is_checked_before_batch_read(inv,monkeypatch):
    i,_,_=prepare(inv,'A1')
    i.s.scope=set()
    monkeypatch.setattr(io,'evidence',lambda *a:pytest.fail('denied source caused evidence read'))
    with pytest.raises(ContractError,match='DOCUMENT_NOT_AUTHORIZED'): attach(i)
