from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0807-nonblank-generation-grammar';O=A/'artifacts/live'
r=json.loads((O/'result.json').read_text());root=R/r['journal_root'];rows=[]
for p in root.glob('children/*/legal-agent/**/journal.sqlite'):
 with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
  ev=[(k,json.loads(v)) for k,v in db.execute('select kind,payload_json from event order by seq')]
  entries=[v for k,v in ev if k=='WORKFLOW_ENTRY_BOUND']
  intent=[v for k,v in ev if k=='REQUEST_ENTRY_ACCEPTED']
  phases=[json.loads(x[0]).get('source_stage') for x in db.execute('select body_json from model_view')]
  rows.append({'journal':str(p.relative_to(R)),'host_entries':entries,
     'side':intent[0]['command']['source_category'] if intent else None,
     'issues':intent[0]['intent']['issues'] if intent else [],
     'child_entry_model_calls':sum(s in ('request-entry','source-request-route','memory-intent') for s in phases),
     'child_composition_model_calls':sum(s=='memory-compose' for s in phases),
     'system_definition_reads':sum(k=='SYSTEM_DEFINITION_ORIGINALS_ACQUIRED' for k,_ in ev)})
out={'fresh_host_entries':sum(len(v['host_entries']) for v in rows),'child_entry_model_calls':sum(v['child_entry_model_calls'] for v in rows),
     'child_composition_model_calls':sum(v['child_composition_model_calls'] for v in rows),'children':rows}
(A/'artifacts/parent-task-observation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='children'},ensure_ascii=False))
