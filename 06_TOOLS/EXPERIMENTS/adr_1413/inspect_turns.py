"""Post-run inspection; grading data never enters live.py."""
from common import *
import sqlite3
base=ART/'public-live/photo-conversation-selected'
case=read(DES/'live-cases.json')[0]
calls=read(base/'calls.json');generations=read(base/'generations.json')
observed=read(base/'result.json');derivations=read(base/'authorized-derivations.json') if (base/'authorized-derivations.json').exists() else []
source=ROOT/read(DES/'baseline.json')['release']['data_path']/'store.sqlite'
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
 original=db.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',('7bbe815ff43b6635','1390')).fetchone()[0]
def strings(v):
 if isinstance(v,str):
  try:w=json.loads(v)
  except (ValueError,TypeError):yield v
  else:
   if w==v:yield v
   else:yield from strings(w)
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
def named(v,key):
 if isinstance(v,dict):
  if key in v:yield v[key]
  for x in v.values():yield from named(x,key)
 elif isinstance(v,list):
  for x in v:yield from named(x,key)
turns=[]
for step in case['steps']:
 number=step['number'];folder=base/('turn-'+str(number));result=next((r for r in observed['turns'] if r['step']['number']==number),None)
 if result is None:
  turns.append({'number':number,'question':step['question'],'executed':False,'reason':'Earlier stop condition'});continue
 value=read(folder/'response.json.gz')['body'];answer=value.get('answer') or {}
 row={'number':number,'question':step['question'],'executed':True,'result':result,
  'answer':(folder/'public-answer.txt').read_text() if (folder/'public-answer.txt').exists() else (folder/'answer.txt').read_text(),
  'response_sha256':sha(folder/'response.json.gz'),'states':[r for r in derivations if r['turn']==number],
  'model_decisions':[],'continuity_inputs':[],'final_original_checks':[],'physical_calls':[c for c in calls if c['turn']==number]}
 for g in generations:
  if g['turn']!=number:continue
  p=base/'canonical'/f"{g['number']:03d}.json.gz";record=read(p);view=record['view'];out=p.with_name(f"{g['number']:03d}-output.json.gz")
  stage=g['stage'];response=read(out) if out.exists() else None
  if stage in ('request-entry','memory-resolve','memory-command-check','memory-reason-decision-review') or 'read-choice' in stage or stage=='memory-guided-answer':
   row['model_decisions'].append({'number':g['number'],'stage':stage,'output':response,'status':g['status'],'error':g.get('error'),'input_path':str(p.relative_to(ROOT))})
  if stage=='memory-resolve':
   row['continuity_inputs'].append({'utterance':view.get('utterance'),'goals':[{'id':goal.get('id'),'state':{k:v for k,v in goal.get('state',{}).items() if k!='document_ids'},'dialogue':goal.get('dialogue'),'previous_response':goal.get('previous_response')} for goal in view.get('goals',[])]})
  if stage=='memory-guided-answer':
   originals=list(named(view,'originals'))
   related=[c for c in calls if c['canonical_number']==g['number']]
   row['final_original_checks'].append({'canonical_number':g['number'],'originals':originals,
    'target_paragraph2_in_originals':any(original in text for text in strings(originals)),
    'physical':[{'number':c['number'],'target_text_in_actual_outbound':any(original in text for text in strings(read(base/'raw'/f"call-{c['number']:03d}"/'request.json.gz')))} for c in related]})
 turns.append(row)
put(ART/'turn-details.json',{'turns':turns,'target_original':original,'field_photo_contract':read(ART/'field-photo-context-contract.json')})
print(json.dumps([{'turn':t['number'],'executed':t['executed'],'result':t.get('result'),'answer':t.get('answer'),'states':t.get('states'),'final_original_checks':t.get('final_original_checks')} for t in turns],ensure_ascii=False,indent=2))
