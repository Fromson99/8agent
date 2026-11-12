"""Real spawn and interrupted-stage recovery; synthetic corpus, no real models."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import signal
import time
import zipfile

import pytest

from semantic_runtime.contracts import sha
from lawrag.pipeline import term_generation, document_release as release
from test_genos_meaning_variants import prepared, reference_calls, tool as variants
from test_genos_meaning_bulk import bulk, settings

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / '06_TOOLS/OFFLINE/genos_meaning_recover_r1.py'
spec = importlib.util.spec_from_file_location('meaning_recovery', PATH)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
ORIGINAL = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'


def context(prepared, monkeypatch):
    monkeypatch.setenv('GENOS_VARIANTS_TOOL_PATH', str(ORIGINAL))
    return bulk.fork(prepared, settings())


def fail_at_fulltext(prepared, monkeypatch, reference_calls, *, interrupted=False):
    ctx = context(prepared, monkeypatch)
    before = {p: sha(p) for p in (prepared['source'], prepared['draft']/'dictionary.sqlite',
              prepared['parent']/'review/review.sqlite', ctx['parent']/'review/review.sqlite',
              ctx['parent']/'origin.json', ORIGINAL)}
    fulltext = term_generation.fulltext.build
    def fail(navigation, output, *args, **kwargs):
        output.mkdir()
        (output/'partial.sqlite').write_bytes(b'synthetic incomplete index')
        if interrupted:
            raise KeyboardInterrupt('scripted interrupt')
        raise RuntimeError('scripted fulltext failure')
    fail.__code__ = fail.__code__.replace(co_filename=fulltext.__code__.co_filename)
    monkeypatch.setattr(term_generation.fulltext, 'build', fail)
    adapter = recovery.Recovery(term_generation)
    with adapter.installed(release), pytest.raises(KeyboardInterrupt if interrupted else RuntimeError):
        variants.build_variant(ctx, 'off')
    output = ctx['parent']/'meaning-variants/off'
    receipt = recovery.read(output/'baseline-recovery-r1.json')
    stage = Path(receipt['stage'])
    assert (stage/'generation/navigation/manifest.json').exists()
    assert not (output/'baseline').exists()
    assert all(sha(p)==pin for p,pin in before.items())
    monkeypatch.setattr(term_generation.fulltext, 'build', fulltext)
    return ctx, output, stage, before


@pytest.mark.parametrize('interrupted', [False, True])
def test_fulltext_failure_preserves_navigation_then_resumes_without_rebuilding(prepared, monkeypatch, reference_calls, interrupted):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls, interrupted=interrupted)
    def forbidden(*args, **kwargs):
        raise AssertionError('Completed linking/navigation must not be rebuilt')
    monkeypatch.setattr(term_generation, 'compile_index', forbidden)
    monkeypatch.setattr(term_generation.glossary_linking, 'project', forbidden)
    # Preserve the native fingerprint used by the generation identity.
    from semantic_runtime import term_index as loaded  # the module this run loaded (code root or working tree)
    forbidden.__code__ = forbidden.__code__.replace(co_filename=Path(loaded.__file__).resolve().as_posix())
    with recovery.Recovery(term_generation).installed(release):
        result = variants.build_variant(ctx, 'off')
    assert result['completed'] and result['reference_llm'] and not result['activated']
    assert not stage.exists()
    assert list((output/'baseline').glob('failed-fulltext-*'))
    assert (output/'baseline/generation/fulltext/manifest.json').exists()
    assert all(sha(p)==pin for p,pin in before.items())
    assert len(reference_calls)==1
    with recovery.Recovery(term_generation).installed(release):
        assert variants.build_variant(ctx, 'off') == result
    assert len(reference_calls)==1


def test_checkpoint_tamper_is_rejected_and_preserved(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    nav = stage/'generation/navigation/manifest.json'
    nav.write_text(nav.read_text()+' ')
    with recovery.Recovery(term_generation).installed(release), pytest.raises(ValueError, match='payload changed'):
        variants.build_variant(ctx, 'off')
    assert stage.exists() and not (output/'baseline').exists()
    assert all(sha(p)==pin for p,pin in before.items())


def test_final_verification_failure_reuses_already_completed_fulltext(prepared, monkeypatch, reference_calls):
    from lawrag.pipeline import term_serving_bundle
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    native_verify=term_serving_bundle.verify_assets
    def fail(*args, **kwargs):
        raise RuntimeError('scripted final verification interrupt')
    monkeypatch.setattr(term_serving_bundle,'verify_assets',fail)
    with recovery.Recovery(term_generation).installed(release), pytest.raises(RuntimeError,match='final verification'):
        variants.build_variant(ctx,'off')
    assert (stage/'generation/fulltext/manifest.json').exists()
    monkeypatch.setattr(term_serving_bundle,'verify_assets',native_verify)
    native_fulltext=term_generation.fulltext.build
    def forbidden(*args, **kwargs):
        raise AssertionError('Completed fulltext must not be rebuilt after verification interruption')
    forbidden.__code__=forbidden.__code__.replace(co_filename=native_fulltext.__code__.co_filename)
    monkeypatch.setattr(term_generation.fulltext,'build',forbidden)
    with recovery.Recovery(term_generation).installed(release):
        result=variants.build_variant(ctx,'off')
    assert result['completed'] and not stage.exists()
    assert all(sha(p)==pin for p,pin in before.items())


def test_verified_old_orphan_is_copied_and_reused_without_mutating_original(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    (output/'baseline-recovery-r1.json').unlink()  # Mimic the original R2 orphan with no recovery receipt.
    (stage/'generation/navigation/.nfs-synthetic-retained').write_bytes(b'synthetic NFS tombstone')
    old_files = {p:sha(p) for p in stage.rglob('*') if p.is_file()}
    original_compile = term_generation.compile_index
    def forbidden(*args, **kwargs):
        raise AssertionError('Orphan navigation must not be rebuilt')
    forbidden.__code__ = forbidden.__code__.replace(co_filename=original_compile.__code__.co_filename)
    monkeypatch.setattr(term_generation, 'compile_index', forbidden)
    with recovery.Recovery(term_generation).installed(release):
        result = variants.build_variant(ctx, 'off')
    assert result['completed'] and stage.exists()
    assert all(sha(p)==pin for p,pin in old_files.items())
    assert all(sha(p)==pin for p,pin in before.items())
    assert recovery.read(output/'baseline-recovery-r1.json')['origin']['path'] == str(stage)


def test_incomplete_old_scratch_is_preserved_and_native_inputs_rebuilt(prepared, monkeypatch, reference_calls):
    ctx = context(prepared, monkeypatch)
    orphan = ctx['parent']/'meaning-variants/off/.baseline-original-removed'
    orphan.mkdir(parents=True)
    marker = orphan/'.nfs-retained'; marker.write_bytes(b'synthetic NFS orphan')
    with recovery.Recovery(term_generation).installed(release):
        result = variants.build_variant(ctx, 'off')
    assert result['completed'] and marker.read_bytes()==b'synthetic NFS orphan'


def test_multiple_valid_orphans_are_not_selected_by_recency(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    (output/'baseline-recovery-r1.json').unlink()
    other = stage.parent/'.baseline-second'
    shutil.copytree(stage, other)
    with recovery.Recovery(term_generation).installed(release), pytest.raises(ValueError, match='Multiple valid'):
        variants.build_variant(ctx, 'off')
    assert stage.exists() and other.exists()


def test_original_bundle_byte_and_path_pins_remain_exact(monkeypatch):
    monkeypatch.setitem(sys.modules, 'genos_meaning_variants', variants)
    monkeypatch.setenv('GENOS_VARIANTS_TOOL_PATH', str(ORIGINAL))
    bundle, embedded = recovery.load_bundle(ORIGINAL)
    assert sha(ORIGINAL)==recovery.ORIGINAL_SHA256
    native_pins = variants.code_pins()
    with recovery.Recovery(term_generation).installed(release):
        assert embedded.code_pins()==native_pins
    assert bundle.VERSION=='genos-meaning-bulk-v2'


def test_recovery_main_delegates_entire_original_off_pipeline_and_publish(prepared, monkeypatch, reference_calls, tmp_path):
    monkeypatch.setitem(sys.modules,'genos_meaning_variants',variants)
    ctx=context(prepared,monkeypatch)
    before={p:sha(p) for p in (prepared['source'],prepared['parent']/'review/review.sqlite',
                              ctx['parent']/'review/review.sqlite',ctx['parent']/'origin.json',ORIGINAL)}
    shared=tmp_path/'shared';shared.mkdir()
    assert recovery.main(['--original-txt',str(ORIGINAL),'baseline','--data-root',str(prepared['parent'].parents[1]),
                          '--run-id','prepared','--shared-root',str(shared)])==0
    assert len(reference_calls)==1
    selector=recovery.read(shared/'prepared-bulk-r2-meaning-off/rag-selection.json')
    assert not selector['activated'] and selector['reference_llm']
    assert all(sha(p)==pin for p,pin in before.items())
    assert not (shared/'CURRENT.json').exists()


def test_real_file_spawn_preflight_passes_before_original_pins_check(tmp_path):
    env = {**os.environ, 'PYTHONPATH':str(ROOT/'02_BACKEND')}
    outcome = subprocess.run([sys.executable, str(PATH), '--original-txt', str(ORIGINAL), 'check',
                              '--data-root', str(tmp_path/'no-corpus')], env=env,
                             capture_output=True, text=True, timeout=90)
    assert 'spawn workers + PeCab PASS' in outcome.stdout, outcome.stdout+outcome.stderr
    assert outcome.returncode==1  # Prepared corpus deliberately missing; no model request.
    assert '/workspace/<stdin>' not in outcome.stderr


def test_real_stdin_spawn_reproduces_the_photo_failure(tmp_path):
    env = {**os.environ, 'PYTHONPATH':str(ROOT/'02_BACKEND')}
    code = ('from concurrent.futures import ProcessPoolExecutor\n'
            'from multiprocessing import get_context\n'
            'from semantic_runtime.fulltext import _search_forms\n'
            'with ProcessPoolExecutor(max_workers=2,mp_context=get_context("spawn")) as pool:\n'
            '    print(list(pool.map(_search_forms,["모의 전문 색인"])))\n')
    outcome = subprocess.run([sys.executable, '-'], input=code, cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=30)
    assert outcome.returncode!=0
    assert '<stdin>' in outcome.stderr and 'BrokenProcessPool' in outcome.stderr


PACKAGE = ROOT/'08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r1'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R1'


def checkout(tmp_path):
    root = tmp_path/'field-checkout'; root.mkdir()
    (root/'02_BACKEND').symlink_to(ROOT/'02_BACKEND', target_is_directory=True)
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Synthetic','-c','user.email=fixture@example.invalid',
                    '-c','core.hooksPath=/dev/null','commit','--allow-empty','-qm','synthetic checkout'],check=True)
    transfer=root/'TRANSFER';transfer.mkdir()
    for suffix in ('.zip','.txt'):
        shutil.copyfile(PACKAGE/(STEM+suffix),transfer/(STEM+suffix))
    binary=tmp_path/'bin';binary.mkdir()
    python=binary/'python3'
    python.write_text('#!/usr/bin/env bash\nexec '+str(sys.executable)+' "$@"\n')
    python.chmod(0o700)
    env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'GENOS_CODE_ROOT':str(root)}
    return root,transfer/(STEM+'.txt'),python,env


def test_final_archive_exact_inventory_no_javascript_and_bash_syntax():
    with zipfile.ZipFile(PACKAGE/(STEM+'.zip')) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist())=={row['path'] for row in manifest['files']}|{'CODE_MANIFEST.json'}
        import hashlib
        for row in manifest['files']:
            assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
            assert Path(row['path']).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        assert z.read('06_TOOLS/OFFLINE/genos_meaning_recover_r1.py')==PATH.read_bytes()
        assert z.read('original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt')==ORIGINAL.read_bytes()
    text=(PACKAGE/(STEM+'.txt')).read_text()
    assert '.venv/bin/python' not in text
    subprocess.run(['bash','-n',str(PACKAGE/(STEM+'.txt'))],check=True)


def test_actual_mailed_installer_file_preflight_backup_and_idempotence(prepared, monkeypatch, reference_calls, tmp_path):
    ctx=context(prepared,monkeypatch)
    root,txt,python,env=checkout(tmp_path)
    env.update(GENOS_DATA_ROOT=str(prepared['parent'].parents[1]),GENOS_VARIANTS_RUN_ID='prepared',
               GENOS_VARIANTS_ORIGINAL=str(ORIGINAL))
    target=root/'06_TOOLS/OFFLINE/genos_meaning_recover_r1.py'
    target.parent.mkdir(parents=True);target.write_text('# synthetic previous runner\n')
    before=sha(ORIGINAL),sha(ctx['parent']/'review/review.sqlite')
    for attempt in range(2):
        outcome=subprocess.run(['bash',str(txt),'check'],cwd=root,env=env,capture_output=True,text=True,timeout=90)
        assert outcome.returncode==0,outcome.stdout+outcome.stderr
        assert 'PACKAGE_HASHES PASS' in outcome.stdout
        assert 'spawn workers + PeCab PASS' in outcome.stdout
        assert 'bulk origin PASS' in outcome.stdout
        assert target.read_bytes()==PATH.read_bytes()
    logs=prepared['parent'].parents[1]/'LOGS/prepared/meaning-recovery-r1'
    assert len(list(logs.glob('runner-before-*.py')))==1
    assert next(logs.glob('runner-before-*.py')).read_text()=='# synthetic previous runner\n'
    assert before==(sha(ORIGINAL),sha(ctx['parent']/'review/review.sqlite'))
    assert not (root/'CURRENT.json').exists()


def test_actual_mailed_background_detach_duplicate_lock_and_only_own_pid_stop(tmp_path):
    root,txt,python,env=checkout(tmp_path)
    python.write_text('#!/usr/bin/env bash\n'
        'if [[ "${1:-}" == -u && "${2:-}" == *genos_meaning_recover_r1.py && "${3:-}" == check ]]; then exit 0; fi\n'
        'if [[ "${1:-}" == -u && "${2:-}" == *genos_meaning_recover_r1.py && "${3:-}" == baseline ]]; then\n'
        '  exec '+str(sys.executable)+' -u -c '\
        "'import signal,time; signal.signal(signal.SIGINT,signal.default_int_handler); "
        "print(\"SCRIPTED RECOVERY WORKER START\",flush=True); time.sleep(120)'\nfi\n"
        'exec '+str(sys.executable)+' "$@"\n')
    env.update(GENOS_DATA_ROOT=str(tmp_path/'data'),GENOS_VARIANTS_RUN_ID='scripted-recovery')
    env.pop('GENOS_VARIANTS_ORIGINAL',None)
    meta=tmp_path/'data/LOGS/scripted-recovery/meaning-recovery-r1/off-worker.json'
    pid=None
    try:
        outcome=subprocess.run(['bash',str(txt)],cwd=root,env=env,capture_output=True,text=True,timeout=10)
        assert outcome.returncode==0,outcome.stdout+outcome.stderr
        record=recovery.read(meta);pid=record['pid']
        deadline=time.monotonic()+5
        while 'SCRIPTED RECOVERY WORKER START' not in Path(record['log']).read_text() and time.monotonic()<deadline:
            time.sleep(.05)
        assert 'SCRIPTED RECOVERY WORKER START' in Path(record['log']).read_text()
        outcome=subprocess.run(['bash',str(txt)],cwd=root,env=env,capture_output=True,text=True,timeout=10)
        assert outcome.returncode==1 and 'already holds' in outcome.stdout
        assert recovery.read(meta)==record
        outcome=subprocess.run(['bash',str(txt),'stop-off'],cwd=root,env=env,capture_output=True,text=True,timeout=10)
        assert outcome.returncode==0,outcome.stdout+outcome.stderr
        assert 'Interrupt sent only to recorded off' in outcome.stdout
        deadline=time.monotonic()+5
        while 'KeyboardInterrupt' not in Path(record['log']).read_text() and time.monotonic()<deadline:
            time.sleep(.05)
        assert 'KeyboardInterrupt' in Path(record['log']).read_text()
        pid=None
    finally:
        if pid and Path('/proc',str(pid)).exists(): os.kill(pid,signal.SIGINT)
