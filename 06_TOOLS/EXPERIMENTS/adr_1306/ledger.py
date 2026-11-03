"""Post-selection article-root accounting, independent of answer-quality scoring."""
from common import *
import statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
audit=read(ART/'source-wire-audit.json');m=read(ADR/'실험/manifest.json');did='7bbe815ff43b6635';inventory={(did,n) for n in audit['source_article_inventory']};captures=[];counts={};source_counts={};acquired_counts={};recalls={};notrun=[]
for arm in ('review-off',):
 counts[arm]=[];source_counts[arm]=[];acquired_counts[arm]=[];recalls[arm]=[]
 for case in read(DES/'cases.json'):
  a=next((x for x in audit['cells'] if x['case_id']==case['id'] and x['arm']==arm),None)
  rec=StageLedgerRecorder(case['id'],arm,identity_canonicalizer)
  if a is None:
   notrun.append(case['id']+'-'+arm)
   for sid,kind,parents in [('source','source',()),('acquired','retrieve',('source',)),('present','present',('acquired',))]:rec.record_stage(sid,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Request not dispatched after global stop; no observed evidence')
   available=set();acquired=set();presented=set()
  else:
   available=inventory;acquired={(did,n) for n in a['acquired_articles']};presented={(did,n) for n in a['presented_articles']}
   assert acquired<=inventory and presented<=acquired
   rec.record_stage('source','source',sorted(available))
   rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before this attempt ended; not proof of irrelevant/missing law' for x in available-acquired})
   rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'No exact original span observed in outbound model input before termination' for x in acquired-presented})
  # Gold coordinates join only after all actual acquisition and outbound snapshots are fixed.
  gold=(did,1388 if case['article']==365 else 1420)
  captures.append(grade_capture(rec.capture(),[gold]));counts[arm].append(len(presented));source_counts[arm].append(len(available));acquired_counts[arm].append(len(acquired));recalls[arm].append(int(gold in presented))
run=build_run_artifact('run-001',captures,{a:['source','acquired','present'] for a in counts});artifact=build_experiment_artifact('ADR-1306',m['experiment_id'],[run])
artifact['audit']={'meaning':'Counts describe actually acquired/delivered original article roots, not final answer correctness. A missing original at termination is not a legal absence finding. Non-dispatched cases have zero observed delivery, not a measured search failure.','not_dispatched':notrun,'source_artifact_version':audit['source_artifact_version'],'inventory_source':'Same-document-artifact local immutable store; verified Gold source version matches.'}
artifact['artifact_sha256']=deterministic_sha256({k:v for k,v in artifact.items() if k!='artifact_sha256'})
put(ART/'retrieval-stage-ledger.json',artifact)
metrics={'changed':True,'corpus_total':len(inventory),'before_filter':{a:sum(v) for a,v in source_counts.items()},'after_filter':{a:sum(v) for a,v in acquired_counts.items()},'presented_total':{a:sum(v) for a,v in counts.items()},'presented_mean':{a:statistics.mean(v) for a,v in counts.items()},'presented_p50':{a:statistics.median(v) for a,v in counts.items()},'presented_p95':{a:max(v) for a,v in counts.items()},'golden_recall':{a:statistics.mean(v) for a,v in recalls.items()},'selectivity':{a:statistics.mean(v)/len(inventory) for a,v in counts.items()},'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((ART/'retrieval-stage-ledger.json').relative_to(ROOT)),'sha256':sha(ART/'retrieval-stage-ledger.json'),'not_applicable_reason':None}}
put(ART/'retrieval-metrics.json',metrics);print(json.dumps(metrics,ensure_ascii=False))
