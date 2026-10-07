"""Freeze a public-only, isolated prompt measurement before any model request."""
import ast, hashlib, importlib.util, json, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0547-gemma-main-prompt-compaction-measurement'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); release=read(R/pointer['manifest_path']); old=R/release['code_root']
sys.path.insert(0,str(R/'02_BACKEND'))
spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.adr0547_old_prompts',old/'02_BACKEND/semantic_runtime/legal_agent/question_obligations.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod.PROMPTS['review'] += (' Write issue and reason text in Korean for a legal reviewer. Identify the document and article/paragraph when supplied, '
    'and the specific legal condition, exception, missing fact or source comparison to check. '
    'Do not put internal IDs, schema fields or runtime terminology in prose; keep identifier fields exactly as specified.')
assert len(mod.SYSTEM)==3330
print('baseline instruction lengths',len(mod.SYSTEM),len(mod.PROMPTS['review']))
write(A/'artifacts/baseline-prompts.json',{'system':mod.SYSTEM,'prompts':mod.PROMPTS,'source':str((old/'02_BACKEND/semantic_runtime/legal_agent/question_obligations.py').relative_to(R)),'source_sha256':sha(old/'02_BACKEND/semantic_runtime/legal_agent/question_obligations.py'),'reconstruction':'r3 frozen prompt constants + exact 325-character Korean review instruction from the pre-compaction workspace audit; runtime behavior otherwise current'})
write(A/'artifacts/product-cases.json',{'schema_version':'adr0547-public-cases-v1','cases':[
 {'case_id':'public-issue-01','question':'정관 변경의 결의요건은?\n(업무 문맥: 주주총회와 이사회의 권한 배분)'},
 {'case_id':'public-issue-02','question':'상법상 주식회사 이사회 결의 요건과 특별이해관계인의 의결권은?'},
 {'case_id':'public-issue-03','question':'상법상 주식회사 이사 선임의 결의요건과 집중투표제의 적용 조건은?'}]})
grant=read(old/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');write(A/'artifacts/public-grant.json',grant)
write(A/'artifacts/policy-snapshot.json',read(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'))
config=read(R/'00_SYSTEM/PIPELINE.json');deps={}
for node in config['profiles']['legal-rag']['nodes']:
 entry=config['engines'][node['engine']]; manifest=read(R/entry['manifest']);deps.update(manifest['files']);deps[entry['manifest']]=sha(R/entry['manifest'])
for p in ['00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py',pointer['manifest_path']]:deps[p]=sha(R/p)
write(A/'artifacts/control-code-hashes.json',deps)
settings=read(R/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json')
design={'schema_version':'adr0547-frozen-design-v1','experiment_id':'ADR-0547-experiment-v1',
 'model':'google/gemma-4-31b-it','provider_routing':read(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_routing'],'thinking':False,
 'generation':release['data_path'],'generation_manifest_sha256':release['data_manifest_sha256'],
 'local_grant_code_root':release['code_root'],'public_scope':grant['public_document_ids'],'immutable_export_allowed':False,
 'product_cases':'04_EXPERIMENTS/ADR/ADR-0547-gemma-main-prompt-compaction-measurement/artifacts/product-cases.json',
 'profile':settings,'case_order':['public-issue-01','public-issue-02','public-issue-03'],
 'e2e_arm_order':{'public-issue-01':['baseline','compact'],'public-issue-02':['compact','baseline'],'public-issue-03':['baseline','compact']},
 'fixed_replay_phases':{'compose':2,'review':1},
 'fixed_view_rule':'First baseline E2E model_view of this phase, else first compact E2E model_view. Same unmodified saved view for both arms and repeats. Missing phase is recorded as unmeasured, never fabricated.',
 'fixed_replay_arm_order':'AB then BA for compose; BA/AB alternate by case for review',
 'max_physical_calls':120,'per_call_timeout_seconds':180,'same_cache_policy':'provider default; cache counts are recorded, no hidden warmup model calls',
 'success_criteria':{'fixed_input_token_reduction_min':0.25,'fixed_compose_median_latency_reduction_min':0.20,'allowed_new_format_failures':0,'required_exact_source_preservation':True},
 'failure_criteria':'Token or latency threshold not met, new schema failures, or altered source text/coordinates. No claim of semantic noninferiority without an independent gold evaluation.',
 'semantic_quality':'unmeasured; source quotation/reference checks and final answer existence only, not legal correctness scores',
 'baseline_note':'Pre-compaction wire/phase instructions reconstructed from frozen r3 + recorded pre-compaction review suffix; same current pipeline, review-advisory policy and sources in both arms.',
 'main_wiring_unchanged':True,'new_model_calls_before_freeze':0}
write(A/'artifacts/design-draft.json',design)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Remove duplicate source/schema/navigation payload while retaining the same source contracts and current v5 behavior.'
m['design'].update(hypothesis='Compact requests reduce provider input tokens by >=25% and fixed-source compose median HTTP time by >=20% with no new schema errors.',primary_metric='paired fixed-view provider prompt_tokens and compose HTTP seconds',success_criteria=design['success_criteria'],failure_criteria=design['failure_criteria'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:
 arm['changes']='Recorded pre-compaction instructions, repeated schema/span text, compose navigation metadata' if arm['id']=='baseline' else 'Current user-requested v5 compact wire projection and phase-specific instructions'
 arm['controls']='Same current runtime, immutable source generation/public scope, Gemma Parasail FP8 thinking off, temperature 0, phase token/repair bounds. Fixed phase replay reuses exact identical server view.'
m['runs'][0].update(selection_rule='Three public corporate-law questions specified before all requests; one E2E pair each and fixed compose two pairs / review one pair each, alternating order.',case_ids=design['case_order'],artifact_path='04_EXPERIMENTS/ADR/ADR-0547-gemma-main-prompt-compaction-measurement/artifacts/run-001/result.json',status='planned')
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':design['model'],'repeats':1}]
m['dataset'].update(name='Three public corporate-law prompt-latency cases',version='20260928-v1',frozen_source=design['product_cases'],sha256=sha(A/'artifacts/product-cases.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting']['not_applicable_reason']='MAIN source generation/retrieval implementation unchanged; E2E source selections observed, fixed-view replay does no retrieval. No golden-recall or answer-quality experiment.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
write(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','compact','--experiment-id',m['experiment_id'],'--arm-id','compact','--run-id','run-001']
for p in ['02_BACKEND/semantic_runtime/legal_agent/gateway.py','02_BACKEND/semantic_runtime/legal_agent/question_obligations.py','02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py']:cmd+=['--source',p]
subprocess.run(cmd,cwd=R,check=True)
print('design drafted, public-only source generation and both arms pinned before model calls')
