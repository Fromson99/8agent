"""T01–T10 synthetic contract checks. No live model quality experiment."""
import importlib.util
import os
import shutil
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.tiers_policy import DEFAULT_PROFILE
from semantic_runtime.legal_agent.errors import ProposalError,ContractError
from semantic_runtime.legal_agent.publication import prepare,export,recover
from semantic_runtime.legal_agent.source_bundle import validate_current
from semantic_runtime.contracts import digest
from test_legal_agent_double_harness import generation,ROOT,BINDING,wire
from test_tool_exploration_v3 import tool,read,delivered,assessment

@pytest.fixture(autouse=True)
def preserve_contract_evidence(request,tmp_path):
    yield
    base=os.environ.get('SOURCE_TIERS_EVIDENCE_DIR')
    if not base:return
    destination=Path(base)/request.node.name
    destination.mkdir(parents=True,exist_ok=True)
    for file in tmp_path.rglob('journal.sqlite'):
        target=destination/file.relative_to(tmp_path);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    for file in tmp_path.rglob('manifest.json'):
        target=destination/file.relative_to(tmp_path);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    for file in tmp_path.glob('contract-*'):
        shutil.copy2(file,destination/file.name)

PROFILE={**DEFAULT_PROFILE,'model_binding':BINDING,'max_model_attempts':16}

def selection(v,items=None):
    picks=[]
    for e in (v['exact_evidence'] if items is None else items):
        picks.append({'evidence_id':e['evidence'],'tier':'CORE','basis_span_ids':[
            p['span_id'] for p in v['selectable_spans'] if p['evidence_id']==e['evidence']][:1],
            'relevance_reason':'모의 질문에서 승인 범위를 확인','relation_refs':[], 'interpretation_status':'UNCERTAIN'})
    return {'goal_id':v['goal_id'],'question_revision':v['question_revision'],'view_id':v['view_id'],
        'selections':picks,'pending':[],'rejected':[]}

def turn(selection=None,actions=(),intent='CONTINUE',assessments=()):
    return {'source_selection':selection,'actions':list(actions),'intent':intent,'reason':'모의 검증',
        'assessments':list(assessments),'relation_assessments':[]}

class Transport:
    binding=BINDING
    def __init__(self,mode='normal'):self.calls=[];self.mode=mode
    def validate_model(self):return {'verified':True,'synthetic':True}
    def send_once(self,*,body,ticket):
        self.calls.append(body);v=json.loads(body['messages'][1]['content'])['view']
        if v['phase']=='select_sources':
            d=selection(v)
            if self.mode=='empty':d['selections']=[]
            return wire(d)
        if v['phase']=='compose':return wire({'bad':'injected compose schema failure'})
        if not v['last_action_results']:
            return wire(turn(actions=[tool('locate',locator='모의승인규정 제1조',target=v['corpus_root'],branch='any',cursor=None)]))
        if not v['exact_evidence']:
            target=next(o['items'][0]['target'] for o in v['last_action_results'] if o['tool']=='locate')
            return wire(turn(actions=[tool('read',target=target,extent='subtree',cursor=None)]))
        if self.mode=='repeat':return wire(turn(actions=[tool('read',target=v['exact_evidence'][0]['evidence'],extent='self',cursor=None)]))
        return wire(turn(selection(v) if self.mode!='empty' else None,intent='DRAFT',
            assessments=[assessment(e) for e in v['exact_evidence']] if self.mode=='compose_failure' else []))

def app_for(tmp_path,generation,transport=None,profile=None):
    return create_app(tmp_path,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v4',
        legal_agent_profile=profile or PROFILE,legal_agent_transport=transport or Transport())

@contextmanager
def session(tmp_path,generation,profile=None):
    app=app_for(tmp_path,generation,profile=profile);p=app.state.pipeline
    try:
        with p.term_agent.open_session({'question':'승인?','document_ids':['d'],'use_llm':True},query=p.plan('승인?',['d']),runtime=tmp_path/'runtime') as s:yield s
    finally:p.store.close()

