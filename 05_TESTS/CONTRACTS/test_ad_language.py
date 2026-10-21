"""Synthetic AD contracts. Scripted model outputs test wiring, not LLM quality."""
import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from semantic_runtime.ad_mode import handle, ENTER, EXIT
from semantic_runtime.ad_store import Store
from semantic_runtime.ad_backend import Backend
from semantic_runtime import ad_gateway, ad_model
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository

ROOT=Path(__file__).resolve().parents[2]


def target(rows=(),view='',selection=False,all_rows=False):
    return {'view_id':view,'rows':list(rows),'selection':selection,'all_rows':all_rows}


def output(action,**args):
    plan={'action':action,'args':args}
    return {'plan':plan,'receipt':{'provider':'genos','trust_zone':'internal','model':'internal-test','usage':{'total_tokens':7}},'raw':{'plan':plan}}


@pytest.fixture
def records(tmp_path):
    path=tmp_path/'case-memory/cases-v4.sqlite'
    repo=ShortcutRepository(path)
    principal={'user_id':'owner','team_id':'financial_team','document_ids':['d'],'authenticated':True}
    ids=[]
    for i in range(25):
        body={'session_id':f'case-{i}','request_id':f'r-{i}','question':f'합성 사건 {i}','document_ids':['d']}
        ids.append(repo.connect(repo.intake(body,principal)['id'],principal)['id'])
    repo.close()
    from test_successful_core_routes import seed_ad_case
    for i,ident in enumerate(ids):seed_ad_case(path,ident,principal,f'case-{i}')
    count=[0]
    def ask(q,model=None,chat='chat',request=None):
        count[0]+=1
        return handle(path,'financial_team','genos-chat',chat,q,request or str(count[0]),interpret=model)
    assert ask(ENTER)['ad_mode'] is True
    return path,ask,ids


def test_every_natural_language_followup_uses_model_with_sql_context(records):
    path,ask,_=records;contexts=[]
    def model(ctx,*_):
        contexts.append(ctx)
        if ctx['question']=='숏컷보여줘':return output('list',kind='shortcut',query='')
        if ctx['question']=='1번 보여줘':
            assert ctx['state']['active_view']['rows']['items'][0]['ordinal']==1
            return output('detail',target=target([1]))
        assert ctx['question']=='그 사건 발언도 보여줘'
        assert ctx['state']['selection'][0]['kind']=='shortcut'
        assert ctx['state']['history'][-1]['request']=='1번 보여줘'
        return output('children',target=target(selection=True),child='발언')
    for q in ['숏컷보여줘','1번 보여줘','그 사건 발언도 보여줘']:
        response=ask(q,model)
        assert response['answer_status']=='administration',response
        assert '| ' in response['text'] and '```' not in response['text']
    assert len(contexts)==3
    db=sqlite3.connect(path)
    assert db.execute('SELECT count(*) FROM ad_language_turn').fetchone()[0]==3
    assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==25
    db.close()


def test_clarification_then_restart_followup_retains_intent(records):
    path,ask,_=records
    ask('숏컷 좀',lambda *_:output('list',kind='shortcut',query=''))
    def ambiguous(ctx,*_):
        return output('clarify',message='몇 번 항목을 휴지통으로 옮길까요?')
    clarified=ask('그거 지워',ambiguous)
    assert clarified['clarification'].startswith('몇 번')
    assert sqlite3.connect(path).execute('SELECT count(*) FROM ad_change').fetchone()[0]==0
    def followup(ctx,*_):
        assert ctx['state']['history'][-1]['request']=='그거 지워'
        assert '휴지통' in ctx['state']['history'][-1]['message']
        return output('mutate',target=target([1]),operation='trash')
    result=ask('첫 번째 거',followup)
    assert result['results'][0]['action']=='trash'
    assert '| 항목 | 값 |' in result['text']


def test_cached_request_never_calls_model_twice_and_conflict_keeps_result(records):
    _,ask,_=records;calls=[]
    def model(*_):calls.append(1);return output('list',kind='shortcut',query='')
    a=ask('숏컷 보여줘',model,request='same')
    assert ask('숏컷 보여줘',model,request='same')==a
    assert ask('위키 보여줘',model,request='same')['answer_status']=='error'
    assert ask('숏컷 보여줘',model,request='same')==a
    assert len(calls)==1


def test_model_runs_without_sql_write_lock_and_exit_fences_pending_plan(records):
    path,ask,_=records
    ask('숏컷',lambda *_:output('list',kind='shortcut',query=''))
    def model(*_):
        # A second writer can transact while the LLM call is outstanding.
        with sqlite3.connect(path,timeout=.1) as db:
            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE ad_feature SET changed_at=changed_at')
        assert ask(EXIT)['ad_mode'] is False
        return output('mutate',target=target([1]),operation='trash')
    response=ask('첫 거 지워',model)
    assert response['answer_status']=='error' and 'AD_CONFLICT' in response['text']
    assert response['ad_mode'] is False
    assert sqlite3.connect(path).execute('SELECT count(*) FROM ad_change').fetchone()[0]==0


