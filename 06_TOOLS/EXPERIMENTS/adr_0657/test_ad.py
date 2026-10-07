import json
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from semantic_runtime.ad_mode import handle,ENTER,EXIT
from semantic_runtime.ad_store import Store,features,fingerprint,excluded
from semantic_runtime.ad_backend import Backend
from semantic_runtime.ad_jobs import run_one,schedule_tick,schedule_time
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import encoded,digest,MemoryError


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'cases-v4.sqlite';repo=ShortcutRepository(path)
    p={'user_id':'owner','team_id':'request','document_ids':['d1'],'authenticated':True}
    ids=[]
    for i in range(25):
        b={'session_id':'s'+str(i),'request_id':'r'+str(i),'question':'example '+str(i),'document_ids':['d1']}
        inv=repo.connect(repo.intake(b,p)['id'],p);ids.append(inv['id'])
    scope=repo.scope(p)
    value={'topic':'mock topic','question':'mock question','claims':[],'procedures':[],'members':[],
           'documents':['d1'],'completeness':'OPEN','unresolved':[],'input_cases':[ids[0]]}
    repo.db.execute('INSERT INTO sw_unit VALUES(?,?,1)',('unit:test',scope))
    repo.db.execute('INSERT INTO sw_knowledge VALUES(?,1,?,?,?,?)',('unit:test','build:test',encoded(value),digest(value),'OPEN'))
    repo.db.execute("INSERT INTO sw_lifecycle VALUES(?,1,'PUBLISHED')",('unit:test',))
    repo.close()
    counter=[0]
    def ask(text,chat='chat-a',workspace='request',request=None):
        counter[0]+=1
        return handle(path,workspace,'genos',chat,text,request or str(counter[0]))
    return path,p,ids,ask


def ok(answer):
    assert answer and answer['answer_status']=='administration',answer
    return answer


@pytest.mark.parametrize('q',['shortcut 목록','위키 삭제','야간작업 돌리기','[AD모드 시작] 위키 삭제','내용: [AD모드 시작]'])
def test_outside_mode_never_enters(env,q):
    assert env[3](q) is None


def test_exact_gate_and_exit_sessions(env):
    ask=env[3];ok(ask(ENTER));assert ask('위키 목록',chat='chat-b') is None
    assert ask('법률 질문')['answer_status']=='error'
    assert ok(ask(EXIT))['ad_mode'] is False
    assert ask('위키 목록') is None


def test_no_legal_intake_from_ad(env):
    path,_,_,ask=env;db=sqlite3.connect(path)
    before=db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]
    for q in [ENTER,'shortcut 목록','전체 테이블','알수없는 명령',EXIT]:ask(q)
    assert db.execute('SELECT count(*) FROM sw_intake').fetchone()[0]==before
    db.close()


def test_page_selection_mutate_restore(env):
    path,_,_,ask=env;ok(ask(ENTER));v=ok(ask('shortcut 목록'))['view_id']
    page=ok(ask('다음'))['text'];assert ':21' in page and '25/25' in page
    assert '20/25' in ok(ask('이전'))['text']
    # Exact row ID is stable across page calls and own mutations.
    row=sqlite3.connect(path).execute('SELECT entity FROM ad_view_row WHERE view=? AND ordinal=2',(v,)).fetchone()[0]
    ok(ask('첫 표 2번 승인'));ok(ask('첫 표 2번 버려'));ok(ask('휴지통'))
    ok(ask('방금 버린 것 복구'))
    db=sqlite3.connect(path);assert db.execute('SELECT trashed FROM ad_object WHERE entity=?',(row,)).fetchone()[0]==0


def test_stale_other_writer_rejected_and_atomic(env):
    path,_,_,ask=env;ok(ask(ENTER));v=ok(ask('shortcut 목록'))['view_id']
    db=sqlite3.connect(path);rows=db.execute('SELECT entity FROM ad_view_row WHERE view=? AND ordinal IN(1,2) ORDER BY ordinal',(v,)).fetchall()
    db.execute('UPDATE sw_investigation SET revision=revision+1 WHERE id=?',(rows[1][0],));db.commit()
    result=ask('1번과 2번 버려');assert result['answer_status']=='error' and 'AD_CONFLICT' in result['text']
    assert db.execute('SELECT count(*) FROM ad_object WHERE trashed=1').fetchone()[0]==0


def test_cross_workspace_view_cannot_read(env):
    path,_,_,ask=env;ok(ask(ENTER));v=ok(ask('shortcut 목록'))['view_id'];ok(ask(ENTER,workspace='other'))
    response=ask(v+':1 자세히',workspace='other');assert response['answer_status']=='error'


