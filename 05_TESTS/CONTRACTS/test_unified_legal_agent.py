"""Synthetic integration contracts, not legal quality or model performance experiments."""
import copy
import json
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import corrected_memory as m
from test_memory_runtime_v2 import fit, command,memory
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,wire
from test_structure_first_search import structured_generation
from test_source_prefix_routing import mixed_generation


class ScriptedTransport:
    binding=settings()['model_binding']
    def __init__(self):
        self.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[])
        self.phases=[];self.fail=None;self.before_return=None
    def validate_model(self):return {'verified':True,'synthetic':True}
    def send_once(self,*,body,ticket):
        v=json.loads(body['messages'][1]['content'])['view']
        phase=v.get('source_stage',v['phase']);self.phases.append(phase)
        if phase==self.fail:raise RuntimeError('injected failure')
        if phase=='source-request-route':out={'mode':'CASE','answer':'','reason':'모의 법률 질문 또는 현재 사건 후속 요청'}
        elif phase.startswith('memory-resolve'):out=fit(copy.deepcopy(self.command),body['response_format']['json_schema']['schema'])
        elif phase.endswith('check'):out={'valid':True,'reason':'synthetic structure check'}
        elif phase.startswith('domain-choice-'):
            offer=v['offer'];out={'method_id':offer['method_id'],'path':'DISCOVERY',
                'concept_ids':[c['id'] for c in offer['concepts']],
                'relation_ids':[r['id'] for r in offer['relations']],'reason':'모의 원문과 조건 확인'}
        elif phase=='memory-intent':out={'purpose':'승인 대상 확인','concepts':['승인']}
        elif phase=='source-query-plan':
            out={'mode':'DIRECT','answer':'법률 질문을 입력해 주세요.','reason':'사용 안내','law_names':[],
                 'queries':[],'browse_view':'documents','document_category':'all','title_query':'','inspect_documents':False}
        elif phase.startswith('source-unit-'):
            row=v['units'][0] if v['units'] else None
            out={'issues':['승인'],'choices':[{'id':row['id'],'scope':row['read_options'][-1][0],
                'reason':'모의 원문 선별'}] if row and phase.startswith('source-unit-triage') else [],
                'needs_search':False,'evidence_sufficient':phase.startswith('source-unit-review'),
                'sufficiency_reason':'모의 원문과 조건 확인'}
            if phase.startswith('source-unit-review') and getattr(self,'fulltext_once',False):
                out.update(needs_search=True,evidence_sufficient=False,search_queries=['승인 대상 추가 원문']);self.fulltext_once=False
        elif phase.startswith('source-reference-'):
            out={'decisions':[{'id':g['id'],'action':'SKIP','scopes':[],
                'reason':'모의 질문의 쟁점과 무관함','applicability':'DOES_NOT_APPLY',
                'applicability_reason':'모의 질문 범위에서 제외됨'} for g in v['groups']], 'needs_more':False}
        elif phase.startswith('source-'):
            schema=body['response_format']['json_schema']['schema']
            labels=schema['properties']['choices']['items']['properties']['id']['enum']
            out={'issues':['승인'],'choices':[{'id':labels[0],'reason':'모의 원문 선별'}] if labels else []}
            if 'needs_fulltext' in schema['properties']:out['needs_fulltext']=False
            if phase=='source-triage' and getattr(self,'fulltext_once',False) and 'needs_fulltext' in schema['properties']:
                out['needs_fulltext']=True;self.fulltext_once=False
        elif phase.startswith('memory-assess'):
            source=v['sources'][0]
            out={'claims':[{'text':'현재 사실 '+json.dumps(v['current_facts'],ensure_ascii=False)+'에 제공 규정을 적용한다.',
                'source_id':source['source_id'],'quote':source['text'][:15]}],'limitations':[]}
        elif phase.startswith('memory-compose'):
            out={'text':('| 현재 판단 |\n|---|\n' if v['format']=='table' else '')+v['assessment']['claims'][0]['text'],**v['assessment']}
        else:raise AssertionError(phase)
        if self.before_return:self.before_return(phase,v)
        if phase.startswith('domain-choice-') and getattr(self,'bad_domain',False):out['concept_ids']=['invented:concept']
        return wire(out)


