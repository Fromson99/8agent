"""Real current API + SSE transport, with a tiny corpus and scripted responses."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from semantic_runtime import observability as obs
from semantic_runtime.chat_adapter import views
from semantic_runtime.legal_agent.answer_stream import capture as answer_capture
from semantic_runtime.progress import capture
from semantic_runtime.request_report import live_log, _journal

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('WORKFLOW_TEST_CODE_ROOT',str(ROOT))
spec=importlib.util.spec_from_file_location('workflow_progress_api_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_0844/test_sources.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
tree=fixture.tree


def application(tmp_path,tree):
    from lawrag.pipeline.search_selection import plan,activate
    activate(plan(tree[0],latest=True))
    app,t=fixture.app_for(tmp_path,tree)
    from test_legal_agent_double_harness import wire
    send=t.send_once
    def current(*,body,ticket):
        from semantic_runtime.legal_agent.navigation_input import expand_cards
        view=expand_cards(json.loads(body['messages'][1]['content'])['view'])
        phase=view.get('source_stage','')
        if '-read-choice' in phase:
            t.views.append((phase,view))
            if view['sources']:
                return wire({'choice':'FINISH','basis_refs':[s['id'] for s in view['sources']],
                             'issue_refs':[i['id'] for i in view['issues']], 'evidence_sufficient':True,'reason':'모의 원문 확인'})
            return wire({'choice':'READ','selections':[{'target':view['read_candidates'][0]['target'],
                        'issue_id':view['issues'][0]['id'],'missing_need':'원문 확인','relation':'DIRECT','source_ref':None}]})
        return send(body=body,ticket=ticket)
    t.send_once=current
    return app,t


@pytest.mark.parametrize('route',['/v1/rag/ask','/v1/workflows/run'])
def test_current_api_progress_logs_stream_final_and_duplicate(tmp_path,tree,route,monkeypatch):
    app,t=application(tmp_path,tree);runtime=tmp_path/'runtime'
    events=[];deltas=[];body=fixture.BODY
    obs.configure();monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','final-cards')
    with TestClient(app) as client, live_log(tmp_path/'logs',body['request_id'],runtime) as (path,handler):
        with capture(body['request_id'],runtime,events.append), answer_capture(body['request_id'],deltas.append):
            out=client.post(route,json=body)
        assert out.status_code==200,out.text
        value=out.json();assert value['report']['rows'],value
        assert value['evidence_refs'] and value['usage']['model_reserved']>0
        handler.writer.drain(2);handler.poll_journal()
        text=path.read_text()
        assert 'workflow.stage.changed' in text and 'MODEL RESPONSE / LLM ANSWER' in text
        assert 'WORKFLOW CHECKPOINT' in text
        assert ''.join(e['text'] for e in deltas)==views()._public_answer_text(value)
        assert len(deltas)>3
        public=json.dumps(events,ensure_ascii=False)
        assert '내규 원문' in public and '외규 원문' in public
        assert '모의내규' in public and '모의승인규정' in public
        call_count=len(t.views)
        again=client.post(route,json=body)
        assert again.status_code==200 and again.json()['answer']==value['answer'] and len(t.views)==call_count
    report=_journal(runtime,value['run_id'])
    assert len(report['children'])==2
    assert all(child['journal']['status']=='FOUND' for child in report['children'])


def test_sse_result_follows_visible_parent_progress_and_answer_chunks(tmp_path,tree,monkeypatch):
    import asyncio,httpx
    app,t=application(tmp_path,tree)
    monkeypatch.setenv('GENOS_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','final-cards')
    sys.path.insert(0,str(ROOT/'08_DEPLOYMENT/GENOS'))
    import main_workflow
    async def invoke(config,data):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
            with obs.context(request_id=data['request_id']):
                out=await client.post('/v1/workflows/run',json={k:v for k,v in data.items() if k!='API_TYPE'})
        return {'status':out.status_code,'body':out.json()}
    monkeypatch.setattr(main_workflow.backend,'service',invoke)
    response=TestClient(main_workflow.app).post('/stream',json={'API_TYPE':'LEGAL_AGENT',**fixture.BODY})
    assert response.status_code==200
    frames=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    kinds=[f['event'] for f in frames]
    assert kinds[-1]=='result' and 'progress' in kinds and 'answer_delta' in kinds
    assert kinds.index('progress')<kinds.index('answer_delta')<kinds.index('result')
    result=frames[-1]['data']['body'];display=result['workflow_display']
    assert '모의내규' in json.dumps(display['agentFlowExecutedData'],ensure_ascii=False)
    assert display['text'].count('| 확인 내용 | 내규 | 외규 | 해석 |\n|---|---|---|---|')==1
    assert ''.join(f['data']['text'] for f in frames if f['event']=='answer_delta')==views()._public_answer_text(result)


def test_resume_new_request_has_progress_without_budget_reset_or_stale_answer(tmp_path,tree,monkeypatch):
    app,t=application(tmp_path,tree);runtime=tmp_path/'runtime'
    obs.configure();monkeypatch.setenv('GENOS_RAG_PROGRESS_UI','final-cards')
    with TestClient(app) as client:
        initial=client.post('/v1/workflows/run',json=fixture.BODY).json()
        count=len(t.views);events=[];deltas=[]
        body={'run_id':initial['run_id'],'session_id':fixture.BODY['session_id'],
              'expected_revision':initial['revision']}
        with obs.context(request_id='resume-delivery'), capture('resume-delivery',runtime,events.append), answer_capture('resume-delivery',deltas.append):
            resumed=client.post('/v1/workflows/resume',json=body)
        assert resumed.status_code==200,resumed.text
        assert resumed.json()['usage']==initial['usage'] and len(t.views)==count
        assert ''.join(e['text'] for e in deltas)==views()._public_answer_text(initial)
        assert all(e['request_id']=='resume-delivery' and e['run_id']==initial['run_id'] for e in events)
        assert '모의내규' in json.dumps(events,ensure_ascii=False)
        deltas.clear()
        with answer_capture('stale-delivery',deltas.append):
            stale=client.post('/v1/workflows/resume',json={**body,'expected_revision':0})
        assert stale.status_code==409 and deltas==[] and len(t.views)==count
