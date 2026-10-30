from pathlib import Path
import json,hashlib,sys,os,runpy,importlib.util
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
f=read(D/'freeze.json')
for p,h in f['files'].items():assert sha(R/p)==h,'BINDING_CHANGED:'+p
case=sys.argv[1];assert case in ['health','cm-009','cm-007']
if case=='cm-007':
 prior=read(O/'live/cm-009/result.json')
 assert prior['unknown']==0 and prior['engine_code_unchanged'] and not (O/'live/cm-009/resource-stop.json').exists(),'BATCH_STOP'
 assert not any(x in prior.get('error','').upper() for x in ['RESOURCE','HASH','BINDING','SCOPE','FORBIDDEN','SWAP']),'BATCH_STOP_INTEGRITY'
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1');sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('gold_connector',R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
if case=='health':
 with mod.open_store(seconds=120,max_calls=100) as (store,request,transport):
  store.selection.require_latest()
  print(json.dumps({'passed':True,'documents':len(request.sources.allowed),'release_id':request.release_id,'sql_calls':len(transport.statements),'model_calls':0}))
else:
 mod.load_runtime();entry=R/f['entry'];sys.argv=[str(entry),case];runpy.run_path(str(entry),run_name='__main__')
