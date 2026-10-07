"""Validate the shipped bytes, exact field TXT and a local committed checkout."""
from pathlib import Path
import ast,hashlib,json,os,subprocess,zipfile
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation

R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
NAME='GENOS_NATIVE_CHAT_SSE_20261007_R1';ZIP=O/(NAME+'.zip');SCRIPT=O/(NAME+'_APPLY.txt')
P=O.parent/'investigation_control_20261007_r4'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def seed(root):
    root.mkdir()
    with zipfile.ZipFile(P/'GENOS_INVESTIGATION_CONTROL_20261007_R4.zip') as z:
        prior={n:z.read(n) for n in z.namelist()}
    for name,raw in prior.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return prior

def hashes(root):
    return {str(p.relative_to(root)):sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}

def run(root,temp,mode,arg,ok=True):
    env={**os.environ,'GENOS_DEV':str(root),'GENOS_PYTHON_DIR':str(R/'.venv/bin'),
        'GENOS_HANDOFF_LOG_DIR':str(temp/'logs'),'PYTHONPATH':str(root/'02_BACKEND'),
        'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),
        'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','GENOS_RUNTIME_DIR':str(temp/'runtime')}
    done=subprocess.run(['bash',str(SCRIPT),mode,str(arg)],env=env,capture_output=True,text=True,timeout=90)
    assert (done.returncode==0)==ok,done.stdout+done.stderr
    assert 'NATIVE_CHAT_EXIT=' in done.stdout
    return done

def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()

def test_shipped_bytes_protocol_and_field_syntax():
    with zipfile.ZipFile(ZIP) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        assert len(manifest['files'])==287
        assert manifest['native_chat']['default_transport']=='json'
        assert manifest['main_basis']['local_active_pointer_changed'] is False
        for row in manifest['files']:
            raw=z.read(row['path'])
            assert sha(raw)==row['sha256'] and raw==(R/row['path']).read_bytes()
            if row['path'].endswith('.py'):
                compile(raw,row['path'],'exec');ast.parse(raw,feature_version=(3,11))
    subprocess.run(['bash','-n',str(SCRIPT)],check=True)
    source=SCRIPT.read_text().split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0]
    compile(source,'native-field-loader','exec');ast.parse(source,feature_version=(3,11))

def test_apply_repeat_native_verify_and_exact_rollback(tmp_path,structured_generation):
    root=tmp_path/'physical';prior=seed(root);alias=tmp_path/'DEV';alias.symlink_to(root,target_is_directory=True)
    state=root/'90_RUNTIME/existing-state.sqlite';state.parent.mkdir();state.write_bytes(b'preserved-state')
    data=hashes(structured_generation)
    run(alias,tmp_path,'check',structured_generation)
    run(alias,tmp_path,'apply',structured_generation)
    run(alias,tmp_path,'apply',structured_generation)
    done=run(alias,tmp_path,'verify',structured_generation)
    assert 'NATIVE_CHAT_CONTRACT PASS' in done.stdout
    assert hashes(structured_generation)==data and state.read_bytes()==b'preserved-state'
    with zipfile.ZipFile(ZIP) as z:
        for name in z.namelist():assert (root/name).read_bytes()==z.read(name)
    backup=next((root/'09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
    run(alias,tmp_path,'rollback',backup)
    for name,raw in prior.items():assert (root/name).read_bytes()==raw,name
    assert not (root/'07_DOCS/REFERENCE/OPERATIONS/GENOS_NATIVE_CHAT_SSE_20261007.md').exists()
    assert hashes(structured_generation)==data and state.read_bytes()==b'preserved-state'

def test_same_checkout_gate_and_local_push(tmp_path,structured_generation):
    root=tmp_path/'DEV';seed(root)
    git(root,'init','-q');git(root,'config','user.name','Native chat validation')
    git(root,'config','user.email','validation@example.invalid')
    git(root,'add','-f','.');git(root,'commit','-qm','Synthetic cumulative predecessor')
    remote=tmp_path/'local-remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
    git(root,'remote','add','origin',str(remote))
    before=hashes(structured_generation)
    done=run(root,tmp_path,'all',structured_generation)
    assert 'GENOS_RELEASE_GATE PASS' in done.stdout and 'NATIVE_CHAT_CONTRACT PASS' in done.stdout
    assert git(remote,'rev-parse','HEAD')==git(root,'rev-parse','HEAD')
    assert not git(root,'status','--porcelain','--untracked-files=no')
    assert hashes(structured_generation)==before
    events=[json.loads(line) for line in (tmp_path/'logs/events.jsonl').read_text().splitlines()]
    assert events[-1]['code_serving_revision']=='NOT_DEPLOYED' and events[-1]['chat_binding']=='NOT_SELECTED'

def test_unknown_field_code_is_preserved(tmp_path,structured_generation):
    root=tmp_path/'DEV';seed(root)
    path=root/'main.py';path.write_bytes(path.read_bytes()+b'\n# unknown field edit\n')
    before=hashes(root)
    run(root,tmp_path,'apply',structured_generation,ok=False)
    assert hashes(root)==before
