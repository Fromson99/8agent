"""Preregister a user-requested exact-code retest, preserving the failed parent."""
from common import *
import sys, shutil
from copy import deepcopy
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1016-final-selected-connection-scope'
pf=read(prior/'artifacts/design-freeze.json'); ps=read(prior/'artifacts/stage.json')
pm=read(prior/'실험/manifest.json'); m=read(ADR/'실험/manifest.json')
assert all(sha(ROOT/n)==h for n,h in ps['working_before'].items())
assert sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')==pf['client_sha256']
design=deepcopy(pf['design'])
design['sampling']='Same known exposed public question once per arm, candidate then control; fixed order, no adaptive reruns, no prompt or model changes. User-requested exact-code retest of provider-blocked ADR1016.'
design['arms'][0].update(derived_from=['ADR-1016-experiment-v1/candidate'],changes='Completed provider-blocked ADR1016 candidate measurement; historical only, zero new calls.')
design['arms'][1].update(changes='Byte-identical ADR1016 candidate product snapshot; only a new execution namespace.')
design['arms'][2].update(changes='Byte-identical preregistered ADR1016 control product snapshot; previous control was not executed.')
design['prerequisites']['retest_authorization']='User: 다시 한번 더 해봐'
design['prerequisites']['previous_result']=str((prior/'artifacts/result.json').relative_to(ROOT))
design['code_isolation'].update(mode='candidate_snapshot',candidates=[])
m['design']=design
m['lineage']['hypothesis_delta']='No product, prompt, model, budget, data or success-criteria change; repeat the prospectively fixed comparison once after prior provider429.'
m['runs'][0].update(arm_ids=['candidate','control'],selection_rule=design['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']=deepcopy(pm['llm_policy'])
m['retrieval_accounting']=deepcopy(pm['retrieval_accounting'])
for key in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):
    m['retrieval_accounting'][key]='PENDING_MEASUREMENT'
save(ADR/'실험/manifest.json',m);save(ART/'design-before-snapshot.json',design)
files=sorted(pf['files']['candidate']);roots={};dirs={}
for arm in ('control','candidate'):
    d=ac.snapshot(ADR,arm,files,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
    c=d/'snapshot';parent_root=ROOT/ps['roots'][arm]
    for name,digest in pf['files'][arm].items():
        assert sha(parent_root/name)==digest
        if sha(c/name)!=digest:shutil.copyfile(parent_root/name,c/name)
    assert {n:sha(c/n) for n in files}==pf['files'][arm]
    roots[arm]=str(c.relative_to(ROOT));dirs[arm]=str(d.relative_to(ROOT))
shutil.copyfile(prior/'artifacts/known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':ps['base_release'],'roots':roots,'candidate_dirs':dirs,
    'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'arm_order':['candidate','control'],'changed_product_files':ps['changed_product_files'],
    'retest_parent':str(prior.relative_to(ROOT)), 'same_frozen_product_bytes':True})
print('Prepared exact parent snapshots:',len(files),'files per arm')
