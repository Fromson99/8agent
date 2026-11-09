"""Per-case retrieval stage ledger (article roots), in the ADR-1421 form.

The ADR-1412 form recorded the whole scope inventory with a discard reason per case;
with CM51's larger acquisitions that build exceeded 4GiB RSS and was stopped. Here the
source stage is the acquired set (as ADR-1421), and corpus_total is the scope inventory size.
"""
from common import *
import statistics
audit=read(ART/'source-wire-audit.json')
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
m=read(ADR/'실험/manifest.json');inventory=len(read(ART/'source-inventory.json')['article_roots']);captures=[];acq=[];counts=[]
for q in m['questions']:
 a=next(a for a in audit['cells'] if a['case_id']==q['case_id']);rec=StageLedgerRecorder(q['case_id'],'selected',identity_canonicalizer)
 acquired=sorted((x[0],int(x[1])) for x in a['acquired_articles']);presented=sorted((x[0],int(x[1])) for x in a['presented_articles'])
 assert set(presented)<=set(acquired)
 rec.record_stage('source','source',acquired);rec.record_stage('acquired','retrieve',acquired,parent_stage_ids=('source',))
 rec.record_stage('present','present',presented,parent_stage_ids=('acquired',),discard_reasons={x:'Not observed in actual outbound input' for x in set(acquired)-set(presented)})
 captures.append(grade_capture(rec.capture(),[]));acq.append(len(acquired));counts.append(len(presented))
ledger=build_experiment_artifact('ADR-1424',m['experiment_id'],[build_run_artifact('run-001',captures,{'selected':['source','acquired','present']})])
ledger['audit']={'meaning':'Acquired and presented article identities per independent cell; no independent gold recall'}
ledger['artifact_sha256']=deterministic_sha256({k:v for k,v in ledger.items() if k!='artifact_sha256'});lp=ART/'retrieval-stage-ledger.json.gz'
if lp.exists():assert read(lp)==ledger
else:write_raw_json(lp,ledger)
m['retrieval_accounting']={'changed':False,'corpus_total':inventory,'before_filter':{'selected':sum(acq)},'after_filter':{'selected':sum(acq)},'presented_total':{'selected':sum(counts)},'presented_mean':{'selected':statistics.mean(counts)},'presented_p50':{'selected':statistics.median(counts)},'presented_p95':{'selected':sorted(counts)[min(len(counts)-1,max(0,round((len(counts)-1)*.95)))]},'golden_recall':{'selected':None},'selectivity':{'selected':statistics.mean(counts)/inventory},'not_applicable_reason':'No independent gold recall; registered CM targets are checked in review-input.json by law name and article.','stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str(lp.relative_to(ROOT)),'sha256':sha(lp),'not_applicable_reason':None}}
put(ADR/'실험/manifest.json',m);print('ledger cases',len(captures),'acquired total',sum(acq),'presented total',sum(counts))