def test_concurrent_and_duplicate_pending_turn_do_not_send_again(records):
    _,ask,_=records;calls=[]
    def model(*_):
        calls.append(1)
        assert ask('숏컷',lambda *_:pytest.fail('duplicate inference'),request='inflight')['answer_status']=='pending'
        assert ask('위키',lambda *_:pytest.fail('parallel inference'),request='another')['answer_status']=='pending'
        return output('list',kind='shortcut',query='')
    assert ask('숏컷',model,request='inflight')['answer_status']=='administration'
    assert len(calls)==1


def test_bad_model_plan_is_audited_without_sql_execution(records):
    path,ask,_=records
    def model(*_):return output('sql',query='DELETE FROM sw_investigation')
    response=ask('알아서 해줘',model)
    assert response['answer_status']=='error'
    db=sqlite3.connect(path)
    assert db.execute('SELECT count(*) FROM sw_investigation').fetchone()[0]==25
    assert 'DELETE FROM' in db.execute('SELECT model_output FROM ad_language_turn').fetchone()[0]
    assert db.execute('SELECT count(*) FROM ad_error').fetchone()[0]==1
    db.close()


def test_inaccessible_view_rejected_even_if_model_invents_reference(records):
    _,ask,_=records
    ask(ENTER,chat='other')
    view=ask('숏컷',lambda *_:output('list',kind='shortcut',query=''),chat='other')['view_id']
    result=ask('1번',lambda *_:output('detail',target=target([1],view=view)))
    assert result['answer_status']=='error' and 'AD_SCOPE' in result['text']


def test_stale_row_revision_rejected_after_model_returns(records):
    path,ask,_=records
    view=ask('숏컷',lambda *_:output('list',kind='shortcut',query=''))['view_id']
    def model(*_):
        with sqlite3.connect(path) as db:
            entity=db.execute('SELECT entity FROM ad_view_row WHERE view=? AND ordinal=1',(view,)).fetchone()[0]
            db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(entity,))
        return output('mutate',target=target([1]),operation='trash')
    result=ask('첫 거 지워',model)
    assert result['answer_status']=='error' and 'AD_CONFLICT' in result['text']


def test_long_detail_tables_preserve_every_character(records):
    path,ask,_=records;text='긴원문|<tag>\n'*3000
    with sqlite3.connect(path) as db:db.execute('UPDATE sw_investigation SET title=?',(text,))
    ask('숏컷',lambda *_:output('list',kind='shortcut',query=''))
    answer=ask('1번 보여줘',lambda *_:output('detail',target=target([1])))
    assert answer['has_more'] and '| 항목 | 값 |' in answer['text']
    shown=answer['text']
    while answer['has_more']:
        answer=ask('계속',lambda *_:output('continue'));shown+=answer['text']
    assert '본문 끝' in shown and '&lt;tag&gt;' in shown and '\\|' in shown
    db=sqlite3.connect(path)
    saved=json.loads(db.execute('SELECT content FROM ad_detail ORDER BY created_at DESC LIMIT 1').fetchone()[0])
    title=''.join(r['value'] for r in saved['rows'] if r['field'].startswith('[1].record.title'))
    assert title==text


def test_outside_mode_and_exact_boundaries_skip_model(records):
    _,ask,_=records
    def unexpected(*_):pytest.fail('model should not be called')
    assert ask(ENTER,unexpected)['ad_mode']
    assert ask(EXIT,unexpected)['ad_mode'] is False
    assert ask('숏컷보여줘',unexpected) is None
    assert ask('내용: [AD모드 시작]',unexpected) is None


def test_multiturn_edit_uses_selected_row_and_preserves_immutable_fields(records):
    path,ask,_=records
    ask('숏컷',lambda *_:output('list',kind='shortcut',query=''))
    begin=ask('첫 번째 제목 바꾸자',lambda *_:output('begin_edit',target=target([1])))
    assert begin['clarification']
    def model(ctx,*_):
        assert ctx['state']['session']['pending_action']=='edit'
        assert ctx['state']['selection'][0]['kind']=='shortcut'
        return output('edit',target=target(selection=True),field='title',value='변경된 합성 제목')
    result=ask('제목은 변경된 합성 제목',model)
    assert result['answer_status']=='administration'
    assert sqlite3.connect(path).execute('SELECT count(*) FROM sw_investigation WHERE title=?',('변경된 합성 제목',)).fetchone()[0]==1
    rejected=ask('근거 해시도 수정',lambda *_:output('edit',target=target(selection=True),field='hash',value='invented'))
    assert rejected['answer_status']=='error' and 'AD_SCHEMA' in rejected['text']


def test_ambiguous_schedule_followup_and_job_status_are_interpreted(records):
    path,ask,_=records
    ask('12시에 해',lambda *_:output('clarify',message='정오인가요, 자정인가요?'))
    def model(ctx,*_):
        assert ctx['state']['history'][-1]['request']=='12시에 해'
        return output('schedule',when='2030-10-08 00:00')
    scheduled=ask('자정',model)
    assert scheduled['schedule_id'] and '| 항목 | 값 |' in scheduled['text']
    job=ask('지금 먼저 돌려줘',lambda *_:output('start_job'))
    assert job['job_id']
    status=ask('얼마나 됐냐',lambda *_:output('job',target=target(),control='status'))
    assert status['answer_status']=='administration' and job['job_id'] in status['text']
    assert sqlite3.connect(path).execute('SELECT count(*) FROM ad_schedule').fetchone()[0]==1


