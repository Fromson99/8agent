from common import *
import statistics
audit=read(ART/'source-wire-audit.json')
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];before=[];acq_counts=[];counts=[]
for q in m['questions']:
 a=next((a for a in audit['cells'] if a['case_id']==q['case_id']),None);rec=StageLedgerRecorder(q['case_id'],'paired',identity_canonicalizer)
 if a:
  acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']};assert presented<=acquired<=inventory
  rec.record_stage('source','source',sorted(inventory));rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before run ended; not a legal absence judgment' for x in inventory-acquired});rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'Not observed in actual outbound input' for x in acquired-presented});before.append(len(inventory))
 else:
  acquired=set();presented=set();before.append(0)
  for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Fixed stored evidence comparison has no RAG retrieval; unattempted cell is not a legal absence judgment')
 captures.append(grade_capture(rec.capture(),[]));acq_counts.append(len(acquired));counts.append(len(presented))
ledger=build_experiment_artifact('ADR-1383',m['experiment_id'],[build_run_artifact('run-001',captures,{'paired':['source','acquired','present']})]);ledger['audit']={'meaning':'Exact source/acquired/presented article identities per independent cell; no independent gold recall'};ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'});lp=ART/'retrieval-stage-ledger.json.gz';write_raw_json(lp,ledger)
m['retrieval_accounting']={'changed':False,'corpus_total':len(inventory),'before_filter':{'paired':sum(before)},'after_filter':{'paired':sum(acq_counts)},'presented_total':{'paired':sum(counts)},'presented_mean':{'paired':statistics.mean(counts)},'presented_p50':{'paired':statistics.median(counts)},'presented_p95':{'paired':max(counts)},'golden_recall':{'paired':None},'selectivity':{'paired':statistics.mean(counts)/len(inventory)},'not_applicable_reason':'No independent gold recall; observed source delivery on fixed corpus','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
put(ADR/'실험/manifest.json',m)
