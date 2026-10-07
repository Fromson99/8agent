"""Read-only diagnosis of completed product executions; no replay or model calls."""
import json,sqlite3,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0497-gemma4-fp8-source-workflow-cm51-fsc10'
def main():
 rows=[]
 for p in sorted((A/'artifacts').glob('run-*/*/gemma/result.json')):
  r=json.loads(p.read_text());j=p.parent/'journal.sqlite'
  with sqlite3.connect('file:'+str(j)+'?mode=ro',uri=True) as d:
   d.row_factory=sqlite3.Row
   errors=[{'kind':x['kind'],**json.loads(x['payload_json'])} for x in d.execute("SELECT kind,payload_json FROM event WHERE kind IN ('OUTPUT_SCHEMA_INVALID','WORKFLOW_REPAIR','SEMANTIC_REPAIR','SOURCE_SELECTION_RECOVERY') ORDER BY seq")]
   views=[{'phase':v['phase'],'chars':len(v['body_json']),'evidence_count':len(json.loads(v['body_json']).get('exact_evidence',[]))} for v in d.execute('SELECT phase,body_json FROM model_view ORDER BY rowid')]
   attempts=[dict(x) for x in d.execute('SELECT v.phase,a.status,count(*) AS count FROM model_attempt a JOIN model_view v USING(view_id) GROUP BY 1,2')]
   shown={x[0] for x in d.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'")}
   cards=r.get('result',{}).get('assembly',{}).get('term_agent',{}).get('source_bundle',{}).get('sources',[])
   checks=[]
   for card in cards:
    checks.append({'selection_id':card['selection_id'],'evidence_was_delivered':card['evidence_id'] in shown,'span_hashes_valid':all(hashlib.sha256(s['text'].encode()).hexdigest()==s['span_hash'] for s in card['spans']),'excerpt_equals_spans':card['excerpt']=='\n'.join(s['text'] for s in card['spans'])})
  rows.append({'run_id':r['run_id'],'case_id':r['case_id'],'arm':r['arm'],'stages':{k:len(v) for k,v in r['stages'].items()},'errors':errors,'limitations':r['limitations'],'views':views,'phases':attempts,'source_checks':checks,'publication':r.get('publication_status'),'execution_error':r['error']})
 out={'rows':rows,'note':'Model-attempt SUCCEEDED denotes a received provider response and real input delivery, not schema-valid output or correct judgment. Selected spans never certify full article reading.'}
 (A/'artifacts/execution-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print('audited',len(rows),'completed product executions')
if __name__=='__main__':main()
