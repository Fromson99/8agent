from pathlib import Path
import json,sys,sqlite3
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
A=R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live';D=A/'artifacts/design';O=A/'artifacts/run-002';read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cases=read(D/'cases.json');refs={c['id']:c for c in read(D/'offline-reference.json')};runs=[]
for rid in ('run-001','run-002'):
 graded=[]
 for c in cases:
  cid=c['id'];a=read(O/cid/'audit.json') if rid=='run-002' else {};reads=a.get('read_coordinates',[]);cited=a.get('final_coordinates',[]);rec=StageLedgerRecorder(cid,'observed',identity_canonicalizer)
  # Reference-version identities are retained exactly; changed source hashes are not silently remapped.
  gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in refs[cid]['targets']]
  skipped=rid=='run-001';why='Pre-model envelope rejection' if cid=='cm-001' else 'Not attempted during envelope preflight'
  rec.record_stage('original_read','source',reads,executed=not skipped,skip_reason=why if skipped else '')
  discarded=[{'identity':x,'reason':'Read original not included in final claim source IDs; no finding of irrelevance or missing data.'} for x in reads if x not in cited]
  rec.record_stage('final_cited','present',cited,parent_stage_ids=['original_read'],discard_reasons=discarded,executed=not skipped,skip_reason=why if skipped else '')
  graded.append(grade_capture(rec.capture(),gold))
 runs.append(build_run_artifact(rid,graded,{'observed':['original_read','final_cited']}))
ledger=build_experiment_artifact('ADR-0878','ADR-0878-experiment-v1',runs);put(O/'retrieval-ledger.json',ledger)
print('Exact original-read to final-citation ledger built, original registered reference coordinates; version drift kept separate')
