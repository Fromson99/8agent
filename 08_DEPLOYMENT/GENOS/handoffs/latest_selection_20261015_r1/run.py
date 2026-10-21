"""Exact checkout install, latest selection, gate and rollback; no network/model."""
import argparse,gzip,importlib.util,json,os,subprocess,sys,types
from pathlib import Path
import installer as ins
from compose import compose,resources
H=Path(__file__).resolve().parent

def run(cmd,root,capture=False):
 r=subprocess.run(list(map(str,cmd)),cwd=root,env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),'PYTHONDONTWRITEBYTECODE':'1','LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'AD_WORKER_ENABLED':'0','GENOS_AUTO_WARMUP':'0'},text=True,capture_output=capture)
 if r.returncode:
  if capture:print(r.stdout+r.stderr,flush=True)
  raise RuntimeError('command failed exit '+str(r.returncode))
 return r

def generation(root,explicit):
 def load(name,path):
  s=importlib.util.spec_from_file_location(name,root/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
 paths=load('latest_fixed_paths','02_BACKEND/semantic_runtime/deployment_paths.py');selector=load('latest_generation','06_TOOLS/COMMANDS/genos_generation_e2e.py');env=dict(os.environ);config=paths.install(root,environment=env)
 g=selector.selected_generation(explicit,settings=env) if config else (selector.selected_generation(explicit) if explicit else selector.operator_generation(root))
 paths.verify_generation(config,g);os.environ['GENOS_GENERATION']=str(g);print('GENERATION='+str(g),flush=True);return g

def scanner(root,payload):
 sys.path.insert(0,str(root/'02_BACKEND'))
 for n in ('semantic_runtime.filename_versions','semantic_runtime.search_selection','lawrag.pipeline.search_selection'):
  rel='02_BACKEND/'+n.replace('.','/')+'.py';m=types.ModuleType(n);m.__file__=str(root/rel);sys.modules[n]=m;exec(compile(payload[rel],m.__file__,'exec'),m.__dict__)
 return m

def state(v):ins.atomic(H/'STATUS.json',ins.encoded(v))
def readstate():return json.loads((H/'STATUS.json').read_text())
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['check','install','apply','status','gate','undo'],nargs='?',default='install');p.add_argument('--root',type=Path,default=Path(os.environ.get('GENOS_DEV_ROOT',str(Path.home()/'DEV'))));p.add_argument('--generation',type=Path);p.add_argument('--exceptions',type=Path,default=Path(os.environ.get('LATEST_EXCEPTIONS_FILE',str(H/'FILENAME_EXCEPTIONS.json'))));a=p.parse_args();root=a.root.expanduser().resolve(strict=True)
 print('CODE_ROOT='+str(root)+' PYTHON='+sys.executable+' VERSION='+sys.version,flush=True)
 if Path(run(['git','rev-parse','--show-toplevel'],root,True).stdout.strip()).resolve()!=root:raise ValueError('existing Git checkout required')
 cli=[sys.executable,'-m','lawrag.pipeline.search_selection']
 with ins.locked(root):
  manifest=json.loads((root/'CODE_MANIFEST.json').read_text());already=manifest.get('cumulative_mail',{}).get('revision')==ins.VERSION
  if already:
   if not (H/'EFFECTIVE_SPEC.json.gz').exists():raise ValueError('Use the same TRANSFER run state; sealed effective spec missing')
   spec=json.loads(gzip.decompress((H/'EFFECTIVE_SPEC.json.gz').read_bytes()));ins.verify(root,spec);payload=ins.inventory(root,manifest)
  else:
   if a.action in ('status','gate','undo'):raise ValueError('latest selection code not installed')
   spec,payload=compose(root)
   raw=gzip.compress(ins.encoded(spec),mtime=0)
   if (H/'EFFECTIVE_SPEC.json.gz').exists() and (H/'EFFECTIVE_SPEC.json.gz').read_bytes()!=raw:raise ValueError('checkout differs from prepared state')
   ins.atomic(H/'EFFECTIVE_SPEC.json.gz',raw)
  g=generation(root,a.generation)
  if a.action=='undo':
   s=readstate();backup=Path(s['backup']);ins.undo(root,backup,check_only=True)
   if s.get('selection_receipt'):run([*cli,'rollback','--receipt',s['selection_receipt']],root)
   ins.undo(root,backup);s['phase']='RESTORED_REDEPLOY_PREVIOUS_REVISION';state(s);return
  if a.action in ('status','gate'):
   s=readstate()
   if s['code_root']!=str(root) or s['generation']!=str(g):raise ValueError('state binding changed')
   value=json.loads(run([*cli,'status','--generation',g],root,True).stdout)
   if value['selection_sha256']!=s['selection_sha256']:raise ValueError('selection differs from installed receipt')
   if a.action=='gate':
    backup=Path(s['backup']);receipt=json.loads((backup/'receipt.json').read_text());archive=backup/'APPLIED_CODE.zip'
    if ins.sha(archive.read_bytes())!=receipt['code_zip_sha256']:raise ValueError('gate archive changed')
    run([sys.executable,root/'06_TOOLS/COMMANDS/genos_release_gate.py','--code-zip',archive,'--deploy-root',root,'--generation',g],root)
    s['phase']='GATE_PASSED_PUSH_REVISION_WORKFLOW_PENDING';s['commit']=run(['git','rev-parse','HEAD'],root,True).stdout.strip();state(s)
   print(json.dumps(value,ensure_ascii=False));return
  value=scanner(root,payload).plan(g,latest=True,exceptions=a.exceptions);raw=ins.encoded(value);plan=H/('SELECTION_PLAN-'+ins.sha(raw)[:16]+'.json');ins.atomic(plan,raw)
  from comparison import write_comparison
  print('COMPARE='+str(write_comparison(value,H/('COMPARE-'+ins.sha(raw)[:16]))),flush=True)
  print(json.dumps({'latest_plan':value['counts'],'exceptions':value['exception_results'],'rag_applied':False},ensure_ascii=False),flush=True)
  if a.action=='check':print('CHECK PASS; no code or RAG selection changed');return
  backups=H/'backups';backups.mkdir(exist_ok=True);ins.apply(root,spec,backups)
  found=[]
  digest=ins.sha((root/'CODE_MANIFEST.json').read_bytes())
  for r in backups.glob('backup-*/receipt.json'):
   v=json.loads(r.read_text())
   if v.get('state')=='VERIFIED' and v.get('code_manifest_sha256')==digest:found.append(r.parent)
  if len(found)!=1:raise ValueError('exact applied backup ambiguous or missing')
  previous=readstate() if (H/'STATUS.json').exists() else {}
  s={'phase':'CODE_APPLIED_SELECTION_PENDING','code_root':str(root),'generation':str(g),'generation_manifest_sha256':ins.sha((g/'manifest.json').read_bytes()),'backup':str(found[0]),'python':sys.executable,'version':sys.version,'code_serving_revision':None,'workflow_test':'NOT_RUN','plan':str(plan)}
  if previous.get('selection_receipt'):s['selection_receipt']=previous['selection_receipt']
  state(s)
  try:
   applied=json.loads(run([*cli,'apply','--plan',plan],root,True).stdout)
   if applied.get('receipt'):s['selection_receipt']=applied['receipt']
   s['selection_sha256']=applied['selection_sha256'];s['phase']='CODE_AND_LATEST_APPLIED_DEPLOYMENT_PENDING';state(s)
   run([*cli,'status','--generation',g],root)
  except Exception:
   s['phase']='CODE_APPLIED_SELECTION_FAILED';state(s);raise
  print('LATEST_SELECTION_APPLIED; commit/gate/push/new revision/SSE/workflow pending',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:print('LATEST_SELECTION_FAILED: '+str(e),file=sys.stderr,flush=True);raise SystemExit(1)
