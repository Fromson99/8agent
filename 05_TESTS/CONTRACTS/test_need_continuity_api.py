from pathlib import Path
import os
import pytest
from conftest import term_glossary


@pytest.mark.parametrize('fault',[None,'need_first','need_twice','open','change_first','change_twice','handoff',
    'rejected_need','rejected_need_first','rejected_need_twice'])
def test_native_need_handoff_repair_limits_saved_reply_and_duplicate(tmp_path,term_glossary,monkeypatch,fault):
    root=Path(__file__).resolve().parents[2]
    # Reuse only the compact-wire fixture decoder and synthetic coverage builder.
    monkeypatch.syspath_prepend(str(root/'06_TOOLS/EXPERIMENTS/adr_1188'))
    monkeypatch.setenv('WORKFLOW_TEST_CODE_ROOT',os.environ.get('NEED_CONTINUITY_CONTRACT_ROOT',os.environ.get('WORKFLOW_TEST_CODE_ROOT',str(root))))
    monkeypatch.setenv('GENOS_AUTO_WARMUP','0')
    monkeypatch.setenv('AD_WORKER_ENABLED','0')
    from need_continuity_fixture import run_api
    result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
    if fault in ('need_twice','change_twice','rejected_need_twice'):
        assert result is None
        return
    response,calls,reviews=result
    stages={r['stage']:r for r in response['assembly']['term_agent']['judgment_view']['stages']}
    receipt=stages['ASSESS']['read_judgment_review']
    declared=[n for n in receipt['prior_needs'] if n.get('origin')=='ANSWER_PROGRESS']
    assert declared and declared[0]['text']=='위임 기준 원문'
    assert receipt['need_continuity']['latest_goals'][0]['status']=='NEEDS_SOURCE'
    assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault in ('need_first','change_first','rejected_need_first') else 1)
    assert not any(p.startswith('memory-compose') for p in calls)
    if fault=='handoff':assert receipt['need_continuity']['stop_reason'].startswith('STOP_UNRESOLVED')
    if fault=='open':
        assert '위임 기준의 추가 확인이 아직 필요하다' in response['answer']['text']
