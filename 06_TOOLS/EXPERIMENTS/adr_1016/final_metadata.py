"""Represent the preregistered skipped control explicitly; preserve the frozen design."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import (StageLedgerRecorder, identity_canonicalizer,
    grade_capture, build_run_artifact, build_experiment_artifact)
m=read(ADR/'실험/manifest.json');ledger=read(ART/'retrieval-ledger.json')
assert read(ART/'stop.json')['reason']=='PROVIDER_FAILURE'
candidate=next(a for a in ledger['runs'][0]['arms'] if a['arm_id']=='candidate')['cases'][0]
rec=StageLedgerRecorder('known-query','control',identity_canonicalizer)
why='Not executed: preregistered provider stop after candidate second call429.'
rec.record_stage('original_read','source',[],executed=False,skip_reason=why)
rec.record_stage('final_cited','present',[],parent_stage_ids=['original_read'],executed=False,skip_reason=why)
save(ART/'retrieval-ledger.json',build_experiment_artifact('ADR-1016','ADR-1016-experiment-v1',[
    build_run_artifact('run-001',[candidate,grade_capture(rec.capture(),[])],{a:['original_read','final_cited'] for a in ('candidate','control')})]))
m['runs'][0]['arm_ids']=['candidate','control']
m['runs'][0]['executed_arm_ids']=['candidate'];m['runs'][0]['skipped_arm_ids']=['control']
for key in ('presented_total','presented_mean','presented_p50','presented_p95','selectivity'):
    m['retrieval_accounting'][key]['control']=0
m['retrieval_accounting']['golden_recall']['control']=None
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
assert m['design']==read(ART/'design-freeze.json')['design']
save(ADR/'실험/manifest.json',m)
artifact_manifest=ART/'manifest.json';old=read(artifact_manifest)
files=[]
for p in sorted(ART.rglob('*')):
    if p.is_file() and p!=artifact_manifest:
        files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
            'description':'Frozen design, native attempt, or post-run audit; see RESULT.txt for executed versus skipped state.',
            'contains_raw_prompts_and_outputs': 'model' in p.parts or p.name=='runtime.tar.gz'})
for p in sorted(Path(__file__).parent.glob('*.py')):
    files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Experiment runner or offline audit script. Product-call runners retain design-freeze hashes.',
        'contains_raw_prompts_and_outputs':False})
save(artifact_manifest,{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1016','created_at':old['created_at'],'files':files})
print('Recorded explicitly skipped control and artifact hashes:',len(files))
