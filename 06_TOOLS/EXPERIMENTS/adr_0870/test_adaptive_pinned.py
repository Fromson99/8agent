"""Opt-in candidate contracts; synthetic sources, no external model calls."""
import json
import sqlite3
from pathlib import Path
from contextlib import closing
import pytest

unit_fts = pytest.importorskip('semantic_runtime.unit_fulltext')
ur = pytest.importorskip('semantic_runtime.legal_agent.unit_reading')
us = pytest.importorskip('semantic_runtime.legal_agent.unit_selection')
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.source_selection import select_sources, originals
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.errors import ContractError
from lawrag.pipeline.term_generation import build_generation
from test_document_release import source
from test_bounded_source_main import settings
from test_legal_agent_v5 import app_for
from test_unified_legal_agent import ScriptedTransport, ok
from test_memory_runtime_v2 import command
from test_legal_agent_double_harness import ROOT, wire


@pytest.fixture
def tree(tmp_path, term_glossary):
    texts=['제1조 승인 규칙','① 다음 각 호의 승인 기준을 적용한다.',
        '1. 승인 원칙은 다음 목과 같다.','가. 긴급 승인 예외는 허용한다.',
        '2. 일반 승인 예외는 허용하지 않는다.','② 승인 후 보고한다.']
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',texts),('other','비공개모의',['별도 원문'])])
    nodes=[('0',None,'kr_article','제1조',0,6),('1','0','circled','①',1,5),
        ('2','1','dot_number:1','1.',2,4),('3','2','hangul_dot','가.',3,4),
        ('4','1','dot_number:1','2.',4,5),('5','0','circled','②',5,6)]
    with sqlite3.connect(raw) as db:
        db.execute("DELETE FROM source_unit WHERE document_id='d'")
        for uid,parent,family,surface,lo,hi in nodes:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,
                json.dumps({'family':family,'surface':surface,'title':'','span':[lo,hi]},ensure_ascii=False)))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';idx=tmp_path/'unit-index'
    unit_fts.build(gen,gen/'navigation',idx,workers=1)
    return gen,unit_fts.UnitFulltextIndex(idx,json.loads((gen/'navigation/manifest.json').read_text()))


@pytest.fixture
def session(tmp_path,tree):
    gen,idx=tree
    app=app_for(tmp_path,gen,ScriptedTransport(),{**settings(),'page_size':1,'max_read_chars':40})
    p=app.state.pipeline;p.term_agent.unit_fulltext=idx
    request={'question':'긴급 승인 예외','document_ids':['d'],'use_llm':False}
    try:
        with p.term_agent.open_session(request,query=p.plan(request['question'],['d']),runtime=tmp_path/'runtime') as s:
            yield s,idx
    finally:p.store.close()


def hit(s,uid='3'):
    src=next(v for v in s.sources.tools.sources.values() if v['document_id']=='d')
    return {'key':src['id']+'#unit:'+uid,'source_id':src['id'],'document_id':'d','unit_id':uid,
        'article_unit_id':'0','document_name':'모의승인규정','heading':src.get('heading',''),
        'match_paths':[{'terms':['긴급','승인'],'unit_rank':1}]}


def record(s):
    h=hit(s);r=SourceRecall(s.sources)
    r.discover=lambda:([h['source_id']],{'discovery_mode':'fulltext','routes':{},'unit_hits':[h]})
    rec=r.prepare();rec['evidence']=s.work.evidence()
    return rec


def test_fts_returns_real_leaf_and_does_not_absorb_sibling_body(tree):
    gen,idx=tree
    with closing(idx.connect()) as db:
        hits=idx.rank_units(db,['긴급'])
        assert len(hits)==1 and hits[0]['unit_id']=='3'
        assert hits[0]['block_ids']==['3'] and '일반' not in hits[0]['text']
        assert len(idx.rank_units(db,['승인']))>=5


def test_fts_scope_and_stale_file_fail_closed(tree):
    gen,idx=tree
    with closing(idx.connect()) as db:
        assert idx.rank_units(db,['긴급'],set())==[]
        with pytest.raises(ValueError,match='scope'):idx.rank_units(db,['긴급'],{'unknown'})
    with (idx.path/'units.sqlite').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='changed'):idx.connect()


