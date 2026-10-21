from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0803-system-owned-workflow-mechanics';O=A/'artifacts/live'
read=lambda p:json.loads(p.read_text())
result=read(O/'result.json');body=read(O/'response.json').get('body',{})
summary={'result':{k:v for k,v in result.items() if k!='usage'},'rows':len(body.get('report',{}).get('rows',[])),'evidence_refs':len(body.get('evidence_refs',[])),'answer':body.get('answer'),'resume_available':body.get('resume_available'),'children':{},'calls':[]}
for p in sorted((O/'raw').glob('call-*')):
 row={'call':p.name}
 if (p/'error.json').exists():row['error']=read(p/'error.json')
 if (p/'response.json').exists():
  v=read(p/'response.json');row.update(model=v.get('model'),provider=v.get('provider'),finish=v.get('choices',[{}])[0].get('finish_reason'))
  try:
   value=json.loads(v['choices'][0]['message']['content'])
   row['decision']={k:value[k] for k in ('next_action','targets','issue_refs') if k in value}
   if value.get('exploration'):row['links']=[{'target':r['target'],'issue_id':r['issue_id']} for r in value['exploration']]
  except (KeyError,ValueError,IndexError):pass
 summary['calls'].append(row)
for side in ('internal','external'):
 child=O/'runtime/workflows'/body.get('run_id','unknown')/'children'/side
 found=list(child.rglob('journal.sqlite'));s={}
 for p in found:
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
   s['evidence_units']=db.execute('select count(*) from evidence_unit').fetchone()[0]
   s['read_observations']=db.execute("select count(*) from observation where tool='read'").fetchone()[0]
   s['events']=[]
   for k,j in db.execute("select kind,payload_json from event where kind in ('RUN_FAILED','LAW_DECISION_REJECTED','REQUEST_ENTRY_ACCEPTED')"):
    value=json.loads(j);diagnostic=value.get('diagnostics',{});contract=diagnostic.get('output_contract',value.get('validation',{}))
    s['events'].append({'kind':k,'code':value.get('code'),'category':contract.get('category'),'issues':[{'code':x.get('code'),'path':x.get('path')} for x in contract.get('issues',[])],'original_journal':str(p.relative_to(R))})
 summary['children'][side]=s
(A/'artifacts/live-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ('answer','children')},ensure_ascii=False,indent=2))
