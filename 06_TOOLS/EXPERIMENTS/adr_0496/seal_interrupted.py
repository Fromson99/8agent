"""Derive explicit interruption records from read-only journals; never replay or mutate them."""
import json,sqlite3,time,hashlib
from datetime import datetime
from pathlib import Path
from run_probe import pin,read,write,ADR
pin()
from semantic_runtime.legal_agent.tiers_repository import TiersRepository
art=ADR/'artifacts';ids=['cm-026','cm-027','cm-028','cm-029','cm-031'];receipts=[]
for cid in ids:
 p=art/'run-001'/cid/'repaired'
 if (p/'result.json').exists():raise RuntimeError('Refuse overwrite '+cid)
 journal=p/'journal.sqlite';before=hashlib.sha256(journal.read_bytes()).hexdigest()
 repo=object.__new__(TiersRepository);repo.db=sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True);repo.db.row_factory=sqlite3.Row
 evidence=repo.evidence();by_e={e['evidence_id']:e['source_id'] for e in evidence};handles=[dict(x) for x in repo.db.execute('SELECT * FROM navigation_handle')]
 read_ids=set(by_e.values());discovered=read_ids|({json.loads(h['identity_json']).get('source_id') for h in handles}-{None})
 presented={by_e[r[0]] for r in repo.db.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if r[0] in by_e}
 selected={by_e[h['payload']['evidence_id']] for h in repo.heads('source_selection',current=True) if h['payload']['status']=='SELECTED'}
 run=repo.run();start=datetime.fromisoformat(run['started_at']).timestamp();last=repo.db.execute('SELECT created_at FROM event ORDER BY seq DESC LIMIT 1').fetchone()[0];end=datetime.fromisoformat(last).timestamp()
 errors=[json.loads(r[0]) for r in repo.db.execute("SELECT payload_json FROM event WHERE kind IN ('WORKFLOW_REPAIR','SEMANTIC_REPAIR') ORDER BY seq")]
 provenance={'reconstructed_after_interruption':True,'journal_sha256':before,'derived_at':time.time(),'last_event_at':last,'source':'Read-only journal; missing final output stays absent; no publication or answer inferred','cause':'Host OOM/reboot' if cid!='cm-031' else 'Worker and supervisor termination, cause unconfirmed'}
 trace={'handles':handles,'evidence':evidence,'assessments':repo.heads('assessment',current=True),'claims':repo.heads('claim',current=True),'observations':repo.observations(10000),'packed':{},'errors':errors,'actions':[dict(x) for x in repo.db.execute('SELECT * FROM action_context')],'source_selections':repo.heads('source_selection'),'source_bundle':{},'notices':repo.notices(),'coverage':repo.coverage(),'relation_assessments':repo.heads('relation_assessment',current=True),'reconstruction':provenance}
 usage=read(p/'calls/usage.json') if (p/'calls/usage.json').exists() else []
 row={'case_id':cid,'arm':'repaired','run_id':'run-001','preflight':False,'error':{'type':'InfrastructureInterruption','message':provenance['cause']},'publication_status':'NOT_REACHED','publication_error':None,'started_at':start,'seconds':round(max(0,end-start),3),'latency_censored':True,'latency_note':'Lower bound from journal start to last event; excludes bootstrap and unknown time to termination. Exclude from latency statistics.','controller_seconds':None,'physical_calls':len(list((p/'calls').glob('*/request.json'))),'usage':usage,'journal_run':run,'budget':repo.budget(),'limitations':['Infrastructure interruption; final model/product outcome unavailable'],'stages':{k:sorted(v) for k,v in [('discovered',discovered),('read',read_ids),('presented',presented),('selected',selected),('answer',set()),('payload_sources',set()),('final_sources',set())]},'reconstruction':provenance}
 repo.db.close();assert hashlib.sha256(journal.read_bytes()).hexdigest()==before
 write(p/'trace.json',trace);write(p/'result.json',row);receipts.append({'case_id':cid,**provenance})
fixture=read(ADR/'product-cases.json');rows={c['case_id']:{'repaired':read(art/'run-001'/c['case_id']/'repaired/result.json')} for c in fixture['cases']}
start=read(art/'run-001/results.partial.json')['started_at']
write(art/'run-001/results.json',{'cases':rows,'started_at':start,'finished_at':time.time(),'run_id':'run-001','terminal_accounting':'56 worker final results + 5 explicit journal-derived interruption records; not 61 normal completions','interrupted_cases':ids,'execution_epochs':'Initial max4 before hostOOM; later max1 with3GiB cap; mixed environment, latency not a uniform benchmark'})
write(art/'interruption-derived-records.json',{'records':receipts,'original_journals_unchanged':True,'normal_worker_completions':56,'reconstructed_interruptions':5})
print('Sealed original61: 56 worker results + 5 explicitly interrupted records; journals unchanged')
