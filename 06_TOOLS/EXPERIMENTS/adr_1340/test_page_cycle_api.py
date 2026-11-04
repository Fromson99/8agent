from pathlib import Path
import importlib.util,json
import pytest
from conftest import term_glossary

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('cycle_current_wire',ROOT/'06_TOOLS/EXPERIMENTS/adr_1332/test_repeat_scope.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
current_wire=prior.current_wire


@pytest.mark.parametrize('fault',[None,'scope_twice'])
def test_page_loop_actual_api_assesses_and_reuses_request(tmp_path,term_glossary,monkeypatch,current_wire,fault):
    from cycle_api_fixture import run_api
    from semantic_runtime.legal_agent.journal_storage import connect
    from semantic_runtime.legal_agent.unified_repository import UnifiedRepository
    from semantic_runtime.legal_agent.unified_publication import validate_saved
    def exercise(api,transport,request,runtime):
        response=api.post('/v1/rag/ask',json=request)
        assert response.status_code==200,response.text
        result=response.json()
        assert len(transport.page_choices)==4,transport.calls
        assert len(transport.calls)<20
        assert '이 확인 업무는 서면 승인 후 시행한다.' in result['answer']['text']
        outcome=result['assembly']['term_agent']['accepted_outcome']
        assert outcome['answer_coverage']==('COVERED' if fault is None else 'INSUFFICIENT'),outcome
        assert bool(result['answer']['claims'])==(fault is None)
        assert len([p for p in transport.calls if p.startswith('memory-assess')])==(1 if fault is None else 2)
        journal=next(runtime.glob('legal-agent/runs/*/'+result['run_id']+'/journal.sqlite'))
        with connect(journal) as db:
            events=[(k,json.loads(v)) for k,v in db.execute('SELECT kind,payload_json FROM event')]
        stops=[v for k,v in events if k=='INVESTIGATION_BOUNDED_STOP']
        assert len(stops)==1 and stops[0]['reason']=='READ_CANDIDATE_PAGE_NO_PROGRESS'
        assert stops[0]['budget']['model_reserved']<37
        assert stops[0]['delivered_fallback_sources']>=2
        assert any(k=='READ_CANDIDATE_PAGE_HANDOFF' for k,v in events)
        moves=[v for k,v in events if k=='READ_CANDIDATE_PAGE_SELECTED']
        assert all(not v['originals_acquired'] and not v['judgments_completed'] for v in moves)
        repo=UnifiedRepository(journal)
        try:validate_saved(repo,result)
        finally:repo.close()
        calls=len(transport.calls)
        again=api.post('/v1/rag/ask',json=request)
        assert again.status_code==200 and again.json()['answer']==result['answer']
        assert len(transport.calls)==calls
        api.app.state.pipeline.store.close()
    run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault,exercise=exercise)
