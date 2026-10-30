from common import *
import sys, shutil

P = ROOT/'04_EXPERIMENTS/ADR/ADR-1153-ontology-selection-main-qualification'
DES.mkdir(parents=True, exist_ok=True)
old = read(P/'실험/manifest.json')
f = read(P/'artifacts/design/freeze.json')
m = read(ADR/'실험/manifest.json')
for key in ('design', 'dataset', 'retrieval_accounting'):
    m[key] = old[key]
m['design'].pop('release_rebase', None)
m['design']['code_isolation']['candidates'] = []
m.update(in_sample=False, decision_eligible=True)
m['lineage']['hypothesis_delta'] = 'No product or evaluation change. Bind the same verified 226 technical conditions to the formal release checks dictionary; audit exact frozen files and deployment receipt.'
m['design']['hypothesis'] = m['lineage']['hypothesis_delta']
m['design']['success_criteria'] = 'Exact 665 frozen product files and 440 serving files match completed1153; inherited 226 technical checks remain hash-bound; explicit nonempty checks dictionary; official preview exact; default OFF, switches and data preserved.'
m['design']['arms'] = [
    {'id':'baseline','role':'baseline','derived_from':['ADR-1153-experiment-v1/integrated'],'changes':'Completed1153 same-code technical qualification','controls':'No result or product edits'},
    {'id':'integrated','role':'candidate','derived_from':['baseline'],'changes':'Deployment receipt contract only','controls':'Same product/profile/data/model and inherited technical conditions'}]
m['llm_policy']['llm_calls'] = []
m['runs'][0].update(arm_ids=['integrated'], selection_rule='Deterministic release receipt contract checks and exact file hashes; no new semantic sample', artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
for name in ('baseline.json','criteria.json','prompt.json','official-preview.json'):
    shutil.copyfile(P/'artifacts/design'/name, DES/name)
def bind(p): return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
put(DES/'inherited-verification.json', {
    'source':bind(P/'실험/manifest.json'), 'result':bind(P/'artifacts/run-001/result.json'),
    'freeze':bind(P/'artifacts/design/freeze.json'), 'rerun':bind(P/'artifacts/check-ontology.json'),
    'framework':bind(P/'artifacts/design/inherited-checks.json'),
    'official_preview':bind(P/'artifacts/design/official-preview.json'),
    'technical_conditions':226, 'new_test_executions':0,
    'reason':'Same product and criteria; completed1153 has 216 inherited and 10 rerun passes. Preserve all previous results.'})
put(DES/'receipt-criteria.json', {'contract':'02_BACKEND/semantic_runtime/release_qualification.py:verify',
    'product_change':False, 'legal_quality_claim':False,
    'checks':['same_product','226_bound_technical_conditions','official_inventory','prompt_only','switches_and_default_off','no_data','same_profile_and_budgets','coordination','nonempty_all_true_checks'],
    'failure':'Any false check prevents completion and promotion'})
m['dataset'].update(name='Deterministic deployment receipt contract audit', version='1154-receipt-v1', frozen_source=str((DES/'receipt-criteria.json').relative_to(ROOT)), sha256=sha(DES/'receipt-criteria.json'))
put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()]
C=ac.snapshot(ADR,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
for n,h in f['files'].items():
    assert sha(ROOT/f['code_root']/n)==h
    dest=C/'snapshot'/n
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/f['code_root']/n,dest)
    if n not in present: ac.register_file(C,n,upstream_state='absent')
print('Prepared same665 files; receipt-only criteria fixed before audit')
