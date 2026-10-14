"""Exercise the exact standalone TXT on three previously delivered checkouts."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest
from test_compact_v2_rag import structured_generation  # noqa: F401

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/full_error_logging_20261007_r10'
RUN=OUT/'GENOS_FULL_ERROR_LOGGING_20261007_R10_RUN.txt'


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()


def seed(tmp_path,parent):
    root=tmp_path/'DEV';root.mkdir()
    archive=next((OUT.parent/parent).glob('*.zip'))
    with zipfile.ZipFile(archive) as z:
        before={name:z.read(name) for name in z.namelist()}
    for name,raw in before.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    git(root,'init','-q');git(root,'config','user.name','Synthetic full error validation')
    git(root,'config','user.email','validation@example.invalid');git(root,'add','-f','.')
    git(root,'commit','-qm','Synthetic parent code')
    return root,before


def run(root,mode,*args,okay=True):
    env={k:v for k,v in os.environ.items() if not k.startswith(('GENOS_','LAWRAG_'))}
    env.update(GENOS_DEV_ROOT=str(root),GENOS_SYSTEM_LOG_ENABLED='0',GENOS_AUTO_WARMUP='0',
        PATH=str(ROOT/'.venv/bin')+os.pathsep+env['PATH'],PYTHONPATH=str(root/'02_BACKEND'),
        LAWRAG_WORKSPACE_ROOT=str(root),LAWRAG_TOOL_WORKSPACE_ROOT=str(root),AD_WORKER_ENABLED='0')
    result=subprocess.run(['bash',str(RUN),mode,*map(str,args)],cwd=root,env=env,
        capture_output=True,text=True,timeout=60)
    assert (result.returncode==0)==okay,result.stdout+result.stderr
    logs=root/'TRANSFER/full-error-logging-r10'
    assert any(p.read_text()==f'{{"exit_code":{result.returncode}}}\n' for p in logs.glob('run-*/EXIT_STATUS.json'))
    return result


@pytest.mark.parametrize('parent',['query_latency_20261007_r4','no_socket_chat_20261007_r3'])
def test_standalone_apply_repeat_verify_undo(tmp_path,parent):
    root,before=seed(tmp_path,parent)
    sentinel=root/'90_RUNTIME/preserved.sqlite';sentinel.parent.mkdir(exist_ok=True);sentinel.write_bytes(b'preserved state')
    run(root,'check');run(root,'apply');run(root,'verify')
    assert 'ALREADY_APPLIED' in run(root,'apply').stdout
    backup=next((root/'TRANSFER/full-error-logging-r10').glob('backup-*'))
    receipt=json.loads((backup/'receipt.json').read_text());assert receipt['state']=='VERIFIED'
    for row in receipt['files']:
        assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['after_sha256']
        assert (backup/row['path']).read_bytes()==before[row['path']]
    run(root,'undo',backup)
    for name,raw in before.items():assert (root/name).read_bytes()==raw,name
    assert sentinel.read_bytes()==b'preserved state'


def test_older_shipped_inventory_mismatch_is_rejected_without_rebinding(tmp_path):
    root,before=seed(tmp_path,'system_logging_20261007_r1')
    result=run(root,'check',okay=False)
    assert 'Engine code mismatch' in result.stdout and '00_SYSTEM/WORKSPACE.json' in result.stdout
    for name,raw in before.items():assert (root/name).read_bytes()==raw,name


def test_drift_failure_is_full_and_preserves_files(tmp_path):
    root,before=seed(tmp_path,'query_latency_20261007_r4')
    target=root/'service.py';target.write_bytes(before['service.py']+b'\n# synthetic newer change\n')
    changed=target.read_bytes();result=run(root,'apply',okay=False)
    assert 'CHECKOUT_DRIFT' in result.stdout and 'Traceback (most recent call last)' in result.stdout
    assert target.read_bytes()==changed and (root/'CODE_MANIFEST.json').read_bytes()==before['CODE_MANIFEST.json']


def test_committed_applied_checkout_and_synthetic_generation_gate(tmp_path,structured_generation):
    root,_=seed(tmp_path,'query_latency_20261007_r4');run(root,'apply')
    backup=next((root/'TRANSFER/full-error-logging-r10').glob('backup-*'))
    names=(backup/'CHANGED_FILES.txt').read_text().splitlines()
    git(root,'add','--',*names);git(root,'commit','-qm','Full error logging')
    assert 'GENOS_RELEASE_GATE PASS' in run(root,'gate',backup,'--generation',structured_generation).stdout
    assert json.loads((backup/'gate-receipt.json').read_text())['state']=='PASS'


def test_editor_paste_has_exact_embedded_logger_and_full_workflow():
    raw=(OUT/'WORKFLOW_PASTE_ALL.txt').read_text();tree=ast.parse(raw,feature_version=(3,11))
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
        and n.func.attr=='b64decode' and n.args and isinstance(n.args[0],ast.Constant))
    import base64,zlib
    assert zlib.decompress(base64.b64decode(call.args[0].value))==(ROOT/'genos_diagnostics.py').read_bytes()
    assert raw.endswith((ROOT/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_text())


def test_log_reader_prints_entire_matching_file(tmp_path):
    text='request-abc\n'+'x'*45000+'\nERROR_LAST_LINE_한글\n'
    target=tmp_path/'server.log';target.write_text(text)
    env={**os.environ,'PATH':str(ROOT/'.venv/bin')+os.pathsep+os.environ['PATH']}
    for args in (['--file',str(target)],['--root',str(tmp_path),'--contains','request-abc']):
        result=subprocess.run(['bash',str(OUT/'READ_ERROR_LOGS.txt'),*args],env=env,capture_output=True,text=True,check=True)
        assert text in result.stdout and target.read_text()==text
