from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0676/integrated'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/pointer['manifest_path']);cm=read(C/'candidate.json');rev=cm['revisions'][-1]
b={'candidate':str(C.relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'baseline_code':base['code_root'],'baseline_release':pointer,'stage':read(D/'release-rebase.json')['stage'],'source_generation':base['data_path'],'active_pointer_hash':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')};put(D/'bindings.json',b)
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0676/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0676/run_case.py')}])
m['dataset']['sha256']=sha(D/'dataset.json');m['design']['arms'][1].update(changes='ADR0675 reviewed integration plus acquisition/reinspection distinction, full control-mode corrective union and requested conditional scope preservation',controls='Same active generation and public145 scope; same model/provider/budgets; gold never supplied to product')
put(A/'실험/manifest.json',m)
paths=[D/'dataset.json',D/'gold.json',D/'rubric.json',D/'judge-contract.json',R/'06_TOOLS/EXPERIMENTS/adr_0676/grade.py',D/'bindings.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',R/'06_TOOLS/EXPERIMENTS/adr_0676/run_case.py',R/base['data_path']/'manifest.json',R/base['data_path']/'store.sqlite',R/base['data_path']/'navigation/manifest.json',R/base['data_path']/'fulltext/manifest.json',C/'candidate.json']
files={str(p.relative_to(R)):sha(p) for p in paths};files.update({str((R/base['code_root']/p).relative_to(R)):h for p,h in base['files'].items()})
put(D/'freeze.json',{'files':files,'criteria':m['design']['success_criteria'],'gold_separation':True,'primary_size':5,'in_sample':True,'decision_eligible':False});print('sealed probe before model calls')
