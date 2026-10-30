from common import *
import sys
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
runs=[]
for run_id,arms in [('run-001',['baseline','compact']),('run-002',['compact'])]:
 cases=[]
 for arm in arms:
  rec=StageLedgerRecorder('fsc-hard-005',arm,identity_canonicalizer)
  if run_id=='run-001':
   for ident,kind,parents in [('original_read','source',[]),('final_cited','present',['original_read'])]:rec.record_stage(ident,kind,[],parent_stage_ids=parents,executed=False,skip_reason='Case not dispatched in run-001: synthetic interface/SQL contracts only, no real retrieval/model call')
  else:
   a=read(RUN/'fsc-hard-005/audit.json');reads=a['read_coordinates'];cites=a['final_coordinates'];rec.record_stage('original_read','source',reads);rec.record_stage('final_cited','present',cites,parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Inspected but not selected for citation; no irrelevance/absence conclusion'} for x in reads if x not in cites])
  cases.append(grade_capture(rec.capture(),[]))
 runs.append(build_run_artifact(run_id,cases,{arm:['original_read','final_cited'] for arm in arms}))
p=RUN/'retrieval-ledger.json';put(p,build_experiment_artifact('ADR-1086','ADR-1086-experiment-v1',runs))
m=read(ADR/'실험/manifest.json');m['retrieval_accounting']['stage_ledger']['sha256']=sha(p);put(ADR/'실험/manifest.json',m)
am=read(ART/'manifest.json')
for row in am['files']:
 if ROOT/row['path']==p:row.update(sha256=sha(p),bytes=p.stat().st_size)
put(ART/'manifest.json',am)
