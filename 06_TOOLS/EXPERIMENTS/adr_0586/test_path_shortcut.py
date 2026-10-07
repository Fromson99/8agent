"""Real-source, no-model contracts for the node-bound path candidate."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = (ROOT/'02_BACKEND/lawrag/research/candidates/adr_0586/path-prefetch'
             '/snapshot/02_BACKEND/semantic_runtime/legal_agent')
sys.path.insert(0, str(ROOT/'02_BACKEND'))
import semantic_runtime.legal_agent as package
package.__path__.insert(0, str(CANDIDATE))
from semantic_runtime.legal_agent import path_shortcut
from semantic_runtime.storage import Store

GENERATION = ROOT/'01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation'
DESIGN = json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0586-node-bound-path-prefetch'
                     '/artifacts/design/cases.json').read_text())


def units_from_store(store, did):
    result = {}
    for row in store.db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
        value = json.loads(row['json'])
        result[(did,str(row['unit_id']))] = {'parent':str(row['parent_id']) if row['parent_id'] is not None else None,
                                             'span':value['span'],'family':value.get('family'),
                                             'title':value.get('title','')}
    return result


def test_actual_trace_compiles_minimal_path_and_stays_scoped(tmp_path):
    store=Store(GENERATION)
    try:
        did=DESIGN['document_id'];db=path_shortcut.PathMemory(tmp_path/'memory.sqlite')
        for case_id in ('RE02','RE03'):
            seed=DESIGN['seed_runs'][case_id]
            raw=(ROOT/seed['path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==seed['sha256']
            entries=db.observe(store=store,trace=json.loads(raw),trace_hash=seed['sha256'],
                               document_id=did,article_unit_id=DESIGN['article_unit_id'])
            assert len(entries)==1
            expected=next(c for c in DESIGN['cases'] if c['seed_case_id']==case_id)
            db.verify_probe(entries[0],expected['required_block_ids'])
            plan=db.compile(store=store,question=expected['question'],document_id=did,
                            focus_unit_id=expected['focus_unit_id'],allowed_document_ids=[did],
                            allowed_status=('VERIFIED_PROBE',))
            assert plan['status']=='HIT'
            assert [t['unit_id'] for t in plan['targets']]==[('10' if case_id=='RE02' else '11')]
            assert all(t['extent']=='exact' for t in plan['targets'])
        negative=DESIGN['negative_case']
        assert db.compile(store=store,question=negative['question'],document_id=did,
                          focus_unit_id=negative['focus_unit_id'],allowed_document_ids=[did],
                          allowed_status=('VERIFIED_PROBE',))['status']=='NO_MATCH'
        assert db.compile(store=store,question=DESIGN['cases'][0]['question'],document_id=did,
                          focus_unit_id='9',allowed_document_ids=[],
                          allowed_status=('VERIFIED_PROBE',))['status']=='OUT_OF_SCOPE'
        db.close()
    finally:
        store.close()


def test_overview_is_preview_and_graph_walk_is_bounded(tmp_path):
    store=Store(GENERATION)
    try:
        did=DESIGN['document_id'];units=units_from_store(store,did)
        overview=path_shortcut.article_overview(store,units,did,DESIGN['article_unit_id'])
        assert overview['article_direct_text'].startswith('제1-2조')
        assert all(row['citation_eligible'] is False for row in overview['child_index'])
        assert len(overview['child_index'])==12
        assert sum(len(row['preview']) for row in overview['child_index'])<1200
        db=path_shortcut.PathMemory(tmp_path/'memory.sqlite')
        seed=DESIGN['seed_runs']['RE02'];raw=(ROOT/seed['path']).read_bytes()
        first=db.observe(store=store,trace=json.loads(raw),trace_hash=seed['sha256'],
                         document_id=did,article_unit_id='2')[0]
        db.verify_probe(first,['9','10'])
        second={**first,'from_unit_id':'10','from_anchor':path_shortcut.anchor(store,did,'10'),
                'to_unit_id':'11','to_anchor':path_shortcut.anchor(store,did,'11'),
                'cues':['연결재무제표작성대상법인'],'proof':{'kind':'SYNTHETIC_CHAIN_TEST'}}
        db.insert({**second,'status':'VERIFIED_PROBE'})
        question='외국 지주회사 자회사와 연결재무제표 작성대상 법인 정의'
        assert len(db.compile(store=store,question=question,document_id=did,
                 focus_unit_id='9',allowed_document_ids=[did],
                 allowed_status=('VERIFIED_PROBE',),max_hops=2)['targets'])==2
        assert len(db.compile(store=store,question=question,document_id=did,
                 focus_unit_id='9',allowed_document_ids=[did],
                 allowed_status=('VERIFIED_PROBE',),max_hops=1)['targets'])==1
        assert db.compile(store=store,question=question,document_id=did,
                 focus_unit_id='9',allowed_document_ids=[did],allowed_status=('VERIFIED_PROBE',),
                 max_chars=1)['status']=='BUDGET_EXCEEDED'
        db.close()
    finally:
        store.close()
