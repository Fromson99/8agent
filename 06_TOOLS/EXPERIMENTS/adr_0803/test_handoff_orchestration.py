"""Full native RAG through workflow API, plus parent/child failure boundaries."""
from copy import deepcopy
from pathlib import Path
import json,os,sqlite3
import pytest
from fastapi.testclient import TestClient
from test_document_release import source
from test_source_span_norm import SpanTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import wire
from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.unit_fulltext import build,UnitFulltextIndex
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import TransportError,ContractError,BudgetExhausted

ROOT=Path(os.environ['WORKFLOW_TEST_CODE_ROOT'])
BODY={'question':'대사: 승인 기준은?','session_id':'s','request_id':'r','as_of':'2026-10-15'}
PRINCIPAL={'user_id':'u','team_id':'risk_team','document_ids':['inside','outside']}

@pytest.fixture
def tree(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[
        ('inside','모의내규',['제1조(승인) 모의승인규정에 따라 승인 후 보고한다.']),
        ('outside','모의승인규정',['제1조(승인) 승인 후 보고한다.'])])
    with sqlite3.connect(raw) as db:
        for did,category in [('inside','internal'),('outside','external')]:
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({
                'document_category':category,'document_metadata':{'team':'risk_team'},
                'workflow_version':{'verified':True,'valid_from':'2020-01-01','valid_to':None}}),did))
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    gen=tmp_path/'built/generation';index=tmp_path/'index'
    build(gen,gen/'navigation',index,workers=1)
    return gen,UnitFulltextIndex(index,json.loads((gen/'navigation/manifest.json').read_text()))

