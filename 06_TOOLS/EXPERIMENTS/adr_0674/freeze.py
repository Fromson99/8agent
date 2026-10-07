from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0674-investigation-control-integration';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0674/integrated'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/pointer['manifest_path']);cm=read(C/'candidate.json');rev=cm['revisions'][-1]
b={'candidate':str(C.relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'baseline_code':base['code_root'],'baseline_release':pointer,'stage':read(D/'release-rebase.json')['stage'],'source_generation':base['data_path'],'active_pointer_hash':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')};put(D/'bindings.json',b)
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001','package-001','main-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0674/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0674/run_case.py')}])
m['design']['arms'][1].update(changes='Latest working tree and audited completed chain features plus exact scope delivery/adoption, saved reinspection, immutable reason references, issue gaps and bounded ASSESS/SELECT reentry; legacy v5 mode retained',controls='Same generation, exported public scope, Qwen3.8 model/provider, runtime budget; frozen full serving inventory, isolated runtime, no gold in product')
m['dataset'].update(name='32 distinct public article groups, 8 requirement types',version='20261006-investigation-holdout-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='All 32 preselected independent article groups, one product run per arm with bounded built-in repairs; no replacement or hidden reruns; all failures scored incorrect',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[('catalogue','source'),('recall','recall'),('acquired','select'),('presented','present')]
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:[{'stage_id':sid,'kind':kind,'parent_stage_ids':([] if i==0 else [stages[i-1][0]])} for i,(sid,kind) in enumerate(stages)] for arm in ['baseline','integrated']}
# Stage field shape is completed against stable validator before calls.
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None,summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING')
put(A/'실험/manifest.json',m)
paths=[D/'dataset.json',D/'gold.json',D/'rubric.json',D/'bindings.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',R/'06_TOOLS/EXPERIMENTS/adr_0674/run_case.py',R/base['data_path']/'manifest.json',R/base['data_path']/'store.sqlite',R/base['data_path']/'navigation/manifest.json',R/base['data_path']/'fulltext/manifest.json',C/'candidate.json']
files={str(p.relative_to(R)):sha(p) for p in paths};files.update({str((R/base['code_root']/p).relative_to(R)):h for p,h in base['files'].items()})
put(D/'freeze.json',{'files':files,'criteria':m['design']['success_criteria'],'gold_separation':True,'primary_size':32});print('sealed before any real model call')