def test_idempotent_same_message_and_conflict(env):
    path,_,_,ask=env;ok(ask(ENTER));ok(ask('shortcut 목록'))
    a=ok(ask('1번 버려',request='retry'));b=ok(ask('1번 버려',request='retry'));assert a==b
    assert ask('2번 버려',request='retry')['answer_status']=='error'
    db=sqlite3.connect(path);assert db.execute("SELECT count(*) FROM ad_change WHERE action='trash'").fetchone()[0]==1


def test_sql_catalog_and_raw_details(env):
    path,_,_,ask=env;ok(ask(ENTER));ok(ask('전체 테이블'));ok(ask('테이블 sw_event'))
    r=ok(ask('1번 자세히'));assert 'payload' in r['text']
    s=Store(path);columns={r[1]:r[2] for r in s.db.execute('PRAGMA table_info(ad_schedule)')}
    assert columns['due_at']=='REAL' and columns['enabled']=='INTEGER'
    assert s.db.execute("SELECT name FROM sqlite_master WHERE name='ad_schedule_due'").fetchone()
    with pytest.raises(sqlite3.IntegrityError):s.db.execute('UPDATE ad_feature SET wiki=9')
    s.close()


def test_edit_multiturn_and_immutable_original(env):
    path,_,_,ask=env;ok(ask(ENTER));ok(ask('shortcut 목록'));ok(ask('2번 수정'))
    r=ok(ask('제목을 수정된 제목으로 수정'));assert r['results'][0]['action']=='edit'
    db=sqlite3.connect(path);assert db.execute("SELECT count(*) FROM sw_investigation WHERE title='수정된 제목'").fetchone()[0]==1
    with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE sw_event SET kind='changed'")


def test_wiki_edit_new_draft_and_schema_error(env):
    path,p,_,ask=env;ok(ask(ENTER));ok(ask('위키 목록'));ok(ask('1번 선택'))
    ok(ask('/edit topic 새 주제'))
    db=sqlite3.connect(path);assert db.execute('SELECT head FROM sw_unit').fetchone()[0]==2
    assert db.execute('SELECT status FROM sw_lifecycle WHERE revision=2').fetchone()[0]=='DRAFT'
    r=ask('/edit claims 잘못된값');assert r['answer_status']=='error' and 'must be an array' in r['text']
    ok(ask('오류 목록'));assert 'AD_SCHEMA' in ok(ask('1번 자세히'))['text']


def test_feature_off_keeps_admin(env):
    path,_,_,ask=env;ok(ask(ENTER));ok(ask('둘 다 꺼'));ok(ask('shortcut 목록'));ok(ask('1번 버려'));ok(ask('방금 버린 것 복구'))
    assert ask('야간작업 돌리기')['answer_status']=='error'
    ok(ask('위키 켜'));db=sqlite3.connect(path);assert features(db,'request')['shortcut']==0 and features(db,'request')['wiki']==1


def test_wiki_trash_blocks_current_and_restore(env):
    path,p,_,ask=env;ok(ask(ENTER));ok(ask('위키 목록'));ok(ask('1번 버려'))
    repo=ShortcutRepository(path)
    with pytest.raises(MemoryError):repo.current('unit:test',1,p)
    ok(ask('방금 버린 것 복구'));assert repo.current('unit:test',1,p)['revision']==1
    repo.close()


def test_schedule_midnight_and_ambiguity(env):
    ask=env[3];ok(ask(ENTER));r=ok(ask('야간작업 시작 예약 저녁 12시'))
    assert datetime.fromtimestamp(r['due_at'],ZoneInfo('Asia/Seoul')).hour==0
    assert '정오' in ok(ask('야간작업 예약 12시'))['text']
    assert 'schedule_id' in ok(ask('자정'))


def test_schedule_durable_cancel_and_due_once(env):
    path,_,_,ask=env;ok(ask(ENTER));r=ok(ask('야간작업 예약 저녁 12시'));key=r['schedule_id']
    ok(ask(EXIT));s=Store(path)
    schedule_tick(s,now=r['due_at']+1);schedule_tick(s,now=r['due_at']+2)
    assert s.db.execute('SELECT count(*) FROM ad_job WHERE schedule=?',(key,)).fetchone()[0]==1
    s.close();ok(ask(ENTER));ok(ask('예약 목록'));ok(ask('1번 예약 취소'))


def test_job_fail_report_and_retry(env):
    path,_,_,ask=env;ok(ask(ENTER));job=ok(ask('야간작업 돌리기'))['job_id'];s=Store(path)
    def fail(*args):raise ValueError('schema path units[0].claims: missing source_id')
    run_one(s,fail)
    assert s.db.execute('SELECT count(*) FROM ad_error WHERE job=?',(job,)).fetchone()[0]==1
    assert 'missing source_id' in ok(ask('진행상황 알려줘'))['text']
    ok(ask('작업 중지'));assert s.db.execute('SELECT desired FROM ad_job WHERE id=?',(job,)).fetchone()[0]=='PAUSE'
    ok(ask('실패 작업 재시도'))
    assert s.db.execute("SELECT count(*) FROM ad_job_item WHERE job=? AND status='FAILED'",(job,)).fetchone()[0]==0
    s.close()


