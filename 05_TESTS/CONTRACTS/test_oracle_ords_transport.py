"""Real loopback HTTP, missing SDK, and single-send Oracle consumer contracts."""
import base64
import builtins
import importlib.util
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.error import URLError

import pytest

from semantic_runtime import oracle_dp, oracle_ords
from semantic_runtime.oracle_dp_io import DPError, SQL, BudgetPause
from semantic_runtime.oracle_query import QuerySQL


@pytest.fixture
def endpoint():
    state = SimpleNamespace(calls=[], status=200, expiry=3600, token_body=None,
                            sql_body={'items': [{'resultSet': {
                                'items': [{'answer': '한글 원문'}], 'offset': 0, 'hasMore': False}}]})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = self.rfile.read(int(self.headers['Content-Length']))
            state.calls.append((self.path, self.headers['Authorization'], data))
            auth = self.path.endswith('/oauth/token')
            body = (state.token_body if state.token_body is not None else
                    {'access_token': 'test-token', 'token_type': 'Bearer', 'expires_in': state.expiry}) if auth else state.sql_body
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200 if auth else state.status)
            if not auth and state.status in (301, 302, 307, 308):
                self.send_header('Location', '/redirect-must-not-be-followed')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    state.url = f'http://127.0.0.1:{server.server_port}/ords/'
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def missing_sdk(monkeypatch, name='genos'):
    original = builtins.__import__

    def importing(module, *args, **kwargs):
        if module == 'genos.ords':
            raise ModuleNotFoundError('test SDK import failure', name=name)
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', importing)


def configured(monkeypatch, endpoint):
    monkeypatch.setenv('DP', 'oracle')
    monkeypatch.setenv('GENOS_ORACLE_TABLE_MAPPING', 'mapped')
    monkeypatch.setenv('ORACLE_ORDS_SCHEMA', 'b04')
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_ID', 'test-id')
    monkeypatch.setenv('ORACLE_ORDS_CLIENT_SECRET', 'test-secret')
    monkeypatch.delenv('ORACLE_ORDS_BASE_URL', raising=False)
    monkeypatch.setenv('LLMOPS_ORDS_BASE_URL', endpoint.url)


def rest(endpoint):
    return oracle_ords.RestClient(schema='b04', auth_key=('test-id', 'test-secret'),
                                  base_url=endpoint.url)


@pytest.mark.parametrize('missing', ['genos', 'genos.ords'])
def test_real_read_uses_existing_factory_mapping_and_sql_contract(monkeypatch, endpoint, missing):
    configured(monkeypatch, endpoint)
    missing_sdk(monkeypatch, missing)
    client = oracle_dp.client_from_environment()
    assert isinstance(client, oracle_ords.RestClient)
    assert client.schema_map.names('document').table
    sql = QuerySQL(client, binding='test', deadline=time.monotonic()+10, max_calls=2)
    statement = 'SELECT :value AS answer FROM dual'
    for _ in range(2):
        assert sql.query(statement, [('value', '한글 원문', 'VARCHAR2')], limit=1) == [{'ANSWER': '한글 원문'}]
    assert sql.calls == 2
    assert len(endpoint.calls) == 3  # one OAuth, two SQL; budget counts SQL as before
    assert endpoint.calls[0][:2] == ('/ords/b04/oauth/token', 'Basic ' + base64.b64encode(b'test-id:test-secret').decode())
    sent = endpoint.calls[1]
    assert sent[:2] == ('/ords/b04/_/sql', 'Bearer test-token')
    assert json.loads(sent[2]) == {'statementText': statement, 'offset': 0, 'limit': 1,
                                 'binds': [{'name': 'value', 'value': '한글 원문', 'data_type': 'VARCHAR2'}]}
    with pytest.raises(BudgetPause):
        sql.query(statement)
    assert len(endpoint.calls) == 3


