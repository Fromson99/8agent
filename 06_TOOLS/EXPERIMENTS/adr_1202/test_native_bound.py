from conftest import term_glossary
from native_fixture import run_api
import pytest

@pytest.mark.parametrize('fault',[None,'change_first','change_twice','gap_link'])
def test_native_bundle_dispatch_final_change_repair_and_reuse(tmp_path,term_glossary,monkeypatch,fault):
    result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
    if fault!='change_twice':
        response,calls,reviews=result
        assert response['assembly']['term_agent']['accepted_outcome']['answer_coverage']==('PARTIAL' if fault=='gap_link' else 'COVERED')
        assert not any(p.startswith('memory-compose') for p in calls)
