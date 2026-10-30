import json,sqlite3

def test_accepted_agent_judgments_export_to_work(tmp_path,term_glossary,monkeypatch):
    from test_native_integrated import test_read_judgment_api_retains_decisions_and_reuses_request
    monkeypatch.setenv('GENOS_ONTOLOGY_CAPTURE_ENABLED','on')
    test_read_judgment_api_retains_decisions_and_reuses_request(tmp_path,term_glossary,'normal',monkeypatch)
    captured=[];failed=[]
    for path in tmp_path.rglob('*.sqlite'):
        with sqlite3.connect(path) as db:
            if 'payload_json' not in [r[1] for r in db.execute('PRAGMA table_info(event)')]:continue
            captured.extend(json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_INPUT'"))
            failed.extend(json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='ONTOLOGY_WORK_CAPTURE_UNAVAILABLE'"))
    assert captured,failed
    assert all(r['input']['judgments'] and r['input']['originals'] for r in captured)
    assert all(not r['automatic_approval'] for r in captured)
    assert not failed,failed