@pytest.mark.parametrize('scope,expected',[
    ('exact:3',{'3'}),('subtree:3',{'3'}),('subtree:2',{'2','3'}),
    ('subtree:1',{'1','2','3','4'}),('subtree:0',{'0','1','2','3','4','5'})])
def test_leaf_and_all_ancestor_subtrees_paginate_without_escape(session,scope,expected):
    s,idx=session;h=hit(s);o=next(o for o in ur.offers(s.sources,h) if o['id']==scope)
    r=ur.read(s.sources,h,o,action_state={'count':0,'chars':0})
    assert r['complete'] and {p['block_id'] for e in r['evidence'] for p in e['spans']}==expected
    assert r['offer']['article_complete']==(scope=='subtree:0')
    if len(expected)>1:assert len(r['actions'])>1


def test_foreign_and_unoffered_read_are_denied(session):
    s,idx=session;h=hit(s);o=ur.offers(s.sources,h)[0]
    with pytest.raises(ContractError):ur.read(s.sources,h,{**o,'block_ids':['5']},action_state={'count':0,'chars':0})
    with pytest.raises(ContractError):ur.offers(s.sources,{**h,'document_id':'other'})


def test_leaf_complete_does_not_mean_article_complete(session):
    s,idx=session;rec=record(s)
    assert not rec['read_complete'] and rec['selection_complete']
    original=next(iter(originals(rec).values()))
    assert '긴급' in original['text'] and '일반' not in original['text'] and not original['article_complete']


def test_original_body_and_expansion_are_chosen_together(session):
    s,idx=session;rec=record(s);seen=[]
    def invoke(system,data,schema,phase,timeout):
        seen.append(data)
        if phase=='source-unit-triage':
            row=data['units'][0];assert '긴급' in row['original']['text']
            return {'issues':['예외 비교'],'choices':[{'id':row['id'],'scope':'subtree:1','status':'ADOPT','reason':'동일 항의 모든 호 비교'}],'needs_search':False}
        assert '일반 승인' in data['sources'][0]['text'] and '보고' not in data['sources'][0]['text']
        return {'issues':[],'choices':[],'needs_search':False}
    selected=select_sources('승인 예외 비교',rec,invoke,remaining_seconds=120,session=s.sources)
    assert selected['status']=='complete' and len(selected['final_ids'])==1
    assert selected['read_scopes'][0]['offer']['unit_id']=='1'
    assert {p['block_id'] for e in selected['selected_evidence'] for p in e['spans']}=={'0','1','2','3','4'}


def test_empty_initial_selection_stays_pending(session):
    s,idx=session;rec=record(s)
    def invoke(system,data,schema,phase,timeout):
        if phase=='source-unit-review':assert data['sources']==[] and data['units'][0]['original']['text']
        return {'issues':['미해결'],'choices':[],'needs_search':False}
    out=select_sources('승인',rec,invoke,remaining_seconds=120,session=s.sources)
    assert out['status']=='pending' and out['needs_fulltext'] and out['final_ids']==[]


def test_empty_schema_has_no_invalid_enum():
    assert 'enum' not in us.schema([],[],8)['properties']['choices']['items']['properties']['id']
    assert us.schema([],[],8)['properties']['choices']['maxItems']==0


def test_cross_unit_scope_is_rejected(session):
    s,idx=session;rec=record(s);r=rec['unit_reads'][0]
    with pytest.raises(ValueError,match='scope'):
        us.validate({'choices':[{'id':'U1','scope':'subtree:5','status':'ADOPT','reason':'형제 항으로 이동'}]},{'U1':r},16)


def test_read_budget_cannot_be_bypassed_by_expansion(session):
    from semantic_runtime.legal_agent.errors import BudgetExhausted
    s,idx=session;h=hit(s);o=ur.offers(s.sources,h)[0]
    with pytest.raises(BudgetExhausted):
        ur.read(s.sources,h,o,action_state={'count':ur.POLICY['read_actions'],'chars':0})


def test_conflicting_original_span_is_rejected():
    with pytest.raises(ContractError,match='overlap'):
        ur.reassemble([{'spans':[{'block_id':'1','start_cp':0,'end_cp':3,'text':'abc'},
            {'block_id':'1','start_cp':1,'end_cp':3,'text':'zz'}]}])


