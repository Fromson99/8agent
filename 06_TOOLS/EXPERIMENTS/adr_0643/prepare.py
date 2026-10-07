from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0643-shortcut-generation-compatible';D=A/'artifacts/design';OLD=R/'04_EXPERIMENTS/ADR/ADR-0642-shortcut-main-integration-holdout';C=R/'02_BACKEND/lawrag/research/candidates/adr_0643/integrated';code=C/'snapshot'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
config=read(code/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 p=code/entry['manifest'];v=read(p)
 for f in v['files']:v['files'][f]=sha(code/f)
 put(p,v);entry['sha256']=sha(p)
put(code/'00_SYSTEM/PIPELINE.json',config)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
for name in ['inputs.json','gold.json','bindings.json']:
 value=read(OLD/'artifacts/design'/name)
 if name=='bindings.json':value['candidate']=str(C.relative_to(R))
 put(D/name,value)
repair=read(OLD/'artifacts/run-001/accounting-coordinate-repair.json');put(D/'coordinates.json',repair['coordinates'])
m=read(A/'실험/manifest.json');old=read(OLD/'실험/manifest.json')
for field in ['design','llm_policy','dataset','retrieval_accounting']:m[field]=old[field]
m['phase']='probe';m['in_sample']=True;m['decision_eligible']=False
m['lineage']['hypothesis_delta']='Pin exact active glossary compiler; bounded compiler pages with atomic cursor/build commit; preserve removed legacy facts as unknown.'
m['design']['hypothesis']='Selected-generation compiler pin repairs the pre-model integration failure without weakening cache validation.'
m['design']['success_criteria']=old['design']['success_criteria'].replace('All 81 prior','All 85 prior')+' Known cases are regression evidence only; no MAIN eligibility.'
m['design']['arms'][0]['derived_from']=['ADR-0642-experiment-v1/integrated']
m['design']['arms'][1]['changes']='ADR0642 integration plus exact active glossary compiler, bounded DB compiler pages, partial-context OPEN gate, atomic build/cursor and removed-fact migration.'
c=read(C/'candidate.json');rev=c['revisions'][0]
m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0643/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0643/run.py')}]
m['dataset'].update(name='ADR0642 three observed public-law regressions',version='20261005-regression-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),caveat='Already observed in ADR0642. Not a new holdout; stored-source version only.')
m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),sha256=None)
m['runs'][0].update(purpose='primary',selection_rule='All3 previously observed cases; no case replacement or retry. Both arms fresh current execution.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m);put(D/'freeze.json',{'files':{str(p.relative_to(R)):sha(p) for p in D.glob('*.json')},'success_criteria':m['design']['success_criteria']})
print('frozen regression candidate and inputs')
