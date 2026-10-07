from pathlib import Path
import json,hashlib,sys,importlib.util
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0673-investigation-chain-cm-six';C=R/'02_BACKEND/lawrag/research/candidates/adr_0673/chain-cm-six';S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));spec=importlib.util.spec_from_file_location('candidate_tools',R/'06_TOOLS/COMMANDS/adr_candidate.py');ac=importlib.util.module_from_spec(spec);spec.loader.exec_module(ac)
m=json.loads((C/'candidate.json').read_text());registered={x['target_path'] for x in m['files']}
for p in sorted(S.rglob('*')):
 if p.is_file() and str(p.relative_to(S)) not in registered:
  assert '__pycache__' not in p.parts
  target=str(p.relative_to(S));ac.register_file(C,target,upstream_state='present' if (R/target).is_file() else 'absent')
replacements={};newfile='02_BACKEND/semantic_runtime/legal_agent/investigation_chain.py'
def refresh(v):
 if isinstance(v,dict):
  for k,h in list(v.items()):
   if isinstance(h,str) and len(h)==64 and (S/k).is_file():v[k]=sha(S/k)
   else:refresh(h)
  if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in v:v[newfile]=sha(S/newfile)
 elif isinstance(v,list):
  for z in v:refresh(z)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 old=sha(p);x=json.loads(p.read_text());refresh(x);put(p,x);replacements[old]=sha(p)
x=json.loads((S/'00_SYSTEM/PIPELINE.json').read_text())
def pins(v):
 if isinstance(v,dict):
  for k,h in v.items():
   if isinstance(h,str) and h in replacements:v[k]=replacements[h]
   else:pins(h)
 elif isinstance(v,list):
  for z in v:pins(z)
pins(x);put(S/'00_SYSTEM/PIPELINE.json',x)
ac.refresh(C);ac.freeze(C);m=json.loads((C/'candidate.json').read_text());rev=m['revisions'][-1]
manifest=json.loads((A/'실험/manifest.json').read_text())
runner=R/'06_TOOLS/EXPERIMENTS/adr_0673/run_probe.py'
manifest['design']['code_isolation']['candidates']=[{'candidate_id':'chain-cm-six','experiment_id':manifest['experiment_id'],'arm_id':'chain-cm-six','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['sha256'] if 'sha256' in rev else rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
put(A/'실험/manifest.json',manifest)
put(A/'artifacts/design/frozen-design.json',{k:manifest[k] for k in ['design','dataset','runs','llm_policy','lineage']})
source=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation'
files=[runner,R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',source/'manifest.json',source/'store.sqlite',source/'navigation/manifest.json',source/'fulltext/manifest.json',source/'fulltext/units.sqlite',A/'artifacts/design/dataset.json',A/'artifacts/design/frozen-design.json',R/manifest['lineage']['parents'][0]['manifest_path']]
put(A/'artifacts/design/bindings.json',{'candidate':str(C.relative_to(R)),'revision_id':rev['revision_id'],'candidate_manifest_sha256':sha(C/'candidate.json'),'source_generation':str(source.relative_to(R)),'files':{str(p.relative_to(R)):sha(p) for p in files}})
print(json.dumps(manifest['design']['code_isolation']['candidates'],ensure_ascii=False))
