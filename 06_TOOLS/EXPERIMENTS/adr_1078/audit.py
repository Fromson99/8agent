"""Run the frozen new composed-state finite contract; no real corpus or model."""
from common import *
import resource
import socket
import sys
import time
import traceback

sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))


def blocked(*args,**kwargs):
    raise RuntimeError('Network forbidden in ADR1078 primary')


socket.create_connection = socket.socket.connect = blocked
out = ADR/'artifacts/run-001'
out.mkdir(exist_ok=False)
start = time.perf_counter()
checks = {}
try:
    frozen = read(DESIGN/'freeze.json')
    baseline = read(DESIGN/'baseline.json')
    prep = read(DESIGN/'candidate-preparation.json')
    matrix = read(DESIGN/'state-matrix.json')
    code = ROOT/frozen['code_root']
    assert all(sha(ROOT/p) == h for p,h in frozen['files'].items())
    checks['frozen_inputs_runners_and_prior_evidence'] = True
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    checks['main104_unchanged'] = True
    old = read(ROOT/prep['prior_candidate_freeze']['path'])
    assert frozen['serving_files'] == old['serving_files']
    checks['all420productbytes_identical_to_prior_candidate'] = True
    changed = {name for name,value in baseline['manifest']['files'].items() if frozen['serving_files'][name] != value}
    assert changed == set(prep['changed']) and changed <= set(TARGETS)|set(prep['pin_paths'])
    checks['only2source_modules_and31pins_over_main104'] = len(changed) == 33
    pins = 0
    for ref in read(code/'00_SYSTEM/PIPELINE.json')['engines'].values():
        assert sha(code/ref['manifest']) == ref['sha256']
        for name,value in read(code/ref['manifest'])['files'].items():
            assert (frozen['serving_files'].get(name) or sha(code/name)) == value,name
            pins += 1
    checks['all_engine_pins_valid'] = True
    from state_contract import run
    census = run(ROOT/baseline['manifest']['code_root'],code,matrix,out)
    assert census['status'] == 'PASS' and census['paired_cases'] == matrix['counts']['total_pairs'],census
    checks['all_new_composed_state_pairs_equivalent'] = True
    expected_counts = {name:row['paired_cases'] for name,row in matrix['categories'].items()}
    assert census['counts'] == expected_counts and census['calls_per_arm'] == matrix['counts']['calls_per_arm']
    checks['all_declared_categories_and_calls_completed'] = True
    assert not census.get('failures')
    checks['no_failure_or_case_pruning'] = True
    assert all(sha(ROOT/p) == h for p,h in frozen['files'].items())
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    checks['after_run_input_and_pointer_immutability'] = True
    assert all(v is True for v in checks.values())
    put(out/'result.json',{'schema_version':'adr1078-composed-state-result-v1','status':'COMPLETE',
        'strict_success':True,'checks':checks,'census':census,'serving_files':420,
        'engine_pins':pins,'changed_files':sorted(changed),'wall_seconds':time.perf_counter()-start,
        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'new_model_calls':0,'real_corpus_loads':0,'network_calls':0,
        'prior1318_pairs':'Already-observed support, not part of this new case count.',
        'limitations':['New finite composed-state contract only, not legal-quality holdout.',
            'Same known product candidate is evaluated on new predeclared state sequences; not independent product development.',
            'Cached reuse assumes synchronous menu and immutable-store check_unchanged; no cross-view persistence.',
            'Removed redundant I/O is not equivalent to arbitrary failure schedules attached only to those omitted calls.',
            'Native replay and prior35viewbaseline are known in-sample secondary evidence; no completed-baseline request-speed claim.']})
    print('PASS:',census['paired_cases'],'new state pairs;',pins,'pins;model0/corpus0')
except BaseException as error:
    put(out/'FAILED.json',{'error_type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc(),
        'checks_before_failure':checks,'wall_seconds':time.perf_counter()-start,'new_model_calls':0})
    raise
