from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0931-general-research-evidence-update';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);assert pointer['generation']==89
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
previous=R/'04_EXPERIMENTS/ADR/ADR-0930-connected-read-review-fix'
cases=read(previous/'artifacts/design/cases.json');put(D/'cases.json',cases)
criteria={'hypothesis':'Explicit question-grounded comparison fields, semantic priority of bounded follow-up tasks, and source-bound incremental review preserve relevant evidence better than numeric fallback, insertion-order tasks and full previous-row rewriting.',
 'required':['RP registry-order fix preserved as an independent frozen control; general candidate adds no compact locator projection and no question/term/article specific rules.',
 'Same four known requests on both freshly executed arms return sourced output with original/scope/hash/state and saved/duplicate consumer integrity.',
 'Question fields are explicit; numeric alone does not create numerator/denominator tasks. Every selected requirement is grounded in the user question.',
 'Follow-up execution follows model-declared CORE/DEPENDENCY/CONTEXT priority and exact target tie-break; same two-acquisition and physical-call/deadline limits.',
 'Every new evidence in follow-up review receives USED/CONTEXT/UNRELATED/UNRESOLVED reasoning; USED mechanically links to a changed item citation, untouched prior items remain preserved.',
 'Offline original/answer audit checks all previously supported core subjects, applicability/exception and known missing source routes; no approved legal gold is asserted.',
 'Relevant normal/failure/recovery/repeat/budget/resume/ACL/hash and actual service-path tests pass; legacy and non-comparison behavior remains available.'],
 'failure':['Source/ACL/hash/state/consumer regression','RP missing-law crash or empty answer','Previously supported core source/issue lost without source-grounded inapplicability explanation','New original silently ignored without update disposition','Question-specific code or answer injection'],
 'controls':'Selected MAIN89 code/data/profile/Qwen3.8 ParasailFP8 none and same model40/tool1024/1800s, parent recoveries2; both arms contain only preserved RP fix in common; ADR0930 locator compression excluded.',
 'selection':'Fresh paired four known public synthetic topics; alternating arm order by case, exactly one request per arm/case, no outcome-adaptive reruns. Historical ADR0929/0930/0925 observations audited separately, not treated as fresh control.',
 'failure_owner':'Workflow model adapter owns its one schema correction; native source output_contract owns its existing one correction; gateway owns transport retry. Mechanical invalid IDs/citations/USED linkage reject within that same budget; semantic uncertainty keeps originals and explanatory unresolved status, does not trigger forced legal repair. State counters/deadlines and completed acquisition receipts survive resume.',
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'max_new_calls':320,'wall_seconds_per_request':1800},
 'latency_limit':'Per request <= existing1800s; report paired latency/input/output/calls and any >25% regression; do not claim population improvement from four known samples.',
 'in_sample':True,'decision_eligible':False,'main_changed':False,'genos_executed':False}
put(D/'criteria.json',criteria)
audit_requirements={'provision-comparison':['3-8 provision/reserve distinction; no substitute institution scope'],
 'pf-downgrade':['3-7 classification, annex7 and3-8 provisioning','17-1 grade/classification mapping when read; previous missing must be revised or explained','3-24-4 exception investigated or explained with source; distinguish financial investment and merchant bank scope'],
 'rp-bond-scope':['5-18 covered securities and BBB grade; conditional automatic investment top3 distinct','Do not attribute4-89-2 grade to5-18; linked181/124-2 acquired as needed'],
 'leverage':['3-6 definition and numerator/denominator','3-24-4 applicable special rule and3-26(7) linkage','Internal absence is unconfirmed, not proven']}
put(D/'offline-audit-only.json',audit_requirements)
schedule=[]
for i,c in enumerate(cases):
 for arm in (('rp_only','generalized') if i%2==0 else ('generalized','rp_only')):schedule.append({'arm':arm,'case_id':c['id']})
put(D/'schedule.json',schedule)
names=sorted(release['files']);put(D/'serving-files.json',names)
put(D/'working-before.json',{n:sha(R/n) for n in names})
put(D/'working-drift.json',[{'path':n,'active':release['files'][n],'working':sha(R/n)} for n in names if sha(R/n)!=release['files'][n]])
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Evidence/issue retention with question-grounded fields and auditable incremental updates',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0930-experiment-v1/fixed'],'changes':'Completed ADR0930 historical reference only; not re-executed','controls':criteria['controls']},{'id':'rp_only','role':'candidate','derived_from':['baseline'],'changes':'MAIN89 plus only previously tested new-document registration fix; remove three PF compact-input changes and repin','controls':criteria['controls']},{'id':'generalized','role':'candidate','derived_from':['rp_only'],'changes':criteria['hypothesis'],'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['rp_only','generalized'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='same-known-cm-three-plus-leverage',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':320}]
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},{'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','rp_only','generalized')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='Exact read/return/citation identities; approved legal gold unavailable.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
rp=R/'02_BACKEND/lawrag/research/candidates/adr_0930/fixed/revisions/rev-007/snapshot/02_BACKEND/semantic_runtime/legal_agent/law_navigation.py'
for arm in ('rp_only','generalized'):
 candidate=arm.replace('_','-')
 cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',candidate,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
 for n in names:cmd+=['--source',n]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0931'/candidate/'snapshot'
 for n in names:
  if sha(R/n)!=release['files'][n]:(C/n).write_bytes((R/release['code_root']/n).read_bytes())
 (C/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py').write_bytes(rp.read_bytes())
print('Frozen design and isolated MAIN89+RP snapshots prepared; active/working product unchanged.')
