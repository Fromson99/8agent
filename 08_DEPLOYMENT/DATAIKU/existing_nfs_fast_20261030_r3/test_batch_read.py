"""Contracts of the exact packaged client; remote database responses are simulated."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TEMP = tempfile.TemporaryDirectory(prefix='nfs-r3-contract-')
CODE = Path(TEMP.name)
with zipfile.ZipFile(HERE/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R3.zip') as z:
    z.extractall(CODE)
sys.path[:0] = [str(CODE), str(CODE/'client'), str(CODE/'client/02_BACKEND'),
               str(ROOT/'05_TESTS/CONTRACTS')]
from semantic_runtime import oracle_dp_io as io
from lawrag.pipeline import oracle_migration as migration
from lawrag.pipeline.oracle_query_dataiku import DataikuClient, render
from test_oracle_dp import Oracle, fixture_source
from semantic_runtime.physical_mapping import SchemaMap
from semantic_runtime import oracle_dp_assets as assets, oracle_query_catalog as q

namespace = dict(globals())
for filename, selected in [('test_oracle_dp_runtime.py', 'AssetOracle'),
                           ('test_oracle_query_catalog.py', 'Oracle'),
                           ('test_existing_nfs_mapped_recovery.py', 'MappedOracle')]:
    source = (ROOT/'05_TESTS/CONTRACTS'/filename).read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == selected)
    exec(compile(ast.get_source_segment(source, node), filename, 'exec'), namespace)
    if selected == 'Oracle': namespace['QueryOracle'] = namespace['Oracle']
MappedOracle = namespace['MappedOracle']


def batch_response(original, method, path, payload):
    """Interpret only new SELECT branches; existing fake validates original templates."""
    sql = payload['statementText']
    binds = {b['name']: b for b in payload.get('binds', [])}
    rows = []
    branches = sql.split(' UNION ALL ')
    assert 1 <= len(branches) <= 32
    for branch in branches:
        match = re.match(r'SELECT :(b\d+)_slot AS CLOB_SLOT, ', branch)
        assert match, branch
        prefix = match[1]
        names = re.findall(r':([A-Za-z][A-Za-z0-9_]*)', branch)
        selected = [dict(binds[n], name=n[len(prefix)+1:]) for n in names if n != prefix+'_slot']
        statement = re.sub(r'^SELECT :b\d+_slot AS CLOB_SLOT, ', 'SELECT ', branch)
        statement = statement.replace(':'+prefix+'_', ':')
        result = original(method, path, dict(payload, statementText=statement, binds=selected, limit=1))
        rows.extend(dict(r, CLOB_SLOT=binds[prefix+'_slot']['value'])
                    for r in result['items'][0]['resultSet']['items'])
    return {'items': [{'resultSet': {'items': list(reversed(rows)), 'hasMore': False, 'offset': 0}}]}


class BatchOracle(Oracle):
    source_clob_batch_size = 32

    def __init__(self):
        super().__init__()
        self.physical = []
        self.fault = None

    def request(self, method, path, json):
        self.physical.append(copy.deepcopy(json))
        if ' AS CLOB_SLOT' not in json['statementText']:
            return super().request(method, path, json)
        if self.fault == 'timeout':
            raise TimeoutError('synthetic timeout')
        result = batch_response(super().request, method, path, json)
        rs = result['items'][0]['resultSet']
        rows = rs['items']
        if self.fault == 'missing': rows.pop()
        elif self.fault == 'duplicate': rows[-1] = dict(rows[0])
        elif self.fault == 'slot': rows[0]['CLOB_SLOT'] = 999
        elif self.fault == 'string_slot': rows[0]['CLOB_SLOT'] = str(rows[0]['CLOB_SLOT'])
        elif self.fault == 'length': rows[0]['TOTAL'] += 1
        elif self.fault == 'empty': rows[0]['PIECE'] = ''
        elif self.fault == 'null': rows[0]['PIECE'] = None
        elif self.fault == 'extra': rows[0]['X'] = 1
        elif self.fault == 'oversize': rows[0]['PIECE'] = 'x' * 1001
        elif self.fault == 'content': rows[0]['PIECE'] = 'x' * io.units(rows[0]['PIECE'])
        elif self.fault == 'hasMore': rs['hasMore'] = True
        elif self.fault == 'offset': rs['offset'] = 1
        elif self.fault == 'db_error': return {'items': [{'errorCode': 1031}]}
        return result


def expected_rows(count=20):
    result = []
    for index in range(count):
        # UTF-16 boundary at the last code unit of each nominal 1000-unit chunk.
        value = ('가' * 999 + '😀' + "'\r\n ") * 3
        result.append(dict(DATASET_VERSION='a'*64, DOCUMENT_ID="문서'001", BLOCK_ID=f'{index:04}',
                           UNIT_ID='0007', TEXT=value, SOURCE_ARTIFACT_SHA256='b'*64,
                           SOURCE_JSON='{"text":"' + value + '"}', JSON_TEXT_ELIDED=0))
    return result


def populate(remote, rows):
    remote.data['block_payload'] = {tuple(r[c] for c in io.KEYS['block_payload']): copy.deepcopy(r) for r in rows}


def test_packaged_bytes_and_same_checkpoint_identity():
    base = HERE.with_name('existing_nfs_transfer_20261029_r2')
    with zipfile.ZipFile(base/'DATAIKU_EXISTING_NFS_CLIENT_20261029_R2.zip') as z:
        for name in ('client/02_BACKEND/lawrag/pipeline/oracle_full_package.py',
                     'client/02_BACKEND/lawrag/pipeline/oracle_migration.py',
                     'client/managed_job.py', 'client/physical_mapping.yaml', 'COMPUTE_CODE_SHA256.txt'):
            assert (CODE/name).read_bytes() == z.read(name)
    for name, digest in json.loads((CODE/'PACKAGE_FILES.json').read_text()).items():
        assert hashlib.sha256((CODE/name).read_bytes()).hexdigest() == digest
    for name, digest in json.loads((CODE/'client/CODE_PINS.json').read_text())['files'].items():
        assert hashlib.sha256((CODE/'client'/name).read_bytes()).hexdigest() == digest


def test_bounded_batch_unicode_order_and_original_bytes(tmp_path):
    remote = BatchOracle(); expected = expected_rows(); populate(remote, expected)
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic')
    observed = io.read_batch(sql, 'block_payload', expected)
    io.compare_batch('block_payload', expected, observed)
    chunks = [p for p in remote.physical if ' AS CLOB_SLOT' in p['statementText']]
    assert chunks and any(p['limit'] == 32 for p in chunks)
    assert all(1 <= p['limit'] <= 32 for p in chunks)
    assert sql.calls == len(remote.physical)
    # Branch offsets must follow actual returned length, including surrogate boundaries.
    positions = [b['value'] for p in chunks for b in p['binds'] if b['name'].endswith('_pos')]
    assert 1000 in positions
    assert not any(' AS PIECE' in p['statementText'] and ' AS CLOB_SLOT' not in p['statementText'] for p in remote.physical)


@pytest.mark.parametrize('fault', ['missing','duplicate','slot','string_slot','length','empty','null',
                                  'extra','oversize','content','hasMore','offset','db_error','timeout'])
def test_invalid_continuations_never_complete_or_retry(tmp_path, fault):
    remote = BatchOracle(); expected = expected_rows(2); populate(remote, expected); remote.fault = fault
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic')
    with pytest.raises(io.DPError):
        io.compare_batch('block_payload', expected, io.read_batch(sql, 'block_payload', expected))
    assert remote.writes == 0
    assert sum(' AS CLOB_SLOT' in p['statementText'] for p in remote.physical) <= 4


def test_null_empty_and_short_values_need_no_continuation(tmp_path):
    remote = BatchOracle(); rows = expected_rows(3)
    for row, value in zip(rows, [None, '', '한글😀']): row.update(TEXT=value, SOURCE_JSON=value)
    populate(remote, rows)
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic')
    observed = io.read_batch(sql, 'block_payload', rows)
    assert observed == rows and sql.calls == 1


def test_missing_existing_rows_and_conflicting_tail(tmp_path):
    remote = BatchOracle(); expected = expected_rows(3); populate(remote, expected[:2])
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic')
    assert io.compare_batch('block_payload', expected, io.read_batch(sql, 'block_payload', expected), require_all=False) == expected[2:]
    key = next(iter(remote.data['block_payload']))
    remote.data['block_payload'][key]['TEXT'] = remote.data['block_payload'][key]['TEXT'][:-1] + 'Z'
    with pytest.raises(io.DPError, match='ROW_CONFLICT'):
        io.compare_batch('block_payload', expected, io.read_batch(sql, 'block_payload', expected))


def test_explicit_serial_mode_preserves_legacy_queries(tmp_path):
    remote = BatchOracle(); remote.source_clob_batch_size = 1
    expected = expected_rows(1); populate(remote, expected)
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic')
    io.compare_batch('block_payload', expected, io.read_batch(sql, 'block_payload', expected))
    assert not any(' AS CLOB_SLOT' in p['statementText'] for p in remote.physical)


def test_cumulative_call_budget_and_no_automatic_retry(tmp_path):
    remote = BatchOracle(); expected = expected_rows(2); populate(remote, expected)
    sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic', max_calls=2)
    with pytest.raises(io.BudgetPause): io.read_batch(sql, 'block_payload', expected)
    assert len(remote.physical) == 2
    next_sql = io.SQL(remote, journal=tmp_path/'calls.jsonl', binding='synthetic', max_calls=2)
    with pytest.raises(io.BudgetPause): io.read_batch(next_sql, 'block_payload', expected)
    assert len(remote.physical) == 2


def test_real_migration_pause_pending_resume_and_idempotence(tmp_path):
    source = fixture_source(tmp_path/'source', n=25)
    remote = BatchOracle()
    args = dict(target_binding='synthetic', directory=tmp_path/'logs', action='run')
    paused = migration.transfer(remote, source, max_batches=2, **args)
    assert paused['status'] == 'PAUSED'
    receipt = Path(paused['receipt']); previous = json.loads(receipt.read_text())
    # Commit a block then lose its response. Resume must reconcile it, preserving the cursor.
    remote.mode = 'after_timeout'
    with pytest.raises(io.DPError, match='WRITE_UNCONFIRMED'): migration.transfer(remote, source, **args)
    failed = json.loads(receipt.read_text()); assert failed['pending']['kind'] == 'block_payload'
    assert migration.transfer(remote, source, **args)['status'] == 'SOURCE_COMPLETE'
    state = json.loads(receipt.read_text())
    assert state['deadline'] == previous['deadline'] and state['pending'] is None
    assert state['calls'] > previous['calls']
    writes = remote.writes
    assert migration.transfer(remote, source, **args)['status'] == 'SOURCE_COMPLETE'
    assert remote.writes == writes
    assert len(remote.data['block_payload']) == 25
    assert migration.transfer(remote, source, **dict(args, action='verify'))['status'] == 'VERIFIED'


def test_physical_mapping_and_real_dataiku_rendering(tmp_path, monkeypatch):
    import pandas as pd
    from lawrag.pipeline import oracle_query_dataiku as bridge
    remote = MappedOracle(SchemaMap.load(CODE/'client/physical_mapping.yaml'))
    remote.source = BatchOracle()
    rows = expected_rows(3); populate(remote.source, rows)
    captured, rendered = {}, []
    original = bridge.render
    def capture(text, binds, **kw):
        captured.update(statementText=text, binds=[dict(name=n,value=v,data_type=t) for n,v,t in binds])
        return original(text, binds, **kw)
    monkeypatch.setattr(bridge, 'render', capture)
    class Executor:
        def query_to_df(self, text, *, infer_from_schema, parse_dates):
            assert infer_from_schema and not parse_dates
            rendered.append(text)
            if ' AS CLOB_SLOT' in text:
                assert ' UNION ALL ' in text and ':b0_' not in text
                assert 'SIDDS.' in text and "문서''001" in text
            result = remote.request('POST', '/sql', dict(captured, limit=32))
            return pd.DataFrame(result['items'][0]['resultSet']['items'])
    client = DataikuClient(Executor(), 'AIDP', 'LEGAL_RAG', schema_map=remote.schema_map)
    client.source_clob_batch_size = 32
    sql = io.SQL(client, journal=tmp_path/'calls.jsonl', binding='synthetic')
    io.compare_batch('block_payload', rows, io.read_batch(sql, 'block_payload', rows))
    assert any(' AS CLOB_SLOT' in text for text in rendered)


def test_progress_displays_pause_reason_without_modifying_files(tmp_path, monkeypatch, capsys):
    import types
    job = tmp_path/'legal-existing-nfs-20261029-r1/financial-risk-success-20261005-schema-r2/oracle-import-r2'
    source = job/'source/synthetic'; source.mkdir(parents=True)
    (job/'full-state.json').write_text(json.dumps(dict(stage='source', status='PAUSED', stages={}, error='STAGE_PAUSED: source')))
    (source/'state.json').write_text(json.dumps(dict(status='PAUSED', reason='BUDGET_PAUSED', calls=158847,
        deadline=1793800000, tables={'block_payload': {'rows':205707}}, pending={'kind':'block_payload','rows':4})))
    (source/'calls.jsonl').write_text(json.dumps(dict(call=158847,status='ACKNOWLEDGED'))+'\n')
    before = {p.relative_to(job):p.read_bytes() for p in job.rglob('*') if p.is_file()}
    monkeypatch.setitem(sys.modules, 'dataiku', types.SimpleNamespace(get_custom_variables=lambda:{'LEGAL_PIPELINE_SCRATCH':str(tmp_path)}))
    text = (HERE/'DATAIKU_NFS_PROGRESS_R3.txt').read_text()
    exec(compile(text, 'progress-r3', 'exec'), {})
    output = capsys.readouterr().out
    assert 'STAGE_PAUSED: source' in output and 'BUDGET_PAUSED' in output and '205707' in output
    assert {p.relative_to(job):p.read_bytes() for p in job.rglob('*') if p.is_file()} == before


