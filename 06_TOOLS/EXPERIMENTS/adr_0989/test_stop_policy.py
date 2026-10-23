from stop_policy import StopPolicy, RunStopped, terminal_failure
import pytest

def test_provider_failure_stops_even_after_exit_zero(tmp_path):
    p = StopPolicy(tmp_path / 'stop.json')
    p.before_call(0)
    p.stop('PROVIDER_FAILURE', 1, 429)
    assert terminal_failure({'service_status': 503}, {'reason': 'PROVIDER_FAILURE'}, 0) == 'PROVIDER_FAILURE'
    with pytest.raises(RunStopped): p.before_call(1)
    with pytest.raises(RunStopped): StopPolicy(p.path).before_call(0)

def test_budget_stops_before_ninth_call(tmp_path):
    p = StopPolicy(tmp_path / 'stop.json')
    for n in range(8): p.before_call(n)
    with pytest.raises(RunStopped): p.before_call(8)
    with pytest.raises(RunStopped): p.before_call(0)

def test_first_failure_preserved(tmp_path):
    p = StopPolicy(tmp_path / 'stop.json')
    p.stop('PROVIDER_FAILURE', 1, 429)
    before = p.path.read_bytes()
    p.stop('SERVICE_FAILURE', 2)
    assert p.path.read_bytes() == before

@pytest.mark.parametrize('result,code,expected', [
    ({'service_status': 200, 'error': None}, 0, None),
    ({'service_status': 503, 'error': None}, 0, 'SERVICE_FAILURE'),
    ({'service_status': 200, 'error': {'type': 'Failure'}}, 0, 'RECORDED_FAILURE'),
    ({'service_status': 200}, 1, 'PROCESS_FAILURE'),
])
def test_terminal_result(result, code, expected):
    assert terminal_failure(result, exit_code=code) == expected
