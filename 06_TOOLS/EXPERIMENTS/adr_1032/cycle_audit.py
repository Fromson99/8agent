"""Offline check of canonical executed scope identities, never display aliases."""
from common import *
from collections import Counter
P=ART/'known-query/candidate';events=read(P/'events-audit.json')
def fingerprint(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
steps=[];seen=set();repeats=[]
for e in events:
 if e['kind']!='INVESTIGATION_CHAIN_STEP':continue
 step=e['payload']
 if step.get('status')!='APPLIED':continue
 for a in step.get('targets',[]):
  scope=a.get('identity',{}).get('connection_scope')
  if step['action']!='FOLLOW_CONNECTION' or not scope:continue
  key=fingerprint(scope['members'])
  row={'sequence':e['seq'],'number':step['number'],'scope_id':scope['id'],'label':scope['label'],'members_hash':key,'reason':step.get('reason'),'outcome':step.get('outcome'),'unchanged_repeat':key in seen}
  if key in seen:repeats.append(row)
  seen.add(key);steps.append(row)
records=[e['payload'] for e in events if e['kind']=='CONNECTION_DIRECTORY_RECORDED']
counts=Counter(x['members_hash'] for x in records)
stop=[e['payload'] for e in events if e['kind']=='INVESTIGATION_BOUNDED_STOP']
review=read(ART/'execution-review.json')
report={'applied_connection_selections':steps,'unchanged_repeat_count':len(repeats),'unchanged_repeats':repeats,'directory_records':records,'duplicate_directory_records':{k:v for k,v in counts.items() if v>1},'bounded_stops':stop,'model_finish_calls':[x['call'] for x in review['calls'] if x['choice']=='FINISH'],'valid_observation':bool(steps),'meaning':'No executed scopes means unmeasured, not proof that cycles were prevented.'}
save(ART/'cycle-review.json',report)
print(json.dumps({k:report[k] for k in ('unchanged_repeat_count','duplicate_directory_records','bounded_stops','model_finish_calls','valid_observation')},ensure_ascii=False))
