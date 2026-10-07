"""Independent authoring branches, scripted models only; no semantic quality claim."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

from semantic_runtime.contracts import sha
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.reference_resolution_repository import ReferenceResolutionRepository
from semantic_runtime import reference_resolution_protocol as protocol
from lawrag.pipeline import document_release as release, glossary_review, reference_resolution
from test_document_release import source, ReviewProvider

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('meaning_variants', ROOT / '06_TOOLS/OFFLINE/genos_meaning_variants.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.fixture
def prepared(tmp_path, term_glossary, monkeypatch):
    raw = source(tmp_path / 'raw.sqlite', [
        ('doc', '모의규정', ['“영업일”이란 은행이 영업하는 날을 말한다.',
                           '“영업일”이란 은행이 정상 근무하는 날을 말한다.', '관련 규정 제1조에 따른다.']),
        ('external:a', '가상규정A', ['첫 번째 후보 원문']),
        ('external:b', '가상규정B', ['두 번째 후보 원문'])])
    monkeypatch.setattr(release, 'selected_sources', lambda *a: ([raw], {str(raw): sha(raw)}))
    profile = tmp_path / 'profile.json'
    profile.write_text('{"model_binding":{"model":"scripted-no-network","provider":"genos","trust_zone":"internal"}}')
    release.build(tmp_path, 'prepared', term_glossary, stage='prepare', reference_profile=profile)
    return tool.prepared(tmp_path, 'prepared')


@pytest.fixture
def reference_calls(monkeypatch):
    calls = []
    def run(state, profile, *, max_cases, batch_size):
        calls.append((str(state), json.loads(profile.read_text()), batch_size))
        with closing(ReferenceResolutionRepository(state / 'review.sqlite')) as repo:
            for row in repo.cases(('CANDIDATES_READY',)):
                case = repo.case_view(row['case_id'])
                view = repo.save_view([case])
                value = {'cases': [{'case_id': case['case_id'],
                                    'selected_candidate_ids': [case['candidates'][0]['id']],
                                    'evidence_ids': ['E1'], 'abstain_reason': None,
                                    'explanation': '합성 계약 응답, 품질 승인 아님'}]}
                attempt = repo.reserve_attempt(view, {'model': 'scripted-no-network'}, 'L1', 1, 'reference_resolution')
                repo.attempt_sent(attempt)
                repo.finish_attempt(attempt, 'SUCCEEDED', {'body_json': value}, {'model': 'scripted-no-network'})
                repo.store_observations(view['view_id'], protocol.validate_batch(value, [case]))
        return reference_resolution.auto_approve(state)
    monkeypatch.setattr(reference_resolution, 'run', run)
    return calls


def frozen(context):
    return {p: sha(p) for p in (context['source'], context['draft'] / 'dictionary.sqlite',
                               context['parent'] / 'plan.json', context['parent'] / 'sources/selection.json')}


def test_off_and_on_have_separate_links_refs_search_and_no_activation(prepared, reference_calls, tmp_path):
    original = frozen(prepared)
    review = prepared['parent'] / 'review/review.sqlite'
    review_before = sha(review)
    off = tool.build_variant(prepared, 'off')
    assert sha(review) == review_before
    assert off['meaning_review_status'] == 'SKIPPED' and off['reference_llm']
    assert off['reference_model_attempts'] == {'SUCCEEDED': 1}
    assert reference_calls and reference_calls[0][2] == 8
    with pytest.raises((ValueError, FileNotFoundError)):
        tool.build_variant(prepared, 'on')
    provider = ReviewProvider()
    result = tool.review_worker(prepared, batch=1, provider=provider)
    assert result['completed'] and result['review_status'] == 'PARTIAL'
    on = tool.build_variant(prepared, 'on')
    assert on['meaning_review_status'] == 'PARTIAL'
    assert len(reference_calls) == 2
    assert off['generation_path'] != on['generation_path']
    for receipt in (off, on):
        assert not receipt['activated'] and not receipt['quality_certified']
        output = Path(receipt['release_path'])
        assert (output / 'baseline/links/links.sqlite').is_file()
        with closing(Store(Path(receipt['generation_path']))) as store:
            index = TermIndex(Path(receipt['generation_path']) / 'navigation', store)
            tools = index.tools(['doc'])
            try:
                assert tools.search_labels(['영업일'], ['doc'])
            finally:
                tools.db.close()
        assert tool.verify_variant(output)['completed']
    assert all(sha(p) == pin for p, pin in original.items())
    assert not (tmp_path / 'generations/CURRENT.json').exists()
    assert tool.build_variant(prepared, 'off') == off
    assert len(reference_calls) == 2


def test_worker_recovers_interrupted_keeps_complete_failed_and_batches(prepared, capsys):
    parent = prepared['parent']
    provider = ReviewProvider()
    glossary_review.run(parent / 'review', max_jobs=1, provider=provider)
    with sqlite3.connect(parent / 'review/review.sqlite') as db:
        pending = [r[0] for r in db.execute("SELECT id FROM job WHERE status='pending' ORDER BY id")]
        assert len(pending) >= 2
        db.execute("UPDATE job SET status='failed',error='synthetic existing error' WHERE id=?", (pending[0],))
        db.execute("UPDATE job SET status='running' WHERE id=?", (pending[1],))
        db.execute("INSERT INTO attempt(job_id,status) VALUES (?,'running')", (pending[1],))
    before = glossary_review.inspect(parent / 'review')
    original = frozen(prepared)
    calls_before = provider.calls
    result = tool.review_worker(prepared, batch=1, provider=provider)
    assert result['review_status'] == 'PARTIAL'
    assert provider.calls - calls_before == before['jobs'].get('pending', 0) + 1
    with sqlite3.connect(parent / 'review/review.sqlite') as db:
        assert db.execute("SELECT count(*) FROM attempt WHERE status='interrupted'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM job WHERE status='failed'").fetchone()[0] == 1
    calls_before = provider.calls
    assert tool.review_worker(prepared, provider=provider)['cached']
    assert provider.calls == calls_before
    assert all(sha(p) == pin for p, pin in original.items())
    assert 'ETA=' in capsys.readouterr().out


@pytest.mark.parametrize('bad', ['schema', 'transport'])
def test_errors_visible_and_preserved_not_retried_forever(prepared, capsys, bad):
    class BadProvider(ReviewProvider):
        def call(self, *a):
            if bad == 'transport':
                raise RuntimeError('synthetic transport problem details')
            value, receipt = super().call(*a)
            value['job_id'] = 'invented'
            return value, receipt
    result = tool.review_worker(prepared, batch=1, provider=BadProvider())
    assert result['completed'] and result['review_status'] == 'PARTIAL'
    status = glossary_review.inspect(prepared['parent'] / 'review')
    assert status['jobs']['failed'] == status['total_jobs']
    captured = capsys.readouterr()
    assert 'Traceback' in captured.err
    assert 'original traceback follows' in captured.out


def test_worker_cannot_overlap_original_driver(prepared):
    with tool.locked(prepared['parent'] / '.lock'):
        with pytest.raises(BlockingIOError):
            tool.review_worker(prepared, provider=ReviewProvider())
    assert not (prepared['parent'] / 'review/completion.json').exists()


def test_consecutive_failure_interrupt_does_not_drain_queue_and_can_resume(prepared, monkeypatch):
    monkeypatch.setattr(tool, 'FAILURE_STREAK_LIMIT', 2)
    class Down(ReviewProvider):
        def call(self, *a): raise RuntimeError('scripted outage')
    with pytest.raises(KeyboardInterrupt, match='consecutive failures'):
        tool.review_worker(prepared, provider=Down())
    state = prepared['parent'] / 'review'
    counts = glossary_review.inspect(state)['jobs']
    assert counts['failed'] == 2
    assert counts.get('pending', 0) + counts.get('running', 0) > 0
    assert not (state / 'completion.json').exists()
    result = tool.review_worker(prepared, provider=ReviewProvider())
    assert result['completed'] and result['review_status'] == 'PARTIAL'
    assert glossary_review.inspect(state)['jobs']['failed'] == 2


def test_on_consumes_validated_proposals_but_off_does_not(prepared, reference_calls):
    class SameProvider(ReviewProvider):
        def call(self, role, task, data, schema):
            value, receipt = super().call(role, task, data, schema)
            evidence = list(dict.fromkeys(data['left_sense']['evidence_ids'] + data['right_sense']['evidence_ids']))
            value['identity'] = {'decision': 'SAME', 'evidence_ids': evidence}
            value['relation_assessment'] = 'NOT_ESTABLISHED'
            return value, receipt
    off = tool.build_variant(prepared, 'off')
    tool.review_worker(prepared, provider=SameProvider())
    on = tool.build_variant(prepared, 'on')
    edges = {}
    for mode, receipt in [('off', off), ('on', on)]:
        with sqlite3.connect(Path(receipt['generation_path']) / 'navigation/navigation.sqlite') as db:
            edges[mode] = [json.loads(r[0]) for r in db.execute('SELECT json FROM edge')]
    assert not any(e.get('status') == 'MODEL_REVIEWED_PROPOSAL' for e in edges['off'])
    assert any(e.get('status') == 'MODEL_REVIEWED_PROPOSAL' and e['code'] == 'SAME'
               and e['evidence'] and not e['canonical_approval'] for e in edges['on'])


def test_publish_explicit_selections_and_tamper(prepared, reference_calls, tmp_path):
    tool.build_variant(prepared, 'off')
    tool.review_worker(prepared, provider=ReviewProvider())
    tool.build_variant(prepared, 'on')
    shared = tmp_path / 'shared'
    shared.mkdir()
    for mode in ('off', 'on'):
        output = prepared['parent'] / 'meaning-variants' / mode
        receipt = tool.publish(output, shared)
        assert not receipt['activated']
        assert tool.publish(output, shared) == receipt
        selected = json.loads((Path(receipt['path']) / 'rag-selection.json').read_text())
        assert selected['GENOS_GENERATION'] == str(shared / ('prepared-meaning-' + mode) / 'generation')
        assert selected['reference_llm'] and not selected['activated']
    manifest = shared / 'prepared-meaning-off/generation/manifest.json'
    manifest.write_text(manifest.read_text() + ' ')
    with pytest.raises(ValueError, match='differs'):
        tool.publish(prepared['parent'] / 'meaning-variants/off', shared)
    assert not (shared / 'CURRENT.json').exists()


def test_reference_no_progress_stops_with_original_status(prepared, monkeypatch):
    def stalled(*args, **kwargs):
        assert kwargs['execute'] is True
        return {'completed': False, 'cases': {'MODEL_FAILED': 1}}
    monkeypatch.setattr(reference_resolution, 'advance', stalled)
    with pytest.raises(ValueError, match='blocked'):
        tool.build_variant(prepared, 'off')
    assert not (prepared['parent'] / 'meaning-variants/off/release.json').exists()


def test_prepared_input_or_tool_drift_is_not_silently_rebound(prepared, reference_calls):
    tool.build_variant(prepared, 'off')
    profile = prepared['profile']
    profile.write_text(profile.read_text() + ' ')
    with pytest.raises(ValueError, match='changed'):
        tool.verify_variant(prepared['parent'] / 'meaning-variants/off')
    with pytest.raises(ValueError, match='profile'):
        tool.prepared(prepared['parent'].parents[1], 'prepared')


def test_field_profile_cannot_silently_route_internal_documents_to_external_model(prepared):
    profile = prepared['profile']
    profile.write_text('{"model_binding":{"provider":"openrouter","trust_zone":"external"}}')
    plan_path = prepared['parent'] / 'plan.json'
    plan = json.loads(plan_path.read_text())
    plan['reference_model']['sha256'] = sha(profile)
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='internal GENOS'):
        tool.prepared(prepared['parent'].parents[1], 'prepared')


def test_handoff_embeds_exact_tool_and_uses_field_python():
    path = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R1_UTF8.txt'
    text = path.read_text()
    embedded = text.split("<<'GENOS_VARIANTS_PY'\n", 1)[1].rsplit('\nGENOS_VARIANTS_PY', 1)[0]
    assert embedded == (ROOT / '06_TOOLS/OFFLINE/genos_meaning_variants.py').read_text()
    compile(embedded, str(path), 'exec')
    assert 'python3 -u -' in text and '.venv/bin/python' not in text
    assert 'nohup' in text and 'flock -n 8' in text
    assert 'GENOS_VARIANTS_TOOL_PATH' in text
    subprocess.run(['bash', '-n', str(path)], check=True)


@pytest.mark.parametrize('filename', ['GENOS_MEANING_VARIANTS_R1_UTF8.txt','GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'])
def test_background_launcher_survives_parent_exit_locks_duplicates_and_stops_own_pid(tmp_path,filename):
    """Exercise nohup/PID/lock behavior with a dummy review process, no pipeline/model."""
    binary = tmp_path / 'bin'
    binary.mkdir()
    fake = binary / 'python3'
    # Runtime fixture: only the review action is replaced by an interruptible sleeper.
    fake.write_text('#!/usr/bin/env bash\n'
                    'if [[ "${1:-}" == -u && "${2:-}" == - && "${3:-}" == review ]]; then\n'
                    f'  exec {sys.executable} -u -c '\
                    "'import signal,time; signal.signal(signal.SIGINT,signal.default_int_handler); "
                    "print(\"SCRIPTED REVIEW START\",flush=True); time.sleep(120)'\n"
                    'fi\n'
                    f'exec {sys.executable} "$@"\n')
    fake.chmod(0o700)
    path = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4' / filename
    environment = {**os.environ, 'PATH': str(binary) + ':' + os.environ['PATH'],
                   'GENOS_CODE_ROOT': str(ROOT), 'GENOS_DATA_ROOT': str(tmp_path / 'data'),
                   'GENOS_VARIANTS_RUN_ID': 'scripted-background'}
    metadata = tmp_path / 'data/LOGS/scripted-background/meaning-variants/worker.json'
    pid = None
    try:
        launched = subprocess.run(['bash', str(path), 'review-background'], env=environment,
                                  text=True, capture_output=True, timeout=8)
        assert launched.returncode == 0, launched.stdout + launched.stderr
        record = json.loads(metadata.read_text()); pid = record['pid']
        deadline = time.monotonic() + 5
        while 'SCRIPTED REVIEW START' not in Path(record['log']).read_text() and time.monotonic() < deadline:
            time.sleep(.05)
        assert 'SCRIPTED REVIEW START' in Path(record['log']).read_text()
        duplicate = subprocess.run(['bash', str(path), 'review-background'], env=environment,
                                   text=True, capture_output=True, timeout=5)
        assert duplicate.returncode == 1 and 'already holds' in duplicate.stdout
        assert json.loads(metadata.read_text()) == record
        stopped = subprocess.run(['bash', str(path), 'stop-review'], env=environment,
                                 text=True, capture_output=True, timeout=5)
        assert stopped.returncode == 0 and 'Sent interrupt only' in stopped.stdout
        deadline = time.monotonic() + 5
        while 'KeyboardInterrupt' not in Path(record['log']).read_text() and time.monotonic() < deadline:
            time.sleep(.05)
        assert 'KeyboardInterrupt' in Path(record['log']).read_text()
        pid = None
        if 'R2_BULK' in filename:
            resumed = subprocess.run(['bash',str(path),'review-background'],env=environment,
                                     text=True,capture_output=True,timeout=8)
            assert resumed.returncode == 0, resumed.stdout+resumed.stderr
            newer = json.loads(metadata.read_text()); pid = newer['pid']
            assert newer['log'] != record['log']
            assert Path(record['log']+'.pid.json').is_file()
            deadline=time.monotonic()+5
            while 'SCRIPTED REVIEW START' not in Path(newer['log']).read_text() and time.monotonic()<deadline:
                time.sleep(.05)
            stopped=subprocess.run(['bash',str(path),'stop-review'],env=environment,text=True,capture_output=True,timeout=5)
            assert stopped.returncode==0 and 'Sent interrupt only' in stopped.stdout
            deadline=time.monotonic()+5
            while 'KeyboardInterrupt' not in Path(newer['log']).read_text() and time.monotonic()<deadline:
                time.sleep(.05)
            assert 'KeyboardInterrupt' in Path(newer['log']).read_text()
            pid=None
    finally:
        if pid and Path('/proc', str(pid)).exists():
            os.kill(pid, signal.SIGINT)
