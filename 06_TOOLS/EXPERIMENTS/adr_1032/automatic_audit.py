"""Offline observations of automatic acquisition and actual provider-visible text."""
from common import *
import importlib.util, sys, collections
sys.path.insert(0,str(ROOT/'02_BACKEND'))
s=read(ART/'stage.json'); C=ROOT/s['roots']['candidate']; P=ART/'known-query/candidate'
spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.audit_projection',C/'02_BACKEND/semantic_runtime/legal_agent/navigation_input.py')
proj=importlib.util.module_from_spec(spec);spec.loader.exec_module(proj)
events=read(P/'events-audit.json'); sources=read(P/'source-audit.json')
directories=[e for e in events if e['kind']=='SMALL_CONNECTION_DIRECTORY']
acquired=[e for e in events if e['kind']=='SMALL_CONNECTION_ORIGINAL_ACQUIRED']
o=read(ART/'observations.json')['by_arm']['candidate']
targets={law:sorted({r['source_id'] for r in rows}) for law,rows in o['observed_targets'].items()}
def walk(value):
 if isinstance(value,dict):
  yield value
  for child in value.values():yield from walk(child)
 elif isinstance(value,list):
  for child in value:yield from walk(child)
calls=[]
for p in sorted((P/'model').glob('call-*/request.json')):
 raw=read(p);v=proj.expand_cards(json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user')).get('view',{}))
 visible=[]
 for item in walk(v):
  sid=item.get('source_id')
  if not sid:continue
  texts=[]
  for field in ('text','quote','original_text'):
   if isinstance(item.get(field),str) and item[field]:texts.append(item[field])
  texts += [span['text'] for span in item.get('spans',[]) if isinstance(span,dict) and isinstance(span.get('text'),str)]
  if texts:visible.append({'source_id':sid,'text_hashes':sorted({hashlib.sha256(t.encode()).hexdigest() for t in texts}),'characters':sum(map(len,texts))})
 calls.append({'call':p.parent.name,'stage':v.get('source_stage',v.get('phase')),'sources_with_text':visible,
  'target_original_visible':{law:any(x['source_id'] in ids for x in visible) for law,ids in targets.items()},
  'automatic_receipts':v.get('automatic_connection_reads',[]),'request_sha256':sha(p)})
selections=read(P/'scope-audit.json')['selections']
parents=[{'scope_id':r['id'],'label':r['label'],'members':[m for m in r['members'] if m.get('parent_body_block_ids')]} for r in selections]
parents=[r for r in parents if r['members']]
out={'automatic_directory_count':len(directories),'automatic_acquired_count':len(acquired),
 'directories':directories,'acquired':acquired,'calls':calls,'scopes_with_parent_bodies':parents,
 'target_delivery':{law:{'acquired':bool(ids),'text_delivered_calls':[x['call'] for x in calls if x['target_original_visible'][law]]} for law,ids in targets.items()},
 'boundary_observations':{'small_directory_encountered':any(1<=e['payload']['endpoint_count']<=2 for e in directories),
 'large_directory_menu_only':[{k:e['payload'].get(k) for k in ('scope_id','endpoint_count','status','reason')} for e in directories if e['payload']['endpoint_count']>2],
 'automatic_model_calls_reported':sum(bool(e['payload'].get('model_called')) for e in acquired),
 'recursive_auto_reads_reported':sum(bool(e['payload'].get('recursive')) for e in acquired)},
 'limits':'Single known question; no encountered boundary is not a successful live test. Text hashes identify provider-visible original bodies without duplicating them; headings alone do not count.'}
save(ART/'automatic-review.json',out)
print(json.dumps({k:out[k] for k in ('automatic_directory_count','automatic_acquired_count','target_delivery','boundary_observations')},ensure_ascii=False,indent=2))
