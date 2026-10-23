"""Offline audit of the goal opinions and their actual consuming actions."""
from common import *
p=ART/'known-query/candidate'
events=read(p/'events-audit.json')
reviews=[e for e in events if e['kind']=='ANSWER_PROGRESS_REVIEWED']
steps=[e for e in events if e['kind']=='INVESTIGATION_CHAIN_STEP']
physical=[json.loads(x) for x in (p/'physical-calls.jsonl').read_text().splitlines()]
entry_path=p/'model/call-001-service/response.json'
try:
 entry=json.loads(read(entry_path)['choices'][0]['message']['content'])
 original_issues=entry['intent']['issues']
except (KeyError,ValueError,IndexError):original_issues=[]
ids={i['id'] for i in original_issues}
issues=[]
for e in reviews:
 value=e['payload'];goals=value['review']['goals']
 if len(goals)!=len(ids) or {g['issue_id'] for g in goals}!=ids:issues.append({'seq':e['seq'],'reason':'original issue mismatch'})
 next_steps=[s for s in steps if s['seq']>e['seq']]
 step=next_steps[0]['payload'] if next_steps else None
 if step and step['action'] not in ('FINISH','PENDING') and not value['handoff']:
  for target_issue in step.get('issue_refs',[]):
   if value.get('effective_goal_states', {}).get(target_issue, next((g['status'] for g in goals if g['issue_id']==target_issue),None))!='NEEDS_SOURCE':issues.append({'seq':e['seq'],'reason':'tool for answered goal'})
result={'original_issues':original_issues,'accepted_goal_reviews':len(reviews),
 'goal_contract_issues':issues,'separate_progress_model_calls':[r for r in physical if 'progress' in str(r.get('phase')) or 'goal-review' in str(r.get('phase'))],
 'bound_requirements':[e['payload'] for e in events if e['kind']=='GOAL_REQUIREMENT_BOUND'],
 'assembled_actions':[e['payload'] for e in events if e['kind']=='GOAL_ACTION_ASSEMBLED'],
 'accepted_finish_count':sum(e['kind']=='READ_CHOICE_SELECTED' and e['payload']['choice']['choice']=='FINISH' for e in events),
 'repair_calls':[r for r in physical if str(r.get('phase')).endswith('-repair')],
 'physical_navigation_calls':sum('-read-choice' in str(r.get('phase')) for r in physical),
 'effective_enabled':read(p/'effective-profile.json')['candidate_navigation']['answer_progress_control'],
 'timeline':[{'seq':e['seq'],'choice':e['payload']['choice'],'goals':e['payload']['review']['goals'],
              'effective_goal_states':e['payload'].get('effective_goal_states',{}),'assessment_requirements':e['payload'].get('assessment_requirements',[]),'handoff':e['payload']['handoff'],'unchanged_steps_by_issue':e['payload']['unchanged_steps_by_issue']} for e in reviews],
 'meaning':'Accepted per-issue model opinions, not independently certified legal sufficiency. Review and choice are produced by the same physical call.'}
save(ART/'goal-review.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('timeline','original_issues')},ensure_ascii=False))
