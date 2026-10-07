"""Exercise the exact field TXT against small synthetic data and local Git only."""
from pathlib import Path
import ast,hashlib,json,os,shutil,subprocess,zipfile
import pytest
from conftest import term_glossary
from test_compact_v2_rag import structured_generation

R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent
NAME='GENOS_INVESTIGATION_CONTROL_20261007_R2';ZIP=O/(NAME+'.zip');SCRIPT=O/(NAME+'_APPLY.txt')
P=R/'08_DEPLOYMENT/GENOS/handoffs/investigation_logging_20261006_r2'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def seed(root,kind='parent'):
 root.mkdir()
 if kind=='parent':
  m=json.loads((P/'CODE_MANIFEST.json').read_text());pr=json.loads((P/'HANDOFF.json').read_text())
  with zipfile.ZipFile(P/(pr['version']+'.zip')) as z:items={x['path']:z.read(x['path']) for x in m['files']}
  base=R/'09_ARTIFACTS/DELIVERIES/investigation_logging_20261006_r2'
  for row in m['required_files']:
   raw=(base/row['path']).read_bytes();assert sha(raw)==row['sha256'];items[row['path']]=raw
 else:
  with zipfile.ZipFile(ZIP) as z:items={n:z.read(n) for n in z.namelist() if n!='CODE_MANIFEST.json'}
 for name,raw in items.items():
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
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
  mf=json.loads(z.read('CODE_MANIFEST.json'));assert len(mf['files'])==269+len(mf['gate_dependency_closure']) and not mf['required_files']
  assert '02_BACKEND/lawrag/pipeline/term_serving_bundle.py' in mf['gate_dependency_closure']
  assert mf['main_basis']['serving_files']==m['files']
  for n,h in m['files'].items():assert sha(z.read(n))==h
  for n in z.namelist():assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.sqlite','.db','.key','.pem'}
 assert (O/(NAME+'_WORKFLOW_PASTE_ALL.txt')).read_bytes()==(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py').read_bytes()
 subprocess.run(['bash','-n',str(SCRIPT)],check=True)
 code=SCRIPT.read_text().split("<<'LOADER_PY'\n",1)[1].rsplit('\nLOADER_PY',1)[0]
 compile(code,'field-txt-loader','exec');ast.parse(code,feature_version=(3,11))
@pytest.mark.parametrize('kind',['parent','main'])
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
def seed_inventory(root):return [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()]
def test_full_txt_commits_gates_and_pushes_exact_bytes_to_local_remote(tmp_path,structured_generation):
 root=tmp_path/'DEV';prior=seed(root);git(root,'init','-q');git(root,'config','user.name','Handoff validation');git(root,'config','user.email','validation@example.invalid')
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
