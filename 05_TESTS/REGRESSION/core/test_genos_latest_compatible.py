"""Exact latest-mail artifact compatibility, synthetic/fake provider only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest
from . import test_genos_build_package as base
from . import test_genos_all_corpus_package as alltests

ROOT=base.ROOT
PATCH=ROOT/'09_ARTIFACTS/HANDOFF/GENOS/genos-all-corpus-compatible-20260910.zip'
LATEST=ROOT/'09_ARTIFACTS/HANDOFF/GENOS/genos-semantic-backend-hash-fix-20260910.zip'
INSTALLER=ROOT/'06_TOOLS/COMMANDS/genos_apply_compatible.sh'
sha=lambda b:hashlib.sha256(b).hexdigest()


def unpack(archive,root):
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name.endswith('/') or not (name.startswith(('00_SYSTEM/','02_BACKEND/','06_TOOLS/','07_DOCS/')) or name=='service.py'):
                continue
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))


def host(tmp_path,latest=False):
    root=tmp_path/'DEV';root.mkdir()
    unpack(base.PRIOR,root)
    if latest:
        unpack(LATEST,root)
        # The earlier logging patch supplied these exact dependency bytes.
        with zipfile.ZipFile(PATCH) as z:
            for name in ('02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/pipeline.py','02_BACKEND/semantic_runtime/observability.py'):
                (root/name).write_bytes(z.read(name))
    transfer=root/'TRANSFER';transfer.mkdir()
    shutil.copyfile(PATCH,transfer/PATCH.name)
    shutil.copyfile(INSTALLER,transfer/INSTALLER.name)
    (root/'.env').write_text('GENOS_PRIVATE_KEY=do-not-touch\n')
    (root/'data/corpus/internal').mkdir(parents=True)
    (root/'data/corpus/internal/keep.zip').write_bytes(b'raw zip unchanged')
    transport=root/'02_BACKEND/semantic_runtime/genos.py'
    transport.write_text(transport.read_text()+'\n# local successful transport repair\n')
    return root


def run(root,*args):
    return subprocess.run(['bash',str(root/'TRANSFER'/INSTALLER.name),*args],cwd=root,
                          env={**os.environ,'GENOS_SCHEMA_BUILD_ROOT':str(root)},capture_output=True,text=True)


@pytest.mark.parametrize('latest',[False,True])
def test_install_latest_preserved_and_registry_closed(tmp_path,latest):
    root=host(tmp_path,latest)
    transport=root/'02_BACKEND/semantic_runtime/genos.py';before=transport.read_bytes()
    result=run(root);assert result.returncode==0,result.stdout+result.stderr
    with zipfile.ZipFile(PATCH) as z:
        manifest=json.loads(z.read('patch-manifest.json'))
        for name,record in manifest['files'].items():
            if not record['preserve_existing']:assert sha((root/name).read_bytes())==record['sha256']
    assert transport.read_bytes()==before
    assert (root/'.env').read_text()=='GENOS_PRIVATE_KEY=do-not-touch\n'
    assert (root/'data/corpus/internal/keep.zip').read_bytes()==b'raw zip unchanged'
    assert 'obs.context' in (root/'02_BACKEND/semantic_runtime/app.py').read_text()
    assert 'SEMANTIC_LLM_BACKEND' in (root/'service.py').read_text()
    assert (root/'06_TOOLS/COMMANDS/genos_build_all.sh').is_file()
    assert run(root).returncode==0
    assert len(list((root/'runtime/patch-backups').glob('genos-compatible-*/receipt.json')))==1


@pytest.mark.parametrize('problem',['unknown','symlink','corrupt','dependency'])
def test_failure_is_prewrite_and_unknowns_all_reported(tmp_path,problem):
    root=host(tmp_path,True)
    app=root/'02_BACKEND/semantic_runtime/app.py';provider=root/'02_BACKEND/semantic_runtime/provider.py'
    if problem=='unknown':
        for p in (app,provider):p.write_text(p.read_text()+'\n# unknown edit\n')
    elif problem=='symlink':
        other=tmp_path/'outside.py';app.rename(other);app.symlink_to(other)
    elif problem=='corrupt':
        (root/'TRANSFER'/PATCH.name).write_bytes(b'bad archive')
    else:
        p=root/'00_SYSTEM/SCHEMAS/legal-semantic-v2.schema.json';p.write_text('{}')
    before={str(p):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and 'TRANSFER' not in p.parts}
    result=run(root)
    assert result.returncode!=0
    assert all(sha(Path(p).read_bytes())==h for p,h in before.items())
    assert not (root/'runtime/patch-backups').exists()
    if problem=='unknown':assert 'app.py' in result.stdout and 'provider.py' in result.stdout


def test_crlf_known_version_and_check_only(tmp_path):
    root=host(tmp_path,True);app=root/'02_BACKEND/semantic_runtime/app.py'
    app.write_bytes(app.read_bytes().replace(b'\n',b'\r\n'));before=app.read_bytes()
    result=run(root,'--check-only');assert result.returncode==0,result.stdout+result.stderr
    assert app.read_bytes()==before and not (root/'runtime/patch-backups').exists()
    result=run(root);assert result.returncode==0,result.stdout+result.stderr
    assert b'\r\n' not in app.read_bytes()


def test_exact_zip_isolated_full_build(tmp_path,monkeypatch):
    monkeypatch.setattr(base,'PATCH',PATCH)
    alltests.test_isolated_zip(tmp_path,None)


def test_latest_mail_bytes_and_python311_syntax():
    import ast
    with zipfile.ZipFile(PATCH) as z,zipfile.ZipFile(LATEST) as latest:
        for name in latest.namelist():assert z.read(name)==latest.read(name)
        for name in z.namelist():
            if name.endswith('.py'):ast.parse(z.read(name),feature_version=(3,11))


def test_failed_second_write_rolls_back(tmp_path):
    import sys
    root=host(tmp_path,False)
    before={str(p):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and 'TRANSFER' not in p.parts}
    body=INSTALLER.read_text().split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    prelude='import os\n_real=os.replace\n_count=0\ndef fail_second(*a,**kw):\n global _count\n _count+=1\n if _count==2:raise OSError("synthetic disk failure")\n return _real(*a,**kw)\nos.replace=fail_second\n'
    result=subprocess.run([sys.executable,'-c',prelude+body,str(root/'TRANSFER'/PATCH.name),str(root)],text=True,capture_output=True)
    assert result.returncode!=0 and 'synthetic disk failure' in result.stderr
    assert all(sha(Path(p).read_bytes())==h for p,h in before.items())
    assert not list((root/'runtime/patch-backups').glob('*/receipt.json'))


def test_python311_installed_entrypoints(tmp_path):
    root=host(tmp_path,True)
    result=run(root);assert result.returncode==0,result.stdout+result.stderr
    python=ROOT/'09_ARTIFACTS/STAGING/ADR-0263-venv/bin/python'
    code=('import sys\nassert sys.version_info[:2]==(3,11)\n'
          'from lawrag.pipeline import genos_build,genos_corpus\n'
          'from semantic_runtime.app import create_app\n'
          'from semantic_runtime.provider import Haiku\n'
          'import service\n'
          'assert service._provider(service._ROOT,service._ROOT/"runtime",{}).backend=="genos"\n'
          'args=genos_build.parser().parse_args(["build","--build-dir","data/builds/syntax-check"])\n'
          'assert args.build_dir=="data/builds/syntax-check"\nprint("Python3.11 imports and provider selection PASS; no network calls")\n')
    result=subprocess.run([str(python),'-c',code],cwd=root,text=True,capture_output=True,
                          env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),
                               'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
                               'SEMANTIC_LLM_BACKEND':'genos','GENOS_BASE_URL':'http://genos.invalid',
                               'GENOS_LLM_SERVING_ID':'226','GENOS_LLM_KEY':'synthetic-only'})
    assert result.returncode==0,result.stdout+result.stderr
