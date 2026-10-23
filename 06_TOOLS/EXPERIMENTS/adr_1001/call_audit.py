"""Offline call purposes and actual chosen targets; never feeds model input."""
from common import *
from collections import Counter
P=ART/'known-query/candidate'
def expand(value):
 if isinstance(value,list):return [expand(x) for x in value]
 if isinstance(value,dict):
  if 'table_rows' in value:return [expand(dict(zip(value['table_columns'],row))) for row in value['table_rows']]
  return {k:expand(v) for k,v in value.items()}
 return value
def category(phase):
 if phase=='request-entry':return 'request_entry'
 if 'read-choice' in phase:return 'next_action'
 if phase.startswith('source-reference'):return 'connection_decision'
 if phase.startswith('memory-assess'):return 'assessment'
 if phase.startswith('memory-compose'):return 'composition'
 return 'other'
times={x['call']:x for x in map(json.loads,(P/'physical-calls.jsonl').read_text().splitlines())}
rows=[]
for path in sorted((P/'model').glob('call-*/request.json')):
 number=int(path.parent.name.split('-')[1]);request=read(path)
 view=expand(json.loads(next(m['content'] for m in request['messages'] if m['role']=='user'))['view'])
 response=read(path.with_name('response.json'));phase=view.get('source_stage',view.get('phase'))
 try:proposal=json.loads(response['choices'][0]['message']['content'])
 except (KeyError,ValueError,IndexError):proposal={}
 references=view.get('references',{});cards=references.get('dependency_cards',[])
 targets=[]
 for selection in proposal.get('selections',[]):
  target=selection.get('target');card=next((x for x in cards if x.get('read_action')==target),None)
  offered=next((x for x in view.get('read_candidates',[]) if x.get('target')==target),None)
  targets.append({'target':target,'reason':selection.get('missing_need'),'source_ref':selection.get('source_ref'),
   'linked_card':({k:card.get(k) for k in ('anchor','target','direction','already_read','coordinate','reference_id')} if card else None),
   'read_candidate':offered})
 rows.append({'call':number,'phase':phase,'category':category(phase),'seconds':times[number]['seconds'],
  'transport_status':times[number]['status'],'finish_reason':response.get('choices',[{}])[0].get('finish_reason'),
  'usage':response.get('usage'),'choice':proposal.get('choice'),'targets':targets,
  'sources_seen':[{'id':x.get('id'),'heading':x.get('heading'),'document_name':x.get('document_name')} for x in view.get('sources',[])],
  'connection_cards':len(cards),'completed_cards_with_read_action':sum(bool(c.get('already_read') and c.get('read_action')) for c in cards),
  'previous_assessments':len(view.get('previous_assessments',[])),
  'response_file':str(path.with_name('response.json').relative_to(ROOT))})
summary={'physical_calls':len(rows),'by_category':dict(Counter(x['category'] for x in rows)),
 'provider_seconds':sum(x['seconds'] for x in rows),'completed_cards_with_read_action':sum(x['completed_cards_with_read_action'] for x in rows),
 'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','calls':rows,
 'interpretation':'Observed single run only. Repeated phase may reflect bounded repair or new state; inspect native journal before classifying it as redundant.'}
save(ART/'call-audit.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ('calls','interpretation')},ensure_ascii=False))
for row in rows:print(row['call'],row['phase'],row['choice'],round(row['seconds'],3))