@pytest.fixture
def unified(tmp_path,structured_generation):
    transport=ScriptedTransport()
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    app=create_app(tmp_path,structured_generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile={**settings(),'max_model_attempts':40},
        legal_agent_transport=transport,memory_identity=lambda req:principal,runtime_root=tmp_path/'90_RUNTIME'/'semantic')
    app.state.pipeline.contracts.pipeline['shortcut_v4']['features']['capture']=False
    with TestClient(app) as client:
        original_post=client.post
        admin_calls=0
        def with_ad_query(url,*args,**kwargs):
            nonlocal admin_calls
            if url!='/v1/rag/memory/query':return original_post(url,*args,**kwargs)
            admin_calls+=1
            session_id=kwargs['json'].get('session_id') or 'fixture-read'
            kwargs['json']={**kwargs['json'],'session_id':session_id}
            identity={'session_id':session_id,'request_id':'fixture-ad-'+str(admin_calls)}
            original_post('/v1/rag/ask',json={**identity,'question':'[AD모드 시작]'})
            try:return original_post(url,*args,**kwargs)
            finally:original_post('/v1/rag/ask',json={**identity,'request_id':identity['request_id']+'-end','question':'[AD모드 종료]'})
        client.post=with_ad_query
        n=0
        def send(c=None,**overrides):
            nonlocal n
            n+=1
            if c is not None:transport.command=c
            body={'question':'모의승인규정 제1조의 승인 대상은?','session_id':'s','request_id':'r'+str(n),**overrides}
            return client.post('/v1/rag/ask',json=body)
        yield client,send,transport,principal,tmp_path/'90_RUNTIME'/'semantic'


def ok(response):
    assert response.status_code==200,response.text
    return response.json()


def test_v6_returns_answer_without_assessment_or_composition_judge(unified):
    _,send,t,p,runtime=unified
    def forbid(phase,data):
        if phase in ('memory-assess-check','memory-compose-check'):
            raise AssertionError('disabled semantic review was called')
    t.before_return=forbid
    result=ok(send())
    assert result['answer']['text'] and result['answer']['claims']
    receipt=result['answer']['provider_receipt']
    assert receipt['assessment_review_status']==receipt['final_review_status']=='SKIPPED'
    assert receipt['claim_review_status']=='UNREVIEWED' and receipt['quality_certified'] is False
    assert not {'memory-assess-check','memory-compose-check'} & set(t.phases)
    journal=next((runtime/'legal-agent'/'runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        kinds={r[0] for r in db.execute('SELECT kind FROM event')}
    assert {'MEMORY_SEMANTIC_REVIEW_SKIPPED','FINAL_REVIEW_SKIPPED'} <= kinds


def test_v6_still_rejects_fabricated_quote_without_semantic_judge(unified,monkeypatch):
    _,send,t,p,runtime=unified
    original=t.send_once;fabricated_calls=[]
    def fabricated(*,body,ticket):
        view=json.loads(body['messages'][1]['content'])['view']
        phase=view.get('source_stage',view['phase'])
        if phase.startswith('memory-assess'):
            fabricated_calls.append(phase)
            source=view['sources'][0]
            return wire({'claims':[{'text':'모의 판단','source_id':source['source_id'],
                'quote':'원문에 없는 위조 인용문'}],'limitations':[]})
        return original(body=body,ticket=ticket)
    monkeypatch.setattr(t,'send_once',fabricated)
    response=send()
    assert response.status_code==502 and response.json()['answer_status']=='failed'
    assert '원문에 없는 위조 인용문' not in response.text and 'fabricated source quote' not in response.text
    journals=list((runtime/'legal-agent'/'runs').glob('*/*/journal.sqlite'))
    assert journals
    from semantic_runtime.legal_agent.journal_storage import connect
    with connect(journals[-1]) as db:
        rejected=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='OUTPUT_DECISION_STATE'") if 'fabricated source quote' in r[0]]
    assert len(fabricated_calls)==2
    assert list((runtime/'runs').glob('*.json'))==[]
    assert not {'memory-assess-check','memory-compose-check'} & set(t.phases)


def test_u01_u02_full_question_correction_restore_confirmation_legal_wiki_new_session(unified):
    client,send,t,p,runtime=unified
    first=ok(send());gid=first['question_id']
    assert first['response_schema']=='legal-agent-unified-response-v1' and first['run_id']
    one=ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])))
    two=ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'B'}])))
    assert one['executed']==two['executed']==['ASSESS','COMPOSE']
    body={'question':'','session_id':'s','request_id':'query','query_kind':'history','question_id':gid,'limit':100}
    history=ok(client.post('/v1/rag/memory/query',json=body))['events']
    original=next(e for e in history if e['kind']=='START')['id']
    restored=ok(send(command('STATE_RESTORE',target=gid,restore_event=original,restore_fields=['facts'])))
    assert restored['question_id']==gid and restored['revision']==4
    stored=ok(send(command('EXPERIENCE_CONFIRM',target=gid),question='최종 맞아. 기억해줘.'))
    kid=stored['experience_id'];assert kid and stored['status']=='STORED'
    wiki_pages=[]
    for kind in ('legal_wiki',):
        out=ok(client.post('/v1/rag/memory/query',json={**body,'query_kind':kind}))
        page=out['pages'][0];wiki_pages.append(page)
        assert page['experience_id']==kid and page['experience_revision']==4
    assert wiki_pages[0]['judgment_refs']
    reused=ok(send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,
        task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[]),session_id='other'))
    assert reused['status']=='REUSED' and reused['experience_id']==kid
    assert reused['executed']==['COMPOSE'] and reused['question_id']!=gid
    # Every request uses one native journal for resolver, source actions and judgment.
    journals=list((runtime/'legal-agent'/'runs').glob('*/*/journal.sqlite'))
    assert len(journals)==6
    for journal in journals:
        with sqlite3.connect(journal) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==6
            kinds=[r[0] for r in db.execute('SELECT kind FROM event')]
            assert 'MEMORY_MODEL_SESSION' in kinds
            if journal.parent.name==first['run_id']:assert 'CASE_JUDGMENT_ACCEPTED' in kinds
            assert db.execute('SELECT status FROM run').fetchone()[0]=='COMPLETED'
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute("SELECT count(*) FROM route WHERE goal=? AND status='ACTIVE'",(gid,)).fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM event WHERE goal=? AND kind=\'CORRECT\'',(gid,)).fetchone()[0]==3