def test_partial_unit_is_not_selection_eligible(session,monkeypatch):
    s,idx=session;execute=s.sources.execute
    def partial(*args,**kw):
        r=execute(*args,**kw)
        return {**r,'coverage':{**r.get('coverage',{}),'complete':False}}
    monkeypatch.setattr(s.sources,'execute',partial)
    rec=record(s)
    assert rec['unit_reads'][0]['complete'] is False and rec['selection_complete']==[]


def test_multiple_matching_units_survive_article_projection(session):
    s,idx=session;h=hit(s);second=hit(s,'4');r=SourceRecall(s.sources)
    r.discover=lambda:([h['source_id']],{'discovery_mode':'fulltext','routes':{},'unit_hits':[h,second]})
    rec=r.prepare()
    assert len(rec['unit_reads'])==1
    assert [h['unit_id'] for h in rec['unit_reads'][0]['hit']['matched_hits']]==['3','4']
    assert rec['unit_reads'][0]['offer']['block_ids']==['0','1','2','3','4']
    assert not rec['read_complete']


@pytest.mark.parametrize('manifest_binding',[False,True,None])
def test_selected_scopes_drive_durable_assessment_after_confirmation(tmp_path,tree,manifest_binding):
    from fastapi.testclient import TestClient
    gen,idx=tree
    if manifest_binding:
        from lawrag.pipeline.fulltext_stage import derive
        derived=tmp_path/'unit-serving-generation'
        derive(gen,derived,workers=1)
        gen=derived
    class Transport(ScriptedTransport):
        def send_once(self,*,body,ticket):
            v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
            if phase in ('source-unit-triage','source-unit-review'):
                self.phases.append(phase)
                choices=[]
                if phase=='source-unit-triage':
                    row=next(r for r in v['units'] if any(o[0]=='subtree:1' for o in r['read_options']))
                    choices=[{'id':row['id'],'scope':'subtree:1','status':'ADOPT','reason':'승인 예외를 동일 항 전체와 비교'}]
                    rule=body['response_format']['json_schema']['schema']['properties']['choices']['items']
                    if 'status' not in rule['properties']:choices[0].pop('status')
                return wire({'issues':['승인'],'choices':choices,'needs_search':False})
            if phase in ('memory-assess','memory-compose'):
                assert '일반 승인' in v['sources'][0]['text'] and '보고' not in v['sources'][0]['text']
            return super().send_once(body=body,ticket=ticket)
    t=Transport();t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='긴급 승인 예외',queries=['긴급 승인'],facts=[])
    import importlib.util
    source_code=Path(unit_fts.__file__).resolve().parents[2]
    code=source_code  # Complete frozen code root; preserve workflow manifest pins.
    app=create_app(tmp_path,gen,contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,
        memory_identity=lambda r:{'user_id':'u','team_id':'risk_team','document_ids':['d']})
    if manifest_binding:
        assert app.state.pipeline.term_agent.unit_fulltext is app.state.pipeline.term_agent.get_fulltext()
    elif manifest_binding is False:
        app.state.pipeline.term_agent.unit_fulltext=idx
    try:
        with TestClient(app) as client:
            body={'question':'긴급 승인 예외','session_id':'s','request_id':'r1'}
            first=ok(client.post('/v1/rag/ask',json=body));gid=first['question_id']
            t.command=command('EXPERIENCE_CONFIRM',target=gid)
            stored=ok(client.post('/v1/rag/ask',json={**body,'request_id':'r2','question':'기억해줘'}));kid=stored['experience_id']
            # Current wiki management has separate AD contracts; this case
            # preserves original scope/evidence through confirmation and reuse.
            t.command=command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,task='긴급 승인 예외',queries=['긴급 승인'],facts=[])
            reused=ok(client.post('/v1/rag/ask',json={**body,'session_id':'new','request_id':'r3'}))
            assert reused['status'] in ('READY','REUSED') and 'COMPOSE' in reused['executed']
            if reused['status']=='READY':assert 'READ' in reused['executed'] and 'SELECT' in reused['executed']
            else:assert reused['executed']==['COMPOSE']
    finally:app.state.pipeline.store.close()