def test_job_fence_rejects_disabled_commit(env):
    path,_,_,ask=env;ok(ask(ENTER));job=ok(ask('야간작업 돌리기'))['job_id'];s=Store(path)
    def callback(job,item,guard):
        ok(ask('위키 꺼'));guard();raise AssertionError('must not commit')
    run_one(s,callback)
    assert s.db.execute('SELECT status FROM ad_job WHERE id=?',(job,)).fetchone()[0]=='PAUSED';s.close()


def test_job_sql_restart_expired_lease(env):
    path,_,_,ask=env;ok(ask(ENTER));job=ok(ask('야간작업 돌리기'))['job_id'];s=Store(path)
    s.db.execute("UPDATE ad_job SET status='RUNNING',lease='old',lease_until=1 WHERE id=?",(job,));s.close()
    s=Store(path);calls=[]
    def compile_(j,item,guard):guard();calls.append(item['queue_id']);return {'status':'DONE'}
    run_one(s,compile_);assert calls
    assert s.db.execute('SELECT completed FROM ad_job WHERE id=?',(job,)).fetchone()[0]==1;s.close()


def test_detail_no_truncation(env):
    path,_,_,ask=env;db=sqlite3.connect(path);db.execute('UPDATE sw_investigation SET title=?',('한글'*10000,));db.commit();db.close()
    ok(ask(ENTER));ok(ask('shortcut 목록'));a=ok(ask('1번 자세히'));assert a['has_more']
    while a['has_more']:a=ok(ask('계속'))
    assert '본문 끝' in a['text']


def test_new_view_does_not_reuse_stale_selection(env):
    ask=env[3];ok(ask(ENTER));ok(ask('shortcut 목록'));ok(ask('1번 선택'));ok(ask('위키 목록'))
    assert ask('그거 버려')['answer_status']=='error'


def test_children_as_tables(env):
    ask=env[3];ok(ask(ENTER));ok(ask('shortcut 목록'))
    text=ok(ask('2번 발언 보여줘'))['text'];assert 'event' in text
    assert 'record' in ok(ask('1번 자세히'))['text']


def test_service_ad_before_legal_application(env,monkeypatch):
    import importlib.util,asyncio
    from conftest import CODE
    path=env[0];runtime=path.parent/'runtime'
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(runtime));monkeypatch.setenv('GENOS_STATE_DIR',str(path.parent))
    monkeypatch.setenv('TEAM_ID','request');monkeypatch.setenv('AD_WORKER_ENABLED','0')
    spec=importlib.util.spec_from_file_location('test_ad_service',CODE/'service.py');svc=importlib.util.module_from_spec(spec);spec.loader.exec_module(svc)
    def forbidden():raise AssertionError('AD must not initialize legal agent')
    svc.application=forbidden
    def send(q):return asyncio.run(svc.service({}, {'API_TYPE':'AD_PROBE','question':q,'ad_session_id':'bridge','ad_channel':'genos','request_id':q}))
    assert send('위키 목록')['body']=={'ad_handled':False}
    assert send(ENTER)['body']['ad_mode'] is True
    assert send('도움말')['body']['response_schema']=='ad-mode-v1'
    assert send(EXIT)['body']['ad_mode'] is False


def test_worker_continuation_is_not_completed(env):
    path,_,_,ask=env;ok(ask(ENTER));job=ok(ask('야간작업 돌리기'))['job_id'];s=Store(path)
    run_one(s,lambda *_:{'results':[{'status':'CONTINUE'}]})
    assert s.db.execute('SELECT completed FROM ad_job WHERE id=?',(job,)).fetchone()[0]==0
    assert s.db.execute("SELECT count(*) FROM ad_job_item WHERE job=? AND status='DONE'",(job,)).fetchone()[0]==0
    s.close()


def test_pending_schedule_keeps_daily_intent(env):
    ask=env[3];ok(ask(ENTER));ok(ask('매일 야간작업 예약 12시'));r=ok(ask('자정'))
    db=sqlite3.connect(env[0]);assert db.execute('SELECT repeat_seconds FROM ad_schedule WHERE id=?',(r['schedule_id'],)).fetchone()[0]==86400


def test_trash_row_restore_phrase(env):
    ask=env[3];ok(ask(ENTER));ok(ask('shortcut 목록'));ok(ask('1번 버려'));ok(ask('휴지통'))
    assert ok(ask('휴지통 1번 복구'))['results'][0]['action']=='restore'


