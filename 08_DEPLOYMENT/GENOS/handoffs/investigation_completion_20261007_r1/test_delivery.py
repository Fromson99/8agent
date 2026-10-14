"""Exercise the exact field TXT against small synthetic data and local Git only."""
from pathlib import Path
import ast,hashlib,json,os,shutil,subprocess,zipfile
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation

R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
NAME='GENOS_INVESTIGATION_COMPLETION_20261007_R1';ZIP=O/(NAME+'.zip');SCRIPT=O/(NAME+'_APPLY.txt')
P=R/'08_DEPLOYMENT/GENOS/handoffs/investigation_logging_20261006_r2'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def nfs_install(root,revision,log):
 d=R/'08_DEPLOYMENT/GENOS/handoffs'/('nfs_read_probe_20261006_'+revision)
 record=json.loads((d/'VALIDATION.json').read_text());archive=d/(record['version']+'.zip')
 assert sha(archive.read_bytes())==record['code_zip_sha256']
 import types
 with zipfile.ZipFile(archive) as z:source=z.read('06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py')
 module=types.ModuleType('_verified_nfs_install');exec(compile(source,str(archive),'exec'),module.__dict__)
 log.mkdir();return module.install(types.SimpleNamespace(archive=archive,zip_sha256=record['code_zip_sha256'],code_root=root),log)
def seed(root,kind='parent'):
 root.mkdir()
 if kind in ('parent','nfs'):
  m=json.loads((P/'CODE_MANIFEST.json').read_text());pr=json.loads((P/'HANDOFF.json').read_text())
  with zipfile.ZipFile(P/(pr['version']+'.zip')) as z:items={x['path']:z.read(x['path']) for x in m['files']}
  base=R/'09_ARTIFACTS/DELIVERIES/investigation_logging_20261006_r2'
  for row in m['required_files']:
   raw=(base/row['path']).read_bytes();assert sha(raw)==row['sha256'];items[row['path']]=raw
 else:
  with zipfile.ZipFile(ZIP) as z:items={n:z.read(n) for n in z.namelist() if n!='CODE_MANIFEST.json'}
 for name,raw in items.items():
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 if kind=='nfs':
  old=json.loads((R/'08_DEPLOYMENT/RELEASES/local-genos-unit-v6-20261006-r1/release.json').read_text())
  n='08_DEPLOYMENT/GENOS/stream_app.py';p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/old['code_root']/n).read_bytes())
  git(root,'init','-q');git(root,'config','user.name','Handoff validation');git(root,'config','user.email','validation@example.invalid')
  git(root,'add','-f','--',*sorted({*items,n}));git(root,'commit','-qm','Synthetic field before NFS')
  nfs_install(root,'r1',root.parent/'install-r1')
  # The old NFS helper was tracked. Subsequent cumulative RAG edits remain
  # uncommitted, matching the second photograph's commit preflight failure.
  git(root,'add','-f','--',*seed_inventory(root));git(root,'commit','-qm','Earlier NFS diagnostic code')
  with zipfile.ZipFile(ZIP) as z:
   n=next(name for name in sorted(items) if name.startswith('02_BACKEND/semantic_runtime/legal_agent/') and items[name]!=z.read(name));new=z.read(n)
  (root/n).write_bytes(new)
  nfs_install(root,'r7',root.parent/'install-r7')
  items={n:(root/n).read_bytes() for n in seed_inventory(root) if not n.startswith(('.git/','09_ARTIFACTS/'))}
 return items
def env(root,temp):return {**os.environ,'GENOS_DEV':str(root),'GENOS_PYTHON_DIR':str(R/'.venv/bin'),'GENOS_HANDOFF_LOG_DIR':str(temp/'logs'),'PYTHONPATH':str(root/'02_BACKEND'),'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
def run(root,temp,mode,arg,ok=True,script=SCRIPT):
 done=subprocess.run(['bash',str(script),mode,str(arg)],env=env(root,temp),capture_output=True,text=True,timeout=90)
 assert (done.returncode==0)==ok,done.stdout+done.stderr
 assert 'INVESTIGATION_CONTROL_EXIT=' in done.stdout
 return done
def hash_tree(path):return {str(p.relative_to(path)):sha(p.read_bytes()) for p in path.rglob('*') if p.is_file()}
def assert_installed(root):
 with zipfile.ZipFile(ZIP) as z:
  for n in z.namelist():assert (root/n).read_bytes()==z.read(n),n
def git(root,*args):return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()
def test_exact_main_inventory_and_syntax():
 p=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());m=json.loads((R/p['manifest_path']).read_text())
 with zipfile.ZipFile(ZIP) as z:
  mf=json.loads(z.read('CODE_MANIFEST.json'));assert len(mf['files'])==290 and not mf['required_files']
  assert '02_BACKEND/lawrag/pipeline/term_serving_bundle.py' in mf['gate_dependency_closure']
  assert mf['main_basis']['serving_files']==m['files']
  for n,h in m['files'].items():assert sha(z.read(n))==h
  for n in z.namelist():assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.sqlite','.db','.key','.pem'}
 assert (O/(NAME+'_WORKFLOW_PASTE_ALL.txt')).read_bytes()==(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()
 subprocess.run(['bash','-n',str(SCRIPT)],check=True)
 code=SCRIPT.read_text().split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0]
 compile(code,'field-txt-loader','exec');ast.parse(code,feature_version=(3,11))
