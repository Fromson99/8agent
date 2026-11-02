"""Offline exact-request accounting; no model invocation or product edits."""
from common import *
import collections,importlib,re
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
P=ART/'live/review-whatif'
def size(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
def walk(v,path=''):
 yield path,v
 if isinstance(v,dict):
  for k,x in v.items():yield from walk(x,path+'/'+k)
 elif isinstance(v,list):
  for k,x in enumerate(v):yield from walk(x,path+'/'+str(k))
prompt_modules=[('completion_execution','MODERN_ASSESS_PROMPT'),('completion_v8','PROMPT'),('assessment_consistency','PROMPT'),('read_judgment_final','PROMPT'),('need_continuity','PROMPT'),('judgment_changes','PROMPT'),('requirement_coverage','PROMPT'),('ontology_assessment','PROMPT'),('scenario_review','PROMPT')]
prompts={m+'.'+a:getattr(importlib.import_module('semantic_runtime.legal_agent.'+m),a) for m,a in prompt_modules}
rows=[]
for folder in sorted((P/'raw').glob('call-*')):
 req=read(folder/'request.json.gz');started=read(folder/'started.json');schema=req.get('response_format',{}).get('json_schema',{}).get('schema',{})
 texts=[m.get('content','') for m in req.get('messages',[]) if isinstance(m.get('content'),str)]
 system='\n'.join(m['content'] for m in req['messages'] if m['role']=='system')
 user='\n'.join(m['content'] for m in req['messages'] if m['role']=='user')
 schema_nodes=[(p,x) for p,x in walk(schema) if isinstance(x,dict)]
 scenario=[(p,x) for p,x in schema_nodes if p.endswith('/properties/scenario_review')]
 strings=collections.defaultdict(list)
 try:decoded=json.loads(user)
 except ValueError:decoded={}
 for p,v in walk(decoded):
  if isinstance(v,str) and len(v)>=50:strings[v].append(p)
 exact_repeats=[{'chars_each':len(s),'occurrences':len(paths),'paths':paths,'text_sha256':hashlib.sha256(s.encode()).hexdigest()} for s,paths in strings.items() if len(paths)>1]
 lines=collections.Counter(line.strip() for line in system.splitlines() if len(line.strip())>=30)
 output_repetitions=[]
 response_path=folder/'response.json.gz'
 if response_path.exists():
  response=read(response_path)
  try:output=json.loads(response['choices'][0]['message']['content'])
  except (ValueError,KeyError,IndexError,TypeError):output={}
  for path,text in walk(output):
   if not isinstance(text,str) or len(text)<100:continue
   repeated=collections.Counter(re.findall(r'\([^()]{4,60}\)[.!]?',text))
   repeats=[{'text':x,'count':n} for x,n in repeated.items() if n>1]
   if repeats:output_repetitions.append({'path':path,'chars':len(text),'repetitions':repeats})
 rows.append({'output_repetitions':output_repetitions,'number':started['number'],'turn':started['turn'],'stage':started['stage'],
 'request_utf8_bytes':size(req),'schema_utf8_bytes':size(schema),'system_utf8_bytes':len(system.encode()),'user_utf8_bytes':len(user.encode()),
 'schema_object_definitions_including_alternatives':sum('properties' in x for _,x in schema_nodes),
 'required_name_occurrences_including_alternatives':sum(len(x.get('required',[])) for _,x in schema_nodes),
 'schema_alternative_nodes':sum('anyOf' in x or 'oneOf' in x for _,x in schema_nodes),
 'root_fields':list(schema.get('properties',{})),'root_required':schema.get('required',[]),
 'scenario_wire_properties':[{'path':p,'properties':list(x.get('properties',{})),'required':x.get('required',[])} for p,x in scenario],
 'scenario_hash_requested':any(p.endswith('/properties/scenario_review/properties/context_hash') for p,_ in schema_nodes),
 'full_prompt_occurrences':{k:system.count(v) for k,v in prompts.items() if v},
 'repeated_system_lines':[{'count':n,'text':s} for s,n in lines.items() if n>1],
 'repeated_wire_strings':sorted(exact_repeats,key=lambda x:x['chars_each']*(x['occurrences']-1),reverse=True)[:15]})
canonical=[]
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(p)['view'];stage=v.get('source_stage','')
 if not stage.startswith('memory-assess'):continue
 strings=collections.defaultdict(list)
 for path,x in walk(v):
  if isinstance(x,str) and len(x)>=80:strings[x].append(path)
 duplicate=[{'chars_each':len(x),'occurrences':len(paths),'paths':paths,'text_sha256':hashlib.sha256(x.encode()).hexdigest()} for x,paths in strings.items() if len(paths)>1]
 canonical.append({'path':str(p.relative_to(ROOT)),'stage':stage,'top_level_sizes':sorted([{'key':k,'utf8_bytes':size(x)} for k,x in v.items()],key=lambda x:x['utf8_bytes'],reverse=True),
  'long_string_repetitions':sorted(duplicate,key=lambda x:x['chars_each']*(x['occurrences']-1),reverse=True)[:20],
  'output_contracts_requested':[k for k in read(p)['schema'].get('properties',{}) if any(t in k for t in ('review','usage','assessment'))],
  'repair_diagnostics':(v.get('repair_feedback') or {}).get('validation')})
if '--preview' not in sys.argv:put(ART/'wire-schema-audit.json',{'source':'Exact provider requests plus separately labelled canonical views','rows':rows,'canonical':canonical,
 'measurement_limits':['Byte sizes are not tokenizer counts','Required occurrences include mutually exclusive schema branches; not number of fields in one response','Repeated-string counts do not imply removable content or causal failure; no additive token savings claimed']})
print(json.dumps([{'call':r['number'],'stage':r['stage'],'schema_bytes':r['schema_utf8_bytes'],'system_bytes':r['system_utf8_bytes'],'user_bytes':r['user_utf8_bytes'],'scenario_hash_requested':r['scenario_hash_requested'],'repeat_lines':len(r['repeated_system_lines'])} for r in rows],ensure_ascii=False))
