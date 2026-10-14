"""Concise user progress preserves committed judgments, scope and transport."""
import asyncio
import json
import logging
from pathlib import Path
import pytest
from semantic_runtime.contracts import digest
from semantic_runtime.progress import ProgressCapture
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.obligation_repository import ObligationRepository
import importlib.util


def workflow():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('key_progress_views', root/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def journal(tmp_path):
    run_id = 'a'*32
    context = RequestContext.create({'id':'q1','question':'모의 질문'}, {'question':'모의 질문'},
        {'scope':{'document_version_ids':['allowed']}},60,run_id)
    path = tmp_path/'legal-agent/runs/day'/run_id/'journal.sqlite'
    repo = ObligationRepository(path,context,{'max_model_attempts':10,'finalization_reserve':2,'max_tool_actions':10})
    events = []; projection = ProgressCapture('r1',tmp_path,events.append); projection.run_id=run_id
    yield repo,projection,events
    repo.close()


def evidence(did='allowed',suffix='1'):
    return {'evidence_id':'e'+suffix,'source_id':'s'+suffix,'document_id':did,'unit_id':'u1',
            'generation_id':'synthetic','source_artifact_hash':'0'*64,'text_hash':'0'*64,
            'role':'reference','temporal_status':'unknown','spans':[],
            'metadata':{'document_name':'모의규정' if did=='allowed' else '비공개 규정','heading':'제1조'}}


def read(repo,item):
    return repo.record_observation({'tool':'read','args':{'target':item['evidence_id']}},
        {'status':'OK','coverage':{'complete':True},'next_cursor':None},[item],verify=lambda _:None)


def display_events(events):
    display = workflow()._ChatProgress({})
    display.enabled = display.show_progress = display.show_inline_progress = True
    sent = []
    async def emit(name, value, room): sent.append((name, value))
    display.emit = emit
    async def run():
        for event in events: await display.progress(event)
    asyncio.run(run())
    return display, sent, ''.join(v for k,v in sent if k == 'token')


def test_wait_and_wire_codes_never_become_user_steps(journal):
    repo, projection, events = journal
    for kind in ('ATTEMPT_SENT','ATTEMPT_FINISHED'):
        repo.event(kind, {'attempt_id':'does-not-exist','action':'START','status':'SUCCEEDED'})
    projection.poll_journal()
    record = logging.LogRecord('genos', logging.INFO, '', 0, 'model.attempt.started', (), None)
    record.fields = {'request_id':'r1','phase':'compose'}
    projection.emit(record)
    assert not events
    display, sent, text = display_events([
        {'schema_version':'rag-progress-v1','kind':kind,'label':'대기 중 · 90초'}
        for kind in ('heartbeat','model_wait')])
    assert not sent and not display.blocks and not text


def test_all_laws_and_search_values_are_separate_lines_and_scope_filtered(journal):
    repo, projection, events = journal
    laws = [{'document_id':'allowed','name':f'모의법령 {i}'} for i in range(1,20)]
    repo.event('LAW_FULLTEXT_DIRECTORY', {'queries':['승인','공시','조건'],
        'laws':laws+[{'document_id':'other','name':'비공개법령'}],'total_laws':20})
    projection.poll_journal()
    _,_,text = display_events(events)
    for law in laws: assert '- '+law['name']+'\n' in text
    assert '- 모의법령 1\n\n- 모의법령 2' in text
    assert '비공개' not in text
    assert len(events)==3


def test_only_one_read_start_per_law_until_return(journal):
    repo, projection, events = journal
    for i in range(1,15):
        repo.event('UNIT_READ_STARTED', {'document_id':'allowed','document_name':'모의규정','location':f'제{i}조'})
        repo.event('UNIT_READ_FINISHED', {'document_id':'allowed','document_name':'모의규정','location':f'제{i}조','complete':True})
    repo.event('INVESTIGATION_POINT_RETURNED', {'reason':'다른 적용 조건을 확인해야 합니다'})
    repo.event('UNIT_READ_STARTED', {'document_id':'allowed','document_name':'모의규정','location':'제15조'})
    projection.poll_journal()
    assert len([e for e in events if e['kind']=='reading']) == 2
    assert [e['kind'] for e in events] == ['reading','revised','reading']
    assert '다른 적용 조건' in events[1]['details'][0]


@pytest.fixture
def native(journal,tmp_path):
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    old,_,_ = journal
    repo = UnifiedRepository(tmp_path/'native/journal.sqlite',old.context,
        {'max_model_attempts':10,'finalization_reserve':2,'max_tool_actions':10})
    events = []; projection = ProgressCapture('r1',tmp_path,events.append)
    projection.run_id = old.context.run_id; projection.journal_path = repo.path
    yield repo,projection,events
    repo.close()


def commit(repo,stage,payload,*,bad_hash=False):
    with repo.transaction():
        seq = repo.event('CASE_JUDGMENT_ACCEPTED', {'stage':stage,'payload_hash': '0'*64 if bad_hash else digest(payload)})
        repo.put('case_stage','case:'+stage,payload,seq)


def test_stage_decisions_are_from_verified_payloads_and_bound_sources(native):
    repo,projection,events = native
    read(repo,evidence()); read(repo,evidence('other','private'))
    commit(repo,'INTENT',{'purpose':'승인 대상과 예외 조건을 확인합니다','concepts':['승인','예외']})
    commit(repo,'PLAN',{'queries':['긴급 승인 조건']})
    commit(repo,'RECALL',{'selected_for_read':['s1'],'discovery':{'law_navigation':{'terms':['승인','조건']}}})
    commit(repo,'ASSESS',{'claims':[{'source_id':'s1','text':'모의 규정상 승인이 필요합니다'},
                                 {'source_id':'sprivate','text':'비공개 판단'}],'limitations':[]})
    commit(repo,'COMPOSE',{},bad_hash=True)
    projection.poll_journal()
    steps = [e for e in events if e.get('basis',{}).get('kind')=='CASE_JUDGMENT_ACCEPTED']
    assert [e['basis']['stage'] for e in steps]==['INTENT','PLAN','RECALL','ASSESS']
    text = json.dumps(steps,ensure_ascii=False)
    assert '승인 대상과 예외 조건' in text and '긴급 승인 조건' in text and '승인이 필요' in text
    assert '본문 검색에 사용한 단어: 승인 / 조건' in text
    assert '비공개' not in text


def test_stage_reentry_reports_destination_and_gap(journal):
    repo,projection,events = journal
    repo.event('CASE_STAGE_REENTRY', {'from_stage':'ASSESS','stage':'SELECT','gaps':[{'reason':'예외 적용 근거가 부족합니다'}]})
    projection.poll_journal()
    assert events[0]['label']=='근거 선택 단계로 돌아갑니다'
    assert events[0]['details']==['예외 적용 근거가 부족합니다']


def test_real_fulltext_activity_is_grouped_by_law(journal):
    repo,projection,events = journal
    repo.event('SOURCE_FULLTEXT_RESULTS', {'query':'기한 연장','locations':[
        {'document_id':'allowed','document_name':'모의법','location':f'제{i}조'} for i in range(30)]})
    projection.poll_journal()
    assert len(events)==1 and events[0]['details']==['본문 검색어: 기한 연장','모의법']


def test_new_judgment_summary_does_not_change_source_report():
    from semantic_runtime.legal_agent.readable_log import render_detail
    text = render_detail('AGENT SOURCE FULLTEXT RESULTS', {'query':'승인','locations':[
        {'document_name':'모의규정','location':f'제{i}조'} for i in range(1,25)]})
    assert all(f'제{i}조' in text for i in range(1,25))


def test_fixed_intent_codes_and_repeated_law_choices_are_readable(native):
    repo,projection,events = native
    commit(repo,'INTENT',{'purpose':'GENERAL_RULE_EXPLANATION','concepts':['system:question'],
                         'issues':[{'question':'모의 규정의 승인 대상은 무엇인가?'}]})
    for reason in ('첫 원문 확인','원문 재확인','근거 확보'):
        repo.event('LAW_SELECTION_DECISION',{'status':'INVESTIGATE','law':{'document_id':'allowed','name':'모의규정'},'reason':reason})
    repo.event('REQUEST_ROUTED',{'mode':'CASE','reason':'법률 질문이므로 CASE로 분류하고 START합니다'})
    projection.poll_journal()
    text = json.dumps(events,ensure_ascii=False)
    assert 'GENERAL_RULE' not in text and 'system:question' not in text and 'START' not in text
    assert len([e for e in events if e.get('basis',{}).get('kind')=='LAW_SELECTION_DECISION'])==1
    assert '승인 대상은 무엇인가' in text


def test_execution_reentry_keeps_original_exception_and_records_destination(monkeypatch):
    from types import SimpleNamespace
    from semantic_runtime.legal_agent.unified_rag import UnifiedExecution, NativeExecution
    from semantic_runtime.legal_agent.corrected_memory import Reenter
    recovery = Reenter('SELECT','more originals required',{'gaps':[{'reason':'예외 확인 필요'}]})
    def fail(*args,**kwargs): raise recovery
    monkeypatch.setattr(NativeExecution,'stage',fail)
    saved = []
    execution = object.__new__(UnifiedExecution)
    execution.host = SimpleNamespace(domain=SimpleNamespace(select=lambda *a:{}))
    execution.s = SimpleNamespace(work=SimpleNamespace(event=lambda kind,payload:saved.append((kind,payload))))
    with pytest.raises(Reenter) as caught: execution.stage('ASSESS',{}, {}, '질문','prose')
    assert caught.value is recovery
    assert saved==[('CASE_STAGE_REENTRY',{'from_stage':'ASSESS','stage':'SELECT','gaps':[{'reason':'예외 확인 필요'}],'reason':'more originals required'})]
