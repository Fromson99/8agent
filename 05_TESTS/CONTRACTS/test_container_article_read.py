"""Real generated empty-own containers; synthetic sources and model transport only."""
from copy import deepcopy
from types import SimpleNamespace
import json,sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.unit_fulltext import build,UnitFulltextIndex
from semantic_runtime.legal_agent import law_navigation as ln,law_candidates as lc,unit_reading as ur,unit_relations as rel,completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError,BudgetExhausted
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source
from test_unit_fulltext_adaptive_read import session,hit
from test_structure_reading import setup,value
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT
from test_investigation_scope_recovery import ScopeTransport
from test_unit_read_canonical_boundaries import grouped

@pytest.fixture
def tree(tmp_path,term_glossary):
    texts=['제1조 승인 규칙','① 다음 각 호의 승인 기준을 적용한다.',
           '1. 승인 원칙은 다음 목과 같다.','가. 긴급 승인 예외는 허용한다.',
           '2. 일반 승인 예외는 허용하지 않는다.','② 승인 후 보고한다.']
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',texts),('other','비공개모의',['별도 원문'])])
    nodes=[('0',None,'kr_article','제1조',0,6),('1','0','circled','①',1,5),
           ('2','1','dot_number:1','1.',2,4),('3','2','hangul_dot','가.',3,4),
           ('4','1','dot_number:1','2.',4,5),('5','0','circled','②',5,6),
           ('6','0','text','도입문',0,1)]
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid,parent,family,surface,lo,hi in nodes:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,
                json.dumps({'family':family,'surface':surface,'title':'','span':[lo,hi]},ensure_ascii=False)))
        db.execute("UPDATE source_block SET unit_id='6' WHERE document_id='d' AND block_id='0'")
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';idx=tmp_path/'unit-index';build(gen,gen/'navigation',idx,workers=1)
    with sqlite3.connect(gen/'store.sqlite') as db:
        assert db.execute("SELECT COUNT(*) FROM source_block WHERE document_id='d' AND unit_id='0'").fetchone()[0]==0
    return gen,UnitFulltextIndex(idx,json.loads((gen/'navigation/manifest.json').read_bytes()))

def action(s,sid,unit=None):
    identity={'source_id':sid,'document_id':s.tools.sources[sid]['document_id']}
    if unit is not None:identity['unit_id']=unit
    return {'T':{'id':'T','action':'READ_ARTICLES','identity':identity,'label':'선택한 조문 전체 읽기'}}

def execute(inv,actions):
    data,_=inv.view();v=value(data,'READ_ARTICLES','T')
    inv.execute_tool(v,{'sources':[]},actions)
    return v

def acquired_blocks(inv):
    return {p['block_id'] for r in inv.p['selected'].values() for e in r['evidence'] for p in e['spans']}

@pytest.mark.parametrize('explicit_unit',[None,'0','1'])
def test_container_read_preserves_exact_selected_subtree(session,explicit_unit):
    native,_=session;inv,_=setup(native);sid=hit(native)['source_id'];s=native.sources
    assert not ur.blocks(s,'d','0','exact')
    assert all(o['extent']!='exact' for o in ur.offers(s,rel.hit_for(s,sid,None)))
    execute(inv,action(s,sid,explicit_unit))
    expected={'1','2','3','4'} if explicit_unit=='1' else {'0','1','2','3','4','5'}
    assert acquired_blocks(inv)==expected
    assert all(e['document_id']=='d' for r in inv.p['selected'].values() for e in r['evidence'])
    assert all(g['status']!='ACTIVE' for g in inv.p['groups'].values())
    assert inv.p['basis_history']=={}
    for r in inv.p['selected'].values():
        assert r['offer']['unit_id']==(explicit_unit or '0')
        for e in r['evidence']:s.source.verify(e)


def test_same_completed_read_and_resume_reuse_evidence_and_budget(session):
    native,_=session;inv,rec=setup(native);actions=action(inv.s,hit(native)['source_id'])
    decision=execute(inv,actions);state=deepcopy(inv.p['read_state']);checkpoint=deepcopy(inv.p)
    resumed=ln.Investigation(inv.s,inv.question,rec,None,120,checkpoint,None)
    resumed.execute_tool(decision,{'sources':[]},actions)
    assert resumed.p['read_state']==state and acquired_blocks(resumed)=={'0','1','2','3','4','5'}
    assert all(p['status']=='ACQUIRED' for p in resumed.p['read_plans'].values())


