"""Only native connections/navigation/fulltext; forbid model, evidence and serving work."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import sys
import zipfile
import pytest
from semantic_runtime.contracts import sha
from test_genos_meaning_variants import prepared
from test_genos_optimized_rebuild_r7 import mixed
from test_genos_optimized_rebuild_r6 import historical
from test_genos_optimized_rebuild_r5 import real_checkout

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '06_TOOLS/OFFLINE'))
import genos_reindex_only as index
import genos_reindex_runner as runner
import genos_reindex_logging as logging
import package_genos_reindex_r8 as pack


@pytest.fixture
def selected(prepared, tmp_path):
    context = index.prepared(prepared['parent'].parents[1], 'prepared')
    context['execution_code_pins'] = {}
    manifest = tmp_path / 'code-manifest.json'; manifest.write_text('{"code":"synthetic"}')
    return runner.fork_prepared(context, context['parent'].parents[1], 'index-only', manifest)


def forbid_extra_work(monkeypatch):
    from lawrag.pipeline import glossary_review, reference_resolution, term_serving_bundle
    def forbidden(*a, **k): raise AssertionError('Authoring/model/serving packaging must not run')
    for module, name in ((glossary_review, 'complete'), (reference_resolution, 'advance'),
                         (reference_resolution, 'apply'), (term_serving_bundle, 'prepare_assets')):
        monkeypatch.setattr(module, name, forbidden)


def test_connections_navigation_fulltext_no_models_and_exact_input_preservation(selected, prepared, tmp_path, monkeypatch):
    forbid_extra_work(monkeypatch)
    before = {str(p): sha(p) for p in (prepared['source'], prepared['draft'] / 'dictionary.sqlite', prepared['parent'] / 'plan.json')}
    log = logging.BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        result = index.rebuild(selected, log=log)
        assert result['completed'] and result['model_calls'] == 0 and not result['serving_packaged']
        assert result['document_count'] == 3
        assert not (Path(result['generation_path']) / 'glossary').exists()
        assert Path(result['fulltext_path'], 'fulltext.sqlite').is_file()
        from semantic_runtime.fulltext import FulltextIndex
        navigation_manifest = json.loads((Path(result['generation_path']) / 'navigation/manifest.json').read_text())
        search = FulltextIndex(result['fulltext_path'], navigation_manifest)
        with closing(search.connect()) as db: assert search.rank(db, ['은행'])
        with sqlite3.connect(Path(result['generation_path']) / 'navigation/navigation.sqlite') as db:
            assert db.execute('SELECT count(*) FROM occurrence').fetchone()[0] > 0
            assert db.execute('SELECT count(*) FROM reference').fetchone()[0] > 0
        assert all(sha(p) == expected for p, expected in before.items())
        assert index.rebuild(selected, log=log)['manifest_sha256'] == result['manifest_sha256']
    finally: log.close(0)


def test_fulltext_failure_resume_preserves_and_reuses_completed_navigation(selected, tmp_path, monkeypatch):
    from semantic_runtime import fulltext
    from lawrag.pipeline import term_generation
    forbid_extra_work(monkeypatch)
    original = fulltext.build
    def interrupted(navigation, output, **kwargs):
        Path(output).mkdir(); (Path(output) / 'partial').write_text('retained')
        raise RuntimeError('synthetic fulltext interruption')
    monkeypatch.setattr(fulltext, 'build', interrupted)
    log = logging.BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        with pytest.raises(RuntimeError, match='synthetic fulltext interruption'): index.rebuild(selected, log=log)
        nav = selected['parent'] / 'reindex/baseline/generation/navigation/navigation.sqlite'; before = sha(nav)
        monkeypatch.setattr(fulltext, 'build', original)
        import semantic_runtime.term_index as term_index
        monkeypatch.setattr(term_generation, 'compile_index', lambda *a, **k: (_ for _ in ()).throw(AssertionError('navigation must be reused')))
        # Keep the exact native compiler identity even though the test blocks its invocation.
        term_generation.compile_index.__code__ = term_generation.compile_index.__code__.replace(co_filename=term_index.__file__)
        result = index.rebuild(selected, log=log)
        assert sha(nav) == before and result['completed']
        assert list((selected['parent'] / 'reindex').glob('incomplete-fulltext-*/partial'))
    finally: log.close(0)


def test_only_consumed_knowledge_databases_checked_and_unused_evidence_not_read(tmp_path):
    from lawrag.pipeline import glossary_knowledge as knowledge
    directory = tmp_path / 'bundle'; directory.mkdir()
    for name in ('lookup', 'legal'):
        with sqlite3.connect(directory / (name + '.sqlite')) as db:
            db.execute('CREATE TABLE surface(key,source,node_id,label,kind)')
            db.execute("INSERT INTO surface VALUES('x','source','n','label','kind')")
    rows = [{'path': n + '.sqlite', 'bytes': (directory / (n + '.sqlite')).stat().st_size, 'sha256': sha(directory / (n + '.sqlite'))} for n in ('lookup', 'legal')]
    rows.append({'path': 'evidence/not-present.json', 'bytes': 100, 'sha256': 'unused'})
    (directory / 'manifest.json').write_text(json.dumps({'schema_version': knowledge.VERSION, 'files': rows, 'dictionary_sha256': 'selected', 'counts': {}}))
    original = knowledge.verify
    log = logging.BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        with index.index_knowledge(log):
            knowledge.verify(directory, force=True)
            with closing(knowledge.Knowledge(directory)) as reader:
                assert list(reader.surfaces()) == ['x']
                assert set(reader.dbs) == {'lookup'}
            with sqlite3.connect(directory / 'lookup.sqlite') as db: db.execute("INSERT INTO surface VALUES('new','s','n','l','k')")
            with pytest.raises(ValueError, match='payload hash mismatch'): knowledge.verify(directory, force=True)
        assert knowledge.verify is original
    finally: log.close(0)


def test_event_history_complete_current_state_updates_bounded(tmp_path, monkeypatch):
    calls = []; original = logging.atomic
    def counted(path, value): calls.append(value['seq']); original(path, value)
    monkeypatch.setattr(logging, 'atomic', counted)
    log = logging.BuildLog(tmp_path / 'log', terminal=io.StringIO())
    for i in range(100): log.emit('small-file', 'DONE', number=i)
    log.close(0)
    events = [json.loads(s) for s in (tmp_path / 'log/events.jsonl').read_text().splitlines()]
    assert len(events) == 101 and events[-1]['status'] == 'FINISHED'
    assert len(calls) < 10
    assert json.loads((tmp_path / 'log/current.json').read_text())['status'] == 'FINISHED'


def test_r8_package_and_script_policy():
    script = (pack.OUT / (pack.STEM + '.txt')).read_text()
    assert 'genos_reindex_runner.py' in script and '--shared-root' not in script and '--reference-cases' not in script
    assert script.index('run_stage code-preflight') < script.index('run_stage stop-old')
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z:
        rows = json.loads(z.read('CODE_MANIFEST.json'))['files']
        assert any(r['path'].endswith('genos_reindex_only.py') and r['allow_missing'] for r in rows)
        assert all(__import__('hashlib').sha256(z.read(r['path'])).hexdigest() == r['sha256'] for r in rows)


def test_stop_only_same_checkout_and_prepared_build(tmp_path, monkeypatch):
    import subprocess
    dev = tmp_path / 'DEV'; tool = dev / '06_TOOLS/OFFLINE/genos_optimized_rebuild.py'
    tool.parent.mkdir(parents=True); tool.write_text('import time; time.sleep(60)\n')
    monkeypatch.setenv('LAWRAG_WORKSPACE_ROOT', str(dev))
    processes = [subprocess.Popen([sys.executable, str(tool), 'build', '--prepared-run', run, '--dev', str(dev)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for run in ('selected', 'other')]
    log = logging.BuildLog(tmp_path / 'log', terminal=io.StringIO())
    try:
        import time; time.sleep(.05)
        runner.stop_recorded(tmp_path / 'data', 'selected', log, timeout=3)
        assert processes[0].wait(timeout=2) != 0
        assert processes[1].poll() is None
        assert (tmp_path / 'log' / ('stopped-build-' + str(processes[0].pid) + '.json')).is_file()
    finally:
        for process in processes:
            if process.poll() is None: process.terminate()
            process.wait(timeout=2)
        log.close(0)


def test_r8_helpers_apply_on_mixed_r7_field_baseline(mixed):
    import importlib.util
    payload, dev, _, _, _, _, before = mixed
    with zipfile.ZipFile(pack.OUT / (pack.STEM + '.zip')) as z: z.extractall(payload)
    spec = importlib.util.spec_from_file_location('r8_field_apply', payload / 'APPLY.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.apply(dev)
    assert (dev / '06_TOOLS/OFFLINE/genos_reindex_runner.py').is_file()
    module.dependency().rollback(next((dev / '.genos-pipeline-optimization-backups').iterdir()))
    assert all(sha(dev / name) == expected for name, expected in before.items())
    assert not (dev / '06_TOOLS/OFFLINE/genos_reindex_runner.py').exists()


def test_model_profile_and_review_database_are_not_index_inputs(prepared):
    prepared['profile'].unlink()
    (prepared['parent'] / 'review/review.sqlite').unlink()
    context = index.prepared(prepared['parent'].parents[1], 'prepared')
    assert 'profile' not in context
    assert str(prepared['profile']) not in context['pins']
