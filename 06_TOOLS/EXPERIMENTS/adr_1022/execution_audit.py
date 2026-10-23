"""Offline actual provider choice and connection/locator visibility audit."""
from common import *
import importlib.util, sys
sys.path.insert(0,str(ROOT/"02_BACKEND"))
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate'];P=ART/'known-query/candidate'
spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent.audit_projection',C/'02_BACKEND/semantic_runtime/legal_agent/navigation_input.py')
proj=importlib.util.module_from_spec(spec);spec.loader.exec_module(proj)
rows=[]
for p in sorted((P/'model').glob('call-*/request.json')):
 raw=read(p);v=proj.expand_cards(json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user')).get('view',{}))
 response=read(p.with_name('response.json')) if p.with_name('response.json').exists() else {}
 try:r=json.loads(response['choices'][0]['message']['content'])
 except (KeyError,IndexError,ValueError):r={}
 targets=[r['target']] if 'target' in r else [x['target'] for x in r.get('selections',[])]
 opts={x['target']:x for x in v.get('tool_options',[])}
 reads={x['target']:x for x in v.get('read_candidates',[])}
 labels=[]
 for t in targets:
  x=opts.get(t) or reads.get(t) or {}
  labels.append({'target':t,'label':x.get('label') or ' '.join(str(x.get(k,'')) for k in ('document','coordinate','heading')).strip(),'missing_need':next((x.get('missing_need') for x in r.get('selections',[]) if x['target']==t),None)})
 locators=['']+[x['target'] for x in v.get('locator_options') or []]
 gaps=[{k:g.get(k) for k in ('kind','missing_target','material','reason')} for g in r.get('gaps',[])]
 rows.append({'call':p.parent.name,'stage':v.get('source_stage',v.get('phase')),'choice':r.get('choice'),'targets':labels,'reason':r.get('reason'),
  'connection_review':v.get('connection_review'),'connection_cards':len(v.get('references',{}).get('dependency_cards',[])),
  'source_count':len(v.get('sources',[])),'locator_options_count':len(locators)-1,'gaps':gaps,
  'unsupported_gap_proposals':[g for g in gaps if g.get('missing_target','') not in locators],
  'claims':len(r.get('claims',[])),'finish_reason':(response.get('choices') or [{}])[0].get('finish_reason'),
  'usage':response.get('usage'), 'request_sha256':sha(p)})
refcalls=[x for x in rows if str(x['stage']).startswith('source-reference')]
result={'calls':rows,'reference_model_calls':len(refcalls),'finish_proposed_before_review':[x['call'] for x in rows if x['choice']=='FINISH' and (x['connection_review'] or {}).get('required_before_finish')],
 'unsupported_gap_proposals':sum(len(x['unsupported_gap_proposals']) for x in rows),
 'note':'Observed model proposals and input visibility; final legal correctness is not certified. Synthetic checks separately cover invalid locator rejection.'}
save(ART/'execution-review.json',result)
for x in rows:print(json.dumps({k:x[k] for k in ('call','stage','choice','targets','claims','gaps','finish_reason')},ensure_ascii=False))
