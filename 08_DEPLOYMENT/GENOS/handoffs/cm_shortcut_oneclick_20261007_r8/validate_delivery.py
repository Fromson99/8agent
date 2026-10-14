"""Verify sealed recipes and exact TXT with no user configuration or real remote."""
import base64
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
NAME='GENOS_CM_ONECLICK_20261007_R8'
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def module():
    path=ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py';spec=importlib.util.spec_from_file_location('oneclick',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def write(root,payload):
    for name,raw in payload.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

def main():
    spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    tests=json.loads(gzip.decompress((OUT/'TEST_BASES.json.gz').read_bytes()))
    one=module();lib=one.library(spec)
    assert sha((ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes())==json.loads((OUT/'SOURCE_BINDING.json').read_bytes())['oneclick_source_sha256']
    representative=[]
    for basis in tests['bases']:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            payload={p:base64.b64decode(tests['blobs'][fingerprint]) for p,fingerprint in basis['files'].items()};write(root,payload)
            before=sha(payload['CODE_MANIFEST.json']);recipe=spec['recipes'][basis['recipe_id']]
            assert one.inspect_input(root,spec,lib)[2]['id']==recipe['id']
            binding={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':'/fixed/generation','runtime':'/fixed/runtime','state':None,'generation_manifest_sha256':'0'*64}
            with contextlib.redirect_stdout(io.StringIO()):_,_,changes,manifest=one.prepare(root,spec,lib,binding)
            final={p:raw for p,raw in payload.items() if p!='CODE_MANIFEST.json'};final.update({p:raw for p,raw in changes.items() if p!='CODE_MANIFEST.json'})
            assert {p:sha(raw) for p,raw in final.items() if p!=one.CONFIG}==spec['inventories'][recipe['after']]
            lib.verify_bindings(final)
            target=root/'service.py';old=target.read_bytes();target.write_bytes(old+b'\n# unknown\n')
            try:one.prepare(root,spec,lib,binding)
            except ValueError:pass
            else:raise AssertionError('unknown field change accepted')
            assert sha((root/'CODE_MANIFEST.json').read_bytes())==before
            representative.append({'basis':basis['label'],'prepare_and_unknown_change_rejection':True})
    # Every variant map is sealed and every post-code pin can be checked without
    # repeating the full pre-existing R6 native/core contracts or copying data.
    for recipe in spec['recipes'].values():
        after=spec['inventories'][recipe['after']]
        patches=spec['patch_sets'][recipe['patches']]
        config=json.loads(one.blob(spec,patches['00_SYSTEM/PIPELINE.json']))
        for entry in config['engines'].values():
            manifest=json.loads(one.blob(spec,patches[entry['manifest']]))
            assert sha(encoded(manifest))==entry['sha256']
            assert all(after[p]==s for p,s in manifest['files'].items())
    real=[];transcript=[]
    selected=[tests['bases'][0],next(x for x in tests['bases'] if 'SYSTEM_LOGGING' in x['label'] and '/nfs-list-r1' in x['label'])]
    for i,basis in enumerate(selected):
        with tempfile.TemporaryDirectory(prefix='cm-oneclick-validation-',dir=ROOT/'90_RUNTIME') as directory:
            prefix=Path(directory);(prefix/'.genos-offline-validation').write_text('offline fixture')
            root=prefix/'DEV';root.mkdir();transfer=root/'TRANSFER';transfer.mkdir()
            payload={p:base64.b64decode(tests['blobs'][s]) for p,s in basis['files'].items()};write(root,payload)
            run=transfer/(NAME+'_RUN.txt');run.write_bytes((OUT/run.name).read_bytes())
            generation=prefix/Path(spec['paths']['generation']).relative_to('/')
            source=ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation'
            for path in source.rglob('*'):
                target=generation/path.relative_to(source)
                if path.is_dir():target.mkdir(parents=True,exist_ok=True)
                elif path.is_file():target.parent.mkdir(parents=True,exist_ok=True);os.link(path,target)
            runtime=prefix/Path(spec['paths']['runtime']).relative_to('/')
            case=runtime/'case-memory';case.mkdir(parents=True)
            database=case/'cases-v4.sqlite'
            with sqlite3.connect(database) as db:db.execute('CREATE TABLE keep_fixture(value TEXT)');db.execute("INSERT INTO keep_fixture VALUES('preserve')")
            remote=prefix/'remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
            def git(*a):subprocess.run(['git','-C',str(root),*a],check=True,capture_output=True)
            git('init','-q');git('add','-f','--',*payload)
            git('-c','user.name=Offline fixture','-c','user.email=fixture@example.invalid','commit','-qm','known field fixture')
            git('remote','add','origin',str(remote))
            env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH'],
                 'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0','GENOS_SYSTEM_LOG_DIR':str(prefix/'logs'),'GENOS_LOG_SPOOL_DIR':str(prefix/'spool')}
            for key in list(env):
                if key.startswith('CM_') or key in ('GENOS_GENERATION','GENOS_RUNTIME_DIR','GENOS_STATE_DIR','GENOS_DEV_ROOT','GENOS_DEV','GENOS_PYTHON_DIR'):env.pop(key)
            count=2 if i==0 else 1
            for replay in range(count):
                result=subprocess.run(['bash',str(run),'--validation-prefix',str(prefix)],cwd=prefix,env=env,capture_output=True,text=True,timeout=240)
                transcript.append(basis['label']+' replay='+str(replay)+'\n'+result.stdout+result.stderr)
                assert result.returncode==0,transcript[-1]
                status=json.loads((transfer/'cm-oneclick-r8/STATUS.json').read_bytes())
                assert status['state']=='READY_FOR_REVISION_DEPLOYMENT' and status['model_calls']==0
                assert status['code_serving_revision'] is None and status['workflow_verified'] is False
                receipt=json.loads(Path(status['receipt']).read_bytes());assert len(receipt['records'])==51 and receipt['visibility']=='COMMON_CATALOG'
                with sqlite3.connect(database) as db:
                    assert db.execute('SELECT value FROM keep_fixture').fetchone()[0]=='preserve'
                    assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
                actual=subprocess.run(['git','--git-dir',str(remote),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
                assert actual==status['commit']
            real.append({'basis':basis['label'],'complete_TXT_runs':count,'common_units':51,'entries':98,
                         'without_user_env':True,'local_commit_gate_push':True,'existing_state_preserved':True,'replay_no_duplicate':count==2})
            print('END_TO_END PASS',basis['label'],flush=True)
    result={'sealed_recipes':len(spec['recipes']),'input_inventories':len(spec['states']),'representatives':representative,
            'real_TXT':real,'model_calls':0,'real_remote_push':False,'GENOS_field_verified':False,'email_sent':False}
    (OUT/'VALIDATION.json').write_bytes(encoded(result))
    (OUT/'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
    print('PASS',len(spec['recipes']),'recipes;',sum(x['complete_TXT_runs'] for x in real),'complete TXT runs',flush=True)

if __name__=='__main__':main()
