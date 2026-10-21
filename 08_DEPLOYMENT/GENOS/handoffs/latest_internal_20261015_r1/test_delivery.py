"""Exercise the sealed ZIP and real TXT in a synthetic Git checkout."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(records):
    with tempfile.TemporaryDirectory(prefix='latest-internal-delivery-') as td:
        work=Path(td); dev=work/'DEV'; dev.mkdir(); transfer=work/'arbitrary-upload';transfer.mkdir()
        for name in ['lawrag','semantic_runtime','PIPELINE','ENGINES']:
            shutil.copytree(ROOT/'02_BACKEND'/name,dev/'02_BACKEND'/name,
                            ignore=shutil.ignore_patterns('research','__pycache__','*.pyc'))
        shutil.copytree(ROOT/'00_SYSTEM',dev/'00_SYSTEM',ignore=shutil.ignore_patterns('__pycache__'))
        for row in json.loads((dev/'00_SYSTEM/WORKSPACE.json').read_text())['roots']:
            (dev/row['canonical_path']).mkdir(parents=True,exist_ok=True)
        shutil.copytree(ROOT/'08_DEPLOYMENT/GENOS/workflow',dev/'08_DEPLOYMENT/GENOS/workflow',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'06_TOOLS/COMMANDS',dev/'06_TOOLS/COMMANDS',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'06_TOOLS/OFFLINE',dev/'06_TOOLS/OFFLINE',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'06_TOOLS/pipeline.py',dev/'06_TOOLS/pipeline.py')
        shutil.copy2(ROOT/'service.py',dev/'service.py')
        (dev/'01_DATA/RAW/internal').mkdir(parents=True)
        for p in (HERE/'before').rglob('*.py'):
            shutil.copy2(p,dev/p.relative_to(HERE/'before'))
        with zipfile.ZipFile(HERE/'GENOS_LATEST_INTERNAL_20261015_R1.zip') as z:
            z.extractall(transfer/'package')
        package=transfer/'package'
        spec=json.loads((package/'PATCH_SPEC.json').read_text())
        env={**os.environ,'GENOS_DEV_ROOT':str(dev),'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH'],
             'LAWRAG_WORKSPACE_ROOT':str(dev),'LAWRAG_TOOL_WORKSPACE_ROOT':str(dev),'PYTHONPATH':str(dev/'02_BACKEND'),
             'PYTHONDONTWRITEBYTECODE':'1'}
        def run(command, *, ok=True, cwd=transfer, extra_env=None):
            p=subprocess.run(command,cwd=cwd,env={**env,**(extra_env or {})},text=True,capture_output=True)
            records.append({'command':[str(v) for v in command],'cwd':str(cwd),'returncode':p.returncode,
                            'stdout':p.stdout,'stderr':p.stderr})
            if ok and p.returncode:raise AssertionError(p.stdout+'\n'+p.stderr)
            if not ok and not p.returncode:raise AssertionError('Expected failure: '+str(command))
            return p
        run(['git','init',str(dev)])
        for key,value in [('user.name','Synthetic Contract'),('user.email','synthetic@example.invalid')]:
            run(['git','-C',str(dev),'config',key,value])
        run(['git','-C',str(dev),'add','02_BACKEND','00_SYSTEM','06_TOOLS','service.py'])
        run(['git','-C',str(dev),'commit','-qm','synthetic build preimage'])
        txt=['bash',str(package/'GENOS_LATEST_INTERNAL_20261015_R1_RUN.txt')]
        run([*txt,'check'])
        result=run([*txt,'apply'])
        backup=Path(next(s.removeprefix('BACKUP=') for s in result.stdout.splitlines() if s.startswith('BACKUP=')))
        run([*txt,'apply'])
        run([*txt,'verify'])
        assert all(sha(dev/r['path'])==r['after'] for r in spec['files'])
        for date in ['20190710','20220331']:
            (dev/('01_DATA/RAW/internal/모의규정('+date+').docx')).write_text(date)
        command=[sys.executable,'-B',str(dev/'06_TOOLS/pipeline.py'),'build-all','--no-models',
                 '--latest-internal-versions','--only-internal','--run-id','latest-check','--check-only']
        run(command,cwd=dev)
        inventory=json.loads(sorted((dev/'01_DATA/LOGS/latest-check').glob('inventory-*.json'))[-1].read_text())
        assert len(inventory['files'])==1 and '20220331' in inventory['files'][0]['path']
        # installed copies execute the same source/merge/index/API contracts
        shutil.copytree(ROOT/'05_TESTS/CONTRACTS',dev/'05_TESTS/CONTRACTS',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'05_TESTS/conftest.py',dev/'05_TESTS/conftest.py')
        shutil.copy2(ROOT/'pytest.ini',dev/'pytest.ini')
        run([sys.executable,'-m','pytest','-q','05_TESTS/CONTRACTS/test_latest_internal_versions.py',
             '--basetemp',str(work/'pytest')],cwd=dev)
        run(['git','-C',str(dev),'add',*[r['path'] for r in spec['files']]])
        run(['git','-C',str(dev),'commit','-qm','apply sealed latest filename policy'])
        # The contract's final tamper modifies RAW only, never the published generation.
        generations=sorted(p for p in (work/'pytest').glob('test_latest_structure_merge_in*/built/generation')
                           if not p.parent.parent.is_symlink())
        assert len(generations)==2
        for generation in generations:
            run([sys.executable,'-B',str(dev/'06_TOOLS/COMMANDS/genos_release_gate.py'),
                 '--code-zip',str(package/'CODE.zip'),'--deploy-root',str(dev),'--generation',str(generation)],
                 cwd=dev,ok=True)
        run([*txt,'undo',str(backup)])
        assert all(sha(dev/r['path'])==r['before'] for r in spec['files'])
        # Unknown preimages are preserved; none of the other files may be changed.
        target=dev/spec['files'][0]['path']; original=target.read_bytes();target.write_bytes(original+b'\n# unknown\n')
        before={r['path']:sha(dev/r['path']) for r in spec['files']}
        run([*txt,'apply'],ok=False)
        assert before=={r['path']:sha(dev/r['path']) for r in spec['files']}
        target.write_bytes(original)
        # Payload tampering is rejected before any application.
        code=package/'CODE.zip';original_zip=code.read_bytes();code.write_bytes(original_zip+b'drift')
        run([*txt,'apply'],ok=False);code.write_bytes(original_zip)
        assert all(sha(dev/r['path'])==r['before'] for r in spec['files'])
        # A post-write verifier failure restores the original bytes and records failure.
        smoke=package/'smoke_check.py';original_smoke=smoke.read_bytes();smoke.write_text('raise RuntimeError("synthetic verify failure")\n')
        run([*txt,'apply'],ok=False)
        assert all(sha(dev/r['path'])==r['before'] for r in spec['files'])
        smoke.write_bytes(original_smoke)
        run([*txt,'apply']);run([*txt,'verify'])
        assert list(transfer.glob('latest-internal-*.log'))
    return records

if __name__=='__main__':
    records=[]
    try:
        records=main(records)
        (HERE/'DELIVERY_RESULT.json').write_text(json.dumps({'status':'PASS','commands':len(records),
            'sealed_zip_sha256':sha(HERE/'GENOS_LATEST_INTERNAL_20261015_R1.zip'),
            'field_execution':'NOT_RUN'},indent=2)+'\n')
    except BaseException:
        import traceback
        (HERE/'DELIVERY_FAILURE.txt').write_text(traceback.format_exc())
        raise
    finally:
        if records:
            with gzip.open(HERE/'DELIVERY_TRANSCRIPT.json.gz','wt',encoding='utf-8') as f:
                json.dump(records,f,ensure_ascii=False)
