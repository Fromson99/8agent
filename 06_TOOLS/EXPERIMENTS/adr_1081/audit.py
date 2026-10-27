"""Run237unexecuted SQL contracts and1345observed support, no corpus/model."""
from common import *
import resource
import socket
import sys
import time
import traceback

sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
def blocked(*args,**kwargs):
    raise RuntimeError('Network forbidden in ADR1081 primary')
socket.create_connection = socket.socket.connect = blocked
out = ADR/'artifacts/run-001'
out.mkdir(exist_ok=False)
start = time.perf_counter()
checks = {}
try:
    frozen = read(DESIGN/'freeze.json')
    baseline = read(DESIGN/'baseline.json')
    observed = read(DESIGN/'observed-comparator.json')
    prep = read(DESIGN/'candidate-preparation.json')
    matrix = read(DESIGN/'sql-matrix.json')
    code = ROOT/frozen['code_root']
    assert all(sha(ROOT/p) == h for p,h in frozen['files'].items())
    checks['frozen_inputs_runners_and_observed_evidence'] = True
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    checks['main104_unchanged'] = True
    prior = read(DESIGN/'prior-observed-evidence.json')
    assert frozen['serving_files'] == read(ROOT/prior['prior_product_freeze']['path'])['serving_files']
    checks['all420productbytes_identical_to_failed1080candidate'] = True
    assert read(DESIGN/'fixture-preflight.json')['status'] == 'PASS' and all(value is True for value in read(DESIGN/'fixture-preflight.json')['checks'].values())
    checks['all1582fixture_constructions_preflight_passed'] = True
    changed = {name for name,value in baseline['manifest']['files'].items() if frozen['serving_files'][name] != value}
    assert changed == set(TARGETS)|set(prep['pin_paths']) and len(changed) == 34
    checks['only3source_modules_and31pins_over_main104'] = True
    delta = {name for name,value in observed['serving_files'].items() if frozen['serving_files'][name] != value}
    assert delta == {SQL_TARGET}|set(prep['pin_paths']) and len(delta) == 32
    before = (ROOT/observed['code_root']/SQL_TARGET).read_text()
    assert before.count(prep['old_sql']) == 1
    assert (code/SQL_TARGET).read_text() == before.replace(prep['old_sql'],prep['new_sql'],1)
    checks['exact_one_sql_predicate_over_observed_comparator'] = True
    pins = 0
    for ref in read(code/'00_SYSTEM/PIPELINE.json')['engines'].values():
        assert sha(code/ref['manifest']) == ref['sha256']
        for name,value in read(code/ref['manifest'])['files'].items():
            assert (frozen['serving_files'].get(name) or sha(code/name)) == value,name
            pins += 1
    checks['all_engine_pins_valid'] = True
    from sql_contract import run
    census = run(ROOT/observed['code_root'],code,matrix,out)
    assert census['status'] == 'PASS' and census['paired_cases'] == matrix['counts']['total_pairs'],census
    assert census['new_primary_pairs'] == 237 and census['observed_support_pairs'] == 1345
    checks['all237unexecuted_primary_sql_pairs_equivalent'] = True
    checks['all1345observed_support_pairs_rechecked'] = True
    assert census['counts'] == {name:row['paired_cases'] for name,row in matrix['categories'].items()}
    assert census['query_counts_per_arm'] == {'consumer':404028,'requested_failure':18,'explain':16}
    checks['all_declared_categories_and404062observations_per_arm_completed'] = True
    assert not census.get('failures')
    checks['no_failure_or_case_pruning'] = True
    assert all(sha(ROOT/p) == h for p,h in frozen['files'].items())
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    checks['after_run_input_and_pointer_immutability'] = True
    assert all(v is True for v in checks.values())
    put(out/'result.json',{'schema_version':'adr1081-valid-fixture-result-v1','status':'COMPLETE',
        'strict_success':True,'checks':checks,'census':census,'serving_files':420,
        'engine_pins':pins,'changed_files':sorted(changed),'wall_seconds':time.perf_counter()-start,
        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'new_model_calls':0,'real_corpus_loads':0,'network_calls':0,
        'prior_cache_pairs':'1318 +280 already-observed contracts; not counted as new SQL cases or holdout.',
        'primary_unexecuted_pairs':237,'observed_sql_support_pairs':1345,
        'fixture_preflight':bound(DESIGN/'fixture-preflight.json'),
        'prior_failed_source':bound(DESIGN/'prior-observed-evidence.json'),
        'limitations':read(DESIGN/'criteria.json')['corruption_boundary'],
        'scope':'237previously unexecuted finite SQL conditions,1345observed support; no independent product development. SQL membership/consumer/error contracts and query plans only. Not unseen legal quality, full corpus corruption audit, end-to-end latency or GENOS certification.'})
    print('PASS:',census['paired_cases'],'total fixture pairs(237new+1345observed);',census['query_observations_per_arm'],'observations/arm;',pins,'pins;model0/corpus0')
except BaseException as error:
    put(out/'FAILED.json',{'error_type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc(),
        'checks_before_failure':checks,'wall_seconds':time.perf_counter()-start,'new_model_calls':0})
    raise
