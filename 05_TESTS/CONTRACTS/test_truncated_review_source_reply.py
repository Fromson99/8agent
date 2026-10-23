"""Typed generation stop must preserve source delivery without a legal judgment."""
from copy import deepcopy
import json, sqlite3
import pytest
from fastapi.testclient import TestClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError, ContractError
from test_main50_request_repair import tree
from test_bounded_delivered_handoff import StopTransport
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT, wire
from conftest import term_glossary

class Truncated(StopTransport):
    def __init__(self, mode):
        super().__init__('repaired'); self.failure_mode=mode
    def send_once(self, *, body, ticket):
        v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v['phase'])
        if phase.startswith('memory-assess'):
            self.phases.append(phase)
            result=wire('{"claims":[{"text":"검증되지 않은 가짜 결론"}],"issue_assessments":[')
            result['body_json']['choices'][0]['finish_reason']='length'
            if self.failure_mode=='adapter':
                exc=ProposalError('incomplete response');exc.response=result;raise exc
            return result
        return super().send_once(body=body,ticket=ticket)

@pytest.mark.parametrize('mode',['adapter','gateway'])
def test_truncated_review_publishes_only_verified_originals_once(tmp_path,tree,mode):
    gen,idx=tree;transport=Truncated(mode);runtime=tmp_path/'runtime'
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'answer_presentation':'grounded-narrative-v1','candidate_navigation':{'mode':'law-first-v1',
        'investigation_control':True,'completion_contract':True,'completion_policy_version':cc.V8,'compact_input':True}}
    def app():
        a=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
            legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=runtime,
            memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
        a.state.pipeline.term_agent.unit_fulltext=idx;return a
    a=app();body={'question':'모의승인규정 제1조 승인 기준은?','session_id':'truncated','request_id':'r1'}
    with TestClient(a) as api:
        r=api.post('/v1/rag/ask',json=body);assert r.status_code==200,r.text
        out=r.json();count=len(transport.phases)
        again=api.post('/v1/rag/ask',json=body)
        assert again.status_code==200 and again.json()['answer']==out['answer']
        assert len(transport.phases)==count
    assert [p for p in transport.phases if p.startswith('memory-assess')]==['memory-assess']
    assert not any(p.startswith('memory-compose') for p in transport.phases)
    assert out['answer']['claims']==[] and '가짜 결론' not in out['answer']['text']
    assert '승인 후 보고한다.' in out['answer']['text'] and '검토' in out['answer']['text']
    meta=out['assembly']['term_agent']
    assert meta['answer_coverage']=='INSUFFICIENT'
    assert meta['accepted_outcome']['disposition']=='LIMITED_ANSWER'
    assert meta['text_integrity']=='VERIFIED_SOURCE_EXCERPTS'
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved,validate_current
    journal=next((runtime/'legal-agent/runs').glob('*/'+out['run_id']+'/journal.sqlite'))
    repo=UnifiedRepository(journal)
    try:
        validate_saved(repo,out)
        events=[(k,json.loads(v)) for k,v in repo.db.execute('select kind,payload_json from event')]
        states=[v for k,v in events if k=='OUTPUT_DECISION_STATE' and v['binding']['owner']=='assessment']
        assert states[-1]['status']=='REJECTED' and not states[-1]['repairable']
        assert any(k=='ASSESSMENT_GENERATION_STOPPED' and v['retry'] is False for k,v in events)
        assert any(k=='ASSESSMENT_SOURCE_EXCERPT_REPLY' for k,v in events)
        budget=repo.budget();deadline=repo.run()['deadline_at']
        changed=deepcopy(out);changed['answer']['text']+='허용된다.'
        with pytest.raises(ContractError):validate_saved(repo,changed)
        with pytest.raises(ContractError):validate_current(repo,out,a.state.pipeline.store,allowed_documents=[])
    finally:repo.close()
    with TestClient(app()) as api:
        r=api.post('/v1/rag/ask',json=body)
        assert r.status_code==200 and r.json()['answer']==out['answer']
        assert len(transport.phases)==count
    repo=UnifiedRepository(journal)
    try:assert repo.budget()==budget and repo.run()['deadline_at']==deadline
    finally:repo.close()
