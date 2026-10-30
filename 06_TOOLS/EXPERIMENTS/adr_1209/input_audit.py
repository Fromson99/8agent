"""Read actual saved wire requests; no regeneration, provider calls or prompt edits."""
from common import *
import gzip,collections
size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
rows=[]
for number in [1198,1200,1201,1203,1205,1206]:
 adr=next((ROOT/'04_EXPERIMENTS/ADR').glob(f'ADR-{number}-*'))
 for p in sorted(adr.glob('artifacts/**/request.json.gz')):
  if '/runtime' in str(p):continue
  d=json.loads(gzip.decompress(p.read_bytes()))
  if not d.get('messages'):continue
  messages=d['messages'];user=next((m['content'] for m in messages if m.get('role')=='user'),'')
  try:body=json.loads(user)
  except (ValueError,TypeError):body={}
  view=body.get('view',body) if isinstance(body,dict) else {}
  system='\n'.join(m['content'] for m in messages if m.get('role')=='system')
  schema=d.get('response_format',{}).get('json_schema',{}).get('schema',{})
  parts={k:size(v) for k,v in view.items()} if isinstance(view,dict) else {}
  nested={}
  for k in ('read_judgments','answer_progress_context','source_goal_context'):
   if isinstance(view.get(k),dict):nested[k]={a:size(v) for a,v in view[k].items()}
  texts=collections.defaultdict(list)
  def walk(v,path):
   if isinstance(v,str) and len(v)>=80:texts[v].append(path)
   elif isinstance(v,dict):
    for k,x in v.items():walk(x,path+'/'+k)
   elif isinstance(v,list):
    for i,x in enumerate(v):walk(x,path+'/'+str(i))
  walk(view,'')
  repeats=[{'chars':len(s),'occurrences':len(ps),'extra_chars':len(s)*(len(ps)-1),'paths':ps} for s,ps in texts.items() if len(ps)>1]
  repeats.sort(key=lambda x:x['extra_chars'],reverse=True)
  subs=collections.Counter()
  def nodes(v):
   if isinstance(v,dict):
    if 'type' in v or 'anyOf' in v:
     key=json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
     if len(key)>100:subs[key]+=1
    for x in v.values():nodes(x)
   elif isinstance(v,list):
    for x in v:nodes(x)
  nodes(schema)
  rows.append({'adr':number,'call':p.parent.name,'source':bind(p),'phase':view.get('source_stage',view.get('phase')),
   'system_chars':len(system),'user_chars':len(user),'schema_chars':size(schema),'request_chars':size(d),
   'field_chars':dict(sorted(parts.items(),key=lambda x:-x[1])),'nested_field_chars':nested,
   'repeated_text_extra_chars':sum(r['extra_chars'] for r in repeats),'largest_repeated_strings':repeats[:8],
   'repeated_schema_nodes':sum(v-1 for v in subs.values() if v>1),
   'model_input_tokens':None,'usage_note':'Characters measured from saved wire; not token estimates. Timing/failure causality not inferred.'})
put(ART/'input-wire-size-audit.json',{'method':'Saved actual messages and response_format, Unicode chars and compact JSON chars; historical cases differ, no causal A/B claim','rows':rows})
for number in sorted({r['adr'] for r in rows}):
 rr=[r for r in rows if r['adr']==number];mx=max(rr,key=lambda r:r['request_chars']);print(number,len(rr),'max',mx['call'],{k:mx[k] for k in ('system_chars','user_chars','schema_chars','request_chars','repeated_text_extra_chars')},'fields',list(mx['field_chars'].items())[:6])
