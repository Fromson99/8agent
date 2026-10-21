from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0930-connected-read-review-fix';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path'])
assert pointer['generation']==89
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
P=R/'04_EXPERIMENTS/ADR/ADR-0929-other-cm-unstarted-pairs'
cases=read(P/'artifacts/design/cases.json')
cases.append({'id':'leverage','question':'대사: 레버리지비율 관련한 외부 규정은 무엇이고, 내부 규정에는 어떻게 반영되어있냐','api_type':'WORKFLOW_RUN','workflow_id':'risk_team_compare_workflow','origin':'Previously observed known leverage question; not legal holdout.'})
put(D/'cases.json',cases)
criteria={'hypothesis':'Register an offered, scope-validated new document before recording its explicit read decision; compact only locator presentation to avoid redundant whole-field packet reviews while retaining every source and selectable target.',
 'required':['RP new-document read reaches normal original return without missing-law KeyError; rejected targets never register or consume reads.',
 'All four known requests return substantive sourced output and saved/duplicate consumers agree without additional model calls.',
 'PF ITEMS review calls below3; token/latency compared but provider timing and stochastic search are disclosed.',
 'Every offered locator ID remains selectable through the unchanged full provenance validator; no source text/span, scope, version, budget or lead verification is removed.',
 'Offline per-question audit records read/returned/cited core originals and any prior supported issue loss; leverage3-6,3-24-4,3-26(7) remain audit-only checks.',
 'Unchanged baseline contracts plus new cross-document, scope, resume and compact-locator contracts pass. Existing failures remain separately disclosed.'],
 'failure':['New source/ACL/hash/state/consumer failure','RP empty/crashed answer','Lost prior supported core original/issue','PF repeated review count not reduced'],
 'controls':'MAIN89 code/data/profile/model baseline. Only law registry sequencing and locator model projection plus explicit pins change; concurrent GENOS working changes preserved outside serving candidate.',
 'selection':'One candidate request each, RP then PF then provision then leverage; inherit completed MAIN89 CM observations by hash and ADR0925 leverage observation with exact equivalence limitations. No adaptive retries.',
 'failure_owner':'Existing navigation availability rejects invalid/stale/budget-exhausted targets before registry mutation; reader owns source/hash verification and interrupted read receipt. Existing gateway owns transport retry and parent adapter schema repair; no new retry or budget reset. Uncertainty returns originals as partial.',
 'limits':{'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10,'model_calls_per_request':40,'wall_seconds_per_request':1800,'max_new_calls':160},
 'in_sample':True,'decision_eligible':False,'legal_holdout':False,'main_changed':False,'genos_executed':False,
 'promotion':'Known-case probe alone cannot authorize integration or MAIN promotion; independent frozen finite software qualification required.'}
put(D/'criteria.json',criteria)
put(D/'schedule.json',[{'arm':'fixed','case_id':c} for c in ('rp-bond-scope','pf-downgrade','provision-comparison','leverage')])
names=sorted(release['files']);put(D/'serving-files.json',names)
put(D/'working-before.json',{n:sha(R/n) for n in names})
put(D/'working-drift.json',[{'path':n,'active':release['files'][n],'working':sha(R/n)} for n in names if sha(R/n)!=release['files'][n]])
inherited={}
for c in cases:
 p=P/'artifacts/run-001/current'/c['id'] if c['id']!='leverage' else R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation/artifacts/run-001/observed/leverage-comparison'
 inherited[c['id']]={'root':str(p.relative_to(R)),'files':{n:sha(p/n) for n in ('result.json','audit.json','answer.txt') if (p/n).exists()}}
put(D/'inherited.json',inherited)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='New document read/return integrity and unchanged-source PF item review count',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0929-experiment-v1/current'],'changes':'Inherited completed MAIN89 observations; leverage related parent disclosed','controls':criteria['controls']},{'id':'fixed','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['baseline','fixed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='known-cm-three-plus-leverage',version='20261019-r1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':160}]
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},{'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},{'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','fixed')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='Exact read/return/citation identities; approved legal gold unavailable.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','fixed','--experiment-id',m['experiment_id'],'--arm-id','fixed','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0930/fixed/snapshot'
# Preserve concurrent working GENOS changes; experimental serving uses exact selected release versions.
for n in names:
 if sha(R/n)!=release['files'][n]:(C/n).write_bytes((R/release['code_root']/n).read_bytes())
print('Design and snapshot created; active MAIN89 and working product unchanged.')
