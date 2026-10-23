"""Preregister paired existing working code; change only isolated baseline bytes."""
from common import *
import sys, shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1015-definition-context-provider-retest/artifacts'
audit=ROOT/'09_ARTIFACTS/AUDITS/20261023-final-connection-selection'
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='Explicit final structural selection prevents acquired but unselected scopes from entering connection inputs, while preserving whole-article connections when the model selects the whole article. It permits necessary linked originals and bounded completion without a separate scope-judge model.',
    primary_metric='Zero scope leaks or preselection catalog queries in candidate; selection must be exercised in actual model output, with verified source bytes and final response.',
    success_criteria='Candidate HTTP200 with explicit FOLLOW_CONNECTION; all catalogs/cards match the final selected delivered span range; original/hash/ACL mismatches0; no exact already-complete READ repeated; no provider failure; at most14 physical calls; final answer uses acquired sources and either closes the stated source need or preserves it as a limitation. Read97/163 is reported, not a hardcoded required action.',
    failure_criteria='Any outside-scope connection, implicit root expansion, source mismatch, unauthorized span, repeated completed READ, unreported missing source, budget failure, or failure to exercise explicit selection prevents full criteria certification. Provider failure makes behavior comparison unavailable.',
    criteria_frozen_before_run=True,
    sampling='Same known exposed public question, once per arm, candidate then baseline; no rerun or adaptive prompt changes. Fixed order and n=1 limit causal/generalization claims.',
    failure_recovery={'owner':'existing request_repair and shared request budget', 'limits':'14 model calls per arm, reserve3, schema repair1, transport retries0, wall1800s, max2 arms/28calls; provider or transport failure stops remaining arms.', 'state':'full provider wire, native journals and original span receipts; no history reset'},
    prerequisites={'implementation':'The user-authorized deterministic contract fix was completed before the separate experiment request; this experiment snapshots existing working code, and restores the two pre-fix files only inside its isolated baseline.', 'audit':str(audit.relative_to(ROOT))},
    budgets={'per_arm_calls':14,'total_calls':28,'wall_seconds':1800,'rss_limit_gib':6,'minimum_available_gib':4})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR1015 historical result only; no new calls.',controls='Historical lineage, not the executable control of this paired run.')
m['design']['arms'][1].update(changes='Current audited final-selection contract in exactly two product modules, plus consistent engine hashes.',controls='No forced article, automatic definition-context mode, extra progress override or monitor model. Current working profile is shared unchanged except equal operational call/retry/deadline bounds.')
m['design']['arms']=[x for x in m['design']['arms'] if x['id']!='control']
m['design']['arms'].append({'id':'control','role':'candidate','derived_from':['baseline'],
    'changes':'Latest shared working fixes with only connection_scope.py and decision_projection.py restored from the pre-fix audit; automatic previews.',
    'controls':'Same current profile, data, model, request and14call budget as candidate; isolated preregistered control.'})
m['design']['retrieval_stage_plan']['stages_by_arm']={a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ('control','candidate')}
m['runs'][0].update(arm_ids=['candidate','control'],selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'native-service','class':'product','model':'qwen/qwen3.8-27b','repeats':2}]
save(ADR/'실험/manifest.json',m)
save(ART/'design-before-snapshot.json',m['design'])
files=set(read(prior/'design-freeze.json')['files']['candidate'])
files.update('05_TESTS/CONTRACTS/'+n for n in ('test_selected_connection_scope.py','test_selected_connection_scope_api.py','test_final_connection_selection.py'))
files=sorted(n for n in files if (ROOT/n).is_file())
roots={};dirs={}
for arm in ('control','candidate'):
    d=ac.snapshot(ADR,arm,files,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
    c=d/'snapshot';roots[arm]=str(c.relative_to(ROOT));dirs[arm]=str(d.relative_to(ROOT))
    if arm=='control':
        for name in ('connection_scope.py','decision_projection.py'):
            n='02_BACKEND/semantic_runtime/legal_agent/'+name;shutil.copyfile(audit/'before'/n,c/n)
    for p in (c/'02_BACKEND/ENGINES').rglob('*.json'):
        v=read(p)
        if 'files' in v:
            v['files']={n:sha(c/n) for n in v['files']};save(p,v)
    p=c/'00_SYSTEM/PIPELINE.json';v=read(p)
    for e in v['engines'].values():e['sha256']=sha(c/e['manifest'])
    save(p,v)
shutil.copyfile(prior/'known-request.json',ART/'known-request.json')
save(ART/'stage.json',{'base_release':read(prior/'stage.json')['base_release'],'roots':roots,'candidate_dirs':dirs,
    'working_before':{n:sha(ROOT/n) for n in files},'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'arm_order':['candidate','control'],'changed_product_files':['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('connection_scope.py','decision_projection.py')]})
print('Prepared',len(files),'files per arm')
