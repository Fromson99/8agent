from conftest import term_glossary
from native_fixture import run_api

def test_native_rejected_directive_reads_missing_original_and_stores(tmp_path,term_glossary,monkeypatch):
    response,calls,reviews=run_api(tmp_path,term_glossary,'route_recovery',monkeypatch)
    assert response['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
    assert not any(p.startswith('memory-compose') for p in calls)
    assert calls.count('memory-final-original-review')==1
    assert response['answer']['provider_receipt']['final_review_status']=='NO_ISSUES_FOUND'
    assert response['assembly']['term_agent']['final_original_review']['quality_certified'] is False

def test_native_normal_path_unchanged(tmp_path,term_glossary,monkeypatch):
    response,calls,reviews=run_api(tmp_path,term_glossary,'supported',monkeypatch)
    assert response['assembly']['term_agent']['accepted_outcome']['answer_coverage']=='COVERED'