def test_u03_changed_conditions_trigger_investigation(unified):
    _,send,t,p,runtime=unified
    first=ok(send());kid=ok(send(command('EXPERIENCE_CONFIRM',target=first['question_id'])))['experience_id']
    # The scripted check reports equivalence; the server still checks exact facts.
    result=ok(send(command('EXPERIENCE_REUSE',document_scope_mode='AUTHORIZED',knowledge_id=kid,
        task='모의승인규정 제1조의 승인 대상은?',queries=['승인'],facts=[{'name':'대상','value':'다른 대상'}]),session_id='other'))
    assert result['status']=='READY' and 'ASSESS' in result['executed']


def test_u05_presentation_keeps_confirmed_judgment(unified):
    client,send,t,p,runtime=unified
    first=ok(send());gid=first['question_id'];kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    before=ok(client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':kid}))
    table=ok(send(command('ANSWER_PRESENT',target=gid,format='table')))
    after=ok(client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':kid}))
    assert table['executed']==['COMPOSE'] and table['answer']['text'].startswith('|')
    assert before['judgment_refs']['ASSESS']==after['judgment_refs']['ASSESS']


def test_u09_owner_scope_and_u14_request_dedup(unified):
    client,send,t,p,runtime=unified
    first=ok(send(request_id='same'));calls=len(t.phases)
    again=ok(send(request_id='same'))
    assert {k:v for k,v in again.items() if k!='execution_stats'}=={k:v for k,v in first.items() if k!='execution_stats'}
    assert len(t.phases)==calls
    assert send(request_id='same',question='changed').status_code==409
    kid=ok(send(command('EXPERIENCE_CONFIRM',target=first['question_id'])))['experience_id']
    p['user_id']='other'
    assert client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':kid}).status_code==422
    assert send().status_code==422


def test_u04_relink_reassesses_current_case_and_preserves_source_experience(unified):
    client,send,t,p,runtime=unified
    first=ok(send());gid=first['question_id'];old=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    second=ok(send(command('CASE_START',document_scope_mode='AUTHORIZED',task='모의승인규정 제1조의 승인 대상은?',facts=[]),session_id='second'))
    kid=ok(send(command('EXPERIENCE_CONFIRM',target=second['question_id']),session_id='second'))['experience_id']
    linked=ok(send(command('WIKI_RELINK',target=gid,knowledge_id=kid)))
    assert linked['question_id']==gid and 'ASSESS' in linked['executed']
    assert ok(client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':kid}))['experience_id']==kid
    assert client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':old}).status_code==422


def test_u06_failed_correction_resumes_same_request_without_second_correction(unified):
    _,send,t,p,runtime=unified
    gid=ok(send())['question_id'];ok(send(command('EXPERIENCE_CONFIRM',target=gid)))
    t.fail='memory-assess'
    assert send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}]),request_id='retry').status_code==502
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute('SELECT status,pending FROM goal WHERE id=?',(gid,)).fetchone()==('PENDING','ASSESS')
        assert db.execute("SELECT count(*) FROM knowledge WHERE status='ACTIVE'").fetchone()[0]==0
    t.fail=None
    result=ok(send(request_id='retry'))
    assert result['executed']==['ASSESS','COMPOSE']
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute("SELECT count(*) FROM event WHERE goal=? AND kind='CORRECT'",(gid,)).fetchone()[0]==1


