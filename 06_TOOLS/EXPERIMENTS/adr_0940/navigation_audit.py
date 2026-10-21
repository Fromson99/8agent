"""Read-only selected-operation and continuation audit; no semantic equivalence guesses."""
from pathlib import Path
from collections import Counter
import json,gzip,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0940-research-continuity-prompt-cost';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
for P in O.glob('*/*'):
 if not (P/'audit.json').exists():continue
 audit=read(P/'audit.json');choices=[];counts=Counter();events=[];returned={};followups=[]
 for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  out=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
  if not out.exists():continue
  with gzip.open(p,'rt') as f:v=json.load(f)['view']
  with gzip.open(out,'rt') as f:answer=json.load(f)
  if 'target_id' not in answer:continue
  actions=v.get('actions',[]);actions=list(actions.values()) if isinstance(actions,dict) else actions
  selected=next((a for a in actions if a.get('id')==answer['target_id']),None) if answer['target_id'] else None
  operation={k:selected.get(k) for k in ('action','identity')} if selected else None
  if operation:
   operation['query']=answer.get('query');key=json.dumps(operation,sort_keys=True,ensure_ascii=False);counts[key]+=1
  choices.append({'call':int(p.name[:3]),'operation':operation,'return_originals':answer['target_id'] is None,'reason':answer.get('reason'),'progress':v.get('progress'),'continuity_present':bool(v.get('research_continuity'))})
 for ret in audit.get('child_return_history',[]):
  side=ret['side'];now=set(ret['evidence_ids'])
  if side in returned:followups.append({'side':side,'call_id':ret['call_id'],'status':ret['status'],'new_evidence_count':len(now-returned[side]),'returned_evidence_count':len(now)})
  returned[side]=returned.get(side,set())|now
 for p in (P/'runtime').rglob('journal.sqlite'):
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
   for kind,raw in db.execute("select kind,payload_json from event where kind like '%NO_PROGRESS%' or kind like '%STOP%'"):
    events.append({'kind':kind,'payload':json.loads(raw),'journal':str(p.relative_to(P))})
 result={'selected_operations':choices,'duplicate_identical_selected_operations':sum(n-1 for n in counts.values()),'followup_returns':followups,'followups_without_new_evidence':sum(r['new_evidence_count']==0 for r in followups),'stop_events':events,'meaning':'Only exact selected operation identity is compared. Different words or targets are not semantically deduplicated. Return counts are not proof of legal completeness.'}
 (P/'navigation-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print('/'.join(P.parts[-2:]),'choices',len(choices),'duplicate_operations',result['duplicate_identical_selected_operations'],'zero_new_followups',result['followups_without_new_evidence'],'stop_events',len(events))
