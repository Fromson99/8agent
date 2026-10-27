"""Read-only physical-input inspection. Character counts are not token estimates."""
from collections import Counter
import json
from common import ART,read,save,sha

def inspect(root=ART):
 rows=[]
 for path in sorted((root/'matrix').glob('*/model/call-*/request.json')):
  request=read(path);states=[]
  for message in request.get('messages',[]):
   if message.get('role')!='user':continue
   try:payload=json.loads(message['content'])
   except (ValueError,TypeError):continue
   if isinstance(payload,dict) and 'step_state' in payload:states.append(payload['step_state'])
  state=states[0] if len(states)==1 else None
  response=path.with_name('response-receipt.json')
  rows.append({'path':str(path.relative_to(root)),'sha256':sha(path),
   'state_count':len(states),'stage':state and state.get('stage'),
   'state_chars':len(json.dumps(state,ensure_ascii=False,separators=(',',':'))) if state else None,
   'response_receipt_present':response.exists()})
 return {'physical_request_records':len(rows),'with_exactly_one_state':sum(r['state_count']==1 for r in rows),
  'stage_counts':dict(Counter(r['stage'] for r in rows)), 'calls':rows,
  'limitation':'Saved physical requests prove assembled transmission input, not successful model reception or judgment quality. State characters exclude its shared instruction and are not tokens. Logical decision budgets are not retry-time snapshots.'}
if __name__=='__main__':
 result=inspect();save(ART/'step-state-delivery.json',result);print(json.dumps({k:v for k,v in result.items() if k!='calls'},ensure_ascii=False))