class Transport(SpanTransport):
    def __init__(self,mode='normal'):
        super().__init__(False,False);self.mode=mode;self.views=[];self.basis_count=0
    def send_once(self,*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view'];stage=view.get('source_stage',view['phase'])
        self.views.append((stage,deepcopy(view)))
        if stage=='workflow-intake':
            return wire({'issues':[{'id':'i1','label':'승인 기준','numeric':False}],
                'internal_queries':['승인'],'external_queries':['승인'],'scope_note':'모의 기준','missing_user_facts':[]})
        if stage=='workflow-basis':
            self.basis_count+=1
            if self.mode=='followup' and self.basis_count==1:
                return wire({'pairs':[],'gaps':[{'issue_id':'i1','kind':'MISSING_REFERENCE','reason':'내규 원문 추가 확인',
                    'action':{'side':'internal','question':'기존 승인 기준에서 보고 책임을 추가 조사해 주세요.','reason':'미확인 범위'}}],
                    'summary':'추가 조사 필요'})
            a=next((e for e in view['sources'] if e['side']=='internal'),None)
            b=next((e for e in view['sources'] if e['side']=='external'),None)
            pairs=[]
            if a and b:
                quotes=[{'citation_id':e['citation_options'][0]['citation_id']} for e in (a,b)]
                pairs=[{'issue_id':'i1','internal':[a['evidence_id']],'external':[b['evidence_id']],
                    'applicability':{'status':'MATCH','reason':'모의 적용','citations':quotes},
                    'basis_relation':'DIRECT','basis_path':[{'from_evidence':a['evidence_id'],'to_evidence':b['evidence_id'],'citation':quotes[0]}],
                    'comparison_eligibility':True,'reason':'모의 명시 참조','content_difference':'승인 후 보고는 동일','content_citations':quotes}]
            return wire({'pairs':pairs,'gaps':[],'summary':'확보 근거 확인'})
        if stage=='workflow-compare':
            pair=view['basis']['pairs'][0];ids=pair['internal']+pair['external']
            return wire({'rows':[{'item':'승인 기준','verdict':'CONFORMS','difference':'같음','reason':'원문 대조',
                'citations':[{'citation_id':e['citation_options'][0]['citation_id']} for e in view['sources'] if e['evidence_id'] in ids],
                'dimensions':[],'unresolved':[]}],'answer':'양쪽 승인 기준 확인','unresolved':[]})
        if self.mode=='transport_failure' and stage=='source-request-route':
            raise TransportError('synthetic unknown outcome',unknown=True)
        return super().send_once(body=body,ticket=ticket)

def application(tmp_path,tree,mode='normal',limit=80,principal=None):
    gen,index=tree;t=Transport(mode)
    profile={**settings(),'max_model_attempts':limit,'max_read_chars':10000,
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':cc.V8,'compact_input':True}}
    app=create_app(tmp_path,gen,contracts_root=ROOT,workspace_root=Path(__file__).resolve().parents[3],
        provider=object(),implementation='legal-agent-unified-v6',runtime_root=tmp_path/'runtime',
        legal_agent_profile=profile,legal_agent_transport=t,memory_identity=lambda _:principal or PRINCIPAL)
    app.state.pipeline.term_agent.unit_fulltext=index
    return app,t

@pytest.mark.parametrize('path',['/v1/rag/ask','/v1/workflows/run'])
def test_native_answers_evidence_records_budget_and_duplicate(tmp_path,tree,path):
    app,t=application(tmp_path,tree)
    with TestClient(app) as client:
        response=client.post(path,json=BODY);assert response.status_code==200,response.text
        out=response.json();assert set(out['rag_results'])=={'internal','external'},out
        for side in ('internal','external'):
            result=out['rag_results'][side]
            assert result['status']=='completed',result
            assert '승인 후 보고한다.' in result['answer']['text']
            assert result['records'] and result['evidence_ids'] and result['continuation']['goal_id']
            assert result['question'].startswith('내규:' if side=='internal' else '외규:')
        assert out['status']=='completed',out
        calls=len(t.views);again=client.post(path,json=BODY)
        assert again.status_code==200 and again.json()['answer']==out['answer'] and len(t.views)==calls
        assert not any(stage=='workflow-investigate' for stage,_ in t.views)
        assert sum(stage=='memory-assess' for stage,_ in t.views)==2
        basis=next(v for stage,v in t.views if stage=='workflow-basis')
        assert all(basis['rag_results'][s]['answer'] for s in ('internal','external'))
    journal=tmp_path/'runtime/workflows'/out['run_id']/'journal.sqlite'
    with sqlite3.connect(journal) as db:
        child=db.execute("SELECT count(*) FROM event WHERE kind='WORKFLOW_CHILD_RESERVED' AND json_extract(payload_json,'$.kind')='model'").fetchone()[0]
        parent=db.execute('SELECT count(*) FROM model_attempt').fetchone()[0]
        assert out['usage']['model_reserved']==child+parent

def test_followup_preserves_child_case_and_unaffected_side(tmp_path,tree):
    app,t=application(tmp_path,tree,'followup')
    with TestClient(app) as client:
        out=client.post('/v1/rag/ask',json=BODY);assert out.status_code==200,out.text
        out=out.json();views=[v for stage,v in t.views if stage=='workflow-basis'];assert len(views)==2,out
        first,last=[v['rag_results'] for v in views]
        assert first['external']==last['external']
        assert first['internal']['continuation']['goal_id']==last['internal']['continuation']['goal_id']
        assert last['internal']['continuation']['revision']>first['internal']['continuation']['revision']
        assert last['internal']['audit_ref'] and 'records' not in last['internal'] and out['status']=='completed'
        assert out['rag_results']['internal']['records']

@pytest.mark.parametrize('mode,limit',[('transport_failure',80),('normal',6)])
def test_failed_child_and_parent_exhaustion_do_not_claim_absence(tmp_path,tree,mode,limit):
    app,t=application(tmp_path,tree,mode,limit)
    with TestClient(app) as client:
        out=client.post('/v1/rag/ask',json=BODY);assert out.status_code==200,out.text
        value=out.json();assert value['status'] in ('partial','failed')
        assert value['usage']['model_reserved']<=limit
        count=len(t.views);client.post('/v1/rag/ask',json=BODY);assert len(t.views)==count
        assert not any(stage=='workflow-compare' for stage,_ in t.views)

@pytest.mark.parametrize('side,doc',[('internal','inside'),('external','outside')])
def test_empty_other_side_does_not_broaden_scope(tmp_path,tree,side,doc):
    app,t=application(tmp_path,tree,principal={**PRINCIPAL,'document_ids':[doc]})
    with TestClient(app) as client:
        out=client.post('/v1/rag/ask',json=BODY);assert out.status_code==200,out.text
        value=out.json();other='external' if side=='internal' else 'internal'
        assert value['rag_results'][other]['status']=='not_registered'
        assert all(e['document_id']==doc for e in value['assembly']['term_agent']['source_bundle']['sources'])

def test_interrupted_return_recovers_same_rag_request_without_resending_model(tmp_path,tree,monkeypatch):
    from semantic_runtime import workflow_rag
    app,t=application(tmp_path,tree);original=workflow_rag.execute;calls=[]
    def interrupt(port,action,call_id):
        result=original(port,action,call_id);calls.append((action['side'],len(t.views)))
        if len(calls)==1:raise KeyboardInterrupt('after completed RAG, before parent receipt')
        return result
    monkeypatch.setattr(workflow_rag,'execute',interrupt)
    with pytest.raises(KeyboardInterrupt):
        app.state.workflow_runtime.execute({**BODY,'workflow_id':'risk_team_compare_workflow'},PRINCIPAL)
    with TestClient(app) as client:
        before=len(t.views)
        path=next((tmp_path/'runtime/workflows').glob('*/journal.sqlite'))
        with sqlite3.connect(path) as db:revision=db.execute('SELECT revision FROM workflow_state').fetchone()[0]
        out=client.post('/v1/workflows/resume',json={'run_id':path.parent.name,'session_id':'s','expected_revision':revision})
        assert out.status_code==200,out.text
        assert calls[1]==('internal',before),calls
        assert out.json()['status']=='completed'

@pytest.mark.parametrize('mutation',['request','principal','acl','revision','result','child_record'])
def test_saved_response_rejects_conflict_and_tamper(tmp_path,tree,mutation):
    principal=deepcopy(PRINCIPAL);app,t=application(tmp_path,tree,principal=principal)
    with TestClient(app,raise_server_exceptions=False) as client:
        first=client.post('/v1/rag/ask',json=BODY);assert first.status_code==200,first.text
        out=first.json();count=len(t.views);body=deepcopy(BODY)
        if mutation=='request':body['question']='대사: 다른 질문'
        elif mutation=='principal':principal['user_id']='other'
        elif mutation=='acl':principal['document_ids']=['outside']
        elif mutation=='result':
            with sqlite3.connect(tmp_path/'runtime/workflows'/out['run_id']/'journal.sqlite') as db:
                db.execute("UPDATE workflow_state SET result_json='{}'")
        elif mutation=='child_record':
            path=next((tmp_path/'runtime/workflows'/out['run_id']/'children/internal/legal-agent/runs').glob('*/*/journal.sqlite'))
            with sqlite3.connect(path) as db:
                for name, in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='observation'").fetchall():
                    db.execute('DROP TRIGGER "'+name+'"')
                db.execute("UPDATE observation SET result_json='{}'")
        if mutation in ('principal','acl','revision'):
            value=client.post('/v1/workflows/resume',json={'run_id':out['run_id'],'session_id':'s',
                'expected_revision':out['revision']-(1 if mutation=='revision' else 0)})
        else:value=client.post('/v1/rag/ask',json=body)
        assert value.status_code in (403,404,409,500),value.text
        assert len(t.views)==count

@pytest.mark.parametrize('kind',['model','tool','deadline'])
def test_parent_budget_is_durable_and_context_does_not_leak(tmp_path,tree,kind):
    from semantic_runtime.legal_agent.workflow_execution import child_execution,reserve,_parent
    from types import SimpleNamespace
    app,t=application(tmp_path,tree)
    with TestClient(app) as client:
        out=client.post('/v1/rag/ask',json=BODY).json()
    path=tmp_path/'runtime/workflows'/out['run_id']/'journal.sqlite'
    from semantic_runtime.legal_agent.repository import WorkRepository
    work=WorkRepository(path)
    def remaining():
        if kind=='deadline':raise BudgetExhausted('original deadline expired')
        return 100
    try:
        column='model_reserved=model_limit' if kind=='model' else 'tool_used=tool_limit'
        work.db.execute('UPDATE budget SET '+column)
        before=work.budget()
        with child_execution(work,SimpleNamespace(remaining=remaining),'same',['inside']):
            child=SimpleNamespace(workflow_parent=_parent.get(),context=SimpleNamespace(run_id='child'))
            with pytest.raises(BudgetExhausted):reserve(child,'model' if kind=='deadline' else kind)
        assert work.budget()==before and _parent.get() is None
    finally:work.close()

@pytest.mark.parametrize('mutation',['none','scope','team','generation','manifest','policy'])
def test_external_authorization_keeps_internal_data_private_and_exact(tmp_path,mutation):
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.legal_agent.workflow_execution import child_execution
    from semantic_runtime.contracts import sha
    from types import SimpleNamespace
    grant={'workflow_authorization':{'authorized_by':'user','authorization_text':'explicit fixture permission',
        'teams':['risk_team'],'document_ids':['inside','outside'],'generation_id':'g',
        'store_sha256':'source','generation_manifest_sha256':'manifest'}}
    t=LocalGemmaTransport.__new__(LocalGemmaTransport)
    t.grant_path=tmp_path/'grant.json';t.grant_path.write_text(json.dumps(grant));t.grant=grant;t.grant_hash=sha(t.grant_path)
    t.policy_path=tmp_path/'policy.json';t.policy_path.write_text('{}');t.policy_hash=sha(t.policy_path)
    request={'workflow_id':'risk_team_compare_workflow','principal':{'user_id':'u','team_id':'risk_team'},'document_ids':['inside','outside']}
    binding={'generation_id':'g','store_sha256':'source','generation_manifest_sha256':'manifest'}
    if mutation=='scope':request['document_ids'].append('forbidden')
    if mutation=='team':request['principal']['team_id']='other'
    if mutation=='generation':binding['generation_id']='other'
    if mutation=='manifest':binding['generation_manifest_sha256']='other'
    if mutation=='policy':t.policy_path.write_text('{"changed":true}')
    if mutation!='none':
        with pytest.raises(ContractError):t.authorize_workflow(request,binding)
        return
    receipt=t.authorize_workflow(request,binding)
    assert receipt['public_question_asserted'] is False
    context=SimpleNamespace(binding={'external_authorization':receipt})
    with child_execution(None,context,'call',['inside']):
        child=t.authorize({'scope':{'document_version_ids':['inside']}},{'use_llm':True},binding,public_question=False)
        assert child['public_question_asserted'] is False and child['scope_document_ids']==['inside']
