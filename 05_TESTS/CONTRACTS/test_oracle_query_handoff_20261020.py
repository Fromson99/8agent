"""Delivered notebook cell -> maintained publisher; synthetic ORDS, no network/model."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_oracle_dp_runtime import published
from test_compact_v2_rag import structured_generation
from test_oracle_query_catalog import Oracle
from test_oracle_query_schema import SchemaOracle
from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "08_DEPLOYMENT/DATAIKU/legal_oracle_query_transfer_20261020_r1/package/LEGAL_ORACLE_QUERY_TRANSFER_20261020_R1.py"


@pytest.fixture
def handoff(published, tmp_path):
    spec = importlib.util.spec_from_file_location("query_delivery_contract", DELIVERY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, publication, generation = published
    query, schema = Oracle(), SchemaOracle()
    schema.created = {s.split()[2].split('.')[1] for s in q.DDL}
    class Client:
        SQL_PATH = "/sql"
        def request(self, method, path, json):
            text = json['statementText']
            target = schema if 'ALL_' in text else query if 'LEGAL_RAG_QUERY_' in text else source
            return target.request(method, path, json)
    client = Client()
    desk = SimpleNamespace(settings={"log_dir": str(tmp_path / 'logs')}, recovery_required=False,
                           require_connection=lambda: SimpleNamespace(client=client),
                           binding=lambda: 'mock-target', _auth=('test-client', 'test-secret'))
    source_summary = {"status": "TRANSFER_AND_ASSETS_COMPLETE", "DP_RELEASE_ID": publication['release_id'],
                      "dataset_version": source.releases[publication['release_id']]['v']}
    # Previous notebook's summary interface only; current publisher/schema/status APIs are real.
    flow = SimpleNamespace(summary=lambda d, s: copy.deepcopy(source_summary))
    namespace = {'desk': desk, '_legal19_flow': flow, 'SOURCE_SQLITE': str(generation / 'store.sqlite')}
    return module, namespace, query, schema, source, publication, generation


def call(h, action='check', seconds=3600):
    return h[0].run_query_step(h[1], action, ROOT, seconds)


def state_path(h):
    return Path(h[1]['desk'].settings['log_dir']) / 'legal_query_publish' / h[5]['release_id'] / 'state.json'


def test_exact_txt_check_publish_status_and_explicit_repeat(handoff):
    assert DELIVERY.read_bytes() == DELIVERY.with_suffix('.txt').read_bytes()
    source_writes = handoff[4].writes
    assert call(handoff)['status'] == 'READY_TO_PUBLISH'
    assert handoff[2].writes == 0 and not handoff[3].writes
    result = call(handoff, 'publish')
    assert result['status'] == 'COMPLETE' and result['active_changed'] is False
    assert handoff[4].writes == source_writes
    assert not handoff[2].active and not handoff[2].states
    checked = call(handoff, 'status')
    assert checked['status'] == 'QUERY_PUBLICATION_VERIFIED'
    assert checked['rows'] == len(handoff[2].rows) and checked['main_pointer'] is None
    first = json.loads(state_path(handoff).read_text())
    assert call(handoff, 'publish')['release_id'] == result['release_id']
    second = json.loads(state_path(handoff).read_text())
    assert first['deadline'] == second['deadline']
    assert first['verified_rows'] == second['verified_rows']


def test_missing_schema_blocks_before_any_publication(handoff):
    handoff[3].created.remove('LEGAL_Q_ROW_OWNER')
    with pytest.raises(RuntimeError, match='QUERY_SCHEMA_MISSING'):
        call(handoff, 'publish')
    assert not handoff[2].rows and not handoff[3].writes


def test_lost_write_ack_preserves_failed_receipt_and_resumes_once(handoff):
    handoff[2].fail_after_write = True
    with pytest.raises(RuntimeError, match='WRITE_UNCONFIRMED'):
        call(handoff, 'publish')
    failed = json.loads(state_path(handoff).read_text())
    assert failed['status'] == 'FAILED' and handoff[2].rows
    assert not handoff[2].releases and not handoff[2].active
    journal = state_path(handoff).with_name('calls.jsonl')
    calls_before = [json.loads(line) for line in journal.read_text().splitlines()]
    assert call(handoff, 'publish')['status'] == 'COMPLETE'
    complete = json.loads(state_path(handoff).read_text())
    assert complete['deadline'] == failed['deadline']
    assert max(json.loads(line)['call'] for line in journal.read_text().splitlines()) > max(r['call'] for r in calls_before)


def test_expired_budget_is_not_reset_and_status_does_not_claim_complete(handoff):
    call(handoff, 'publish')
    path = state_path(handoff)
    state = json.loads(path.read_text()); state['deadline'] = 1
    path.write_text(json.dumps(state))
    writes = handoff[2].writes
    with pytest.raises(RuntimeError, match='PAUSED'):
        call(handoff, 'publish')
    assert json.loads(path.read_text())['deadline'] == 1
    assert handoff[2].writes == writes
    with pytest.raises(RuntimeError, match='QUERY_NOT_COMPLETE'):
        call(handoff, 'status')


def test_changed_receipt_identity_and_old_desk_hold_block(handoff):
    call(handoff, 'publish')
    path = state_path(handoff)
    saved = json.loads(path.read_text()); saved['identity']['target_binding'] = 'different'
    path.write_text(json.dumps(saved))
    writes = handoff[2].writes
    with pytest.raises(RuntimeError, match='QUERY_RESUME_BINDING'):
        call(handoff, 'publish')
    handoff[1]['desk'].recovery_required = True
    with pytest.raises(RuntimeError, match='R6_STATE'):
        call(handoff)
    assert handoff[2].writes == writes


def test_remote_tampering_rejected_on_publish_and_missing_rows_on_status(handoff):
    call(handoff, 'publish')
    first = next(iter(handoff[2].rows))
    saved = handoff[2].rows.pop(first)
    with pytest.raises(RuntimeError, match='QUERY_ROW_COUNT'):
        call(handoff, 'status')
    handoff[2].rows[first] = {**saved, 'VALUE': '{}', 'N': 2}
    with pytest.raises(RuntimeError, match='ORACLE_ERROR'):
        call(handoff, 'publish')
    assert not handoff[2].active


def test_code_pin_and_resource_rejection_precede_sql(handoff, monkeypatch):
    key = next(iter(handoff[0].CODE_PINS))
    monkeypatch.setitem(handoff[0].CODE_PINS, key, '0' * 64)
    with pytest.raises(RuntimeError, match='CODE_PIN'):
        call(handoff)
    assert not handoff[2].calls


def test_bad_prerequisites_and_failure_secret_masking(handoff):
    with pytest.raises(RuntimeError, match='PREREQUISITE'):
        handoff[0].run_query_step({}, 'check', ROOT)
    def failure(*args):
        raise RuntimeError('example test-secret failure')
    handoff[1]['_legal19_flow'].summary = failure
    with pytest.raises(RuntimeError, match=r'\[MASKED\]'):
        call(handoff)
    log = Path(handoff[1]['desk'].settings['log_dir']) / 'legal_query_handoff_events.jsonl'
    assert 'test-secret' not in log.read_text()
    assert 'traceback' in log.read_text()
