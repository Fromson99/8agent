import asyncio
from copy import deepcopy
import json
import time
import pytest
from semantic_runtime import execution_metrics as em
from semantic_runtime.chat_adapter import views
from semantic_runtime.progress import ProgressCapture
from test_legal_agent_double_harness import work as base_work, generation, make_app
from test_model_decision_repair import work, bounded, SCHEMA


def event(kind='phase',stage='',n=0,**kw):
 return {'schema_version':'rag-progress-v1','request_id':'r','kind':kind,'label':'원시 세부 동작 '+str(n),'details':['PRIVATE_STEP_'+str(n)],'seq':n,'basis':{'kind':'CASE_STAGE_STARTED','stage':stage,'detail_mode':'activity'},**kw}

@pytest.mark.parametrize('repeats',[1,7,137])
def test_many_reads_have_stable_summary_ids_without_turn_counts(monkeypatch,repeats):
 monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','socketio');w=views();d=w._ChatProgress({'socketIOClientId':'fixture'});sent=[]
 async def emit(name,value,room):sent.append((name,deepcopy(value)))
 d.emit=emit
 async def run():
  for stage,kind in [('INTENT','phase'),('RECALL','candidate'),('READ','reading'),('SELECT','selected'),('ASSESS','decision'),('COMPOSE','phase')]:
   for n in range(repeats):await d.progress(event(kind,stage,n))
  await d.progress(event('reading','READ',999))
  await d.progress(event(basis={'kind':'OBS_EVENT','name':'request.finished'}))
  await d.finish('검증한 최종 답변')
 asyncio.run(run());cards=[v for k,v in sent if k=='agentFlowExecutedData']
 assert len(cards)==5 and len(cards[-1])==5 and len({c['nodeId'] for c in cards[-1]})==5
 assert 'PRIVATE_STEP' not in json.dumps(cards) and '원시 세부' not in json.dumps(cards,ensure_ascii=False)
 assert ''.join(v for k,v in sent if k=='token')=='검증한 최종 답변'
 assert sent[-1]==('end','end') and cards[0][0]==cards[-1][0]


def test_sse_projection_coalesces_before_consumer_and_private_events_stay_private(tmp_path):
 events=[];p=ProgressCapture('r',tmp_path,events.append)
 for i in range(80):p.publish('reading','원문 읽기',details=['PRIVATE'],basis={'kind':'UNIT_READ_FINISHED','detail_mode':'activity'})
 p.publish('decision','거절 상세',details=['PRIVATE_ERROR'],basis={'kind':'COMPLETION_ASSESSMENT_REJECTED','detail_mode':'judgment'})
 assert len(events)==1 and events[0]['basis']['stage']=='sources'
 assert 'PRIVATE' not in json.dumps(events)


def test_transport_calls_retries_and_non_call_work_are_separate(work):
 session=bounded(work,['{broken',{'mode':'SEARCH'}],max_schema_repairs=1)
 with em.capture() as metrics:
  result=session.structured('모의 지침',{'question':'모의 질문'},SCHEMA,'source-query-plan',10)
  for i in range(1000):str(i)  # Many local operations are not model calls.
  value=metrics.snapshot()
 assert result=={'mode':'SEARCH'} and len(session.gateway.transport.calls)==2
 assert value['llm_calls']==2 and all(type(c['duration_ms']) is int for c in value['calls'])
 assert value['llm_duration_ms']==sum(c['duration_ms'] for c in value['calls'])
 assert 'broken' not in json.dumps(value)


def test_failed_dispatch_has_duration_and_restores_context(monkeypatch):
 clock=iter([10.0,10.1,10.325,10.5,10.6]);monkeypatch.setattr(em,'time',__import__('types').SimpleNamespace(perf_counter=lambda:next(clock)))
 with em.capture() as m:
  with pytest.raises(RuntimeError):
   with em.transport_attempt('memory-assess','x'):raise RuntimeError('PRIVATE_CAUSE')
  value=m.snapshot()
 assert value['llm_calls']==1 and value['calls'][0]['duration_ms']==224
 assert value['request_duration_ms']==500 and 'PRIVATE' not in json.dumps(value)
 assert em._CURRENT.get() is None


def test_zero_calls_and_unfinished_timing_are_distinct():
 with em.capture() as m:
  assert m.snapshot()['llm_calls']==0
  row=m.begin('sources');v=m.snapshot()
  assert v['calls'][0]['duration_ms'] is None and v['timing_complete'] is False
  m.finish(row,19)
  assert m.snapshot()['timing_complete'] is True


