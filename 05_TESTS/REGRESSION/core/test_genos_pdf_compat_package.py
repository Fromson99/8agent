"""Onsite baseline compatibility; synthetic input, no network or model calls."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
import lawrag.pipeline as pipeline

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / '09_ARTIFACTS/HANDOFF/GENOS/genos-internal-pdf-input-20260915-v2'
BASE = BUNDLE.parent / 'genos-four-stage-20260910.zip'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def install(tmp_path):
    bundle = tmp_path / 'bundle'
    shutil.copytree(BUNDLE, bundle)
    root = tmp_path / 'DEV'
    with zipfile.ZipFile(BASE) as archive:
        archive.extractall(root)
    installer = module('pdf_installer', bundle / 'install.py')
    return root, bundle, installer


def states(root, installer):
    return {n: (root / n).read_bytes() for n in installer.FILES}


def test_preview_apply_idempotence_rollback(install):
    root, bundle, installer = install
    old = states(root, installer)
    installer.run(root, bundle)
    assert states(root, installer) == old
    installer.run(root, bundle, apply=True)
    new = states(root, installer)
    assert all(new[n] != old[n] for n in old)
    installer.run(root, bundle, apply=True)
    backups = list((bundle / 'backups').iterdir())
    assert len(backups) == 1
    installer.run(root, bundle, rollback=backups[0])
    assert states(root, installer) == old


@pytest.mark.parametrize('problem', ['unknown_code', 'bad_payload', 'symlink'])
def test_preflight_rejects_without_partial_write(install, problem):
    root, bundle, installer = install
    name = installer.FILES[-1]
    path = (bundle / 'payload' if problem == 'bad_payload' else root) / name
    if problem == 'symlink':
        target = path.with_suffix('.original')
        path.rename(target)
        path.symlink_to(target)
    else:
        path.write_bytes(path.read_bytes() + b'\n# different\n')
    old = states(root, installer)
    with pytest.raises(ValueError):
        installer.run(root, bundle, apply=True)
    assert states(root, installer) == old
    assert not (bundle / 'backups').exists()


def test_write_failure_restores_before_state(install, monkeypatch):
    root, bundle, installer = install
    old = states(root, installer)
    original = installer.replace
    calls = []
    def fail_second(*args):
        calls.append(args[0])
        if len(calls) == 2:
            raise OSError('synthetic disk failure')
        return original(*args)
    monkeypatch.setattr(installer, 'replace', fail_second)
    with pytest.raises(OSError):
        installer.run(root, bundle, apply=True)
    assert states(root, installer) == old


def test_rollback_rejects_later_edits(install):
    root, bundle, installer = install
    installer.run(root, bundle, apply=True)
    path = root / installer.FILES[-1]
    path.write_bytes(path.read_bytes() + b'\n# later work\n')
    before = states(root, installer)
    with pytest.raises(ValueError):
        installer.run(root, bundle, rollback=next((bundle / 'backups').iterdir()))
    assert states(root, installer) == before


def test_diff_applies_to_exact_baseline_and_reverses(install):
    root, bundle, installer = install
    old = states(root, installer)
    for args in (['--check'], [], ['-R', '--check'], ['-R']):
        subprocess.run(['git', 'apply', *args, str(bundle / 'PATCH.diff')], cwd=root, check=True)
        if args == []:
            assert all((root / n).read_bytes() == (bundle / 'payload' / n).read_bytes() for n in old)
    assert states(root, installer) == old


@pytest.fixture
def selected(monkeypatch):
    build = module('lawrag.pipeline.compat_build', BUNDLE / 'payload/02_BACKEND/lawrag/pipeline/genos_build.py')
    monkeypatch.setattr(pipeline, 'genos_build', build, raising=False)
    monkeypatch.setitem(sys.modules, 'lawrag.pipeline.genos_build', build)
    corpus = module('lawrag.pipeline.compat_corpus', BUNDLE / 'payload/02_BACKEND/lawrag/pipeline/genos_corpus.py')
    monkeypatch.setattr(pipeline, 'genos_corpus', corpus, raising=False)
    monkeypatch.setitem(sys.modules, 'lawrag.pipeline.genos_corpus', corpus)
    cli = module('compat_cli', BUNDLE / 'payload/06_TOOLS/COMMANDS/genos_data_stages.py')
    with zipfile.ZipFile(BASE) as archive:
        stages = type(sys)('lawrag.pipeline.compat_stages')
        stages.__file__ = str(ROOT / '02_BACKEND/lawrag/pipeline/genos_stages.py')
        stages.__package__ = 'lawrag.pipeline'
        exec(compile(archive.read('02_BACKEND/lawrag/pipeline/genos_stages.py'), stages.__file__, 'exec'), stages.__dict__)
    monkeypatch.setattr(pipeline, 'genos_stages', stages, raising=False)
    monkeypatch.setitem(sys.modules, 'lawrag.pipeline.genos_stages', stages)
    return corpus, build, cli, stages


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_pdf_only_without_raw(selected, tmp_path):
    corpus, build, _, _ = selected
    pdf = put(tmp_path / 'PDF/internal/team/rule.PDF', 'synthetic pdf inventory')
    put(pdf.parent / 'original.docx', 'synthetic original')
    plan, report = corpus.collect(tmp_path / 'RAW', internal_pdf_root=pdf.parent.parent, emit=lambda s: None)
    assert report['ok'] and len(plan['files']) == 1
    assert plan['files'][0]['path'] == str(pdf)
    assert plan['files'][0]['input_collection'] == 'PDF/internal'
    assert plan['input_roots']['internal'] == str(pdf.parent.parent)
    assert not (tmp_path / 'RAW').exists()


@pytest.mark.parametrize('problem', ['missing', 'symlink', 'empty_pdf'])
def test_invalid_pdf_no_raw_fallback(selected, tmp_path, problem):
    corpus, _, _, _ = selected
    raw, pdf = tmp_path / 'RAW', tmp_path / 'PDF/internal'
    put(raw / 'internal/old.pdf', 'synthetic old pdf')
    if problem == 'symlink':
        pdf.parent.mkdir()
        pdf.symlink_to(raw / 'internal')
    elif problem == 'empty_pdf':
        put(pdf / 'bad.pdf', '')
    plan, report = corpus.collect(raw, internal_pdf_root=pdf, emit=lambda s: None)
    assert not report['ok'] and report['errors'] and not plan['files']


def test_external_manifest_integrity_preserved(selected, tmp_path):
    corpus, build, _, _ = selected
    raw, pdf = tmp_path / 'RAW', tmp_path / 'PDF/internal'
    put(pdf / 'one.pdf', 'synthetic internal')
    ext = put(raw / 'law/one.xml', '<법령>synthetic external</법령>')
    kwargs = dict(internal_pdf_root=pdf, emit=lambda s: None)
    assert not corpus.collect(raw, **kwargs)[1]['ok']
    manifest = put(raw / 'law/manifest.json', json.dumps({'items': [{'body_file': 'one.xml', 'body_sha256': build.sha(ext)}]}))
    plan, report = corpus.collect(raw, **kwargs)
    assert report['ok'] and len(plan['files']) == 2
    ext.write_text('<법령>changed</법령>')
    assert not corpus.collect(raw, **kwargs)[1]['ok']


def test_cli_check_only_wiring_and_error_exit(selected, tmp_path, monkeypatch):
    _, _, cli, stages = selected
    monkeypatch.setattr(stages, 'offline_data_root', lambda root: tmp_path)
    monkeypatch.setattr(stages, 'execute', lambda *a, **k: pytest.fail('execution during input check'))
    assert cli.main(['--run-id', 'compat', '--check-only']) == 2
    put(tmp_path / 'PDF/internal/one.pdf', 'synthetic inventory')
    assert cli.main(['--run-id', 'compat', '--check-only']) == 0


def test_excluded_internal_not_inspected(selected, tmp_path, monkeypatch):
    corpus, _, _, _ = selected
    pdf = tmp_path / 'protected'
    original = Path.is_symlink
    def guard(path):
        assert path != pdf
        return original(path)
    monkeypatch.setattr(Path, 'is_symlink', guard)
    plan, report = corpus.collect(tmp_path / 'RAW', internal_pdf_root=pdf, exclude_internal=True, emit=lambda s: None)
    assert not report['errors'] and not plan['files']
    assert plan['input_roots']['internal'] is None


def test_structure_stage_metadata_cache_and_no_downstream(selected, tmp_path, monkeypatch, capsys):
    from lawrag.core import ingest
    corpus, build, cli, stages = selected
    source = put(tmp_path / 'PDF/internal/one.pdf', 'synthetic parser input')
    row = corpus.collect(tmp_path / 'RAW', internal_pdf_root=source.parent, emit=lambda s: None)[0]['files'][0]
    calls = []
    def fake_ingest(raw, filename, **kw):
        assert raw == source.read_bytes()
        calls.append(filename)
        folder = kw['store'] / row['document_id']
        meta = {'passed': True, 'used_llm': False}
        build.atomic(folder / 'meta.json', meta)
        build.atomic(folder / 'result.json', {'blocks': [{'idx': 0, 'text': 'synthetic text'}], 'nodes': []})
        return {'doc_id': row['document_id'], 'meta': meta}
    def fake_source_jobs(folder, plan):
        # The immutable source store adapter is outside this input-only patch.
        path = folder / 'authoring-source.sqlite'
        path.write_bytes(b'synthetic source store')
        build.atomic(folder / 'source.json', {'sha256': build.sha(path)})
    monkeypatch.setattr(ingest, 'ingest', fake_ingest)
    monkeypatch.setattr(build, 'source_jobs', fake_source_jobs)
    monkeypatch.setattr(stages, 'offline_data_root', lambda root: tmp_path)
    monkeypatch.setattr(stages, 'parser_identity', lambda root: {'synthetic_adapter': 'v1'})
    monkeypatch.setattr(stages, 'prepare_provider', lambda *a: pytest.fail('downstream provider called'))
    args = ['--run-id', 'structure-compat', '--stage', 'structure', '--execute']
    assert cli.main(args) == 0, capsys.readouterr()
    assert len(calls) == 1
    result = json.loads(next((tmp_path / 'STRUCTURE').glob('*/structure/*/result.json')).read_text())
    assert result['document_metadata']['input_collection'] == 'PDF/internal'
    assert cli.main(args) == 0, capsys.readouterr()
    assert len(calls) == 1
    assert not (tmp_path / 'LLM').exists() and not (tmp_path / 'VECTOR').exists()
