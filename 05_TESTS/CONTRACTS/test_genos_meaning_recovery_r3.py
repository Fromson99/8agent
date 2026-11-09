"""Legacy field imports and complete original recovery, synthetic inputs only."""
import ast
import builtins
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from semantic_runtime.contracts import sha
from semantic_runtime import navigation_storage
from lawrag.pipeline import term_generation, document_release as release
from test_genos_meaning_variants import prepared, reference_calls, tool as variants
from test_genos_meaning_recovery import fail_at_fulltext, context, recovery as r1, ORIGINAL
from test_genos_meaning_recovery_r2 import r2_checkout

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / '06_TOOLS/OFFLINE/genos_meaning_recover_r3.py'
spec = importlib.util.spec_from_file_location('meaning_recovery_r3', PATH)
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
PACKAGE = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r3'
STEM = 'GENOS_MEANING_RECOVERY_20261002_R3'


def hide_audit_import(monkeypatch):
    native = builtins.__import__
    def importing(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'semantic_runtime' and 'navigation_storage' in fromlist:
            raise ImportError("cannot import name 'navigation_storage' from 'semantic_runtime'")
        return native(name, globals, locals, fromlist, level)
    monkeypatch.setattr(builtins, '__import__', importing)
    monkeypatch.setattr(r3, 'storage_module', lambda: None)


def test_photo_import_failure_reproduces_and_monolithic_checkpoint_resumes(prepared, monkeypatch, reference_calls):
    monkeypatch.setattr(navigation_storage, 'separate_navigation', lambda *args: None)
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    assert not r1.read(stage / 'generation/navigation/manifest.json').get('storage')
    plan_bytes = (output / 'plan.json').read_bytes()
    hide_audit_import(monkeypatch)
    with pytest.raises(ImportError, match='navigation_storage'):
        r1.verify_stage(stage, r1.read(output / 'baseline-recovery-r1.json')['identity'])
    with r3.compatible_field(), r3.base.Recovery(term_generation).installed(release), r3.r2.PlanGuard(variants).installed():
        result = variants.build_variant(ctx, 'off')
    assert result['completed'] and not result['activated'] and len(reference_calls) == 1
    assert (output / 'plan.json').read_bytes() == plan_bytes
    assert all(sha(path) == expected for path, expected in before.items())
    assert (output / 'baseline/generation/fulltext/manifest.json').is_file()


def test_split_index_missing_module_is_rejected_before_start(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    assert r1.read(stage / 'generation/navigation/manifest.json').get('storage')
    monkeypatch.setattr(r3, 'storage_module', lambda: None)
    with pytest.raises(RuntimeError, match='audit validation cannot be skipped'):
        r3.check_field(ctx)
    assert stage.exists() and not reference_calls
    assert all(sha(path) == expected for path, expected in before.items())


def test_split_index_still_imports_and_checks_audit_at_runtime(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    identity = r1.read(output / 'baseline-recovery-r1.json')['identity']
    hide_audit_import(monkeypatch)
    with r3.compatible_field(), pytest.raises(ImportError, match='navigation_storage'):
        r3.base.verify_stage(stage, identity)
    assert stage.exists() and not reference_calls
    assert all(sha(path) == expected for path, expected in before.items())


def test_available_split_audit_verifier_rejects_tampering(prepared, monkeypatch, reference_calls):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    identity = r1.read(output / 'baseline-recovery-r1.json')['identity']
    path = stage / 'audit/navigation/manifest.json'; path.write_text(path.read_text() + ' ')
    with r3.compatible_field(), pytest.raises(ValueError, match='audit manifest changed'):
        r3.base.verify_stage(stage, identity)
    assert not reference_calls and stage.exists()


def test_required_function_missing_fails_eagerly(monkeypatch):
    from semantic_runtime import navigation_agent
    monkeypatch.setattr(navigation_agent, 'glossary_assets', None)
    with pytest.raises(RuntimeError, match='navigation_agent.glossary_assets'):
        r3.required_dependencies()


def test_missing_transitive_audit_dependency_is_not_hidden(monkeypatch):
    def import_module(name):
        raise ModuleNotFoundError('synthetic transitive dependency missing', name='synthetic_required_dependency')
    monkeypatch.setattr(r3.importlib, 'import_module', import_module)
    with pytest.raises(ModuleNotFoundError, match='transitive'):
        r3.storage_module()


def test_r3_archive_exact_inventory_original_runners_and_syntax():
    with zipfile.ZipFile(PACKAGE / (STEM + '.zip')) as z:
        manifest = json.loads(z.read('CODE_MANIFEST.json'))
        assert set(z.namelist()) == {row['path'] for row in manifest['files']} | {'CODE_MANIFEST.json'}
        import hashlib
        for row in manifest['files']:
            assert hashlib.sha256(z.read(row['path'])).hexdigest() == row['sha256']
            assert Path(row['path']).suffix not in ('.js', '.jsx', '.mjs', '.cjs')
        for version in ('r1', 'r2', 'r3'):
            name = '06_TOOLS/OFFLINE/genos_meaning_recover_' + version + '.py'
            assert z.read(name) == (ROOT / name).read_bytes()
        assert z.read('original/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt') == ORIGINAL.read_bytes()
    old = ROOT / '08_DEPLOYMENT/GENOS/handoffs/meaning_recovery_20261002_r2'
    handoff = r1.read(old / 'HANDOFF.json')
    assert all(sha(old / name) == expected for name, expected in handoff['files'].items())
    text = (PACKAGE / (STEM + '.txt')).read_text()
    assert '.venv/bin/python' not in text
    subprocess.run(['bash', '-n', str(PACKAGE / (STEM + '.txt'))], check=True)


def checkout_r3(tmp_path):
    root, _, python, env = r2_checkout(tmp_path)
    for suffix in ('.zip', '.txt'):
        shutil.copyfile(PACKAGE / (STEM + suffix), root / 'TRANSFER' / (STEM + suffix))
    return root, root / 'TRANSFER' / (STEM + '.txt'), python, env


def test_actual_mailed_r3_check_verifies_dependencies_and_all_installed_bytes(prepared, monkeypatch, reference_calls, tmp_path):
    ctx, output, stage, before = fail_at_fulltext(prepared, monkeypatch, reference_calls)
    root, txt, _, env = checkout_r3(tmp_path)
    env.update(GENOS_DATA_ROOT=str(prepared['parent'].parents[1]), GENOS_VARIANTS_RUN_ID='prepared',
               GENOS_VARIANTS_ORIGINAL=str(ORIGINAL))
    for _ in range(2):
        outcome = subprocess.run(['bash', str(txt), 'check'], cwd=root, env=env, capture_output=True, text=True, timeout=90)
        assert outcome.returncode == 0, outcome.stdout + outcome.stderr
        assert 'CAPABILITIES required imports/callables PASS' in outcome.stdout
        assert 'CHECK existing off frozen plan PASS' in outcome.stdout
    rows = (ctx['parent'] / 'recovery-field-capabilities-r3.jsonl').read_text().splitlines()
    assert len(rows) == 2 and all(json.loads(row)['navigation_storage_present'] for row in rows)
    assert not reference_calls and stage.exists()
    assert all(sha(path) == expected for path, expected in before.items())
    for version in ('r1', 'r2', 'r3'):
        name = '06_TOOLS/OFFLINE/genos_meaning_recover_' + version + '.py'
        assert (root / name).read_bytes() == (ROOT / name).read_bytes()


def legacy_backend(root):
    """Synthetic older compiler: no split audit feature and no optional module."""
    backend = root / '02_BACKEND'; backend.unlink(); backend.mkdir()
    def link(source, destination):
        Path(destination).symlink_to(source)
        return destination
    skip = shutil.ignore_patterns('__pycache__', '*.pyc')
    research = ROOT / '02_BACKEND/lawrag/research'
    def ignore(directory, names):
        # lawrag/research holds ~770k files that this test never edits; one directory link keeps it importable.
        return skip(directory, names) | ({'research'} if Path(directory) == research.parent else set())
    for source in (ROOT / '02_BACKEND').iterdir():
        if source.name in ('lawrag', 'semantic_runtime'):
            shutil.copytree(source, backend / source.name, copy_function=link, ignore=ignore)
        else:
            (backend / source.name).symlink_to(source, target_is_directory=source.is_dir())
    if research.is_dir():
        (backend / 'lawrag/research').symlink_to(research, target_is_directory=True)
    path = backend / 'lawrag/pipeline/term_generation.py'
    tree = ast.parse(path.read_text())
    class Legacy(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == 'semantic_runtime' and any(name.name == 'navigation_storage' for name in node.names):
                return None
            return node
        def visit_Dict(self, node):
            self.generic_visit(node)
            selected = [(key, val) for key, val in zip(node.keys, node.values)
                        if not isinstance(key, ast.Constant) or key.value != 'navigation_storage_sha256']
            node.keys, node.values = [key for key, _ in selected], [val for _, val in selected]
            return node
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == 'compile_index':
                node.keywords = [keyword for keyword in node.keywords if keyword.arg != 'audit_output']
            return node
    body = ast.unparse(ast.fix_missing_locations(Legacy().visit(tree))) + '\n'
    path.unlink(); path.write_text(body)
    (backend / 'semantic_runtime/navigation_storage.py').unlink()


def test_isolated_real_module_absence_old_compiler_photo_failure_and_r3_full_pipeline(prepared, monkeypatch, tmp_path):
    ctx = context(prepared, monkeypatch)
    before = {path: sha(path) for path in (prepared['source'], prepared['draft'] / 'dictionary.sqlite',
                                          ctx['parent'] / 'review/review.sqlite', ctx['parent'] / 'origin.json', ORIGINAL)}
    root, txt, _, env = checkout_r3(tmp_path)
    legacy_backend(root)
    env.update(GENOS_DATA_ROOT=str(prepared['parent'].parents[1]), GENOS_VARIANTS_RUN_ID='prepared',
               GENOS_VARIANTS_ORIGINAL=str(ORIGINAL), LAWRAG_WORKSPACE_ROOT=str(ROOT))
    # Installation/check occurs before any legacy plan exists.
    install = subprocess.run(['bash', str(txt), 'check'], cwd=root, env=env, capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stdout + install.stderr
    script = root / 'legacy_recovery_fixture.py'
    script.write_text(f'''import importlib.util,json,sys
from pathlib import Path
sys.path.insert(0,{str(root / '02_BACKEND')!r})
sys.path.insert(1,{str(ROOT / '05_TESTS/CONTRACTS')!r})
import pytest
from test_genos_meaning_variants import reference_calls
spec=importlib.util.spec_from_file_location('field_r3',{str(root / '06_TOOLS/OFFLINE/genos_meaning_recover_r3.py')!r})
r3=importlib.util.module_from_spec(spec);spec.loader.exec_module(r3)
def run():
    bundle,variants=r3.base.load_bundle(Path({str(ORIGINAL)!r}))
    settings={{'batch_size':32,'workers':4,'max_tokens':8192,'timeout':120,'max_request_chars':105000,'split_retries':2,'index_reserve_hours':12}}
    context=bundle.fork(variants.prepared(Path({str(prepared['parent'].parents[1])!r}),'prepared'),settings,create=False)
    output=context['parent']/'meaning-variants/off'
    from lawrag.pipeline import term_generation,document_release
    with r3.base.Recovery(term_generation).installed(document_release):
        try: variants.build_variant(context,'off')
        except ImportError as error:
            assert 'navigation_storage' in str(error)
            print('REAL MISSING MODULE PHOTO FAILURE REPRODUCED',flush=True)
        else: raise AssertionError('R1 must reproduce missing optional import')
    plan=(output/'plan.json').read_bytes()
    scratch=list(output.glob('.baseline-*'))
    assert len(scratch)==1
    assert not json.loads((scratch[0]/'generation/navigation/manifest.json').read_text()).get('storage')
    preserved={{str(p):r3.base.sha(p) for p in scratch[0].rglob('*') if p.is_file()}}
    args=['--original-txt',{str(ORIGINAL)!r},'check','--data-root',{str(prepared['parent'].parents[1])!r},'--run-id','prepared']
    assert r3.main(args)==0
    with pytest.MonkeyPatch.context() as patch:
        calls=reference_calls.__wrapped__(patch)
        args[2]='baseline'
        shared=Path({str(tmp_path / 'shared-legacy')!r});shared.mkdir()
        assert r3.main(args+['--shared-root',str(shared)])==0
        assert len(calls)==1
    assert (output/'plan.json').read_bytes()==plan
    assert all(r3.base.sha(p)==pin for p,pin in preserved.items())
    assert (output/'baseline/generation/fulltext/manifest.json').is_file()
    assert (output/'release.json').is_file()
    assert (shared/'prepared-bulk-r2-meaning-off/rag-selection.json').is_file()
    print('LEGACY FULL PIPELINE AND NFS-CONTRACT PUBLICATION PASS',flush=True)
if __name__=='__main__': run()
''')
    outcome = subprocess.run([sys.executable, str(script)], cwd=root, env=env,
                             capture_output=True, text=True, timeout=90)
    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    assert 'REAL MISSING MODULE PHOTO FAILURE REPRODUCED' in outcome.stdout
    assert 'LEGACY FULL PIPELINE AND NFS-CONTRACT PUBLICATION PASS' in outcome.stdout
    assert all(sha(path) == expected for path, expected in before.items())
