from common import *
import statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');audits=read(ART/'source-wire-audit.json')['cells']
inventory={(x[0],int(x[1])) for x in read(ART/'source-inventory.json')['article_roots']};captures=[];stats={}
for arm in ('baseline','guided'):
 before=[];acq=[];present=[]
 for q in m['questions']:
  a=next((a for a in audits if a['case_id']==q['case_id'] and a['arm']==arm),None)
  rec=StageLedgerRecorder(q['case_id'],arm,identity_canonicalizer)
  if a:
   acquired={(x[0],int(x[1])) for x in a['acquired_articles']};shown={(x[0],int(x[1])) for x in a['presented_articles']};assert shown<=acquired<=inventory
   rec.record_stage('source','source',sorted(inventory));rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before stop; not legal absence' for x in inventory-acquired});rec.record_stage('present','present',sorted(shown),parent_stage_ids=('acquired',),discard_reasons={x:'Not observed in actual outbound input' for x in acquired-shown});before.append(len(inventory))
  else:
   acquired=set();shown=set();before.append(0)
   for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Not executed after global UNKNOWN or budget stop')
  captures.append(grade_capture(rec.capture(),[]));acq.append(len(acquired));present.append(len(shown))
 stats[arm]={'before_filter':sum(before),'after_filter':sum(acq),'presented_total':sum(present),'presented_mean':statistics.mean(present),'presented_p50':statistics.median(present),'presented_p95':max(present),'golden_recall':None,'selectivity':statistics.mean(present)/len(inventory) if inventory else 0}
ledger=build_experiment_artifact('ADR-1411',m['experiment_id'],[build_run_artifact('run-001',captures,{arm:['source','acquired','present'] for arm in stats})]);ledger['audit']={'meaning':'Exact article identities per independent cell, including unexecuted cells; no independent gold recall'};ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'})
lp=ART/'retrieval-stage-ledger.json.gz';write_raw_json(lp,ledger)
m['retrieval_accounting']={'changed':True,'corpus_total':len(inventory),**{k:{a:v[k] for a,v in stats.items()} for k in next(iter(stats.values()))},'not_applicable_reason':'No independent gold recall; unexecuted groups included as zero, not a latency or quality comparison.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
put(ADR/'실험/manifest.json',m)
print('Article ledger',len(inventory),stats)
