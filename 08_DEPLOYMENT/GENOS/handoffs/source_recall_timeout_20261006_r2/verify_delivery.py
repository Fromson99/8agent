"""Exercise the shipped TXT on both supported delivered predecessors."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import zipfile

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_SOURCE_RECALL_TIMEOUT_20261006_R2'
BASE = ROOT/'08_DEPLOYMENT/GENOS/handoffs/request_input_20261006_r2/GENOS_V6_REQUEST_INPUT_20261006_R2.zip'
NFS = ROOT/'08_DEPLOYMENT/GENOS/handoffs/nfs_state_sqlite_20261006_r1/GENOS_NFS_STATE_SQLITE_20261006_R1.zip'
TIMER = ROOT/'08_DEPLOYMENT/GENOS/handoffs/source_recall_timeout_20261006_r1/GENOS_SOURCE_RECALL_TIMEOUT_20261006_R1.zip'
ARCHIVE = OUT/(NAME+'.zip')
SCRIPT = OUT/(NAME+'_APPLY.txt')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def contents(path):
    with zipfile.ZipFile(path) as z:
        m = json.loads(z.read('CODE_MANIFEST.json'))
        result = {r['path']:z.read(r['path']) for r in m['files']}
        assert all(sha(result[r['path']]) == r['sha256'] for r in m['files'])
        assert not any(Path(name).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for name in z.namelist())
        return result
base,nfs,timer,payload = contents(BASE),contents(NFS),contents(TIMER),contents(ARCHIVE)
outputs = []
for predecessor in ('request-input-r2','nfs-sqlite-r1','timeout-r1'):
    prior = base if predecessor == 'request-input-r2' else {**base,**nfs} if predecessor == 'nfs-sqlite-r1' else {**base,**nfs,**timer}
    with tempfile.TemporaryDirectory(prefix='source-recall-handoff-') as temp:
        root = Path(temp)/'DEV';root.mkdir()
        for name,raw in prior.items():
            path = root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        runtime = root/'90_RUNTIME/semantic';runtime.mkdir(parents=True)
        db = runtime/'case-memory/cases-v4.sqlite';db.parent.mkdir()
        db.write_bytes(b'installer-must-preserve-operational-db')
        env = {**os.environ,'GENOS_DEV':str(root),'GENOS_RUNTIME_DIR':str(runtime),
               'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),'GENOS_HANDOFF_LOG_DIR':str(Path(temp)/'logs')}
        def run(mode, arg=None, success=True):
            done = subprocess.run(['bash',str(SCRIPT),mode]+([str(arg)] if arg else []),
                env=env,capture_output=True,text=True,timeout=40)
            outputs.append({'predecessor':predecessor,'mode':mode,'exit_code':done.returncode,
                            'stdout':done.stdout,'stderr':done.stderr})
            assert (done.returncode == 0) == success, done.stdout+done.stderr
            assert db.read_bytes() == b'installer-must-preserve-operational-db'
            return done
        run('check');run('apply');run('apply')
        for name,raw in payload.items():assert (root/name).read_bytes() == raw
        cfg = json.loads((root/'00_SYSTEM/PIPELINE.json').read_text())
        for entry in cfg['engines'].values():
            manifest = root/entry['manifest']
            assert sha(manifest.read_bytes()) == entry['sha256']
            for name,digest in json.loads(manifest.read_text())['files'].items():
                assert sha((root/name).read_bytes()) == digest, name
        handoff = json.loads((OUT/'HANDOFF.json').read_text())
        assert sha((root/'02_BACKEND/semantic_runtime/full_glossary.py').read_bytes()) == handoff['compact_reader_sha256']
        # Test the actually installed module, beyond both obsolete timer thresholds.
        probe = '''from types import SimpleNamespace
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.source_recall_global import SourceRecall as GlobalRecall
import time
for cls in (SourceRecall,GlobalRecall):
 r=cls.__new__(cls);r.s=SimpleNamespace(context=RequestContext.create({'question':'모의 원문'},{},{},1800));r.start=time.monotonic()-7200;r.check_time()
print('INSTALLED_SOURCE_RECALL_TIMERS_REMOVED PASS')
'''
        subprocess.run([str(ROOT/'.venv/bin/python'),'-c',probe],cwd=root,
            env={**env,'PYTHONPATH':str(root/'02_BACKEND')},check=True,capture_output=True,text=True)
        subprocess.run(['git','init','-q',str(root)],check=True)
        subprocess.run(['git','-C',str(root),'add','-f','--',*sorted(set(prior)|set(payload))],check=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Delivery check','-c',
            'user.email=delivery-check@example.invalid','commit','-qm','Simulated installed source timeout patch'],check=True)
        spec = importlib.util.spec_from_file_location('gate',root/'06_TOOLS/COMMANDS/genos_release_gate.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        checked=gate.compare_zip_to_checkout(ARCHIVE,root)
        backup=next((root/'09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
        run('rollback',backup)
        for name in payload:
            if name in prior:assert (root/name).read_bytes() == prior[name]
            else:assert not (root/name).exists()
        changed=root/'02_BACKEND/semantic_runtime/legal_agent/source_recall.py'
        changed.write_bytes(changed.read_bytes()+b'\n# unknown field modification\n')
        drift=changed.read_bytes();run('check',success=False);assert changed.read_bytes()==drift
        outputs.append({'predecessor':predecessor,'git_zip_comparison':checked})
result={'supported_predecessors':['request-input-r2','nfs-sqlite-r1','timeout-r1'],
    'standalone_check_apply_repeat_rollback':'PASS','unknown_code_preserved':'PASS',
    'operational_db_preserved':'PASS','installed_timer_check':'PASS',
    'engine_pins':'PASS','compact_reader_preserved':'PASS','no_javascript':'PASS',
    'genos_execution':'NOT_EXECUTED','generation_gate':'NOT_EXECUTED','outputs':outputs}
(OUT/'DELIVERY_VERIFICATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('Three predecessor apply/repeat/rollback/drift/installed timers/pins/Git ZIP checks PASS')
