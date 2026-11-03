"""Observed article accounting; no approved Gold answer exists for this probe."""
from common import *
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact,deterministic_sha256
a=read(ART/'source-wire-audit.json');m=read(ADR/'실험/manifest.json')
inventory={tuple(x) for x in a['source_article_inventory']}
acquired={(x['document_id'],x['article_root']) for x in a['acquired_articles']}
presented={(x['document_id'],x['article_root']) for x in a['presented_articles']}
assert presented<=acquired<=inventory
rec=StageLedgerRecorder('complex-public-law-001','verified',identity_canonicalizer)
rec.record_stage('source','source',sorted(inventory))
rec.record_stage('acquired','retrieve',sorted(acquired),parent_stage_ids=('source',),discard_reasons={x:'Not acquired before connection error; no finding of irrelevance or legal absence' for x in inventory-acquired})
rec.record_stage('present','present',sorted(presented),parent_stage_ids=('acquired',),discard_reasons={x:'No exact span observed in assembled outbound payload before termination' for x in acquired-presented})
run=build_run_artifact('run-001',[grade_capture(rec.capture(),[])],{'verified':['source','acquired','present']})
artifact=build_experiment_artifact('ADR-1300',m['experiment_id'],[run])
artifact['audit']={'gold_status':'No approved gold; empty gold means unscored, never perfect recall.',
    'present_meaning':'Payload assembled for transport, including UNKNOWN call; successful model receipt is separately reported.',
    'semantic_accuracy':None,'historical_baseline_not_executed':True}
artifact['artifact_sha256']=deterministic_sha256({k:v for k,v in artifact.items() if k!='artifact_sha256'})
raw(ART/'retrieval-stage-ledger.json.gz',artifact)
metrics={**m['retrieval_accounting'],'corpus_total':len(inventory),'before_filter':{'verified':len(inventory)},
    'after_filter':{'verified':len(acquired)},'presented_total':{'verified':len(presented)},
    'presented_mean':{'verified':len(presented)},'presented_p50':{'verified':len(presented)},'presented_p95':{'verified':len(presented)},
    'golden_recall':None,'selectivity':{'verified':len(presented)/len(inventory)}}
metrics['stage_ledger']={**metrics['stage_ledger'],'artifact_path':str((ART/'retrieval-stage-ledger.json.gz').relative_to(ROOT)),
    'sha256':sha(ART/'retrieval-stage-ledger.json.gz')}
put(ART/'retrieval-metrics.json',metrics);print(json.dumps(metrics,ensure_ascii=False))