def test_u07_wiki_failure_retains_authority_and_rebuilds(unified,monkeypatch):
    from semantic_runtime.legal_agent.knowledge_repository import KnowledgeRepository
    client,send,t,p,runtime=unified;gid=ok(send())['question_id']
    original=KnowledgeRepository.rebuild
    def broken(*args):raise OSError('injected wiki disk failure')
    monkeypatch.setattr(KnowledgeRepository,'rebuild',broken)
    kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    for kind in ('legal_wiki',):
        assert ok(client.post('/v1/rag/memory/query',json={'query_kind':kind}))['pages'][0]['experience_id']==kid
    with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
        assert db.execute("SELECT status FROM outbox WHERE kind='EXPERIENCE_CONFIRMED'").fetchone()[0]=='PENDING'
    monkeypatch.setattr(KnowledgeRepository,'rebuild',original)
    ok(send(command('EXPERIENCE_CONFIRM',target=gid)))
    assert len(list((runtime/'case-memory'/'wikis').glob('*/legal_wiki/index.json')))==1
    ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])))
    assert ok(client.post('/v1/rag/memory/query',json={'query_kind':'legal_wiki'}))['pages']==[]


def test_u08_late_model_output_cannot_overwrite_new_revision(unified):
    _,send,t,p,runtime=unified;gid=ok(send())['question_id'];published=len(list((runtime/'runs').glob('*.json')))
    def newer(phase,data):
        if phase=='memory-compose':
            with sqlite3.connect(runtime/'case-memory'/'cases-v3.sqlite') as db:
                db.execute("UPDATE goal SET revision=revision+1,status='PENDING' WHERE id=?",(gid,))
            t.before_return=None
    t.before_return=newer
    response=send(command('ANSWER_PRESENT',target=gid))
    assert response.status_code==409 and len(list((runtime/'runs').glob('*.json')))==published


def test_u09_revoked_document_scope_hides_history_and_experience(unified):
    client,send,t,p,runtime=unified;gid=ok(send())['question_id'];kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    p['document_ids']=[]
    for body in ({'query_kind':'history','question_id':gid},{'query_kind':'experience','experience_id':kid}):
        assert client.post('/v1/rag/memory/query',json=body).status_code==422


def test_u10_policy_drift_blocks_exact_reuse(unified):
    client,send,t,p,runtime=unified;gid=ok(send())['question_id'];kid=ok(send(command('EXPERIENCE_CONFIRM',target=gid)))['experience_id']
    client.app.state.pipeline.term_agent.profile['max_model_attempts']+=1
    assert client.post('/v1/rag/memory/query',json={'query_kind':'experience','experience_id':kid}).status_code==422


def test_u12_additional_originals_reenter_existing_source_tools(unified):
    _,send,t,p,runtime=unified;t.fulltext_once=True
    result=ok(send());assert result['executed'].count('RECALL')==2 and result['executed'].count('READ')==2


