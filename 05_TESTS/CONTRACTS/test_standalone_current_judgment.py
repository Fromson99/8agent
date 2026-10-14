"""Actual separate-SSE transport, committed journal judgments and large inventories."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.readable_log import render_detail
from semantic_runtime.request_report import _LiveLog, _tool_summary
from test_rag_key_progress import native, journal, read, evidence, commit
from test_rag_flow_svg import body, workflow

ROOT = Path(__file__).resolve().parents[2]


def test_all_committed_claims_and_selection_reasons_survive_without_private_sources(native):
    repo, projection, events = native
    for i in range(12): read(repo, evidence(suffix=str(i)))
    read(repo, evidence('other', 'private'))
    long_reason = '현재 조건과 원문의 예외를 확인했습니다. ' * 40
    commit(repo, 'SELECT', {'final_ids': ['s'+str(i) for i in range(12)],
        'label_to_source': {'C'+str(i): 's'+str(i) for i in range(12)},
        'decisions': [{'decision': {'choices': [{'id':'C'+str(i), 'reason':long_reason} for i in range(12)]}}]})
    long_claim = '모의 조건에 따라 담당자의 승인이 필요합니다. ' * 40
    claims = [{'source_id':'s'+str(i), 'text':str(i)+' '+long_claim} for i in range(12)]
    commit(repo, 'ASSESS', {'claims': claims + [{'source_id':'sprivate', 'text':'비공개 판단'}],
                           'limitations':['대상자의 신분은 미확인입니다']})
    projection.poll_journal()
    # Public progress is deliberately compact. The detailed, committed journal
    # remains available to the final projection and private request log below.
    assert len(events) <= 5
    assert '비공개' not in json.dumps(events, ensure_ascii=False)
    assert all(e['basis']['detail_mode'] == 'summary' for e in events)
    display = workflow()._ChatProgress({}); display.show_progress=True
    for event in events: asyncio.run(display.progress(event))
    assert len(display.blocks) <= 5
    assert long_claim.strip() not in json.dumps(display.blocks, ensure_ascii=False)
    assert any(long_reason.strip() in row[0] for row in repo.db.execute('SELECT payload_json FROM entity_version'))
    stream = io.StringIO(); live = _LiveLog('r1', stream, repo.path.parent)
    try:
        live.run_id = repo.context.run_id; live.journal_path=repo.path
        live.poll_journal()
        text=stream.getvalue()
        assert all('현재 판단: '+str(i)+' '+long_claim.strip() in text for i in range(12))
        assert '비공개 판단' not in text and '미확인입니다' in text
    finally:
        live.writer.close(); live.close()


def test_native_model_reply_and_rebound_tool_are_meaningful():
    text = render_detail('MODEL RESPONSE / LLM ANSWER', {'phase':'memory-assess', 'status':'SUCCEEDED',
        'reply':{'claims':[{'text':'담당자가 승인 대상입니다'}],
                 'issue_assessments':[{'status':'COVERED','reason':'해당 원문에서 적용 대상을 확인'}],
                 'limitations':['사실 확인 필요']}})
    assert '담당자가 승인 대상' in text and '후속 검증' in text and '표시할 선택 항목 없음' not in text
    summary=_tool_summary({'tool':'case_evidence_rebind','status':'REUSED', 'result':{}},evidence_count=7)
    rebound=render_detail('TOOL RESULT', summary)
    assert '현재 요청에 재결속' in rebound and '7건' in rebound and '결과 수 미기록' not in rebound
    # Unknown counts stay unknown; they are not guessed from the status.
    assert '결과 수 미기록' in render_detail('TOOL RESULT', _tool_summary({'tool':'read','status':'REUSED'}))


def test_candidate_paths_do_not_bury_connected_evidence():
    w=workflow(); raw=body(); view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data'][0]['document_name']='external > financial_team > law > 모의법'
    view['stages'][5]['data']=[{'source_id':'s1','judgment':'모의법에 따라 담당자를 지정합니다'}]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    found=[{'label':'자료 검색', 'kind':'candidate', 'basis':{'kind':'LAW_FULLTEXT_DIRECTORY'},
            'details':['external > financial_team > law > 검색 후보 '+str(i) for i in range(60)]}]
    flow=w._judgment_flow(raw,found); xml=ET.fromstring(flow['svg'])
    entities=[g for g in xml.iter() if 'data-entity' in g.attrib]
    assert len(entities)==3 and flow['metadata']['search_candidate_count']==60
    assert float(xml.attrib['height'])<500
    assert 'external > financial_team' not in ''.join(n.text or '' for n in xml.iter() if n.tag.endswith('text'))
    assert 'external > financial_team > law > 모의법' in ''.join(xml.itertext())
    assert all('검색 후보 '+str(i)+'</li>' in flow['html'] for i in range(60))


def test_original_acquired_during_select_is_connected_to_its_current_claim():
    w=workflow();raw=body();view=raw['assembly']['term_agent']['judgment_view']
    view['stages'][3]['data']=[]
    view['stages'][4]['data']=[{'source_id':'new-scope','document_name':'모의법','coordinate':'제2조',
                               'action':'답변 근거 채택'}]
    view['stages'][5]['data']=[{'source_id':'new-scope','judgment':'추가로 확인한 조문의 현재 판단'}]
    view['content_sha256']=digest({k:v for k,v in view.items() if k!='content_sha256'})
    flow=w._judgment_flow(raw)
    assert flow['metadata']['entity_count']==3 and flow['metadata']['relation_count']==2
    assert '추가로 확인한 조문의 현재 판단' in ''.join(ET.fromstring(flow['svg']).itertext())


def test_separate_raw_sse_keeps_judgment_under_queue_pressure_and_logs_it(monkeypatch):
    spec=importlib.util.spec_from_file_location('separate_sse_judgment',ROOT/'08_DEPLOYMENT/GENOS/stream_app.py')
    app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
    saved=[]; calls=[]
    monkeypatch.setattr(app, 'log_event', lambda logger,name,**fields:saved.append((name,fields)))
    async def execute(data, sink, answer):
        calls.append(data)
        for i in range(300): sink({'kind':'candidate','label':'후보 확인','schema_version':'rag-progress-v1'})
        sink({'kind':'decision','label':'적용 판단','schema_version':'rag-progress-v1',
              'basis':{'kind':'CASE_JUDGMENT_ACCEPTED','stage':'ASSESS','state':'COMPLETED','detail_mode':'judgment'},
              'details':['현재 판단: 모의법에 따라 승인이 필요합니다']})
        return {'status':200,'body':body()}
    async def consume():
        response=await app.stream_response({'request_id':'separate-r1'},execute)
        frames=[]
        async for chunk in response.body_iterator:
            if chunk.startswith('data: '): frames.append(json.loads(chunk[6:]))
        progress=[f['data'] for f in frames if f['event']=='progress']
        assert any('현재 판단:' in json.dumps(v,ensure_ascii=False) for v in progress)
        assert [v['seq'] for v in progress]==list(range(1,len(progress)+1))
        assert frames[-1]['event']=='result' and len(calls)==1 and not app._ACTIVE_REQUESTS
        health=await app.http_health()
        assert health['execution_mode']=='separate-sse-server'
    asyncio.run(consume())
    assert any(name=='agent.current_judgment' and '승인이 필요' in str(fields) for name,fields in saved)
