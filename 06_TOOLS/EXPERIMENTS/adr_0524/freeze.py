from pathlib import Path
import json,hashlib,copy,datetime
R=Path(__file__).resolve().parents[3];P=R/'04_EXPERIMENTS/ADR/ADR-0523-gemma-scoped-exploration-probe';A=R/'04_EXPERIMENTS/ADR/ADR-0524-gemma-fp8-scoped-retrieval';C=R/'02_BACKEND/lawrag/research/candidates/adr_0524/transport'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (A/'artifacts/frozen-design.json').exists()
f=read(P/'artifacts/frozen-design.json');m=read(A/'실험/manifest.json');parent=read(P/'실험/manifest.json');policy=A/'artifacts/gemma-policy.json'
grant=read(P/'artifacts/export-rebinding.json');grant.update(experiment_policy_path=str(policy.relative_to(R)),policy_sha256=sha(policy),basis='Current user gemma로 실험; public145 documents and six public questions. Separate fixed Parasail FP8 run after recorded DeepInfra provider overload; product logic and source scope unchanged.',parent_rebinding_sha256=sha(P/'artifacts/export-rebinding.json'));write(A/'artifacts/export-rebinding.json',grant)
m['lineage']['hypothesis_delta']='Repeat frozen paired Gemma experiment on separately pinned available FP8 provider; no product logic change.';m['design']=copy.deepcopy(parent['design']);m['llm_policy']=copy.deepcopy(parent['llm_policy']);m['runs']=copy.deepcopy(parent['runs']);m['runs'][0].update(status='planned',artifact_path=str((A/'artifacts/run-001/results.json').relative_to(R)),sha256='PENDING')
rev=read(C/'candidate.json')['revisions'][-1];runner=Path(__file__).with_name('run_probe.py');m['design']['code_isolation']['candidates']=[{'candidate_id':'transport','experiment_id':m['experiment_id'],'arm_id':'guarded','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)}]
ov={'schema_version':'user-authorized-openrouter-product-v1','policy_path':str(policy.relative_to(R)),'policy_sha256':sha(policy)};m['llm_policy']['experiment_override']=ov;m['gemma_binding']={**ov,'live_calls_planned_max':168,'live_calls':0};m['dataset']=copy.deepcopy(parent['dataset']);m['dataset']['frozen_source']=str((A/'product-cases.json').relative_to(R));m['retrieval_accounting']['stage_ledger'].update(mode='measured',not_applicable_reason=None);m['retrieval_accounting']['not_applicable_reason']='Awaiting measured run';write(A/'실험/manifest.json',m)
f.update(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),transport_path=rev['files'][0]['frozen_path'],export_authorization=grant,design=m['design'],runs=m['runs'],provider='Parasail FP8',parent_freeze={'path':str((P/'artifacts/frozen-design.json').relative_to(R)),'sha256':sha(P/'artifacts/frozen-design.json')})
f.pop('preflight_revision',None)
for path in [A/'PLAN.md',A/'product-cases.json',policy,A/'artifacts/export-rebinding.json',C/'candidate.json',*[R/x['frozen_path'] for x in rev['files']],*list(Path(__file__).parent.glob('*.py'))]:
 if path.name!='summarize.py':f['file_hashes'][str(path.relative_to(R))]=sha(path)
f['grader_only_hashes']={str((A/'gold-cases.json').relative_to(R)):sha(A/'gold-cases.json')};write(A/'artifacts/frozen-design.json',f)
print('Frozen provider-only retry before model sends',len(f['file_hashes']))
