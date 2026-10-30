from native_fixture import run_api
from conftest import term_glossary

def test_invalid_review_stored_incomplete_no_resend(tmp_path,term_glossary,monkeypatch):
 result,calls,_=run_api(tmp_path,term_glossary,'supported',monkeypatch,review_fault='invalid')
 assert calls.count('memory-final-original-review')==1
 assert result['answer']['provider_receipt']['final_review_status']=='INCOMPLETE'

def test_disabled_has_no_review_call(tmp_path,term_glossary,monkeypatch):
 result,calls,_=run_api(tmp_path,term_glossary,'supported',monkeypatch,review_fault='disabled')
 assert 'memory-final-original-review' not in calls
 assert result['answer']['provider_receipt']['final_review_status']=='SKIPPED'
