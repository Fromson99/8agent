"""Read-only ontology publication audit; no regrading or graph mutation."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0613-cm-memory-current-state-authority';run=A/'artifacts/run-001'
def main():
 rows=[]
 for arm in ['BASELINE','REPAIRED']:
  db=sqlite3.connect('file:'+str(run/arm/'memory.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  for k in db.execute('SELECT * FROM knowledge'):
   p=json.loads(k['payload']);read_ids={s['source_id'] for s in p['parts']['READ']['payload']['originals']};selected=set(p['parts']['SELECT']['payload']['final_ids']);claims={c['source_id'] for c in p['parts']['ASSESS']['payload']['claims']}
   nodes={r['id']:json.loads(r['payload'])['source_id'] for r in db.execute("SELECT * FROM ontology_node WHERE knowledge=? AND kind='SOURCE'",(k['id'],))}
   supported={nodes[r['target']] for r in db.execute("SELECT target FROM ontology_edge WHERE knowledge=? AND relation='SUPPORTED_BY'",(k['id'],))}
   rows.append({'arm':arm,'knowledge':k['id'],'bundle':k['bundle'],'status':k['status'],'read_sources':len(read_ids),'selected_sources':len(selected),'claim_sources':len(claims),'supported_by_sources':len(supported),'supported_but_not_selected':sorted(supported-selected),'supported_but_not_cited':sorted(supported-claims),'note':'Investigation trace may preserve all read sources, but SUPPORTED_BY should distinguish investigated from adopted/cited evidence. Product reuse still uses SELECT/ASSESS; this diagnoses graph semantics, not a fabricated response failure.'})
  db.close()
 out={'type':'post_run_publication_diagnosis','not_a_regrade':True,'knowledge_bundles':rows};(run/'publication-diagnosis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps([{k:v for k,v in x.items() if not isinstance(v,list)} for x in rows],ensure_ascii=False))
if __name__=='__main__':main()
