"""Exact inspected/cited original identities, gold joined only offline."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
refs={x['id']:x for x in read(DES/'offline-reference.json')};graded=[]
for c in read(DES/'cases.json'):
    cid=c['id'];P=RUN/cid;a=read(P/'audit.json') if (P/'audit.json').exists() else {};reads=a.get('read_coordinates',[]);cites=a.get('final_coordinates',[])
    gold=[{'doc_id':t['doc_id'],'node':int(t['node'])} for t in refs[cid]['targets'] if t.get('role')=='required' and str(t.get('node','')).isdigit()]
    rec=StageLedgerRecorder(cid,'observed',identity_canonicalizer);executed=(P/'result.json').exists();why='' if executed else 'Not dispatched after provider/resource/integrity stop; no source absence conclusion'
    rec.record_stage('original_read','source',reads,executed=executed,skip_reason=why)
    discards=[{'identity':x,'reason':'Inspected original not selected for final citation; no finding of irrelevance or data absence.'} for x in reads if x not in cites]
    rec.record_stage('final_cited','present',cites,parent_stage_ids=['original_read'],discard_reasons=discards,executed=executed,skip_reason=why)
    graded.append(grade_capture(rec.capture(),gold))
run=build_run_artifact('run-001',graded,{'observed':['original_read','final_cited']});ledger=build_experiment_artifact('ADR-0979','ADR-0979-experiment-v1',[run]);put(RUN/'retrieval-ledger.json',ledger)
print('Exact post-selection source ledger written')
