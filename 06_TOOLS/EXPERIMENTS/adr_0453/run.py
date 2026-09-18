from pathlib import Path
import json,hashlib,importlib.util,sys,time
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0453-gemini-schema-400-diagnosis';A=D/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0453/transport'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
cm=read(C/'candidate.json');rev=cm['revisions'][-1]
for f in rev['files']:assert sha(R/f['frozen_path'])==f['snapshot_sha256']
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
base=C/'revisions'/rev['revision_id']/'snapshot';variants=load('schema_diagnostic',base/'02_BACKEND/semantic_runtime/schema_diagnostic.py');clientmod=load('diagnostic_client',base/'02_BACKEND/lawrag/research/experiment_client.py')
if '--prepare' in sys.argv:
 m=read(D/'실험/manifest.json');m['design']['code_isolation']['candidates']=[{'candidate_id':'transport','experiment_id':m['experiment_id'],'arm_id':'transport','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(Path(__file__).relative_to(R)),'runner_sha256':sha(Path(__file__))}];(D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');paths=[Path(__file__),A/'source-request.json',A/'design-before-snapshot.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',C/'candidate.json']+[R/f['frozen_path'] for f in rev['files']];new(A/'input-lock.json',{str(p.relative_to(R)):sha(p) for p in paths});new(A/'pre-call-manifest.json',m);print('sealed');raise SystemExit
if (A/'results.json').exists() or (A/'calls').exists():raise ValueError('no rerun')
for p,h in read(A/'input-lock.json').items():assert sha(R/p)==h
request=read(A/'source-request.json');rows=[]
for repeat in [1,2]:
 for name in variants.NAMES[::1 if repeat==1 else -1]:
  system,data,schema=variants.variant(request,name);client=clientmod.GeminiExperimentClient(R,A/'calls'/f'{repeat}-{name}',max_calls=1);start=time.monotonic();out=None;error=None
  try:out=client.generate(system,data,schema,phase='transport_diagnostic')
  except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
  row={'repeat':repeat,'variant':name,'arm_id':'baseline' if name=='original' else 'transport','accepted':out is not None,'error':error,'output':out,'calls':client.calls,'usage':client.usage,'seconds':time.monotonic()-start};rows.append(row);new(A/'runs'/f'{repeat}-{name}.json',row);print(json.dumps({k:row[k] for k in ['repeat','variant','accepted','error']},ensure_ascii=False),flush=True)
new(A/'results.json',{'rows':rows,'summary':{n:sum(r['accepted'] for r in rows if r['variant']==n) for n in variants.NAMES},'meaning':'request acceptance only, no product tool execution','input_drift':[p for p,h in read(A/'input-lock.json').items() if sha(R/p)!=h]})