def test_original_utterance_in_details(env):
    ask=env[3];ok(ask(ENTER));ok(ask('shortcut 목록'))
    r=ok(ask('1번 자세히'));assert 'intake_events' in r['text'] and 'example ' in r['text']


def test_corrupt_sql_visible_and_no_legal_fallthrough(tmp_path):
    p=tmp_path/'broken.sqlite';p.write_bytes(b'not a sqlite database')
    r=handle(p,'request','genos','c','진행상황','r')
    assert r['answer_status']=='error' and 'DatabaseError' in r['text']


def test_chat_adapter_routes_before_legal_without_model(env,monkeypatch):
    import asyncio
    from semantic_runtime import chat_adapter as chat
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(env[0].parent));monkeypatch.setenv('AD_WORKER_ENABLED','0')
    calls=[]
    async def backend(body):
        calls.append(body['API_TYPE'])
        r=handle(env[0],'request',body['ad_channel'],body['ad_session_id'],body['question'],body['request_id'])
        assert r is not None,'No legal model may be called'
        return {'status':200,'body':r}
    monkeypatch.setattr(chat,'call_service',backend)
    for i,q in enumerate([ENTER,'shortcut 목록','2번 승인','2번 버려','방금 버린 것 복구',EXIT]):
        r=asyncio.run(chat.chat({'question':q,'chatId':'adapter','request_id':str(i)},trusted_platform=True))
        assert r['data']['response_schema']=='ad-mode-v1'
    assert calls==['AD_PROBE']*6
    denied=asyncio.run(chat.chat({'question':ENTER,'chatId':'adapter'},trusted_platform=False))
    assert denied['data']['answer_status']=='error' and len(calls)==6


def test_workflow_probe_preserves_raw_session(env,monkeypatch):
    import asyncio,importlib.util
    from conftest import CODE
    spec=importlib.util.spec_from_file_location('ad_test_workflow',CODE/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    workflow=importlib.util.module_from_spec(spec);spec.loader.exec_module(workflow)
    calls=[]
    async def mock_post(*args,**kwargs):
        calls.append((args,kwargs))
        return {'status':200,'body':{'response_schema':'ad-mode-v1','ad_mode':True,'text':'AD test','answer_status':'administration'}}
    # Adapter contract uses its existing HTTP call, not a new endpoint/model.
    import inspect
    source=inspect.getsource(workflow._run_once)
    assert "'API_TYPE':'AD_PROBE'" in source
    body=workflow._request_body('x',{'chatId':'stable-chat','request_id':'r'})
    assert body['ad_session_id']=='stable-chat'


def test_workflow_multiturn_transport(env,monkeypatch):
    import asyncio,importlib.util
    from conftest import CODE
    spec=importlib.util.spec_from_file_location('workflow_multiturn',CODE/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
    calls=[]
    def post(body):
        calls.append(body)
        assert body['API_TYPE']=='AD_PROBE'
        r=handle(env[0],'request',body['ad_channel'],body['ad_session_id'],body['question'],body['request_id'])
        return {'status':200,'body':r}
    monkeypatch.setattr(w,'_post_code_serving',post)
    for i,q in enumerate([ENTER,'shortcut 목록','다음','21번 버려','방금 버린 것 복구',EXIT]):
        result=asyncio.run(w._run_once({'question':q,'chatId':'same-chat','request_id':'w'+str(i)}))
        assert result['response_schema']=='ad-mode-v1' and result['answer_status']=='administration',result
    assert {c['ad_session_id'] for c in calls}=={'same-chat'}


def test_trash_hidden_from_default_list_and_relink(env):
    from semantic_runtime.legal_agent.conversation_linker import propose
    path,p,_,ask=env;ok(ask(ENTER));ok(ask('shortcut 목록'))
    result=ok(ask('1번 버려'));entity=result['results'][0]['id']
    assert entity not in ok(ask('shortcut 목록'))['text']
    repo=ShortcutRepository(path)
    sessions=[r[0] for r in repo.db.execute('SELECT session FROM sw_session_link WHERE investigation=?',(entity,))]
    assert all(entity not in propose(repo,p,session=s).get('investigation_ids',[]) for s in sessions)
    repo.close()


def test_publish_requires_current_evidence_and_never_verifies(env):
    path,p,_,ask=env;ok(ask(ENTER));ok(ask('위키 목록'));ok(ask('1번 선택'));ok(ask('/edit topic 새 제목'));ok(ask('선택한 것 승인'));ok(ask('선택한 것 게시'))
    db=sqlite3.connect(path);assert db.execute('SELECT status FROM sw_lifecycle WHERE revision=2').fetchone()[0]=='PUBLISHED'
    assert db.execute('SELECT count(*) FROM sw_verification').fetchone()[0]==0
