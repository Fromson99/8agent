from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1171-source-goal-execution-model-probe';D=A/'artifacts/design';T=Path(__file__).parent;P=R/'04_EXPERIMENTS/ADR/ADR-1170-supervisor-pagination-contract';O=R/'04_EXPERIMENTS/ADR/ADR-1169-supervisor-cm3-memory-reclaimed'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
criteria={'hypothesis':'Explicit original-source goals retain document/coordinate identity across model actions; server dispatches exact offered lookup/read and prevents unresolved goals from becoming sufficient completion. Compare two pinned models at saved failed states before bounded CM3 live execution.',
'checks':['Exact law/article lookup and read via existing authorized executor','Persist goals on unrelated intermediate reads and across resume; no implicit legal adoption','Reject malformed/outside-scope target; ambiguous coordinates not guessed','Bound route attempts and final reserve; explicit grounded exclusions preserve record','Existing46 supervisor/page contracts and native API judgment/publication preserved','Saved001/007 states compare same inputs across Qwen3.8 and approved GenOS proxy, no gold in product'],
'comparison':{'cases':{'cm-001':'canonical008','cm-007':'canonical006'},'repeats':2,'models':['qwen/qwen3.8-27b','qwen/qwen3.5-122b-a10b'],'max_calls':8,'temperature':0,'reasoning':'off','fallback':False,'pass':'Each of two states must declare or execute the exact missing target twice (4/4), no invalid schema; evaluate raw choice and server-corrected action separately. Higher pass count, then lower total latency breaks ties. Larger model not assumed superior.','full_run_gate':'Only a model passing4/4 controlled next-step probes may execute CM001/007/009 once each. Max40physical/1024tools/1800sec each; batch max120. No model swaps/repeats after failure.'},
'failure':'Stop calls on unknown provider outcome, model/provider mismatch, source/ACL/hash violation. Technical fixture repairs preserve revisions before live calls. Semantic failures retained, no adaptive retry.',
'resource':{'startup_available_gib':5,'min_available_gib':3,'max_rss_gib':4,'max_address_gib':6,'min_disk_gib':20,'swap_growth_mib':128,'psi_policy':'Do not kill on global PSI alone while available>=3GiB and swap stable; retain PSI observation. RAM/RSS/swap limits still stop.','workers':1},
'scope':'Isolated MAIN112+1170 candidate only; no MAIN promotion, GENOS execution, email or git',
'authorization':{'source':'user_message','text':'다 구현해서 실험해봐','scope':'Implement the three proposed changes; saved-state comparison with registered Qwen default and GENOS proxy; gated actual CM3','fallback_allowed':False}}
put(D/'criteria.json',criteria)
for n in ('baseline.json','cases.json','corpus.json','authorization.json'):put(D/n,read(O/'artifacts/design'/n))
a=read(D/'authorization.json');a.update(user_request='다 구현해서 실험해봐',scope=criteria['scope'],max_model_calls=128);put(D/'authorization.json',a)
put(A/'artifacts/evaluation-only/cases.json',read(O/'artifacts/evaluation-only/cases.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact declared source-goal arrival and non-repeating controlled next action',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'controlled','role':'candidate','derived_from':['ADR-1170-experiment-v1/repaired'],'changes':'Explicit source goals, deterministic exact target dispatch, persistent outcome/termination control','controls':'MAIN112 data/budgets; same1170 supervisor/page behavior when feature off'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}})
m['runs'][0].update(arm_ids=['controlled'],selection_rule='Frozen saved001/007 next step2repeats/model; full CM3 only after4/4pass; technical contracts before model',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Known CM001/007 failure states and conditionally CM001/007/009',version='v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Technical and next-action probe; full retrieval accounting added before any gated full execution',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'Saved-state next-action probe with no new retrieval until gated full execution'});put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'controlled',present,experiment_id=m['experiment_id'],arm_id='controlled',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for n in ('common.py','freeze.py','check.py','test_supervisor.py','test_native_supervisor.py','test_supervisor_paging.py','api_fixture_integrated.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1170'/n).read_text().replace('ADR-1170-supervisor-pagination-contract','ADR-1171-source-goal-execution-model-probe').replace("'repaired'","'controlled'")
 (T/n).write_text(s)
p=T/'check.py';s=p.read_text().replace("str(T/'test_supervisor_paging.py')","str(T/'test_supervisor_paging.py'),str(T/'test_source_goals.py')");p.write_text(s)
print('reserved1171, copied459 parent files; criteria frozen before edits')
