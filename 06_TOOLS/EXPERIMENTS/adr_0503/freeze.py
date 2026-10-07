"""Freeze two scoped copies and inputs before live calls; preserve parent records."""
import json,hashlib,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe';P=R/'04_EXPERIMENTS/ADR/ADR-0498-gemma4-fp8-compatible-schema-cm51-fsc10'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 target=A/'artifacts/frozen-design.json';assert not target.exists()
 m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');policy=A/'artifacts/gemma-policy.json';gen=R/prod['generation'];source=read(gen/'manifest.json')
 previous=read(P/'artifacts/frozen-design.json');authorization=previous['export_authorization'].copy()
 assert authorization['scope_document_ids']==prod['public_scope_document_ids']
 assert sha(gen/'store.sqlite')==source['store_sha256']==authorization['source_store_sha256']
 for row in authorization['document_provenance']:
  assert sha(R/'01_DATA/RAW'/row['raw_relative_path'])==row['raw_sha256']
 authpath=R/'08_DEPLOYMENT/CONFIG/legal-source-export.json';assert read(authpath)['enabled']
 assert sha(authpath)==authorization['source_authorization_sha256']
 authorization.update(experiment_policy_path=str(policy.relative_to(R)),policy_sha256=sha(policy),basis='Existing hash-verified public corpus authorization and current explicit user request to test Gemma performance; no private data.',parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'))
 write(A/'artifacts/export-rebinding.json',authorization)
 paths=[A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',policy,A/'artifacts/export-rebinding.json',authpath,gen/'manifest.json',gen/'navigation/manifest.json',gen/'fulltext/manifest.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/EXPERIMENT_OPENROUTER_PROXY.json']
 paths=[p for p in paths if p.exists()]
 runtime=R/previous['runtime_root'];paths+=sorted(p for p in runtime.rglob('*') if p.is_file())
 paths+=sorted(Path(__file__).parent.glob('*.py'))
 candidates=[]
 for arm in ['baseline','obligations']:
  C=R/'02_BACKEND/lawrag/research/candidates/adr_0503'/arm;cm=read(C/'candidate.json');rev=cm['revisions'][-1];paths.append(C/'candidate.json')
  for row in rev['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
  candidates.append({'candidate_id':arm,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(Path(__file__).with_name('run_probe.py').relative_to(R)),'runner_sha256':sha(Path(__file__).with_name('run_probe.py'))})
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates)
 write(A/'실험/manifest.json',m)
 write(target,{'runtime_root':previous['runtime_root'],'arms':['baseline','obligations'],'model':'google/gemma-4-31b-it','design':m['design'],'runs':m['runs'],'export_authorization':authorization,'file_hashes':{str(p.relative_to(R)):sha(p) for p in paths},'semantic_quality_measured':False,'limitations':['7 in-sample public cases once per arm','Existing source and gold versions; no new legal-currency certification','Separate Qwen evaluator twice with swapped labels; no human calibration','MAIN and GENOS unchanged']})
 print('Frozen',len(paths),'inputs; public source fingerprint verified; no calls')
if __name__=='__main__':main()
