"""Explicit frozen-candidate local contracts; never field Dataiku/Oracle."""
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1263-dataiku-bulk-insert-resume'
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1263/bulk'
BASE_REL = Path('08_DEPLOYMENT/DATAIKU/existing_nfs_resume_only_20261030_r10/candidate')
manifest = json.loads((CANDIDATE / 'candidate.json').read_text())
revision = os.environ.get('ADR1263_REVISION', manifest.get('active_revision', 'rev-001'))


def locate():
    # Validate with the official tool before loading any candidate implementation.
    subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / '06_TOOLS/run_tool.py'),
                    'adr_candidate.py', 'validate', str(CANDIDATE)], check=True)
    paths = list((CANDIDATE / 'revisions').glob(revision + '/snapshot'))
    if not paths:
        raise RuntimeError('Frozen revision layout must be inspected, never fall back to mutable snapshot')
    return paths[0] / BASE_REL


def run(code):
    sys.path[:0] = [str(code), str(code / 'client'), str(code / 'client/02_BACKEND')]
    from semantic_runtime import oracle_dp_io as io, oracle_query_catalog as q
    from semantic_runtime.physical_mapping import SchemaMap
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient, render
    from lawrag.pipeline import oracle_deferred_import as deferred
    result = {'revision': revision, 'checks': [], 'field_Dataiku_executed': False,
              'model_calls': 0, 'production_database_changes': False}
    def passed(name): result['checks'].append(name)
    class Capture:
        schema_map = None
        def request(self, statement, binds, **kwargs): self.statement, self.binds = statement, binds
    def rows(start, n):
        return [q.record('bulk.test', {'i': i, 'text': "한글😀 O'Reilly :value " * 30}, key=i,
                         document_id='0007', lookup_id=str(i), owner_id=None if i % 2 else 'source')
                for i in range(start, start+n)]
    batch = rows(0, 500)
    cap = Capture(); q.insert_records(cap, 'a' * 64, batch)
    assert sum(kind == 'CLOB' for _, _, kind in cap.binds) == 1
    assert cap.statement.count('INSERT INTO ') == 1 and cap.statement.count('SELECT COUNT(*)') == 1
    decoded = json.loads(dict((n, v) for n, v, _ in cap.binds)['payload'])
    assert [v['body'] for v in decoded] == [q.json_body(v['value']) for v in batch]
    passed('one_payload_two_set_statements_exact_original_bodies')
    legacy = [('a', rows(i, min(20, 1203-i))) for i in range(0, 1203, 20)]
    for after in (0, 1, 3, 25, 59, 61):
        for size in (20, 500, 5000):
            with patch.object(deferred, 'batches', return_value=iter(legacy)):
                groups = list(deferred.write_groups(None, None, None, after=after, max_rows=size))
            assert [r for _, rs, _ in groups for r in rs] == [r for _, rs in legacy[after:] for r in rs]
            assert all(len(rs) <= size for _, rs, _ in groups)
            assert not groups or groups[-1][2] == len(legacy)
    passed('18_legacy_cursor_and_group_sizes_exact')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='adr1263-contract-') as td:
        path = Path(td)
        with patch.object(deferred.query, 'describe', return_value=({}, {}, {})):
            original = deferred.io.file_sha
            with patch.object(deferred.io, 'file_sha', wraps=deferred.io.file_sha) as sha:
                sha.side_effect = lambda p: deferred.R10_DESCRIPTOR_EXECUTOR if str(p) == deferred.__file__ else original(p)
                deferred.prepared_descriptor(path, {'x': 1}, {}, path)
        with patch.object(deferred.query, 'describe', side_effect=AssertionError('no re-describe')):
            deferred.prepared_descriptor(path, {'x': 1}, {}, path, strict=True)
    passed('strict_R10_completed_descriptor_reused')
    # Baseline implementation only, with the same unchanged record helpers.
    source = (ROOT / BASE_REL / 'client/02_BACKEND/semantic_runtime/oracle_query_catalog.py').read_text()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'insert_records')
    baseline_globals = dict(q.__dict__)
    exec(compile(ast.get_source_segment(source, node), 'R10-frozen-baseline-insert', 'exec'), baseline_globals)
    baseline = baseline_globals['insert_records']
    import oracledb
    import pandas as pd
    metadata = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
    password = dict(x.split('=', 1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
    admin = oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1', user='system', password=password)
    user = 'A8_BULK_' + secrets.token_hex(4).upper(); pw = secrets.token_hex(20); conn = None
    out = ADR / 'artifacts/run-001'; out.mkdir(exist_ok=True)
    try:
        with admin.cursor() as c:
            c.execute(f'CREATE USER {user} IDENTIFIED BY "{pw}" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
            c.execute(f'GRANT CREATE SESSION,CREATE TABLE TO {user}')
        conn = oracledb.connect(dsn='127.0.0.1:11524/FREEPDB1', user=user, password=pw)
        result['oracle_version'] = conn.version
        schema = SchemaMap.load(code / 'client/physical_mapping.yaml'); p = schema.names('query_row')
        columns = ['RELEASE_ID','KIND','ROW_ID','DOCUMENT_ID','LOOKUP_ID','OWNER_ID','TARGET_ID','ROW_SHA256','VALUE_JSON']
        with conn.cursor() as c:
            c.execute('CREATE TABLE ' + p.table.split('.')[-1] + ' (' + ','.join(
                p.c(x) + ' ' + ('CLOB NOT NULL' if x == 'VALUE_JSON' else 'VARCHAR2(512)') for x in columns)
                + ',PRIMARY KEY(' + ','.join(p.c(x) for x in columns[:3]) + '),CHECK(' + p.c('VALUE_JSON') + ' IS JSON))')
        class Executor:
            writes = 0
            fail_ack = False
            last_bytes = 0
            def query_to_df(self, statement, **kwargs):
                with conn.cursor() as c:
                    for text in kwargs.get('pre_queries', []):
                        self.last_bytes = len(text.encode()); c.execute(text.replace('SIDDS.', user + '.')); self.writes += 1
                    c.execute(statement.replace('SIDDS.', user + '.')); names = [v[0] for v in c.description]
                    value = [[v.read() if hasattr(v, 'read') else v for v in row] for row in c.fetchall()]
                    for text in kwargs.get('post_queries', []): c.execute(text)
                if self.fail_ack:
                    self.fail_ack = False
                    raise TimeoutError('injected acknowledgment loss after commit')
                return pd.DataFrame(value, columns=names)
        executor = Executor(); client = DataikuClient(executor, 'LOCAL_SYNTHETIC', 'TEST', schema_map=schema)
        sql = io.SQL(client, journal=out / 'synthetic-sql.jsonl', binding='isolated-adr1263-' + user)
        timings = []
        for i, arm in enumerate(('baseline', 'bulk', 'bulk', 'baseline')):
            rid = hashlib.sha256(('timing-' + str(i)).encode()).hexdigest()
            began = time.perf_counter(); (baseline if arm == 'baseline' else q.insert_records)(sql, rid, batch)
            timings.append({'arm': arm, 'rows': 500, 'seconds': time.perf_counter()-began,
                            'rendered_sql_bytes': executor.last_bytes, 'boundaries': dict(client.last_timing)})
        result['timings'] = timings
        passed('same_500_rows_order_ABBA_all_committed')
        rid = 'a' * 64
        def stored(release):
            with conn.cursor() as c:
                c.execute('SELECT ' + ','.join(p.c(x) for x in columns[1:]) + ' FROM '
                          + p.table.replace('SIDDS.', user+'.') + ' WHERE ' + p.c('RELEASE_ID') + '=:1', [release])
                return {row[1]: [v.read() if hasattr(v, 'read') else v for v in row] for row in c.fetchall()}
        def exact(expected):
            actual = stored(rid)
            assert len(actual) == len(expected)
            for row in expected:
                assert actual[row['row_id']] == [row['kind'], row['row_id'], row['document_id'], row['lookup_id'],
                       row['owner_id'], row['target_id'], row['sha256'], q.json_body(row['value'])]
        q.insert_records(sql, rid, batch); exact(batch); passed('500_exact_full_value_readback')
        q.insert_records(sql, rid, batch); exact(batch); passed('repeat_same_request_no_duplicates')
        other = rows(1000, 500)
        conflict = q.record('bulk.test', {'different': True}, key=0, document_id='0007', lookup_id='0', owner_id='source')
        try: q.insert_records(sql, rid, other[:499] + [conflict])
        except io.DPError: pass
        else: raise AssertionError('unequal existing row accepted')
        exact(batch); passed('499_new_rows_then_conflict_full_rollback')
        executor.fail_ack = True
        try: q.insert_records(sql, rid, other)
        except io.DPError: pass
        else: raise AssertionError('unknown ACK became success')
        exact(batch + other)
        q.insert_records(sql, rid, other); exact(batch + other); passed('commit_ack_loss_explicit_resume_idempotent')
        q.insert_records(sql, rid, [batch[0], batch[0]]); exact(batch + other); passed('same_key_identical_duplicate_in_batch')
        try: q.insert_records(sql, rid, [batch[0], conflict])
        except io.DPError: pass
        else: raise AssertionError('unequal within batch accepted')
        exact(batch + other); passed('same_key_unequal_duplicate_rejected')
        large = [q.record('bulk.test', {'text': "한글😀\\\"\n" * 10000, 'empty': '', 'null': None,
                 'nested': [1, {'x': "' :payload"}]}, key=90000, document_id=None, lookup_id='긴본문')]
        q.insert_records(sql, rid, large); exact(batch + other + large); passed('long_CLOB_Unicode_null_empty_exact')
        capacity = rows(10000, 5000)
        began = time.perf_counter(); q.insert_records(sql, rid, capacity)
        result['capacity_5000_seconds'] = time.perf_counter() - began
        exact(batch + other + large + capacity); passed('5000_one_request_exact_full_readback')
        result['status'] = 'PASS'
    except BaseException as exc:
        result.update(status='FAIL', error_type=type(exc).__name__, error=str(exc)[:500])
        raise
    finally:
        if conn: conn.close()
        with admin.cursor() as c: c.execute('DROP USER ' + user + ' CASCADE')
        admin.close()
        result['isolated_schema_removed'] = True
        (out / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run(locate())