@pytest.mark.parametrize('kind',['parent','main','nfs'])
def test_apply_rerun_verify_rollback_preserves_data_and_state(tmp_path,structured_generation,kind):
 root=tmp_path/'physical-checkout';prior=seed(root,kind)
 alias=tmp_path/'DEV';alias.symlink_to(root,target_is_directory=True)
 state=root/'90_RUNTIME/existing-state.sqlite';state.parent.mkdir();state.write_bytes(b'untouched-state')
 before=hash_tree(structured_generation)
 run(alias,tmp_path,'check',structured_generation);run(alias,tmp_path,'apply',structured_generation)
 assert_installed(root);run(alias,tmp_path,'apply',structured_generation)
 run(alias,tmp_path,'verify',structured_generation)
 assert hash_tree(structured_generation)==before and state.read_bytes()==b'untouched-state'
 backup=next((root/'09_ARTIFACTS/BACKUPS/code-replacement').iterdir())
 run(alias,tmp_path,'rollback',backup)
 for n,raw in prior.items():assert (root/n).read_bytes()==raw,n
 with zipfile.ZipFile(ZIP) as z:
  for n in z.namelist():
   if n not in prior:assert not (root/n).exists(),n
 assert hash_tree(structured_generation)==before and state.read_bytes()==b'untouched-state'
@pytest.mark.parametrize('failure',['unknown-code','cache-receipt','zip-tamper'])
def test_preflight_rejects_tampering_before_code_changes(tmp_path,structured_generation,failure):
 root=tmp_path/'DEV';seed(root)
 if failure=='unknown-code':
  f=root/'02_BACKEND/semantic_runtime/app.py';f.write_bytes(f.read_bytes()+b'\n# unknown local edit\n')
 elif failure=='cache-receipt':
  m=json.loads((structured_generation/'manifest.json').read_text());b=m['glossary'];f=structured_generation/b['cache']/b['cache_receipt'];f.write_bytes(f.read_bytes()+b'\n')
 script=SCRIPT
 if failure=='zip-tamper':
  script=tmp_path/SCRIPT.name;shutil.copyfile(SCRIPT,script);z=tmp_path/ZIP.name;shutil.copyfile(ZIP,z)
  with z.open('ab') as stream:stream.write(b'tamper')
 before_code={n:sha((root/n).read_bytes()) for n in seed_inventory(root)};before_data=hash_tree(structured_generation)
 run(root,tmp_path,'apply',structured_generation,ok=False,script=script)
 assert before_code=={n:sha((root/n).read_bytes()) for n in before_code}
 assert hash_tree(structured_generation)==before_data
 assert not (root/'09_ARTIFACTS/BACKUPS/code-replacement').exists()
def seed_inventory(root):return [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and not p.is_relative_to(root/'.git')]
@pytest.mark.parametrize('kind',['parent','nfs'])
def test_full_txt_commits_gates_and_pushes_exact_bytes_to_local_remote(tmp_path,structured_generation,kind):
 root=tmp_path/'DEV';prior=seed(root,kind);git(root,'init','-q');git(root,'config','user.name','Handoff validation');git(root,'config','user.email','validation@example.invalid')
 git(root,'add','--',*sorted(prior));git(root,'commit','-qm','Synthetic predecessor')
 remote=tmp_path/'remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
 git(root,'remote','add','origin',str(remote));before=hash_tree(structured_generation)
 done=run(root,tmp_path,'all',structured_generation);assert 'GENOS_RELEASE_GATE PASS' in done.stdout
 assert_installed(root);head=git(root,'rev-parse','HEAD');branch=git(root,'symbolic-ref','--short','HEAD')
 assert git(remote,'rev-parse','refs/heads/'+branch)==head
 assert not git(root,'status','--porcelain=v1','--untracked-files=no')
 assert hash_tree(structured_generation)==before
 events=[json.loads(x) for x in (tmp_path/'logs/events.jsonl').read_text().splitlines()]
 assert any(x['stage']=='GIT_PUSHED' and x['commit']==head for x in events)
 assert events[-1]['code_serving_revision']=='NOT_DEPLOYED' and events[-1]['workflow_test']=='NOT_RUN'
 git(root,'show','HEAD:service.py')
 run(root,tmp_path,'all',structured_generation)
 assert git(root,'rev-parse','HEAD')==head

