"""Post-selection accounting; no approved answer-key recall is claimed."""
from common import *
import statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
audit=read(ART/'source-wire-audit.json');m=read(ADR/'실험/manifest.json')
inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};runs=[];counts=[]
for run in m['runs']:
 captures=[]
 for q in m['questions']:
  a=next((x for x in audit['cells'] if x['case_id']==q['case_id']),None) if run['id']=='run-004' else None
  rec=StageLedgerRecorder(q['case_id'],'selected-main',identity_canonicalizer)
  if a:
   acquired={(x[0],int(x[1])) for x in a['acquired_articles']};presented={(x[0],int(x[1])) for x in a['presented_articles']}
   assert presented<=acquired<=inventory
   rec.record_stage('source','source',sorted(inventory))
   rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before termination; does not establish absence or irrelevance' for x in inventory-acquired})
   rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'No exact original span observed in outbound model input' for x in acquired-presented})
  else:
   presented=set()
   for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='No dispatched retrieval: harness admission, global stop, private ordinary model boundary, GUI or unbound input; see case outcome')
  captures.append(grade_capture(rec.capture(),[]))
  if run['id']=='run-004':counts.append(len(presented))
 runs.append(build_run_artifact(run['id'],captures,{'selected-main':['source','acquired','present']}))
artifact=build_experiment_artifact('ADR-1318',m['experiment_id'],runs)
artifact['audit']={'meaning':'Observed article-root acquisition/delivery; 58 unexecuted workbook cases are skipped, not incorrect. Empty gold set means no approved key and no golden recall. Multiple turns aggregate within each original case.','model_calls':0}
artifact['artifact_sha256']=deterministic_sha256({k:v for k,v in artifact.items() if k!='artifact_sha256'})
path=ART/'retrieval-stage-ledger.json.gz';ref=write_raw_json(path,artifact);put(ART/'retrieval-stage-ledger-ref.json',ref)
def per(v):return {'selected-main':v}
metrics={'changed':False,'corpus_total':len(inventory),'before_filter':per(2*len(inventory)),'after_filter':per(sum(len(a['acquired_articles']) for a in audit['cells'])),'presented_total':per(sum(counts)),'presented_mean':per(statistics.mean(counts)),'presented_p50':per(statistics.median(counts)),'presented_p95':per(sorted(counts)[round((len(counts)-1)*.95)]),'golden_recall':per(None),'selectivity':per(statistics.mean(counts)/len(inventory)),'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-004','artifact_path':str(path.relative_to(ROOT)),'sha256':sha(path),'not_applicable_reason':None}}
put(ART/'retrieval-metrics.json',metrics);print(json.dumps(metrics,ensure_ascii=False))
