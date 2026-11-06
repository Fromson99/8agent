from common import *
rows=[];calls=[]
for case in read(DES/'live-cases.json'):
 for arm in ('baseline','guided'):
  d=ART/'public-live'/(case['id']+'-'+arm)
  if not (d/'result.json').exists():
   rows.append({'case_id':case['id'],'arm':arm,'executed':False,'reason':'Global stop; unexecuted is not failed model answer'});continue
  physical=read(d/'calls.json') if (d/'calls.json').exists() else [];calls.extend(physical)
  menus=[];decisions=[];histories=[]
  for p in sorted((d/'canonical').glob('[0-9][0-9][0-9].json.gz')):
   view=read(p)['view'];out=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
   if view.get('tool_options'):menus.append({'canonical':p.name,'choices':sorted({r['choice'] for r in view['tool_options']}),'targets':len(view['tool_options']),'read_candidates':len(view.get('read_candidates',[]))})
   if out.exists() and read(out).get('choice'):decisions.append({'canonical':p.name,'choice':read(out)['choice']})
   def walk(x):
    if isinstance(x,dict):
     for k,v in x.items():
      if k=='dialogue':histories.append({'canonical':p.name,'stage':view.get('source_stage',view.get('phase')),'rows':len(v),'speakers':[r.get('speaker') for r in v],'text_chars':sum(len(r.get('text','')) for r in v)})
      else:walk(v)
    elif isinstance(x,list):
     for v in x:walk(v)
   walk(view)
  rows.append({'case_id':case['id'],'arm':arm,'executed':True,'native_result':read(d/'result.json'),'physical_calls':len(physical),'navigation':decisions,'menus':menus,'dialogue_inputs':histories,'answers':{p.parent.name:p.read_text() for p in d.glob('turn-*/answer.txt')}})
a=read(ART/'source-wire-audit.json')['cells']
result={'cells':rows,'physical_calls':len(calls),'normal':sum(x.get('http_status')==200 and x['status']=='responded' for x in calls),'confirmed429':sum(x.get('http_status')==429 for x in calls),'unknown':sum(x['status']=='unknown' for x in calls),'reported_cost_usd':sum((x.get('usage') or {}).get('cost',0) or 0 for x in calls),'source_checks':sum(x['source_checks'] for x in a),'delivered_checks':sum(x['delivered_checks'] for x in a),'source_acl_wire_mismatches':sum(len(x[k]) for x in a for k in ('source_mismatches','acl_violations','wire_mismatches')),'budget_matches':all(x['budget_matches'] for x in a),'response_replay':0,'no_post_unknown_send':not any(x['status']=='unknown' for x in calls[:-1]),'quality_certified':False}
put(ART/'live-summary.json',result)
print({k:v for k,v in result.items() if k!='cells'})
