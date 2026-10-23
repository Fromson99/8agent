"""Read exact saved model payloads; never change the product or invoke a model."""
from common import *
P=ART/'known-query/candidate'
def expand(v):
 if isinstance(v,list):return [expand(x) for x in v]
 if isinstance(v,dict):
  if 'table_rows' in v:return [expand(dict(zip(v['table_columns'],r))) for r in v['table_rows']]
  return {k:expand(x) for k,x in v.items()}
 return v
calls=[]
for p in sorted((P/'model').glob('call-*/request.json')):
 req=read(p);v=expand(json.loads(next(x['content'] for x in req['messages'] if x['role']=='user'))['view'])
 res=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {}
 choice=res.get('choices',[{}])[0]
 try:proposal=json.loads(choice.get('message',{}).get('content',''))
 except ValueError:proposal={'invalid_or_missing_output':True}
 options={x['id']:x.get('text','') for x in v.get('evidence_options',[]) if isinstance(x,dict) and 'id' in x}
 originals=[]
 for source in v.get('sources',[]):
  text=source.get('text','') or '\n'.join(options[x] for x in source.get('evidence_refs',[]) if x in options)
  originals.append({**{k:source.get(k) for k in ('id','source_id','document_name','heading','selected_scope_complete')},
     'original_chars':len(text),'text_sha256':hashlib.sha256(text.encode()).hexdigest() if text else None,
     'via':'sources.text' if source.get('text') else ('evidence_options' if text else 'metadata_only')})
 calls.append({'call':p.parent.name,'stage':v.get('source_stage',v.get('phase')),
  'question':v.get('question'),'current_request':v.get('current_request'),
  'return_context':{k:v.get('return_context',{}).get(k) for k in ('question','current_request','issues')},
  'originals':originals,'selected_scope':v.get('selected_connection_scope'),
  'inline_connections':v.get('references',{}).get('dependency_cards',[]),
  'scope_choices':v.get('connection_scope_choices',[]),
  'original_omissions':v.get('retained_original_context'),
  'previous_reference_decisions':v.get('previous_reference_decisions',v.get('return_context',{}).get('previous_reference_decisions')),
  'proposal':proposal,'finish_reason':choice.get('finish_reason'),
  'response_model':res.get('model'),'response_provider':res.get('provider'),
  'input_chars':sum(len(x['content']) for x in req['messages']),
  'raw_request_path':str(p.relative_to(ROOT)),'raw_request_sha256':sha(p)})
save(ART/'decision-context-audit.json',{'calls':calls,'scope':'Exact native model payloads; body hashes/lengths only here, full originals in raw requests'})
for c in calls:
 print(c['call'],c['stage'],'originals',[(x['heading'],x['original_chars']) for x in c['originals']],
       'inline',len(c['inline_connections']),'choice',json.dumps(c['proposal'],ensure_ascii=False)[:900])
