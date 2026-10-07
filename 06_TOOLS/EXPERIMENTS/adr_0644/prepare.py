from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0644/integrated';code=C/'snapshot'
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
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine/artifacts/inputs.json');grant=read(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');source=parent['sources']
assert {s['document_id'] for s in source}<=set(grant['public_document_ids'])
g=R/'01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation';assert sha(g/'store.sqlite')==grant['source_store_sha256']
inputs={'initial_questions':['공개 합성 A사 B 투자자의 의무보유를 조사한다. 취득기간은 8개월이라는 가정이며 전문투자자 자격·취득 방식·한도·예외는 미확인이다.','별개의 공개 합성 C사 D 투자자는 취득기간이 2년3개월이라는 가정이다. A사 B의 사실을 복사하지 않고 전문투자자 정의와 필요한 조사를 따로 정리한다.'],'correction':'A사 B의 취득기간 가정을 8개월에서18개월로 정정한다. C사 D의 사실은 그대로다. 자격·취득 방식·한도·예외는 계속 미확인이다.','sources':source,'principal':{'user_id':'public-synthetic-related','team_id':'public-shortcut-research','authenticated':True,'document_ids':sorted({s['document_id'] for s in source})}}
put(D/'inputs.json',inputs)
m=read(A/'실험/manifest.json');m['in_sample']=True;m['decision_eligible']=False
m['lineage']['hypothesis_delta']='Bounded incremental records, explicit related-case compiler, prior unit comparison, source CAS/requeue and legacy artifact/review operation contracts.'
m['design'].update(hypothesis='Explicit related cases preserve distinct facts and delta input avoids rereading committed utterances; all generated legal claims remain unapproved.',primary_metric='Two actual compiler outputs admitted with exact provenance; second input excludes original events.',success_criteria='94 existing and added contract/regression tests plus6 child-process durability tests pass; two actual outputs admitted; prior immutable events omitted in second turn; no merged cross-case factual claims, no legal approval.',failure_criteria='Any contract failure, lost provenance, cross-case factual claim or actual compiler rejection blocks completion of this probe. MAIN remains blocked by ADR0643 quality/latency results regardless.',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
m['design']['arms'][0].update(changes='Completed ADR0643 snapshot and its failed MAIN comparison retained as structural reference; no baseline model rerun',controls='same public source bindings and parent code')
m['design']['arms'][1].update(changes='Incremental/related compiler, operation extensions and exact source recheck',controls='public synthetic records only; same Qwen3.8/Parasail FP8 policy')
c=read(C/'candidate.json');rev=c['revisions'][0];m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0644/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0644/run.py')}]
m['dataset'].update(name='public synthetic explicit related cases and preregistered correction',version='20261005-related-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True)
m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Compiler input provenance and delta contract only; no retrieval selection or legal answer quality comparison.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No product retrieval ranking or filtering measured',summary_run_id=None,artifact_path=None,sha256=None)
m['runs'][0].update(purpose='primary',selection_rule='Two fixed compiler turns: explicit related independent cases, then correction to only first case. No replacement or hidden retry.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'compiler','class':'product','model':'qwen/qwen3.8-27b','repeats':2}]
put(A/'실험/manifest.json',m)
files={str((D/'inputs.json').relative_to(R)):sha(D/'inputs.json'),'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json':sha(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),str((g/'store.sqlite').relative_to(R)):sha(g/'store.sqlite')}
put(D/'freeze.json',{'files':files,'criteria':m['design']['success_criteria']})
print('frozen')
