import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

HERE=Path(__file__).resolve().parent;CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from semantic_runtime import contracts, full_glossary


@pytest.mark.parametrize('raw',[b'',b'abc',('한글😀\x00'*200000).encode()])
def test_both_hash_helpers_work_without_file_digest(tmp_path,monkeypatch,raw):
    monkeypatch.delattr(hashlib,'file_digest',raising=False)
    path=tmp_path/'input.bin';path.write_bytes(raw)
    wanted=hashlib.sha256(raw).hexdigest()
    assert contracts.sha(path)==full_glossary.sha(path)==wanted


def test_real_python310_reproduces_r8_and_passes_r9(tmp_path):
    python=os.environ.get('R9_TEST_PYTHON')
    if not python:pytest.skip('set R9_TEST_PYTHON to an isolated Python3.10 interpreter')
    old=tmp_path/'r8'
    with zipfile.ZipFile(HERE.parent/'existing_nfs_progress_20261030_r8/DATAIKU_EXISTING_NFS_CLIENT_20261030_R8.zip') as z:z.extractall(old)
    sample=tmp_path/'input.bin';sample.write_bytes(b'abc')
    def run(root,preflight=False):
        code=('import sys,hashlib;from pathlib import Path;'
              'assert sys.version_info[:2]==(3,10) and not hasattr(hashlib,"file_digest");'
              f'r=Path({str(root)!r});sys.path[:0]=[str(r),str(r/"client"),str(r/"client/02_BACKEND")];'
              'from semantic_runtime.contracts import sha;'
              f'print(sha(Path({str(sample)!r})));')
        if preflight:code+='from projection_preflight import preflight;preflight(r)'
        return subprocess.run([python,'-I','-c',code],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    baseline=run(old);assert baseline.returncode!=0 and "has no attribute 'file_digest'" in baseline.stderr
    result=run(CODE,True);assert result.returncode==0 and 'DEPENDENCY_PREFLIGHT_PASS' in result.stdout,result.stderr


def test_no_remaining_file_digest_calls_in_runtime_package():
    import ast
    for path in CODE.rglob('*.py'):
        tree=ast.parse(path.read_text())
        assert not any(isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name)
            and n.value.id=='hashlib' and n.attr=='file_digest' for n in ast.walk(tree)),path