def test_u13_fixed_domain_method_does_not_request_or_accept_model_concepts(unified):
    _,send,t,p,runtime=unified;t.bad_domain=True
    result=ok(send())
    assert not any(x.startswith('domain-choice-') for x in t.phases)
    journal=next((runtime/'legal-agent'/'runs').glob('*/'+result['run_id']+'/journal.sqlite'))
    with sqlite3.connect(journal) as db:
        choices=[json.loads(r[0]) for r in db.execute('SELECT choice_json FROM domain_choice')]
    assert choices and all(c['path']=='DISCOVERY' and c['concept_ids']==[] and c['relation_ids']==[] for c in choices)


def test_u14_old_response_cannot_revive_corrected_experience(unified):
    _,send,t,p,runtime=unified;gid=ok(send(request_id='first'))['question_id']
    ok(send(command('FACT_UPDATE',target=gid,facts=[{'name':'대상','value':'A'}])))
    assert send(request_id='first').status_code==409


@pytest.mark.parametrize('question,use_llm',[('안녕하세요',True),('전체 문서 목록',True),('승인 대상은?',False)])
def test_u15_existing_system_routes_and_feedback(unified,question,use_llm):
    client,send,t,p,runtime=unified
    result=ok(client.post('/v1/rag/ask',json={'question':question,'use_llm':use_llm,'document_ids':['d']}))
    assert result['run_id'] and result['answer']['query_id']==result['query']['id']
    assert ok(client.post('/v1/rag/feedback',json={'run_id':result['run_id'],'signal':'OTHER','reason':'모의 계약'}))


def test_u01_source_scope_correction_recorrection_restores_original_event(tmp_path,mixed_generation):
    t=ScriptedTransport();t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task='승인 절차는?',queries=['승인'],facts=[])
    p={'user_id':'u','team_id':'risk_team','document_ids':['internal','external']}
    app=create_app(tmp_path,mixed_generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
        legal_agent_profile={**settings(),'max_model_attempts':40},legal_agent_transport=t,memory_identity=lambda req:p)
    with TestClient(app) as client:
        body={'question':'내규: 승인 절차는?','session_id':'s','request_id':'first'}
        first=ok(client.post('/v1/rag/ask',json=body));gid=first['question_id']
        assert {x['document_id'] for x in first['assembly']['context']}=={'internal'}
        t.command=command('RESEARCH_REPLAN',target=gid,source_category='external')
        external=ok(client.post('/v1/rag/ask',json={**body,'question':'외규로 정정','request_id':'second'}))
        assert {x['document_id'] for x in external['assembly']['context']}=={'external'}
        t.command=command('RESEARCH_REPLAN',target=gid,source_category='ALL')
        ok(client.post('/v1/rag/ask',json={**body,'question':'정정을 다시 정정. 전체 범위','request_id':'third'}))
        ok(client.post('/v1/rag/ask',json={**body,'question':'[AD모드 시작]','request_id':'admin-start'}))
        history=ok(client.post('/v1/rag/memory/query',json={'query_kind':'history','question_id':gid,'session_id':'s'}))['events']
        ok(client.post('/v1/rag/ask',json={**body,'question':'[AD모드 종료]','request_id':'admin-end'}))
        t.command=command('STATE_RESTORE',target=gid,restore_event=history[0]['id'],restore_fields=['source_category'])
        restored=ok(client.post('/v1/rag/ask',json={**body,'question':'최초 조건으로 복원','request_id':'restore'}))
        assert restored['question_id']==gid and {x['document_id'] for x in restored['assembly']['context']}=={'internal'}


def test_u11_exact_experience_lookup_is_independent_of_top_32(memory):
    # This is the repository lookup boundary on synthetic checkpoint payloads.
    db,f,w,send,p=memory
    ids=[]
    for n in range(36):
        first=send(command('CASE_START',task='모의 질문 '+str(n),facts=[]))
        ids.append(send(command('EXPERIENCE_CONFIRM',target=first['goal_id']))['knowledge_id'])
    offered={k['id'] for k in db.candidates(p,'')}
    beyond=next(k for k in ids if k not in offered)
    assert db.checked_knowledge(beyond,p)['id']==beyond
