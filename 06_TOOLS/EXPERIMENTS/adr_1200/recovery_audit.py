"""Offline route receipts; inspection does not alter frozen product or outcome."""
from common import *
cid=sys.argv[1];P=ART/'live'/cid;a=read(P/'audit.json')
s=read(P/'investigation-state.json') if (P/'investigation-state.json').exists() else {}
states=list(s.get('investigation_supervisor',{}).values())
rejects=[e for e in a['events'] if e['kind']=='SUPERVISOR_DIRECTIVE_REJECTED']
recoveries=[e for e in a['events'] if e['kind']=='SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED']
steps=s.get('action_chain',{}).get('steps',[])
target='article:af4d6957c006feaf9b4ed8b9'
result={'case_id':cid,'directive_rejections':rejects,'independent_recoveries':recoveries,
 'trigger_observed':bool(rejects),'recovery_observed':bool(recoveries),
 'new_research_actions':[x for x in steps if x.get('action')=='RESEARCH'],
 'bylaw15_acquired':target in a['read_source_ids'],'bylaw15_cited':target in a['published_source_ids'],
 'bylaw15_candidate_seen':any(g.get('source_id')==target for g in s.get('groups',{}).values()),
 'stop_reasons':[v.get('stop_reason',v.get('failure')) for v in states],
 'state_failure':[v.get('failure') for v in states],
 'checks':{'rejection_preserved_for_each_recovery':len(recoveries)<=len(rejects),
 'directive_not_accepted':all(e['payload']['directive_accepted'] is False for e in recoveries),
 'no_extra_repair_model':all(e['payload']['extra_model_calls']==0 for e in recoveries),
 'recovery_bound_max2':len(recoveries)<=2},
 'scope':'Actual trigger, event and action observation only. Candidate visibility is distinct from source acquisition; no semantic correctness inferred.',
 'new_model_calls':0}
put(P/'recovery-audit.json',result)
print(json.dumps(result,ensure_ascii=False))
