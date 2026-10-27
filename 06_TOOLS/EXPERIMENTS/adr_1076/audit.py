"""Execute only the frozen prospective finite contract census; no real corpus."""
from common import *
import resource
import socket
import sys
import time
import traceback

sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))


def blocked(*args, **kwargs):
    raise RuntimeError('Network is forbidden in ADR1076 finite census')


socket.create_connection = blocked
socket.socket.connect = blocked
output = ADR/'artifacts/run-001'
output.mkdir(exist_ok=False)
started = time.perf_counter()
checks = {}
try:
    frozen = read(DESIGN/'freeze.json')
    baseline = read(DESIGN/'baseline.json')
    preparation = read(DESIGN/'candidate-preparation.json')
    code = ROOT/frozen['code_root']
    assert all(sha(ROOT/name) == expected for name, expected in frozen['files'].items())
    checks['frozen_inputs_and_runners'] = True
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    checks['main104_pointer_unchanged'] = True
    changed = {name for name, old in baseline['manifest']['files'].items()
               if frozen['serving_files'][name] != old}
    assert changed == set(preparation['changed'])
    assert changed <= set(TARGETS) | set(preparation['pin_paths'])
    checks['only_two_source_modules_and_pins'] = True
    pins = 0
    pipeline = read(code/'00_SYSTEM/PIPELINE.json')
    for engine_ref in pipeline['engines'].values():
        assert sha(code/engine_ref['manifest']) == engine_ref['sha256']
        engine = read(code/engine_ref['manifest'])
        for name, expected in engine['files'].items():
            actual = frozen['serving_files'][name] if name in frozen['serving_files'] else sha(code/name)
            assert actual == expected, name
            pins += 1
    checks['all_selected_engine_pins'] = True
    from finite_runner import run
    census = run(ROOT/baseline['manifest']['code_root'], code,
                 read(DESIGN/'finite-matrix.json'), output)
    assert census['status'] == 'PASS' and census['paired_cases'] == 1318, census
    checks['all1318_prospective_pairs_equivalent'] = True
    assert census['counts'] == {'static': 1152, 'transitions': 112, 'integration': 54}
    checks['all_declared_axes_completed'] = True
    assert len(census['read_reduction_witnesses']) >= 2
    checks['direct_and_real_menu_reuse_observed'] = True
    assert all(checks.values()), checks
    assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == baseline['pointer_sha256']
    assert all(sha(ROOT/name) == expected for name, expected in frozen['files'].items())
    checks['after_run_input_immutability'] = True
    put(output/'result.json', {'schema_version': 'adr1076-finite-census-result-v1',
        'status': 'COMPLETE', 'strict_success': True, 'checks': checks, 'census': census,
        'serving_files': 420, 'engine_pins': pins, 'changed_files': sorted(changed),
        'wall_seconds': time.perf_counter()-started,
        'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'new_model_calls': 0, 'real_corpus_loads': 0, 'network_calls': 0,
        'limitations': ['Prospectively fixed finite synthetic contract census only; no legal-quality holdout.',
            'The optimization intentionally removes redundant source I/O. Arbitrary failure schedules attached only to omitted redundant I/O are not equivalent events.',
            'Cached reuse requires a synchronous menu and an immutable-store check_unchanged contract; no cross-view or persisted reuse.',
            'No actual service or GENOS speed measured in this primary census. Known ADR1075 replay is separate in-sample secondary evidence.']})
    print('PASS:1318 finite contract pairs;420 serving files;', pins, 'dependency pins;model0/corpus0')
except BaseException as error:
    put(output/'FAILED.json', {'error_type': type(error).__name__, 'error': str(error),
        'traceback': traceback.format_exc(), 'checks_before_failure': checks,
        'wall_seconds': time.perf_counter()-started, 'new_model_calls': 0})
    raise
