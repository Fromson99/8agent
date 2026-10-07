"""Reference CLI wiring + apply/reuse/rollback in a legacy-shaped isolated checkout."""
import ast
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_RELEASE_PROGRESS_R3_UTF8.txt'


def without_function(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = text.splitlines(keepends=True)
    del lines[node.lineno-1:node.end_lineno]
    return ''.join(lines)


def test_patch_legacy_cli_then_repeat_and_rollback(tmp_path):
    backend = tmp_path / '02_BACKEND'
    package = backend / 'lawrag/pipeline'
    package.mkdir(parents=True)
    (backend / 'lawrag/__init__.py').write_text('__path__.append(' + repr(str(ROOT / '02_BACKEND/lawrag')) + ')\n')
    (package / '__init__.py').write_text('__path__.append(' + repr(str(ROOT / '02_BACKEND/lawrag/pipeline')) + ')\n')
    release = (ROOT / '02_BACKEND/lawrag/pipeline/document_release.py').read_text()
    for line in release.splitlines(keepends=True):
        if "p.add_argument('--reference-model-profile'" in line or "p.add_argument('--max-reference-cases'" in line or "p.add_argument('--reference-batch-size'" in line:
            release = release.replace(line, '')
    release = release.replace(' or a.reference_model_profile', '')
    release = release.replace('reference_profile=a.reference_model_profile, max_reference_cases=a.max_reference_cases,\n                           reference_batch_size=a.reference_batch_size,\n                           ', '')
    reference = without_function((ROOT / '02_BACKEND/lawrag/pipeline/reference_resolution.py').read_text(), 'advance')
    originals = {'document_release.py':release, 'reference_resolution.py':reference}
    for name, text in originals.items(): (package / name).write_text(text)
    data = tmp_path / 'data'; data.mkdir()
    installer = TXT.read_text().split("<<'GENOS_RELEASE_WIRE_PY'\n",1)[1].split('\nGENOS_RELEASE_WIRE_PY',1)[0]
    env = {**os.environ, 'GENOS_DATA_ROOT':str(data), 'PYTHONPATH':str(backend)+':'+str(ROOT/'02_BACKEND')}
    def run(*args):
        return subprocess.run([sys.executable,'-c',installer,*args],cwd=tmp_path,env=env,
                              check=True,capture_output=True,text=True).stdout
    assert 'RELEASE_WIRE_APPLIED' in run()
    assert 'RELEASE_WIRE_ALREADY_APPLIED' in run()
    patched = (package/'document_release.py').read_text()
    assert 'reference_profile=a.reference_model_profile' in patched
    assert '--reference-model-profile' in patched
    assert 'def advance(' in (package/'reference_resolution.py').read_text()
    receipt = next((tmp_path/'TRANSFER/BACKUPS/release-wire-r3').glob('*/receipt.json'))
    assert 'ROLLBACK_PASS' in run('--rollback',str(receipt))
    for name,text in originals.items(): assert (package/name).read_text()==text
