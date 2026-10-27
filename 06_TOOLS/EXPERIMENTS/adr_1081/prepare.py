"""Bind unchanged product bytes, observed evidence and237unexecuted contracts."""
from common import *
from datetime import datetime, timezone
import shutil
import subprocess

prior = ROOT/'04_EXPERIMENTS/ADR/ADR-1080-reference-visibility-point-check'
source = read(prior/'실험/manifest.json')
assert source['reservation']['status'] == 'completed' and source['results']['status'] == 'failed'
assert not any(run['status']=='complete' for run in source['runs'])
old = read(prior/'artifacts/design/freeze.json')
assert all(sha(ROOT/p)==h for p,h in old['files'].items())
old_code = ROOT/old['code_root']
base = read(prior/'artifacts/design/baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == base['pointer_sha256']
matrix_source = ROOT/'06_TOOLS/EXPERIMENTS/adr_1081/sql-matrix.json'
matrix = read(matrix_source)
preflight = read(DESIGN/'fixture-preflight.json')
assert preflight['status'] == 'PASS' and all(value is True for value in preflight['checks'].values())
assert preflight['constructed_fixtures'] == 1582 and preflight['new_primary_fixtures'] == 237 and preflight['observed_support_fixtures'] == 1345
assert all(sha(ROOT/path) == value for path,value in preflight['input_hashes'].items())
criteria = {'schema_version':'adr1081-valid-fixture-criteria-v1','frozen_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Same420productbytes as failed1080candidate. Repair only18 illegal non-NULL source/ref duplicate fixture cases; observed1345pairs are supporting,237previously unexecuted product conditions are prospective primary.',
    'matrix':bound(matrix_source),'primary_pairs':237,'observed_support_pairs':1345,'total_pairs':1582,
    'primary':'Prospectively frozen previously unexecuted finite SQL source/error/order/plan contracts; not unseen legal quality or independent product development.',
    'required':[
        'All237previously unexecuted cases match exact result/error/ordering/oracle/read-only and plan contracts; keep1345observed support separate.',
        'All1582paired fixtures run without pruning. Only18 non-NULL reference_end multiplicity fixtures differ; all observed1345fixture bytes remain identical.',
        'Every fixture passes separate preflight column/PK/construction checks before product bind or consumer execution; valid NULL duplicates remain included.',
        'Candidate420productbytes and MAIN104rebase are identical to failed1080; no product or criterion changes inferred from partial outcomes.',
        'Native known38responses/35frames/finalanswer meet unchanged1080prospective alias/journal contract, with view time below historical35viewbaseline.',
        'Frozen input, permission/source/witness/generation validators, data/profile/schema/prompt/model/menu/search/budgets, MAIN104 and working code remain unchanged.'
    ],
    'failure':'Any mismatch, fixture error, missing declared case, changed source or protected native mismatch blocks qualification; preserve all failure evidence.',
    'evidence_boundary':'Earlier1345SQLpairs and1318+280cachecontracts are observed support only. The237new product-observation conditions were blocked before bind/query in1080. The known replay is in-sample, not new legal holdout.',
    'corruption_boundary':read(prior/'artifacts/design/criteria.json')['corruption_boundary'],
    'schema_boundary':matrix['schema_boundary'],'prior_failed_source':bound(prior/'실험/manifest.json'),
    'fixture_preflight':bound(DESIGN/'fixture-preflight.json'),
    'new_model_calls':0,'network_allowed':False,'max_address_space_bytes':1073741824,
    'actual_corpus_workers':1,'rollback':'Official rollback to immutable MAIN104, separate receipt.'}
put(DESIGN/'criteria.json',criteria)
put(DESIGN/'sql-matrix.json',matrix)
put(DESIGN/'baseline.json',base)
put(DESIGN/'observed-comparator.json',read(prior/'artifacts/design/observed-comparator.json'))
put(DESIGN/'candidate-preparation.json',read(prior/'artifacts/design/candidate-preparation.json'))
put(DESIGN/'prior-observed-evidence.json',{'failed_source':bound(prior/'실험/manifest.json'),
    'prior_primary':bound(prior/'artifacts/run-001/result.json'),
    'prior_raw':bound(prior/'artifacts/run-001/sql-pairs.jsonl.gz'),
    'prior_product_freeze':bound(prior/'artifacts/design/freeze.json'),
    'product_code_root':old['code_root'],'observed_support_pairs':1345,'new_primary_pairs':237,
    'use':'Failed source, not completed parent; final validator lacks a completed product run and that failure is preserved.'})
put(DESIGN/'working-before.json',{name:sha(ROOT/name) for name in base['manifest']['files']})
m = read(ADR/'실험/manifest.json')
assert m['lineage']['parents'][0]['experiment_id']=='ADR-1075-experiment-v1'
m['lineage']['hypothesis_delta']=criteria['scope'];m['decision_eligible']=True
m['relationships'].append({'adr_id':'ADR-1080','experiment_id':source['experiment_id'],'relation':'informed_by',
    'record_path':str((prior/'실험/manifest.json').relative_to(ROOT)),'record_sha256':sha(prior/'실험/manifest.json'),
    'note':'Whole arms failed at invalid fixture construction.1345paired outcomes are observed support;237product conditions unexecuted. Product bytes unchanged; not a completed parent.'})
m['design'].update(hypothesis=criteria['scope'],primary_metric=criteria['primary'],success_criteria=criteria['required'],
    failure_criteria=criteria['failure'],criteria_frozen_before_run=True,prior_observed_evidence=bound(DESIGN/'prior-observed-evidence.json'))
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
    arm['changes']='Observed1078 SQL comparator unchanged' if arm['id']=='baseline' else 'Exact failed1080candidate product bytes, no new product edit'
    arm['controls']=criteria['evidence_boundary']
m['runs'][0].update(selection_rule='All237unexecuted primary cases plus1345separately labeled observed support cases; partition frozen before execution',artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
m['dataset'].update(name='Valid synthetic reference-visibility fixtures',version='valid-fixtures-v1',
    frozen_source=str((DESIGN/'sql-matrix.json').relative_to(ROOT)),sha256=sha(DESIGN/'sql-matrix.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[]
reason='Finite synthetic SQL contracts,237unexecuted primary conditions plus separately labeled1345observed support. No real corpus or legal answer scoring; native known replay separate.'
m['retrieval_accounting']['not_applicable_reason']=reason
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m,replace=True)
command=[str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(ADR),'--candidate-id',CANDIDATE.name,'--experiment-id',m['experiment_id'],'--arm-id','optimized','--run-id','run-001']
for name in sorted(old['serving_files']):command+=['--source',name]
subprocess.run(command,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
for name in old['serving_files']:shutil.copyfile(old_code/name,CANDIDATE/'snapshot'/name)
assert all(sha(CANDIDATE/'snapshot'/name)==h for name,h in old['serving_files'].items())
put(DESIGN/'staging.json',{'prior_product_freeze':bound(prior/'artifacts/design/freeze.json'),
    'source_code_root':old['code_root'],'all420productbytes_identical':True,'new_product_edits':0,
    'primary_unexecuted_cases':237,'observed_support_cases':1345,'new_model_calls':0})
print('Staged unchanged420candidatebytes;237prospective/1345observed; fixturepreflight bound; product execution0')
