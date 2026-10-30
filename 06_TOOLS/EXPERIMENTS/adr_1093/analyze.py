"""Read-only attribution of historical timing and the single profiled replay."""
from common import *
from datetime import datetime
from collections import Counter, defaultdict
import sqlite3,gzip

f=read(DES/'freeze.json');original=read(CASE/'result.json');calls=read(CASE/'calls.json')
db=sqlite3.connect('file:'+str(ROOT/f['source_journal']['path'])+'?mode=ro',uri=True)
events=[{'seq':n,'kind':k,'data':json.loads(p),'time':datetime.fromisoformat(t)} for n,k,p,t in db.execute('SELECT seq,kind,payload_json,created_at FROM event ORDER BY seq')]
byseq={e['seq']:e for e in events}
def interval(a,b):return (byseq[b]['time']-byseq[a]['time']).total_seconds()
views=[x['seconds'] for x in original['observed_spans'] if x['function']=='Investigation.view']
model=sum(x['seconds'] for x in calls)
nonmodel=original['elapsed_seconds']-original['model_transport_seconds']
prepare=next(json.loads(line)['elapsed_ms']/1000 for line in (SOURCE/'live.log').read_text().splitlines()
             if line.startswith('{') and json.loads(line).get('event')=='session.prepare.timings')
residual=nonmodel-sum(views)-prepare
stages={
 'PLAN':interval(25,27),
 'RECALL':interval(30,33),
 'READ':interval(36,122),
 'SELECT_initial_excluding_views_and_model':interval(125,380)-sum(c['seconds'] for c in calls[1:5])-sum(views[:3]),
 'SELECT_reentry_excluding_view':interval(422,430)-views[3],
 'ASSESS_and_COMPOSE_excluding_model':interval(383,421)+interval(433,455)+interval(458,477)-sum(c['seconds'] for c in calls[5:]),
 'INTENT':interval(19,22)}
stages['outside_stage_markers_and_request_envelope']=residual-sum(stages.values())
assert all(x>=0 for x in stages.values())
historical={'nonmodel_seconds':nonmodel,'model_seconds':model,'session_prepare_seconds':prepare,'views_seconds':views,'residual_seconds':residual,'residual_partition':stages,'method':'Intervals between original journal markers; subtract original transport durations and non-overlapping view durations. Marker gaps retained as other; stages are not function-exclusive timers.'}
put(ART/'historical-attribution.json',historical)

def wire(n):
 with gzip.open(CASE/'wire'/f'{n:03d}.json.gz','rt') as stream:return json.load(stream)
def output(n):
 return json.loads(read(next((CASE/'raw').glob(f'call-{n:03d}-*/response.json')))['choices'][0]['message']['content'])
def rows(v):
 if isinstance(v,dict) and 'table_rows' in v:return [dict(zip(v['table_columns'],r)) for r in v['table_rows']]
 return v
inputs={n:json.loads(wire(n)['messages'][1]['content'])['view'] for n in (2,4,5)}
a,b=output(4),output(5);ctx=inputs[4]['read_judgments']
newids=ctx['required'];judgments=rows(a['read_review']['judgments']);counts=Counter(j['judgment_id'] for j in judgments)
originals=rows(ctx['current_originals']);byid={r['id']:r for r in originals}
wrong=[]
for index,j in enumerate(judgments):
 expected=byid.get(j['judgment_id'],{}).get('source_refs',[])
 if expected and not set(j['basis_refs'])&set(expected):wrong.append({'row':index+1,'judgment_id':j['judgment_id'],'actual_basis':j['basis_refs'],'expected_basis':expected})
maps={n:{r['id']:r['name'] for r in rows(inputs[n]['documents'])} for n in (2,4)}
heads=rows(ctx['judgments']);stale=next(j for j in heads if j['id']=='J2')
prompt={'required_new_judgments':newids,'retained_judgments_count':len(heads),'returned_judgments_count':len(judgments),'duplicate_ids':{k:v for k,v in counts.items() if v>1},'missing_ids':sorted(set(newids)-set(counts)),'wrong_basis':wrong,'repair_judgments_identical':a['read_review']['judgments']==b['read_review']['judgments'],'choice_before':a['choice'],'choice_after':b['choice'],'repair_contract':inputs[5]['repair_contract'],'contract_error':inputs[5]['contract_error'],'stale_alias_example':{'alias':'D4','old_document':maps[2]['D4'],'current_document':maps[4]['D4'],'retained_finding':stale['finding']},'size_chars_including_spaces':[],'causal_limit':'Observed interface ambiguity and actual failed repair; no A/B causal success-rate claim.'}
for n in (4,5):
 w=wire(n);prompt['size_chars_including_spaces'].append({'call':n,'system':len(w['messages'][0]['content']),'user':len(w['messages'][1]['content']),'schema_json_default_serialization':len(json.dumps(w['response_format'],ensure_ascii=False))})
put(ART/'prompt-repair-diagnosis.json',prompt)

out=ART/'run-001'
if (out/'result.json').exists():
 result=read(out/'result.json');spans=read(out/'spans.json');log=[]
 for line in (ART/'profile.log').read_text().splitlines():
  if line.startswith('{'):
   try:log.append(json.loads(line))
   except ValueError:pass
 prep=next((r for r in log if r.get('event')=='session.prepare.timings'),{})
 summed=defaultdict(lambda:{'calls':0,'seconds':0.0,'cpu_seconds':0.0})
 for s in spans:
  t=summed[s['name']];t['calls']+=1;t['seconds']+=s['seconds'];t['cpu_seconds']+=s['cpu_seconds']
 bycategory=Counter();hot=defaultdict(Counter);leaf=defaultdict(Counter)
 with gzip.open(out/'samples.jsonl.gz','rt') as stream:
  for line in stream:
   sample=json.loads(line);cat=sample['category'];sec=sample['seconds'];bycategory[cat]+=sec
   for frame in set(sample['stack']):hot[cat][frame]+=sec
   if sample['stack']:leaf[cat][sample['stack'][0]]+=sec
 attribution={'replay_result':result,'prepare':prep,'inclusive_named_spans':dict(sorted(summed.items(),key=lambda x:-x[1]['seconds'])),'sampled_category_seconds':dict(bycategory),'sampled_inclusive_hotspots':{c:[{'frame':k,'sampled_seconds':v} for k,v in counts.most_common(35)] for c,counts in hot.items()},'sampled_leaf_hotspots':{c:[{'frame':k,'sampled_seconds':v} for k,v in counts.most_common(20)] for c,counts in leaf.items()},'warning':'Profiling instrumentation adds overhead. Inclusive nested spans cannot be added; sampled values are estimates, not exact SQL execution timers. Historical22.930seconds are partitioned separately.'}
 if result['completed']:
  attribution['residual_seconds']=result['request_seconds']-prep['elapsed_ms']/1000-summed['navigation.view']['seconds']-summed['transport.recorded']['seconds']
 put(ART/'profile-attribution.json',attribution)
 print(json.dumps({'completed':result['completed'],'historical':historical,'profile_seconds':result['request_seconds'],'named':{k:v for k,v in summed.items() if k.startswith('stage.') or k in ('navigation.view','session.prepare_navigation_context','recall.prepare','journal.event','journal.save_view','journal.put')}},ensure_ascii=False,indent=2))
else:print('Historical and prompt diagnosis saved; replay still in progress')
