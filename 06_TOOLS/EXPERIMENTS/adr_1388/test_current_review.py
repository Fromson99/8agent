import os
from pathlib import Path
import importlib.util
from copy import deepcopy
import json
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent.review_actions import LEGACY_REVIEW_MESSAGE, REVIEW_LABEL
from semantic_runtime import chat_adapter
from need_continuity_fixture import run_api

ROOT = Path(__file__).resolve().parents[3]

spec=importlib.util.spec_from_file_location('scope_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_1326/test_scope_recovery.py')
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)

@pytest.fixture(autouse=True)
def adapted_wire(monkeypatch):
    prior.per_original_wire.__wrapped__(monkeypatch)
    import test_legal_agent_double_harness as harness
    from semantic_runtime.legal_agent import need_continuity
    old=harness.wire
    def wire(value):
        v=need_continuity.scope_claim_model_copy(value)
        r=v.get('read_judgment_review',{})
        rows=r.pop('scope_reviews',None)
        if rows is not None:
            refs={}
            for row in rows:
                for g in row['groups']:refs.setdefault(g['basis_refs'][0],g)
            r['original_reviews']={f'R{i+1}':g for i,g in enumerate(refs.values())}
        for row in r.get('judgments',[]):
            for purpose in (row.get('change_review') or {}).get('purpose_reviews',[]):purpose.pop('claim_refs',None)
        return old(v)
    monkeypatch.setattr(harness,'wire',wire)


@pytest.mark.parametrize('command',[REVIEW_LABEL,LEGACY_REVIEW_MESSAGE])
def test_displayed_command_reuses_failed_goal(tmp_path,term_glossary,monkeypatch,command):
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    def exercise(api,transport,request,runtime):
        from api_fixture_integrated import decode
        from test_agent_loop_fault_recovery import unresolved_assessment
        from test_legal_agent_double_harness import wire
        original=transport.send_once
        def reject(*,body,ticket):
            view=decode(json.loads(body['messages'][1]['content'])['view'])
            if view.get('source_stage','').startswith('memory-assess'):
                transport.calls.append(view['source_stage'])
                transport.views.append(deepcopy(view))
                value=unresolved_assessment(view)
                value['read_judgment_review']['needs']=[]
                return wire(value)
            return original(body=body,ticket=ticket)
        transport.send_once=reject
        first=api.post('/v1/rag/ask',json=request)
        assert first.status_code==200,first.text
        result=first.json()
        assert REVIEW_LABEL in chat_adapter.views()._review_explanation_text(result)
        before=len(transport.calls)
        follow={**request,'question':command,'request_id':'second'}
        r=api.post('/v1/rag/ask',json=follow)
        assert r.status_code==200,r.text
        assert r.json()['question_id']==result['question_id']
        assert r.json()['executed']==['ASSESS','COMPOSE']
        assert r.json()['revision']==result['revision']+1
        assert transport.calls[before:] and all(x.startswith('memory-assess') for x in transport.calls[before:])
        count=len(transport.calls)
        assert api.post('/v1/rag/ask',json=follow).json()['answer']==r.json()['answer']
        assert api.post('/v1/rag/ask',json={**follow,'request_id':'again'}).status_code==409
        assert len(transport.calls)==count
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)


def test_no_offer_or_other_session_never_routes(tmp_path,term_glossary,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1188'))
    def exercise(api,transport,request,runtime):
        first=api.post('/v1/rag/ask',json=request)
        assert first.status_code==200 and first.json()['answer']['claims'],first.text
        count=len(transport.calls)
        for session in [request['session_id'],'another-conversation']:
            r=api.post('/v1/rag/ask',json={**request,'session_id':session,'question':'외규: '+LEGACY_REVIEW_MESSAGE,'request_id':'retry'})
            assert r.status_code==200,r.text
            assert r.json()['answer']['text']=='이 대화의 직전 답변에 다시 실행할 검토가 없습니다.'
        assert len(transport.calls)==count
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)