def test_interrupted_container_read_keeps_evidence_and_continues_same_scope(session,monkeypatch):
    native,_=session;inv,rec=setup(native);actions=action(inv.s,hit(native)['source_id']);original=ur.read
    def interrupt(s,h,o,**kw):
        if o['id']=='subtree:0':raise TimeoutError('synthetic selected-parent interruption')
        return original(s,h,o,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(ur,'read',interrupt)
        with pytest.raises(TimeoutError):execute(inv,actions)
    assert next(iter(inv.p['read_plans'].values()))['status']=='INTERRUPTED'
    prior={e['evidence_id'] for e in inv.s.repo.evidence()};assert prior
    checkpoint=deepcopy(inv.p);before=checkpoint['read_state']['chars']
    resumed=ln.Investigation(inv.s,inv.question,rec,None,120,checkpoint,None)
    execute(resumed,actions)
    assert prior<={e['evidence_id'] for e in inv.s.repo.evidence()}
    assert resumed.p['read_state']['chars']>=before
    assert acquired_blocks(resumed)=={'0','1','2','3','4','5'}


def test_container_read_cannot_reset_exhausted_character_budget(session,monkeypatch):
    native,_=session;inv,_=setup(native);actions=action(inv.s,hit(native)['source_id'])
    state=inv.p['read_state'];before=state['chars']
    monkeypatch.setitem(ur.POLICY,'initial_chars',before)
    with pytest.raises(BudgetExhausted):execute(inv,actions)
    assert state['chars']==before and not inv.p['selected']
    assert not inv.p.get('read_plans')  # Rejected before acknowledging or starting a tool.


def test_foreign_source_is_not_made_readable_by_container_resolution(session):
    native,_=session;inv,_=setup(native)
    foreign=next((sid for sid,src in inv.s.tools.sources.items() if src['document_id']=='other'),None)
    assert foreign is not None and 'other' not in inv.s.scope
    src=inv.s.tools.sources[foreign]
    resolved=lc.structure_hit(inv.s,foreign,src['unit_id'])
    with pytest.raises(ContractError,match='outside current scope'):
        ur.acquire_batch(inv.s,[resolved],inv.p['read_state'])
    assert not inv.p['selected']


def test_container_without_bound_body_still_fails_closed(session,monkeypatch):
    native,_=session;inv,_=setup(native);sid=hit(native)['source_id']
    sources=dict(inv.s.tools.sources)
    sources[sid]={**sources[sid],'blocks':[]}
    monkeypatch.setattr(inv.s.tools,'sources',sources)
    with pytest.raises(ContractError,match='SUBTREE_CROSSES_SOURCE_BOUNDARY'):execute(inv,action(inv.s,sid))
    assert not inv.p['selected']
    assert not inv.p.get('read_plans')


@pytest.mark.parametrize('document,question,expected',[
    ('chap','모의장규정',{'1','2'}),('blob','모의독립본문',{'0'})])
def test_normal_own_body_and_block_only_reads_keep_existing_behavior(grouped,document,question,expected):
    s,_=grouped;inv,_=setup(SimpleNamespace(sources=s),question)
    sid=next(sid for sid,src in s.tools.sources.items() if src['document_id']==document
             and (document=='blob' or str(src['unit_id'])=='1'))
    execute(inv,action(s,sid))
    assert acquired_blocks(inv)==expected
    assert all(e['document_id']==document for r in inv.p['selected'].values() for e in r['evidence'])
    inv.view()  # The next model menu must also support unstructured sources.

@pytest.mark.parametrize('version',[cc.V6,cc.V7,cc.V8])
def test_api_container_original_reaches_answer_and_duplicate_reuses_result(tmp_path,tree,version):
    gen,idx=tree;t=ScopeTransport('normal',version)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':version,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        runtime_root=tmp_path/'runtime',legal_agent_profile=profile,legal_agent_transport=t,
        memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
    app.state.pipeline.term_agent.unit_fulltext=idx
    body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'container-read','request_id':'r1'}
    with TestClient(app) as api:
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        result=response.json();assert '승인 후 보고한다.' in result['answer']['text']
        assert result['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
        calls=len(t.phases);assert api.post('/v1/rag/ask',json=body).json()['answer']==result['answer']
        assert len(t.phases)==calls
    assert any(v['sources'] for v in t.navigation)
    assert not any(p.endswith('-repair') for p in t.phases)