def test_parallel_request_contexts_never_mix():
 async def request(count):
  with em.capture() as m:
   for n in range(count):
    with em.transport_attempt('memory-intent',str(n)):await asyncio.sleep(0)
   return m.snapshot()
 async def run():return await asyncio.gather(request(2),request(5),request(0))
 values=asyncio.run(run());assert [v['llm_calls'] for v in values]==[2,5,0]
 assert [c['number'] for c in values[1]['calls']]==[1,2,3,4,5]


def stats(calls):
 return {'schema_version':'rag-execution-stats-v1','count_basis':'transport-attempts','llm_calls':len(calls),'calls':[{'number':i,'purpose':'assessment','duration_ms':ms} for i,ms in enumerate(calls,1)],'request_duration_ms':8400}

@pytest.mark.parametrize('calls',[[],[1250],[1200,None,3400]])
def test_final_fold_shows_every_time_and_missing_is_not_zero(calls):
 w=views();body={'answer':{'text':'원문 근거의 답변'},'execution_stats':stats(calls)};text=w.render(body)
 assert text.startswith('원문 근거의 답변') and '<details>' in text and 'LLM 호출·처리 시간' in text
 assert '8.40초' in text and 'open' not in text
 for ms in calls:assert ('미확인' if ms is None else f'{ms/1000:.2f}초') in text
 if not calls:assert '호출하지 않았습니다' in text
 assert 'LLM 호출' not in w.render({'answer':{'text':'과거 답변'}})


def test_cached_display_binds_current_stats_and_revision():
 w=views();body={'answer':{'text':'그대로인 답변'},'execution_stats':stats([12])}
 body['workflow_display']=asyncio.run(w.workflow_display_result(body,[event('reading','READ')],request_id='r'))
 assert w._bound_workflow_display(body,'r')
 body['execution_stats']=stats([12,13]);assert w._bound_workflow_display(body,'r') is None
 body['workflow_display']['display_policy_revision']='public-display-v1';assert w._bound_workflow_display(body,'r') is None


def test_actual_api_attaches_only_current_metrics_without_mutating_answer(tmp_path,generation,monkeypatch):
 from fastapi.testclient import TestClient
 app=make_app(tmp_path,generation);original={'answer':{'text':'변경하지 않는 답변','claims':[],'unresolved':[]},'run_id':'fixture'}
 def fake(*args,**kw):
  with em.transport_attempt('memory-assess','one'):pass
  return original
 monkeypatch.setattr(app.state.pipeline,'run',fake)
 with TestClient(app) as client:result=client.post('/v1/rag/ask',json={'question':'모의','use_llm':False}).json()
 assert result['answer']==original['answer'] and 'execution_stats' not in original
 assert result['execution_stats']['llm_calls']==1

@pytest.mark.parametrize('bad',[{'number':1,'purpose':'<script>','duration_ms':9},{'number':True,'purpose':'model','duration_ms':1},{'number':1,'purpose':'model','duration_ms':-1}])
def test_metrics_markup_cannot_leak_arbitrary_fields(bad):
 body={'answer':{'text':'답변'},'execution_stats':{**stats([9]),'calls':[bad],'traceback':'PRIVATE'}}
 assert 'LLM 호출' not in views().render(body) and 'PRIVATE' not in views().render(body)


def test_authorization_rejection_before_dispatch_is_not_a_call(work):
 from semantic_runtime.legal_agent.errors import ContractError
 session=bounded(work,[{'mode':'SEARCH'}])
 transport=session.gateway.transport
 transport.binding={**transport.binding,'trust_zone':'external'}
 def reject(context):raise ContractError('PRIVATE_ACCESS_ERROR')
 transport.validate_authorization=reject
 with em.capture() as metrics:
  with pytest.raises(ContractError):session.structured('모의',{'question':'모의'},SCHEMA,'source-query-plan',10)
  assert metrics.snapshot()['llm_calls']==0
 assert transport.calls==[]


def test_sse_does_not_reenter_earlier_summary_stage(tmp_path):
 events=[];p=ProgressCapture('r',tmp_path,events.append)
 p.publish('decision','검토',basis={'stage':'ASSESS'})
 p.publish('reading','지연 도착',basis={'stage':'READ'})
 assert len(events)==1 and events[0]['basis']['stage']=='answer'
