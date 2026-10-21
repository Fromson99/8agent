from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/p['manifest_path'])
qualified=read(R/'09_ARTIFACTS/AUDITS/20261020-research-continuity/integration.json')
for n,h in qualified['serving_files'].items():assert sha(R/n)==h,n
put(D/'baseline.json',{'pointer':p,'manifest':release});put(D/'working-before.json',qualified['serving_files'])
put(D/'baseline-binding.json',{'code_root':release['code_root'],'serving_files':release['files'],'release_id':p['release_id'],'generation':p['generation']})
cases=[c for c in read(R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch/artifacts/design/cases.json') if c['id'] in ('rp-bond-scope','leverage')]
put(D/'cases.json',cases)
criteria={'hypothesis':'The integrated continuity change reduces source-free repeated exploration without excessive incremental prompt cost or premature loss of original evidence.',
 'primary_metric':'Provider-reported total and per-call prompt tokens, separately from added continuity metadata chars on identical captured source/decision state.',
 'success':['All four terminal API responses and saved/duplicate consumers remain consistent; no source/hash/side/budget regression.',
 'Added continuity metadata <=10% of actual message characters at median and <=20% at maximum; any breach reported as excessive metadata, never hidden by lower call count.',
 'Per-case total provider input tokens <=125% of fresh baseline or report material growth with exact path/call/source differences.',
 'No new source mismatch or deterministic premature no-progress shutdown that drops already-acquired originals; real source selection and missed relevant known roots reviewed separately.'],
 'failure':['Any raw source/hash/ACL mismatch','Resource guard stop','Any above prompt growth threshold breach'],
 'selection':'Two known questions, RP and leverage; one fresh request per arm/case. Counterbalanced order modifiedRP,baselineRP,baselineLeverage,modifiedLeverage. No adaptive reruns.',
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'max_new_calls':160,'calls_per_request':40,'wall_seconds_per_request':1800},
 'controls':'Same current MAIN90 data/search selection, current model policy Qwen3.8/Parasail FP8/no reasoning/no fallback and original approved workflow source grant; same profile and input questions; isolated fresh runtime per request. No new source authorization. Product code unchanged.',
 'limitations':['Known questions; probe, not holdout or legal gold.','Two stochastic paths, one observation each; latency and end-to-end token delta are descriptive.','Added metadata counterfactual excludes changed static instructions, which remain in actual provider totals.','risk_cm originals/annotations/gold are not product inputs. Existing approved workflow grant controls documents.'],
 'offline_only':{'rp-bond-scope':['5-18 direct eligible securities and grade, distinguish neighboring rules'], 'leverage':['3-6 definition ratio,3-24-4 special rule,3-26(7) linkage; internal not-found not proof of absence']}}
put(D/'criteria.json',criteria)
put(D/'schedule.json',[{'arm':a,'case_id':c} for a,c in [('modified','rp-bond-scope'),('baseline','rp-bond-scope'),('baseline','leverage'),('modified','leverage')]])
m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0936-experiment-v1/fixed'],'changes':'Fresh MAIN90 selected release','controls':criteria['controls']},{'id':'modified','role':'candidate','derived_from':['ADR-0939-experiment-v1/qualified'],'changes':'Exact integrated 1.17.0 continuity code, no new product edits','controls':criteria['controls']}]
# Baseline is an additional completed parent, not an inferred old manifest.
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch/실험/manifest.json')
parent_ref=next(x for x in m['lineage']['parents'] if x['arm_id']=='qualified')
# Keep the formal parent qualified; baseline serving release is immutable observational control.
m['design']['arms'][0]['derived_from']=['ADR-0939-experiment-v1/qualified']
m['runs'][0].update(arm_ids=['baseline','modified'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='two-known-public-topics-prompt-cost',version='20261020-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':160}]
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},{'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','modified')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='Known-topic diagnostic, no approved legal gold.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','modified','--experiment-id',m['experiment_id'],'--arm-id','modified','--run-id','run-001']
for n in qualified['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in ('live.py','audit.py','run_sequence.py','deadline.py','archive.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0936'/n).read_text().replace('ADR-0936-durable-research-review-patch','ADR-0940-research-continuity-prompt-cost').replace('adr0936-','adr0940-')
 if n=='live.py':s=s.replace("'request_bytes':size(body),'schemas_valid':True", "'request_bytes':size(body),'schemas_valid':True,**__import__('prompt_metrics').metrics(provider_body)")
 (T/n).write_text(s)
print('Design fixed; unchanged product isolated; four sequential fresh requests planned.')
