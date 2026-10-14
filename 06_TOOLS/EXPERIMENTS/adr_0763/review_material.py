"""Read-only review material after outputs; never imported by product runner."""
from pathlib import Path
import json,sqlite3,sys
R=Path(__file__).resolve().parents[3];number=int(sys.argv[1]) if len(sys.argv)>1 else 763;A=next((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04}-*'))
read=lambda p:json.loads(p.read_text())
for folder in sorted((A/'artifacts/run-001').glob('*/*')):
 if not (folder/'result.json').exists():continue
 r=read(folder/'result.json');events=[];stages=[]
 for jp in (folder/'runtime').rglob('journal.sqlite'):
  db=sqlite3.connect(jp.resolve().as_uri()+'?mode=ro',uri=True);events=[{'seq':seq,'kind':kind,'payload':json.loads(raw)} for seq,kind,raw in db.execute('select seq,kind,payload_json from event order by seq')];stages=[{'stage':eid,'seq':seq,'payload':json.loads(raw)} for eid,seq,raw in db.execute("select entity_id,created_seq,payload_json from entity_version where kind='case_stage' order by created_seq")];db.close()
 nav=[e for e in events if e['kind'] in ('REQUEST_ENTRY_ACCEPTED','LAW_SCOPED_FULLTEXT','LAW_DECISION_REJECTED','INVESTIGATION_CHAIN_STEP','COMPLETION_ASSESSMENT_REJECTED')]
 v={'case_id':r['case_id'],'arm':r['arm'],'http_status':r['http_status'],'seconds':r.get('request_seconds'),'calls':r['model_calls'],'answer':r.get('output',{}).get('answer'),'navigation':nav,'assessments':[s for s in stages if s['stage']=='case:ASSESS']}
 (folder/'review-material.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
 print(r['arm'],r['case_id'],r['http_status'],r['model_calls'],round(r.get('request_seconds',0),1))
 print((r.get('output',{}).get('answer') or {}).get('text','NO ANSWER'))
