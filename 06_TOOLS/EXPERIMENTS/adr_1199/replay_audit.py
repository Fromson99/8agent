"""Read-only receipt for the replay checkpoint; preserve the runner failure."""
from common import *
P=ART/'saved1198-replay';r=read(P/'result.json');s=read(P/'final-state.json.gz')
st=next(iter(s['investigation_supervisor'].values()))
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1198-main117-live-cm007/artifacts/live/cm-007'
f=read(DES/'freeze-rev-001.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.contracts import digest
steps=s['action_chain']['steps']
research=[x for x in steps if x.get('action')=='RESEARCH']
target='article:af4d6957c006feaf9b4ed8b9'
checks={
 'four_stored_responses':len(r['stored_responses'])==4,
 'stored_supervisor_unchanged':r['recoveries'][0]['response_hash']==digest(read(parent/'canonical/004-output.json.gz')),
 'route_recovered':len(r['recoveries'])==1 and r['recoveries'][0]['authorized'] and r['recoveries'][0]['next_action']=='RESEARCH',
 'directive_rejection_preserved':len(st['directive_rejections'])==1 and any(x.get('directive_accepted') is False for x in st['coverage_review']),
 'research_actually_applied':len(research)==1 and research[0]['status']=='APPLIED' and bool(research[0].get('outcome')),
 'same_explicit_queries':research[0]['queries']==read(parent/'canonical/004-output.json.gz')['action']['queries'],
 'next_investigation_reached':r['frames'][-1]['stage']=='source-law-navigation-8-read-choice-page-1-0',
 'bylaw15_candidate_found':any(g.get('source_id')==target for g in s['groups'].values()),
 'existing_source_goals_preserved':len(st['source_goals'])==3 and all(g['status']=='ACQUIRED' for g in st['source_goals']),
 'no_model_or_network_call':r['new_model_calls']==r['network_calls']==0,
 'main_unchanged':r['main117_unchanged'],
 'runner_failure_preserved':r['failure']=={'type':'RuntimeError','message':'This portal is not running'} and not r['boundary_reached'],
}
receipt={'passed':all(checks.values()),'checks':checks,'original_result':bind(P/'result.json'),
 'original_state':bind(P/'final-state.json.gz'),'runner_exit_success':False,
 'runner_issue':'Deliberate BaseException at first unsupplied model decision stopped TestClient portal; context cleanup reported RuntimeError. The raw failed runner/result are preserved. This receipt checks the completed checkpoint without another replay.',
 'scope':'Control-flow only: new RESEARCH applied and bylaw15 candidate found. No claim that bylaw15 was acquired or CM007 completed.',
 'new_model_calls':0,'new_tool_executions':0}
put(ART/'replay-checkpoint-receipt.json',receipt)
print(checks)
assert receipt['passed']