def test_expired_claim_is_failed_without_second_model_send(records):
    path,ask,_=records
    store=Store(path);session=store.session('financial_team','genos-chat','chat')
    from semantic_runtime.ad_store import fingerprint
    store.db.execute("INSERT INTO ad_operation(id,session,request,input_hash,action,status,created_at) VALUES('expired',?,'retry',?,'숏컷','RUNNING',0)",(session['id'],fingerprint('숏컷')))
    store.db.execute("INSERT INTO ad_language_turn VALUES('expired',?,'hash','{}',NULL,NULL,NULL,0,0)",(session['id'],));store.close()
    result=ask('숏컷',lambda *_:pytest.fail('expired claim must not resend'),request='retry')
    assert 'AD_INTERRUPTED' in result['text']


def test_model_failure_stays_ad_and_does_not_fallback(records):
    path,ask,_=records
    def failing(*_):raise RuntimeError('internal LLM unavailable')
    result=ask('숏컷',failing)
    assert result['response_schema']=='ad-mode-v1' and result['answer_status']=='error'
    assert 'internal LLM unavailable' in result['text']
    assert sqlite3.connect(path).execute('SELECT count(*) FROM sw_intake').fetchone()[0]==25


def test_gateway_workflow_calls_internal_interpreter_without_legal_bootstrap(records,monkeypatch):
    path,_,_=records;monkeypatch.setenv('TEAM_ID','financial_team');monkeypatch.setenv('AD_WORKER_ENABLED','0')
    monkeypatch.delenv('GENOS_STATE_DIR',raising=False);monkeypatch.delenv('GENOS_RUNTIME_DIR',raising=False)
    calls=[]
    def model(ctx,*_):calls.append(ctx);return output('list',kind='shortcut',query='')
    monkeypatch.setattr(ad_gateway,'interpret',model)
    spec=importlib.util.spec_from_file_location('workflow_ad_language',ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    def forbidden():pytest.fail('legal application must not bootstrap for AD')
    monkeypatch.setattr(w,'_post_code_serving',lambda body:ad_gateway.intercept(body,path.parents[1],forbidden))
    assert asyncio.run(w.run({'question':ENTER,'chatId':'chat','request_id':'workflow-enter'}))['ad_mode']
    q={'question':'숏컷보여줘','chatId':'chat','request_id':'workflow-natural'}
    result=asyncio.run(w.run(q))
    assert result['language_action']=='list' and result['ad_mode']
    assert len(calls)==1 and calls[0]['state']['session']['chat']=='chat'


@pytest.mark.parametrize('finish,model_id',[('stop','internal-test'),('length','internal-test'),('stop','other-model'),('stop',None)])
def test_internal_adapter_preserves_payload_binding_and_audits_invalid_output(monkeypatch,finish,model_id):
    from semantic_runtime.genos import endpoint
    target_endpoint=endpoint('https://internal.invalid/v1',token='test-secret',read_timeout=91)
    monkeypatch.setattr(ad_model,'from_env',lambda _: (target_endpoint,'internal-test'))
    monkeypatch.setenv('GENOS_RAG_MAX_OUTPUT_TOKENS','1234');sent=[]
    class Transport:
        def __init__(self,target,binding):
            assert binding['provider']=='genos' and binding['trust_zone']=='internal'
        def send_once(self,body,ticket):
            sent.append(body);assert ticket['remaining_seconds']==91
            return {'body_json':{'model':model_id,'choices':[{'finish_reason':finish,'message':{'content':json.dumps({'action':'help','args':{}})}}],
                'usage':{'total_tokens':7}},'body_sha256':'response-hash'}
    monkeypatch.setattr(ad_model,'GenosTransport',Transport)
    result=ad_model.interpret({'question':'숏컷','request_id':'ad-turn'},{'type':'object'},'system')
    assert 'max_tokens' not in sent[0] and sent[0]['chat_template_kwargs']=={'enable_thinking':False}
    assert result['raw']['usage']['total_tokens']==7 and result['receipt']['response_sha256']=='response-hash'
    assert result['receipt']['requested_model']=='internal-test'
    assert result['receipt']['actual_response_model']==model_id
    if finish=='length':assert result['plan'] is None and result['receipt']['decode_error']
    else:assert result['plan']['action']=='help'


def test_service_moves_model_interception_off_async_event_loop(monkeypatch):
    import service
    caller=threading.get_ident();workers=[]
    def intercept(*_):workers.append(threading.get_ident());return {'status':200,'body':{'response_schema':'ad-mode-v1','text':'test'}}
    monkeypatch.setattr(service,'_ad_control',lambda:SimpleNamespace(intercept=intercept,start_worker=lambda *_:None))
    assert asyncio.run(service.service({}, {'API_TYPE':'AD_PROBE'}))['status']==200
    assert workers and workers[0]!=caller