def renderer():
    spec=importlib.util.spec_from_file_location('tier_workflow',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.mark.parametrize('mode',['normal','compose_failure'])
def test_T01_T06_T10_http_bundle_outbox_renderer(tmp_path,generation,mode,monkeypatch):
    t=Transport(mode);app=app_for(tmp_path,generation,t)
    monkeypatch.setenv('GENOS_RAG_SOURCE_BASE_URL','https://synthetic.invalid')
    with TestClient(app) as client:
        r=client.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert r.status_code==200,r.text
        value=r.json();b=value['assembly']['term_agent']['source_bundle']
        assert b['sources'] and not value['answer']['claims'],value
        assert all(c['interpretation_status']=='UNCERTAIN' for c in b['sources'])
        rendered=renderer().render(value)
        assert rendered.endswith('**출처**\n- 핵심 · 모의승인규정 · 제1조 정의')
        assert '/v1/rag/source?' not in rendered
        assert '확인 한계:' not in rendered
        for card in b['sources']:
            assert '제1조' in card['coordinate_label']
            opened=client.get(card['open_url']);assert opened.status_code==200,opened.text
            assert card['spans'][0]['text'] in opened.text
        empty=deepcopy(value);empty['answer']['text']=''
        assert '모의승인규정 · 제1조 정의' in renderer().render(empty)
        assert b['sources'][0]['excerpt'] not in renderer().render(empty)
        assert 'source-tiers.js' in client.get('/rag/').text
        assert 'textContent' in client.get('/rag/source-tiers.js').text
        (tmp_path/'contract-result.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
        (tmp_path/'contract-wire.json').write_text(json.dumps(t.calls,ensure_ascii=False,indent=2))
        (tmp_path/'contract-genos.md').write_text(renderer().render(value))
        from semantic_runtime.legal_agent.source_tiers_ui import SCRIPT
        from html import escape
        doc='<!doctype html><meta charset="utf-8"><style>body{font-family:sans-serif;max-width:900px;margin:35px auto}article{border:1px solid #ccc;padding:12px;margin:12px 0}blockquote{white-space:pre-wrap}</style><h1>모의 계약 검증 · '+mode+'</h1><p>실제 Qwen 품질·GENOS 현장 화면은 미검증</p><pre>'+escape(value['answer']['text'])+'</pre><section id="sources"></section><script>'+SCRIPT+'\nrenderSourceTiers('+json.dumps(b,ensure_ascii=False).replace('<','\\u003c')+');</script>'
        (tmp_path/'contract-screen.html').write_text(doc)
        calls=len(t.calls)
        assert client.post('/v1/rag/ask',json={'question':'전체 문서 목록','use_llm':False}).status_code==200
        assert calls==len(t.calls)
    journal=next((tmp_path/'90_RUNTIME/semantic/legal-agent/runs').glob('*/'+value['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==4
        stored=json.loads(db.execute('SELECT result_json FROM publication').fetchone()[0])
        assert stored['assembly']['term_agent']['source_bundle']==b
        assert db.execute("SELECT count(*) FROM entity_version WHERE kind='source_selection'").fetchone()[0]


def test_T04_unpresented_span_and_reviewed_rejected(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate');delivered(s,v);d=selection(v)
        bad=deepcopy(d);bad['selections'][0]['basis_span_ids']=['unseen']
        with pytest.raises(ProposalError,match='not presented'):s.commit_selection(v,bad)
        bad=deepcopy(d);bad['selections'][0]['interpretation_status']='REVIEWED'
        with pytest.raises(ProposalError,match='independent'):s.commit_selection(v,bad)
        assert not s.work.heads('source_selection')
        s.commit_selection(v,d)
        assert s.build_bundle()['sources']


def test_T03_limits_no_automatic_sources(tmp_path,generation):
    with session(tmp_path,generation,{**PROFILE,'max_core_sources':1}) as s:
        read(s);read(s,'모의승인규정 제2조','r2');v=s.view('investigate');delivered(s,v)
        d=selection(v)
        assert len(d['selections'])>=2
        with pytest.raises(ProposalError,match='tier limit'):s.commit_selection(v,d)
        d['selections']=d['selections'][:1];s.commit_selection(v,d);b=s.build_bundle()
        assert len(b['sources'])==1 and b['candidate_counts']['unselected']>=1
        assert b['sources'][0]['evidence_id']==d['selections'][0]['evidence_id']

@pytest.mark.parametrize('mode',['repeat','empty'])
def test_T05_T09_bounded_recovery_and_no_selection(tmp_path,generation,mode):
    t=Transport(mode);app=app_for(tmp_path,generation,t)
    with TestClient(app) as client:
        r=client.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert r.status_code==200,r.text
        b=r.json()['assembly']['term_agent']['source_bundle']
        assert len(t.calls)<=PROFILE['max_model_attempts']
        assert any(json.loads(c['messages'][1]['content'])['view']['phase']=='select_sources' for c in t.calls)
        if mode=='empty':assert b['status']=='NO_SELECTION' and b['sources']==[]
        else:assert b['sources']


def test_T08_selection_change_blocks_old_bundle(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,selection(v));old=s.build_bundle()
        v=s.view('select_sources');delivered(s,v);d=selection(v);d['selections'][0]['tier']='SUPPLEMENTAL';s.commit_selection(v,d)
        from semantic_runtime.legal_agent.source_bundle import validate_saved
        with pytest.raises(ContractError,match='changed'):validate_saved(s.work,{'assembly':{'term_agent':{'source_bundle':old}}})
        b=s.build_bundle();assert b['sources'][0]['tier']=='SUPPLEMENTAL'
        result={'assembly':{'term_agent':{'source_bundle':b}}}
        with pytest.raises(ContractError,match='authorized'):validate_current(s.work,result,s.sources.store,allowed_documents=[])


def test_T02_principle_exception_both_core(tmp_path,term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',['원칙은 승인이 필요하다. 제2조를 준용한다.','예외는 승인을 받지 않을 수 있다.'])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation') as s:
        read(s,'모의규정 제1조');read(s,'모의규정 제2조','r2')
        v=s.view('investigate');delivered(s,v)
        assert v['relation_menu']
        d=selection(v)
        assert len(d['selections'])==2
        s.commit_selection(v,d);b=s.build_bundle()
        assert len(b['sources'])==2 and {c['tier'] for c in b['sources']}=={'CORE'}
        assert all(c['interpretation_status']=='UNCERTAIN' for c in b['sources'])
        # Both selections are explicit; no server-added linked evidence.
        assert {c['evidence_id'] for c in b['sources']}=={p['evidence_id'] for p in d['selections']}


def test_T07_exact_read_pages_and_unseen_selection(tmp_path,term_glossary):
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    original='긴 원문의 정확한 범위를 확인한다. '*200
    raw=source(tmp_path/'source.sqlite',[('d','모의규정',[original])])
    build_generation(raw,term_glossary,tmp_path/'g',serving=True)
    with session(tmp_path,tmp_path/'g/generation',{**PROFILE,'max_read_chars':600,'source_page_size':1}) as s:
        result=read(s,'모의규정 제1조');pieces=[]
        target=next(o['action']['args']['target'] for o in s.work.observations(100) if o['tool']=='read' and o.get('actor')=='MODEL')
        while True:
            pieces.extend(p for ident in result['evidence_ids'] for p in s.work.evidence(ident)['spans'])
            v=s.view('investigate');delivered(s,v)
            assert len(v['exact_evidence'])==1
            assert len(json.dumps(s.gateway.request('investigate',v,'TurnDecision'),ensure_ascii=False).encode())<BINDING['max_input_bytes']
            if not result['next_cursor']:break
            result=s.sources.execute(tool('read',target=target,extent='subtree',cursor=result['next_cursor']),'page'+str(len(pieces)))
        assert ''.join(p['text'] for p in pieces)==original
        d=selection(v);s.commit_selection(v,d);b=s.build_bundle()
        assert b['sources'][0]['excerpt']==v['exact_evidence'][0]['text']
        assert b['sources'][0]['coverage']=='PARTIAL'
        assert len(s.work.evidence())>1


def test_T08_commit_ready_recovery_is_guarded_idempotent(tmp_path,generation):
    from semantic_runtime.legal_agent.coordinator import run
    from semantic_runtime.stage_runner import StageRunner
    from semantic_runtime.storage import Store
    with session(tmp_path,generation) as s:
        # Exercise the real stages, then simulate interruption after atomic prepare.
        app=app_for(tmp_path/'other',generation);pipeline=app.state.pipeline
        try:result=run(pipeline,s,StageRunner(pipeline))
        finally:pipeline.store.close()
        prepared=prepare(s.work,result,None,__import__('semantic_runtime.contracts',fromlist=['Contracts']).Contracts(ROOT))
        journal=s.work.path
    journals=tmp_path/'runtime/legal-agent/runs';runs=tmp_path/'runs'
    assert recover(journals,runs)[0]['status']=='BLOCKED'
    assert not list(runs.glob('*.json'))
    store=Store(generation)
    try:
        guard=lambda repo,value:validate_current(repo,value,store)
        assert recover(journals,runs,publication_guard=guard)[0]['status']=='COMPLETED'
        assert recover(journals,runs,publication_guard=guard)==[]
        from semantic_runtime.legal_agent.tiers_repository import TiersRepository
        repo=TiersRepository(journal);repo.publication_guard=lambda value:guard(repo,value)
        assert export(repo,runs)==prepared
        assert len(list(runs.glob('*.json')))==1
        repo.close()
    finally:store.close()


def test_T08_interrupted_preserves_model_selection(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate');delivered(s,v);s.commit_selection(v,selection(v));path=s.work.path
    assert recover(tmp_path/'runtime/legal-agent/runs',tmp_path/'runs')[0]['status']=='INTERRUPTED'
    from semantic_runtime.legal_agent.tiers_repository import TiersRepository
    repo=TiersRepository(path)
    assert repo.heads('source_selection',current=True)
    assert not repo.db.execute('SELECT 1 FROM publication').fetchone()
    repo.close()


@pytest.mark.parametrize('finish',['worker','recovery'])
def test_genos_final_answer_returns_before_publication_and_recovers(tmp_path,generation,monkeypatch,finish):
    from semantic_runtime.legal_agent import deferred_publication
    from semantic_runtime.contracts import Contracts
    from semantic_runtime.storage import Store
    from test_legal_agent_v5 import app_for as v5_app_for

    jobs=[]
    monkeypatch.setenv('GENOS_GENERATION',str(generation))
    monkeypatch.setattr(deferred_publication,'schedule',lambda *args:jobs.append(args))
    app=v5_app_for(tmp_path,generation)
    with TestClient(app) as client:
        response=client.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']})
        assert response.status_code==200,response.text
        value=response.json()
        assert value['answer']['text']
        assert value['publication_status']=='PENDING'
        assert len(jobs)==1
        runs=jobs[0][3]
        assert not list(runs.glob('*.json'))
        journal=jobs[0][0]
        with sqlite3.connect(journal) as db:
            assert db.execute('SELECT status FROM run').fetchone()[0]=='RUNNING'
    if finish=='worker':
        deferred_publication._publish(jobs[0])
    else:
        # Simulate a worker dying after sending the answer but before publishing.
        store=Store(generation)
        try:
            recovered=recover(journal.parents[2],runs,
                              publication_guard=lambda repo,result:validate_current(repo,result,store),
                              contracts=Contracts(ROOT))
            assert recovered==[{'run_id':value['run_id'],'status':'COMPLETED'}]
        finally:store.close()
    assert json.loads((runs/(value['run_id']+'.json')).read_text())['answer']==value['answer']
def test_T08_current_manifest_change_blocks_open(tmp_path,generation):
    app=app_for(tmp_path,generation)
    with TestClient(app) as c:
        result=c.post('/v1/rag/ask',json={'question':'승인?','document_ids':['d']}).json()
        url=result['assembly']['term_agent']['source_bundle']['sources'][0]['open_url']
        path=generation/'manifest.json';manifest=json.loads(path.read_text());manifest['scope']['document_version_ids']=[]
        path.write_text(json.dumps(manifest))
        r=c.get(url)
        assert r.status_code>=400 and '모의승인규정' not in r.text


def test_T07_oversized_relation_lossless_detail_pages(tmp_path,generation):
    from semantic_runtime.legal_agent.relation_cards import notice
    from semantic_runtime.legal_agent.repository import encoded
    with session(tmp_path,generation,{**PROFILE,'max_context_chars':16000,'max_read_chars':2000,'relation_page_size':2}) as s:
        read(s);e=s.work.evidence()[0]
        n=s.sources.materialize(notice(e['evidence_id'],'knowledge','synthetic-large',
            neighbour_concept={'id':'c','labels':[{'text':'정확한 개념명'}],'detail':'관계 설명 '*5000}))
        with s.work.transaction():s.work.record_notice(n)
        s.sources.execute(tool('inspect_relation',relation_id=n['relation_id']),'inspect-large')
        chunks=[]
        for i in range(50):
            v=s.view('investigate');delivered(s,v)
            chunks.extend(v['relation_details'])
            more=next((c for c in v['continuations'] if c['section']=='relation_notices'),None)
            if not more:break
            s.sources.execute(tool('view_page',**more['action']['args']),'detail-page'+str(i))
        assert chunks and ''.join(c['fragment'] for c in chunks)==encoded(n)
        assert s.work.notice(n['relation_id'])==n
        assert not s.work.db.execute("SELECT 1 FROM item_presentation WHERE kind='relation' AND item_id=?",(n['relation_id'],)).fetchone()


def test_T03_duplicate_tier_rejected_and_existing_survives_empty(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate');delivered(s,v);d=selection(v)
        duplicate=deepcopy(d);duplicate['selections'].append({**duplicate['selections'][0],'tier':'SUPPLEMENTAL'})
        with pytest.raises(ProposalError,match='duplicate'):s.commit_selection(v,duplicate)
        s.commit_selection(v,d);before=s.build_bundle()['sources']
        v=s.view('select_sources');delivered(s,v);s.commit_selection(v,selection(v,[]))
        assert s.build_bundle()['sources']==before

@pytest.mark.parametrize('family',['reference','definition','term','occurrence','structure','knowledge'])
def test_T02_T07_family_menu_labels_and_non_evidence(tmp_path,generation,family):
    from semantic_runtime.legal_agent.relation_cards import notice
    from semantic_runtime.legal_agent.tiers_views import menu
    with session(tmp_path,generation) as s:
        read(s);e=s.work.evidence()[0]
        n=s.sources.materialize(notice(e['evidence_id'],family,'synthetic-'+family,
            label='영업일',term_label='영업일',neighbour_concept={'id':'synthetic-concept','labels':[{'text':'은행 영업일'}]}))
        with s.work.transaction():s.work.record_notice(n)
        card=menu(s,n)
        assert card['family']==family and card['source_label']
        assert card['concept_labels']['neighbour_concept']['labels'][0]['text']=='은행 영업일'
        assert card['presentation_status']=='MENU_ONLY' and 'guidance' in card
        v=s.view('investigate');delivered(s,v);d=selection(v)
        d['selections'][0]['evidence_id']=n['relation_id']
        with pytest.raises(ProposalError):s.commit_selection(v,d)
        assert not s.work.heads('source_selection')


def test_T09_rejected_sources_not_filled_automatically(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate');delivered(s,v)
        d=selection(v,[]);d['rejected']=[{'evidence_id':e['evidence'],'reason':'질문과 무관한 모의 자료'} for e in v['exact_evidence']]
        s.commit_selection(v,d);b=s.build_bundle()
        assert b['sources']==[] and b['status']=='NO_SELECTION' and b['candidate_counts']['rejected']>0


def test_T04_read_without_successful_presentation_cannot_select(tmp_path,generation):
    with session(tmp_path,generation) as s:
        read(s);v=s.view('investigate')
        with pytest.raises(ProposalError,match='successful'):s.commit_selection(v,selection(v))
        assert s.build_bundle()['sources']==[]


def test_T03_unread_discoveries_in_tier3_not_sources(tmp_path,generation):
    from semantic_runtime.legal_agent.source_candidates import inventory
    with session(tmp_path,generation) as s:
        s.sources.execute(tool('locate',locator='모의승인규정 제2조',target=s.sources.root,branch='any',cursor=None),'unread-candidate')
        rows=inventory(s.work)
        assert rows and all(r['status']=='DISCOVERED_NOT_READ' for r in rows)
        assert not s.work.evidence()
        b=s.build_bundle()
        assert b['sources']==[] and b['candidate_counts']['unselected']==len(rows)


def test_T08_renderer_keeps_untrusted_markdown_literal():
    malicious='![image](https://untrusted.invalid/pixel) <script>x</script>'
    text=renderer()._tier_sources({'sources':[{'tier':'CORE','document_name':malicious,'coordinate_label':'제1조',
        'generation_id':'synthetic','source_artifact_hash':'a'*64,'excerpt':malicious,'relevance_reason':malicious,
        'interpretation_status':'UNCERTAIN','open_url':'javascript:bad'}], 'candidate_counts':{'unselected':0}})
    assert '![image]' not in text and '<script>' not in text and 'javascript:bad' not in text
