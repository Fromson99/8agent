"""Real sealed RUN, installed code, committed checkout gate; synthetic data only."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_SEARCH_LATEST_20261015_R1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(records):
    with tempfile.TemporaryDirectory(prefix='search-latest-delivery-') as temporary:
        work=Path(temporary);dev=work/'DEV';dev.mkdir();transfer=work/'arbitrary-upload';transfer.mkdir()
        for name in ('lawrag','semantic_runtime','PIPELINE','ENGINES'):
            shutil.copytree(ROOT/'02_BACKEND'/name,dev/'02_BACKEND'/name,
                ignore=shutil.ignore_patterns('research','__pycache__','*.pyc'))
        shutil.copytree(ROOT/'00_SYSTEM',dev/'00_SYSTEM',ignore=shutil.ignore_patterns('__pycache__'))
        for row in json.loads((dev/'00_SYSTEM/WORKSPACE.json').read_text())['roots']:
            (dev/row['canonical_path']).mkdir(parents=True,exist_ok=True)
        for name in ('06_TOOLS/COMMANDS','06_TOOLS/OFFLINE','08_DEPLOYMENT/GENOS/workflow','05_TESTS/CONTRACTS'):
            shutil.copytree(ROOT/name,dev/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('06_TOOLS/pipeline.py','service.py','05_TESTS/conftest.py','pytest.ini'):
            shutil.copy2(ROOT/name,dev/name)
        # Runtime inventory can pin stable runners outside the directory copies.
        cfg=json.loads((dev/'00_SYSTEM/PIPELINE.json').read_bytes())
        for entry in cfg['engines'].values():
            m=json.loads((dev/entry['manifest']).read_bytes())
            for name in m['files']:
                if not (dev/name).exists():
                    (dev/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dev/name)
        env={**os.environ,'GENOS_DEV_ROOT':str(dev),'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH'],
             'PYTHONPATH':str(dev/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(dev),
             'LAWRAG_TOOL_WORKSPACE_ROOT':str(dev),'PYTHONDONTWRITEBYTECODE':'1'}
        for key in ('GENOS_GENERATION','GENOS_DATA_ROOT'):env.pop(key,None)
        def run(command,*,ok=True,cwd=transfer):
            result=subprocess.run(command,cwd=cwd,env=env,text=True,capture_output=True)
            records.append({'command':list(map(str,command)),'cwd':str(cwd),'returncode':result.returncode,
                            'stdout':result.stdout,'stderr':result.stderr})
            if ok and result.returncode:raise AssertionError(result.stdout+'\n'+result.stderr)
            if not ok and not result.returncode:raise AssertionError('failure expected')
            return result
        # Build the two synthetic generation fixtures once with final code.
        run([sys.executable,'-m','pytest','-q','05_TESTS/CONTRACTS/test_search_selection.py',
             '--basetemp',str(work/'fixtures')],cwd=dev)
        generations=sorted(p for p in (work/'fixtures').glob('test_existing_database_search_*/built/generation')
                           if not p.parent.parent.is_symlink())
        assert len(generations)==2
        originals={p:sha(p) for g in generations for p in g.rglob('*') if p.is_file()}
        # Restore exact historical preimages; exercise a full checkout manifest too.
        for source in (HERE/'before').rglob('*.py'):shutil.copy2(source,dev/source.relative_to(HERE/'before'))
        for source in (HERE.parent/'latest_internal_20261015_r1/before').rglob('*.py'):
            shutil.copy2(source,dev/source.relative_to(HERE.parent/'latest_internal_20261015_r1/before'))
        for source in (HERE/'before-pins/02_BACKEND').rglob('*.json'):
            shutil.copy2(source,dev/'02_BACKEND'/source.relative_to(HERE/'before-pins/02_BACKEND'))
        shutil.copy2(HERE/'before-pins/PIPELINE.json',dev/'00_SYSTEM/PIPELINE.json')
        for name in ('02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/lawrag/pipeline/search_selection.py'):
            (dev/name).unlink()
        inventory_paths=['02_BACKEND/semantic_runtime/storage.py','02_BACKEND/semantic_runtime/term_index.py',
            '00_SYSTEM/PIPELINE.json','service.py']
        (dev/'CODE_MANIFEST.json').write_text(json.dumps({'format':'8agent-code/1','files':[
            {'path':p,'sha256':sha(dev/p),'bytes':(dev/p).stat().st_size} for p in inventory_paths]},indent=2)+'\n')
        # Confirm unrelated failures against these preimages before installing.
        baseline=run([sys.executable,'-m','pytest','-q',
            '05_TESTS/CONTRACTS/test_genos_team_selection.py::test_workflow_legal_agent_through_service_to_real_v5_app',
            '05_TESTS/CONTRACTS/test_compact_v2_rag.py::test_new_storage_correction_restore_and_reuse',
            '05_TESTS/CONTRACTS/test_term_tools_cache.py','--tb=short'],ok=False,cwd=dev)
        assert '2 failed' in baseline.stdout and '4 errors' in baseline.stdout
        run(['git','init',str(dev)])
        for key,value in [('user.name','Synthetic Contract'),('user.email','synthetic@example.invalid')]:
            run(['git','-C',str(dev),'config',key,value])
        run(['git','-C',str(dev),'add','02_BACKEND','00_SYSTEM','06_TOOLS','service.py','CODE_MANIFEST.json'])
        run(['git','-C',str(dev),'commit','-qm','synthetic preimage'])
        shutil.copy2(HERE/(NAME+'.zip'),transfer/(NAME+'.zip'))
        run(['python3','-m','zipfile','-e','./'+NAME+'.zip','./package'])
        package=transfer/'package';txt=['bash','./package/'+NAME+'_RUN.txt']
        selection_receipts=[];backup=None
        for i,g in enumerate(generations):
            arguments=['--generation',str(g),'--plan',str(package/('PLAN'+str(i)+'.json'))]
            run([*txt,'check',*arguments]);result=run([*txt,'apply',*arguments])
            if backup is None:backup=Path(json.loads((package/'CODE_APPLIED.json').read_text())['backup'])
            receipt=json.loads((package/'SELECTION_APPLIED.json').read_text())['receipt'];selection_receipts.append(receipt)
            run([*txt,'apply',*arguments]);run([*txt,'status','--generation',str(g)])
            applied=json.loads((package/'CODE_APPLIED.json').read_text())
            assert Path(applied['backup'])==backup
            if i==0:
                run(['git','-C',str(dev),'add',*applied['files']])
                run(['git','-C',str(dev),'commit','-qm','apply sealed latest search selection'])
            run([*txt,'gate','--generation',str(g)])
            run([*txt,'rollback','--receipt',receipt])
        assert originals=={p:sha(p) for g in generations for p in g.rglob('*') if p.is_file()}
        run([sys.executable,'-m','pytest','-q','05_TESTS/CONTRACTS/test_search_selection.py',
             '05_TESTS/CONTRACTS/test_latest_internal_versions.py','--basetemp',str(work/'installed-tests')],cwd=dev)
        run([*txt,'undo-code','--backup',str(backup)])
        spec=json.loads((package/'PATCH_SPEC.json').read_text())
        states=lambda:{r['path']:sha(dev/r['path']) if (dev/r['path']).exists() else None for r in spec['files']}
        before=states()
        assert all(before[r['path']] in r['before'] for r in spec['files'])
        args=['--generation',str(generations[0]),'--plan',str(package/'PLAN0.json')]
        target=dev/spec['files'][0]['path'];raw=target.read_bytes();target.write_bytes(raw+b'\n# unknown\n')
        changed=states();run([*txt,'apply',*args],ok=False);assert changed==states();target.write_bytes(raw)
        z=package/'CODE.zip';raw=z.read_bytes();z.write_bytes(raw+b'tampered')
        run([*txt,'apply',*args],ok=False);assert before==states();z.write_bytes(raw)
        smoke=package/'smoke_check.py';raw=smoke.read_bytes();smoke.write_text('raise RuntimeError("injected verification failure")\n')
        run([*txt,'apply',*args],ok=False);assert before==states();smoke.write_bytes(raw)
        assert list(transfer.glob('search-latest-*.log'))
    return records


if __name__=='__main__':
    records=[]
    try:
        main(records)
        (HERE/'DELIVERY_RESULT.json').write_text(json.dumps({'status':'PASS','commands':len(records),
            'sealed_zip_sha256':sha(HERE/(NAME+'.zip')),'field_execution':'NOT_RUN'},indent=2)+'\n')
    except BaseException:
        import traceback
        (HERE/'DELIVERY_FAILURE.txt').write_text(traceback.format_exc());raise
    finally:
        with gzip.open(HERE/'DELIVERY_TRANSCRIPT.json.gz','wt',encoding='utf-8') as f:json.dump(records,f,ensure_ascii=False)