def test_sdk_is_preserved_without_rest_or_changed_options(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    sdk = ModuleType('genos.ords')
    calls = []
    sdk.ORDSClient = lambda **kw: (calls.append(kw) or SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'genos.ords', sdk)
    client = oracle_dp.client_from_environment()
    assert client.schema_map
    assert calls == [{'schema': 'b04', 'auth_key': ('test-id', 'test-secret'), 'timeout': 600, 'verify': True}]
    assert not endpoint.calls  # SDK default URL remains untouched


def test_ords_timeout_from_environment(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    sdk = ModuleType('genos.ords')
    calls = []
    sdk.ORDSClient = lambda **kw: (calls.append(kw) or SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'genos.ords', sdk)
    monkeypatch.setenv('GENOS_ORACLE_ORDS_TIMEOUT_SECONDS', '120')
    oracle_dp.client_from_environment()
    assert calls[-1]['timeout'] == 120
    monkeypatch.setenv('GENOS_ORACLE_ORDS_TIMEOUT_SECONDS', 'ten')
    with pytest.raises(DPError, match='GENOS_ORACLE_ORDS_TIMEOUT_SECONDS'):
        oracle_dp.client_from_environment()


def test_broken_sdk_dependency_does_not_fall_back(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    missing_sdk(monkeypatch, 'sdk_internal_dependency')
    with pytest.raises(DPError, match='SDK dependency'):
        oracle_dp.client_from_environment()
    assert not endpoint.calls


def test_sdk_constructor_failure_does_not_fall_back(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    sdk = ModuleType('genos.ords')

    def fail(**kwargs):
        raise RuntimeError('test-secret must not be returned')

    sdk.ORDSClient = fail
    monkeypatch.setitem(sys.modules, 'genos.ords', sdk)
    with pytest.raises(DPError, match='DP_CONNECT: RuntimeError') as err:
        oracle_dp.client_from_environment()
    assert 'test-secret' not in str(err.value)
    assert not endpoint.calls


@pytest.mark.parametrize('status', [301, 302, 307, 308, 401, 403, 429, 500, 503])
def test_write_http_failure_is_unconfirmed_and_never_resent(endpoint, tmp_path, status):
    endpoint.status = status
    endpoint.sql_body = {'error': 'test-secret test-token raw SQL content'}
    sql = SQL(rest(endpoint), journal=tmp_path/'calls.jsonl', binding='test', max_calls=5)
    with pytest.raises(DPError, match=f'WRITE_UNCONFIRMED: ORDS_SQL_HTTP: {status}') as err:
        sql.request('BEGIN NULL; END;', write=True)
    assert all(s not in str(err.value) for s in ['test-secret', 'test-token', 'raw SQL'])
    assert len(endpoint.calls) == 2
    assert sql.calls == 1
    events = [json.loads(line) for line in (tmp_path/'calls.jsonl').read_text().splitlines()]
    assert [e['status'] for e in events] == ['STARTED', 'WRITE_UNCONFIRMED']


def test_real_write_ack_and_oracle_error_are_not_swallowed(endpoint, tmp_path):
    endpoint.sql_body = {'items': [{'result': 1}]}
    sql = SQL(rest(endpoint), journal=tmp_path/'write.jsonl', binding='test')
    assert sql.request('BEGIN NULL; END;', write=True) == {'result': 1}
    endpoint.sql_body = {'items': [{'errorCode': 942, 'errorMessage': 'test-secret'}]}
    with pytest.raises(DPError, match='ORACLE_ERROR: ORA-00942'):
        sql.query('SELECT 1 FROM missing_table')
    assert len(endpoint.calls) == 3


def test_partial_read_remains_failure(endpoint):
    endpoint.sql_body['items'][0]['resultSet']['hasMore'] = True
    sql = QuerySQL(rest(endpoint), binding='test', deadline=time.monotonic()+10)
    with pytest.raises(DPError, match='PARTIAL_READ'):
        sql.query('SELECT answer FROM dual')
    assert len(endpoint.calls) == 2


def test_timeout_after_sql_send_never_replays(endpoint, tmp_path):
    client = rest(endpoint)
    original = client._opener.open
    sql_sends = []

    def open_once(request, **kwargs):
        if request.full_url.endswith('/_/sql'):
            sql_sends.append(request.data)
            raise URLError(TimeoutError('response lost after commit'))
        return original(request, **kwargs)

    client._opener.open = open_once
    sql = SQL(client, journal=tmp_path/'lost.jsonl', binding='test')
    with pytest.raises(DPError, match='WRITE_UNCONFIRMED: ORDS_SQL_TRANSPORT'):
        sql.request('BEGIN NULL; END;', write=True)
    assert len(sql_sends) == 1 and sql.calls == 1


def test_token_expiry_and_concurrent_requests(endpoint):
    client = rest(endpoint)
    send = lambda _: client.request('POST', client.SQL_PATH, json={'statementText': 'SELECT 1 FROM dual'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(list(pool.map(send, range(4)))) == 4
    assert sum(p.endswith('/oauth/token') for p, _, _ in endpoint.calls) == 1
    client._expires_at = 0
    send(None)
    assert sum(p.endswith('/oauth/token') for p, _, _ in endpoint.calls) == 2
    assert sum(p.endswith('/_/sql') for p, _, _ in endpoint.calls) == 5


@pytest.mark.parametrize('body', [b'invalid JSON test-secret', [], {}, {'access_token': 'bad\ntoken'},
                                  {'access_token': 'valid', 'token_type': 'Basic'}])
def test_invalid_auth_never_sends_sql(endpoint, body):
    endpoint.token_body = body
    client = rest(endpoint)
    with pytest.raises(DPError):
        client.request('POST', client.SQL_PATH, json={'statementText': 'SELECT 1 FROM dual'})
    assert len(endpoint.calls) == 1


def test_missing_rest_address_is_explicit_config_error(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    missing_sdk(monkeypatch)
    monkeypatch.delenv('LLMOPS_ORDS_BASE_URL')
    with pytest.raises(DPError, match='DP_CONFIG: REST requires'):
        oracle_dp.client_from_environment()
    assert not endpoint.calls


def test_explicit_base_url_and_case_sensitive_alias_are_preserved(monkeypatch, endpoint):
    configured(monkeypatch, endpoint)
    missing_sdk(monkeypatch)
    monkeypatch.setenv('ORACLE_ORDS_BASE_URL', endpoint.url)
    monkeypatch.setenv('LLMOPS_ORDS_BASE_URL', 'https://unused.invalid')
    monkeypatch.setenv('ORACLE_ORDS_SCHEMA', 'B04')
    client = oracle_dp.client_from_environment()
    client.request('POST', client.SQL_PATH, json={'statementText': 'SELECT 1 FROM dual'})
    assert [p for p, _, _ in endpoint.calls] == ['/ords/B04/oauth/token', '/ords/B04/_/sql']


def test_expired_transport_deadline_sends_nothing(endpoint):
    client = rest(endpoint)
    with pytest.raises(DPError, match='ORDS_TIMEOUT'):
        client._token(time.monotonic()-1)
    assert not endpoint.calls


def test_actual_root_service_factory_selects_rest_without_network_at_construction(monkeypatch, endpoint, tmp_path):
    configured(monkeypatch, endpoint)
    missing_sdk(monkeypatch)
    for key in ('GENOS_LLM_URL', 'GENOS_LLM_KEY', 'GENOS_LLM_MODEL', 'GENOS_LLM_SERVING_ID',
                'GENOS_RAG_ONTOLOGY_CONFIG', 'DP_QUERY_RELEASE_ID', 'GENOS_SHARED_LOG_DIR',
                'GENOS_DETAIL_LOG_DIR', 'GENOS_STATE_DIR'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('GENOS_RUNTIME_DIR', str(tmp_path/'oracle-runtime'))
    monkeypatch.setenv('GENOS_SYSTEM_LOG_DIR', str(tmp_path/'logs'))
    monkeypatch.setenv('GENOS_AUTO_WARMUP', '0')
    from semantic_runtime import oracle_runtime_paths
    monkeypatch.setattr(oracle_runtime_paths, '_PROVIDER', None)
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('ords_root_service_contract', root/'service.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    factory = entry._oracle_factory()
    assert factory.is_oracle_query_factory
    assert isinstance(factory.client, oracle_ords.RestClient)
    assert factory.client.schema_map.names('document').table
    assert factory.binding['data_provider'] == 'oracle'
    assert not endpoint.calls
    sql = QuerySQL(factory.client, binding='service-contract', deadline=time.monotonic()+10)
    assert sql.query('SELECT answer FROM dual') == [{'ANSWER': '한글 원문'}]
    assert len(endpoint.calls) == 2


@pytest.mark.parametrize('response', [b'not JSON', [], {'items': []}])
def test_invalid_sql_response_preserves_failure(endpoint, response):
    endpoint.sql_body = response
    sql = QuerySQL(rest(endpoint), binding='test', deadline=time.monotonic()+10)
    with pytest.raises(DPError):
        sql.query('SELECT answer FROM dual')
    assert len(endpoint.calls) == 2 and sql.calls == 1


def test_response_bound_is_enforced_without_retry(endpoint):
    client = rest(endpoint)
    client.MAX_RESPONSE_BYTES = 10
    sql = QuerySQL(client, binding='test', deadline=time.monotonic()+10)
    with pytest.raises(DPError, match='ORDS_SQL_SIZE'):
        sql.query('SELECT answer FROM dual')
    assert len(endpoint.calls) == 2


def test_401_refreshes_for_next_request_without_replaying_failed_sql(endpoint):
    client = rest(endpoint)
    endpoint.status = 401
    with pytest.raises(DPError, match='ORDS_SQL_HTTP: 401'):
        client.request('POST', client.SQL_PATH, json={'statementText': 'first SQL'})
    assert len(endpoint.calls) == 2
    endpoint.status = 200
    client.request('POST', client.SQL_PATH, json={'statementText': 'second SQL'})
    assert [json.loads(data)['statementText'] for path, _, data in endpoint.calls if path.endswith('/_/sql')] == ['first SQL', 'second SQL']
    assert sum(path.endswith('/oauth/token') for path, _, _ in endpoint.calls) == 2
