from copy import deepcopy
from pathlib import Path
import importlib.util, json
import pytest
from conftest import term_glossary
from semantic_runtime.legal_agent import connection_scope as cs

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('completion_wire1342',ROOT/'06_TOOLS/EXPERIMENTS/adr_1332/test_repeat_scope.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
current_wire=prior.current_wire

@pytest.mark.parametrize('fault',['first','twice'])
def test_actual_api_explanation_repair_and_incomplete_publication(tmp_path,term_glossary,monkeypatch,current_wire,fault):
    import test_legal_agent_double_harness as harness
    from need_continuity_fixture import run_api
    from semantic_runtime.legal_agent.bounded_source_session import _Gateway
    from semantic_runtime.legal_agent.unified_publication import validate_saved
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    old=harness.wire;attempts=[];sent=[]
    def inject(value):
        if isinstance(value,dict) and value.get('claims') and 'read_judgment_review' in value:
            attempts.append(deepcopy(value))
            if fault=='twice' or len(attempts)==1:
                value=deepcopy(value);extra=deepcopy(value['claims'][0]);extra['claim_id']='C99'
                value['claims'].append(extra)
        return old(value)
    monkeypatch.setattr(harness,'wire',inject)
    request=_Gateway.request
    def capture(self,*args,**kw):
        result=request(self,*args,**kw);phase=args[1].get('source_stage','')
        if phase.startswith('memory-assess') or '-read-choice' in phase:
            assert cs.FINISH_GUIDANCE in result['messages'][0]['content'];sent.append(phase)
        return result
    monkeypatch.setattr(_Gateway,'request',capture)
    def exercise(api,transport,body,runtime):
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        result=response.json();outcome=result['assembly']['term_agent']['accepted_outcome']
        assert len(attempts)==2
        assert outcome['answer_coverage']==('COVERED' if fault=='first' else 'INSUFFICIENT')
        assert bool(result['answer']['claims']) is (fault=='first')
        repairs=[v for v in transport.views if v.get('source_stage')=='memory-assess-repair']
        assert len(repairs)==1
        choices=repairs[0]['repair_feedback']['decision_repair_choices']
        exact=next(r for r in choices if r['cause']=='CLAIM_WITHOUT_MATCHING_ADOPTION')
        assert exact['claim_id']==exact['claim']['claim_id']
        assert exact['claim_evidence_refs']==exact['claim']['evidence_refs']
        assert all(exact['claim_id'] not in j['claim_refs'] for j in exact['related_judgments'])
        assert '이 확인 업무는 서면 승인 후 시행한다.' in result['answer']['text']
        assert '최종 검토 미완료 판단:' not in result['answer']['text']
        journal=next(runtime.glob('legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        repo=UnifiedRepository(journal)
        try:validate_saved(repo,result)
        finally:repo.close()
        count=len(transport.calls)
        again=api.post('/v1/rag/ask',json=body)
        assert again.status_code==200 and again.json()['answer']==result['answer']
        assert len(transport.calls)==count and len(attempts)==2
        assert 'memory-assess' in sent and 'memory-assess-repair' in sent
        api.app.state.pipeline.store.close()
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,exercise=exercise)
