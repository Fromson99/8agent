from pathlib import Path
import pytest
from conftest import term_glossary
@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice','need_first','need_twice','open'])
def test_native_api_wire_repair_receipt_and_duplicate(tmp_path,term_glossary,monkeypatch,fault):
    R=Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(R/'06_TOOLS/EXPERIMENTS/adr_1188'))
    from general_scope_native_fixture import run_api
    result=run_api(tmp_path,term_glossary,'goal_control',monkeypatch,coverage_fault=fault)
    if fault in ('scope_twice','need_twice'):
        assert result is None;return
    response,calls,reviews=result
    stages={r['stage']:r for r in response['assembly']['term_agent']['judgment_view']['stages']}
    receipt=stages['ASSESS']['read_judgment_review']
    assert receipt['need_continuity']['version']=='declared-need-continuity-v2'
    assert receipt['need_continuity']['scope_reviews']==receipt['review']['scope_reviews']
    assert len([p for p in calls if p.startswith('memory-assess')])==(2 if fault in ('scope_first','need_first') else 1)
