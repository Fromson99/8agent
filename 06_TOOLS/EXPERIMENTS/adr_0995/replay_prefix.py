"""Conditional continuation of actual saved responses, with original-source checks."""
from common import *
from copy import deepcopy
class Prefix:
 def __init__(self,out):self.out=out;self.count=0
 def replay(self,payload):
  if self.count>=4:return None
  binding=read(ART/'replay-prefix-binding.json')
  assert sha(ART/'replay-prefix-binding.json')==read(ART/'design-freeze.json')['replay_binding_sha256']
  assert all(sha(ROOT/n)==h for n,h in binding['files'].items())
  parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0992-compact-prompts-acquired-handoff/artifacts/known-query/candidate/model'/f'call-{self.count+1:03d}-service'
  previous=read(parent/'request.json');raw=read(parent/'response.json')
  def view(body):return json.loads(next(m['content'] for m in body['messages'] if m['role']=='user'))['view']
  old,new=view(previous),view(payload)
  checks={
   'phase':old['source_stage']==new['source_stage'],
   'system':[m for m in previous['messages'] if m['role']=='system']==[m for m in payload['messages'] if m['role']=='system'],
   'schema':previous['response_format']==payload['response_format']}
  keys=['question','law_title_hints'] if self.count==0 else ['current_request','issues','direct_search_scope'] if self.count<3 else ['current_request','issues','sources','evidence_options','user_fact_sources','original_requirements']
  checks.update({k:old.get(k)==new.get(k) for k in keys})
  value=json.loads(raw['choices'][0]['message']['content'])
  if value.get('target'):
   def target(v):
    rows=v.get('tool_options',[])
    if isinstance(rows,dict):rows=[dict(zip(rows['table_columns'],r)) for r in rows['table_rows']]
    return next((r for r in rows if r.get('target')==value['target'] and r.get('choice')==value['choice']),None)
   checks['selected_tool']=target(old)==target(new) and target(new) is not None
  path=self.out/'replay'/f'prefix-{self.count+1:03d}';path.mkdir(parents=True,exist_ok=False)
  save(path/'request.json',payload);save(path/'checks.json',checks)
  assert all(checks.values()),'Saved-prefix input mismatch: '+','.join(k for k,v in checks.items() if not v)
  save(path/'response.json',raw)
  save(path/'receipt.json',{'mode':'REPLAY_ACTUAL_RESPONSE','fresh_external_call':False,'source_request':str((parent/'request.json').relative_to(ROOT)),'source_response':str((parent/'response.json').relative_to(ROOT)),'checks':checks})
  self.count+=1
  return {'status_code':200,'body_json':deepcopy(raw),'body_text':None,'retry_after':None}