def test_photo_r2_failure_is_reproduced_and_r4_accepts_verified_hooks(tmp_path,structured_generation):
 root=tmp_path/'DEV';seed(root,'nfs')
 # Reproduce the historical R2 field state using its contemporary R4 bytes,
 # rather than a newly changed generation-44 agent file injected by seed().
 prior=R/'08_DEPLOYMENT/GENOS/handoffs/investigation_control_20261007_r4'
 with zipfile.ZipFile(prior/'GENOS_INVESTIGATION_CONTROL_20261007_R4.zip') as z:
  for p in (root/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py'):
   name=str(p.relative_to(root))
   if name in z.namelist():p.write_bytes(z.read(name))
 before=hash_tree(root)
 old=R/'08_DEPLOYMENT/GENOS/handoffs/investigation_control_20261007_r2/GENOS_INVESTIGATION_CONTROL_20261007_R2_APPLY.txt'
 done=run(root,tmp_path,'apply',structured_generation,ok=False,script=old)
 assert 'CHECKOUT_DRIFT: 08_DEPLOYMENT/GENOS/stream_app.py' in done.stdout
 assert {n:h for n,h in hash_tree(root).items() if n!='.genos-code-replacement.lock'}==before
 run(root,tmp_path,'check',structured_generation)

@pytest.mark.parametrize('conflict',['unrelated','unknown-staged','hook-edit'])
def test_changes_are_reported_and_preserved_before_install(tmp_path,structured_generation,conflict):
 root=tmp_path/'DEV';seed(root,'nfs')
 if conflict=='unrelated':
  p=root/'unrelated.txt';p.write_text('original');git(root,'add','--',p.name);git(root,'commit','-qm','Independent tracked file');p.write_text('pending edit')
 elif conflict=='unknown-staged':
  p=root/'service.py';raw=p.read_bytes();p.write_bytes(raw+b'\n# unrecognized staged change\n');git(root,'add','--','service.py');p.write_bytes(raw)
 else:
  p=root/'08_DEPLOYMENT/GENOS/stream_app.py';p.write_bytes(p.read_bytes()+b'\n# unknown field edit\n')
 before=hash_tree(root);head=git(root,'rev-parse','HEAD')
 done=run(root,tmp_path,'all',structured_generation,ok=False)
 assert 'CHECKOUT_PREFLIGHT' in done.stdout and 'Checkout changes preserved' in done.stdout
 assert before==hash_tree(root) and git(root,'rev-parse','HEAD')==head
 assert not (root/'09_ARTIFACTS/BACKUPS/code-replacement').exists()
 report=json.loads(next((tmp_path/'logs').glob('CHECKOUT_PREFLIGHT-*.json')).read_text())
 if conflict=='unrelated':assert report['unrelated_tracked_or_staged_paths']==['unrelated.txt']
 elif conflict=='unknown-staged':assert report['unknown_staged_bytes'][0]['path']=='service.py'
 else:assert report['mismatches'][0]['path']=='08_DEPLOYMENT/GENOS/stream_app.py'
 run(root,tmp_path,'inspect','');assert before==hash_tree(root)

def test_actual_r7_driver_reproduces_photo_commit_preflight_failure():
 from test_genos_nfs_data_probe import FieldContracts
 fixture=FieldContracts();fixture.setUp()
 try:
  root=fixture.root;pending=root/'02_BACKEND/prior_cumulative_edit.py';pending.parent.mkdir(exist_ok=True)
  pending.write_text('# original code\n');git(root,'add','--',str(pending.relative_to(root)));git(root,'commit','-qm','Prior cumulative development')
  pending.write_text('# known pending cumulative code\n');head=git(root,'rev-parse','HEAD');data=hash_tree(fixture.gen)
  source=R/'08_DEPLOYMENT/GENOS/handoffs/nfs_read_probe_20261006_r7'
  transfer=root/'TRANSFER';transfer.mkdir()
  for suffix in ['.zip','_RUN.txt']:shutil.copyfile(source/('GENOS_NFS_READ_20261006_R7'+suffix),transfer/('GENOS_NFS_READ_20261006_R7'+suffix))
  done=subprocess.run(['bash',str(transfer/'GENOS_NFS_READ_20261006_R7_RUN.txt'),'all','--generation',str(fixture.gen),'--runtime',str(fixture.runtime),'--nfs-base',str(fixture.nfs)],env={**os.environ,'GENOS_DEV':str(root),'PATH':str(R/'.venv/bin')+':'+os.environ['PATH']},capture_output=True,text=True,timeout=45)
  (O/'PHOTO_NFS_R7_REPRODUCTION.log').write_text(done.stdout+done.stderr)
  assert done.returncode==1 and 'unrelated tracked changes present' in done.stdout
  status=json.loads(next((transfer/'nfs-probe-logs').glob('prepare-*/STATUS.json')).read_text())
  assert status['phase']=='checkout_commit_preflight'
  assert git(root,'rev-parse','HEAD')==head and hash_tree(fixture.gen)==data
  assert pending.read_text()=='# known pending cumulative code\n'
 finally:fixture.doCleanups()
