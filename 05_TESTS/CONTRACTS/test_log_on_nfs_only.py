"""LOG=on writes the per-request .log under the NFS report root (user 2026-11-11).

Actual service.py entry, Oracle-only records (adr_1244 local Oracle fixture, scripted model).
With only LOG=on the root is the earlier place /nfs-root/diamo/8-agent/rag-request-reports
(a temporary folder here), laid out <date>/<team>/legal_agent/<id>.log, next to the same-named
.json report and _qa row the CPU/Oracle report commands read; no .txt, .trace.txt, .llm_raw.jsonl
or agent-raw-v1 file. With LOG off nothing changes.
"""
import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('log_on_nfs_only_base', ROOT/'05_TESTS/CONTRACTS/test_concurrent_chats_oracle.py')
_base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_base)
native_oracle = _base.native_oracle  # noqa: F401  (fixture)
published = _base.published  # noqa: F401  (fixture)
structured_generation = _base.structured_generation  # noqa: F401  (fixture)


def ask_once(native_oracle, tmp_path, monkeypatch, session):
    ask, _, _ = _base.service(native_oracle, tmp_path, monkeypatch)
    out, _ = ask(session, 'req-'+session)
    assert out['status'] == 200, out
    from semantic_runtime import request_report
    deadline = time.monotonic()+30
    while time.monotonic() < deadline and request_report._FINALIZER_QUEUE.unfinished_tasks:
        time.sleep(0.2)
    assert not request_report._FINALIZER_QUEUE.unfinished_tasks


def files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())


def test_log_on_alone_writes_the_log_and_report_in_the_default_root(native_oracle, tmp_path, monkeypatch):
    from semantic_runtime import request_report
    default = tmp_path/'nfs-root'/'diamo'/'8-agent'/'rag-request-reports'
    monkeypatch.setattr(request_report, 'DEFAULT_LOG_ROOT', str(default))
    monkeypatch.setenv('LOG', 'on')
    setenv = monkeypatch.setenv  # the base setup names its own report root; LOG=on alone must not need one
    monkeypatch.setattr(monkeypatch, 'setenv', lambda k, v, *a: None if k == 'GENOS_SHARED_LOG_DIR' else setenv(k, v, *a))
    monkeypatch.delenv('GENOS_SHARED_LOG_DIR', raising=False)
    ask_once(native_oracle, tmp_path, monkeypatch, 's-log-on')
    found = files(default)
    log = [f for f in found if f.endswith('.log')]
    assert len(log) == 1 and len(found) == 3, found
    stem = log[0][:-len('.log')]
    day, team, component, name = log[0].split('/')
    assert sorted(found) == sorted([log[0], stem+'.json', f'{day}/{team}/{component}/_qa/{name[:-4]}.row']), found
    assert len(day) == 10 and day[4] == day[7] == '-' and team == 'unassigned' and component == 'legal_agent'
    text = (default/log[0]).read_text(encoding='utf-8')
    for label in ('RAG INPUT / QUESTION', 'MODEL CALL', 'MODEL RAW RESPONSE', 'MODEL RESPONSE / LLM ANSWER',
                  'SERVICE OUTCOME', 'SERVICE RETURN SCHEDULED', 'FINAL RESPONSE / ANSWER'):
        assert '=== '+label+' ===' in text, label
    assert 'request.started' in text and 'model.attempt.started' in text
    assert 'raw_sidecar_status' not in text


def test_log_off_keeps_the_report_and_qa_row(native_oracle, tmp_path, monkeypatch):
    for name in ('LOG', 'GENOS_LOG', 'GENOS_LIVE_LOG'):
        monkeypatch.delenv(name, raising=False)
    ask_once(native_oracle, tmp_path, monkeypatch, 's-log-off')
    logs = tmp_path/'synthetic-nfs-logs'
    found = [f for f in files(logs) if not f.startswith('agent-raw-v1/')]
    assert sorted(f.rsplit('.', 1)[-1] for f in found) == ['json', 'row'], found
