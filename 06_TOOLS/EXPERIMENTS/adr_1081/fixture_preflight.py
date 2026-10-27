"""Fixture construction only: no product import, bind, or consumer execution.

Extract only fixture-generation functions from the old/new harness ASTs and
literal SQL from the frozen production shared_reference_schema AST. Execute
that DDL and synthetic INSERTs in ephemeral SQLite databases. This is an input
integrity preflight, never a baseline/candidate product result comparison.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
import resource
import socket
import sqlite3
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1081-reference-visibility-valid-fixtures'
OLD = ROOT / '06_TOOLS/EXPERIMENTS/adr_1080'
OLD_ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1080-reference-visibility-point-check'
PRIMARY_KEYS = {
    'source': ('id',), 'reference': ('id',),
    'reference_end': ('source_id', 'reference_id'),
    'reference_target': ('reference_id', 'ordinal'),
    'reference_candidate': ('reference_id', 'candidate_id'),
    'reference_candidate_end': ('source_id', 'reference_id', 'candidate_id'),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def read(path):
    return json.loads(Path(path).read_text())


def extract_fixture(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    wanted = {'_json', '_sha', '_reference', '_fixture_rows', '_cases'}
    constants = {'ROLES', 'COLUMNS', 'BASE_DDL'}
    namespace = {'json': json, 'hashlib': hashlib, 'deepcopy': deepcopy, 'product': product}
    functions = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants:
                namespace[name] = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            functions.append(node)
    assert {node.name for node in functions} == wanted and constants <= namespace.keys()
    # No module imports or product-capable harness functions enter this code.
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(path) + ':fixture-only', 'exec'), namespace)
    return namespace, {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                       if isinstance(node, ast.FunctionDef)}


def schema_statements(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'shared_reference_schema')
    statements = []
    for node in function.body:
        assert isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        call = node.value
        assert isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
        assert call.func.value.id == 'db' and call.func.attr in ('execute', 'executescript')
        assert len(call.args) == 1 and not call.keywords
        sql = ast.literal_eval(call.args[0])
        assert isinstance(sql, str)
        statements.append((call.func.attr, sql))
    assert len(statements) == 2 and statements[0] == ('execute', 'DROP TABLE reference')
    return statements


def key_report(rows, columns):
    violations, nullable_duplicates = {}, {}
    for name, values in rows.items():
        assert all(len(row) == len(columns[name]) for row in values), name
        indices = [columns[name].index(column) for column in PRIMARY_KEYS[name]]
        counts = Counter(tuple(row[index] for index in indices) for row in values)
        bad = [(key, count) for key, count in counts.items() if count > 1 and all(v is not None for v in key)]
        nullable = [(key, count) for key, count in counts.items() if count > 1 and any(v is None for v in key)]
        if bad:
            violations[name] = bad
        if nullable:
            nullable_duplicates[name] = nullable
    return violations, nullable_duplicates


def construct(fixture, schema, case, rows):
    db = sqlite3.connect(':memory:')
    try:
        # Match the unchanged frozen harness's construction and serialization.
        db.execute('PRAGMA cache_size=-1024')
        db.execute('PRAGMA temp_store=MEMORY')
        db.executescript(fixture['BASE_DDL'])
        if case['layout'] == 'compact':
            for operation, sql in schema:
                getattr(db, operation)(sql)
        columns = fixture['COLUMNS']
        for name, values in rows.items():
            info = db.execute('PRAGMA main.table_info("' + name + '")').fetchall()
            assert tuple(row[1] for row in info) == columns[name], (case['id'], name, info)
            if name in fixture['ROLES']:
                pk = tuple(row[1] for row in sorted(info, key=lambda row: row[5]) if row[5])
                assert pk == PRIMARY_KEYS[name], (case['id'], name, pk)
                assert all(row[3] == 0 for row in info if row[5]), 'Fixture rowid PK changed NULL rules'
            placeholders = ','.join('?' for _ in columns[name])
            db.executemany('INSERT INTO "' + name + '" VALUES (' + placeholders + ')', values)
        assert db.execute('PRAGMA main.integrity_check').fetchall() == [('ok',)]
        # These are the declared fixture mutations, not product requests. They
        # run only after a valid schema and legal initial rows were confirmed.
        if case['category'] == 'requested_failures':
            fault = case['fault']
            if fault == 'requested_malformed_json':
                table = 'reference_payload' if case['layout'] == 'compact' else 'reference'
                db.execute('UPDATE ' + table + ' SET json=? WHERE id=?', ('{malformed', 'R10'))
            elif fault == 'missing_reference_relation':
                db.execute(('DROP VIEW' if case['layout'] == 'compact' else 'DROP TABLE') + ' reference')
            elif fault == 'missing_source_relation':
                db.execute('DROP TABLE source')
            else:
                raise AssertionError(fault)
        db.commit()
        db.execute('PRAGMA query_only=ON')
        assert db.execute('PRAGMA main.integrity_check').fetchall() == [('ok',)]
        return hashlib.sha256(db.serialize(name='main')).hexdigest()
    finally:
        db.close()


def prior_success_hashes(path, expected_ids, failed_case):
    found = {}
    setup_failure_seen = False
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('kind') != 'pair':
                continue
            ident = row['case']['id']
            if ident in expected_ids:
                assert ident not in found and row['problems'] == []
                baseline, optimized = row['baseline'], row['optimized']
                assert baseline['status'] == optimized['status'] == 'COMPLETE'
                assert baseline['main_before_sha256'] == optimized['main_before_sha256']
                found[ident] = baseline['main_before_sha256']
            else:
                assert ident == failed_case and not setup_failure_seen
                assert all(row[arm]['status'] == 'HARNESS_ERROR' and row[arm]['observations'] == []
                           and row[arm]['error_type'] == 'IntegrityError' for arm in ('baseline', 'optimized'))
                setup_failure_seen = True
    assert set(found) == expected_ids and setup_failure_seen
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ADR / 'artifacts/design/fixture-preflight.json')
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = output.with_name(output.stem + '-rows.jsonl.gz')
    if output.exists() or raw.exists():
        raise FileExistsError('Preflight output already exists; preserve it and use a new explicit output path')
    resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    sys.dont_write_bytecode = True
    def forbidden(*args, **kwargs):
        raise RuntimeError('Fixture-only preflight forbids networking')
    socket.getaddrinfo = forbidden
    socket.socket.connect = forbidden
    def forbid_product_import(event, args):
        if event == 'import' and (args[0].startswith(('semantic_runtime', 'lawrag', '_adr1080_', '_adr1081_'))):
            raise RuntimeError('Fixture-only preflight forbids product imports')
    sys.addaudithook(forbid_product_import)
    started = time.perf_counter()
    checks, failures, changed, nullable, seen = {}, [], [], [], []
    observed_count = primary_count = 0
    current = None
    input_hashes = {}
    result = {}
    with gzip.open(raw, 'xt', encoding='utf-8') as stream:
        def emit(row):
            stream.write(encoded(row).decode() + '\n')
            stream.flush()
        try:
            matrix_path = HERE / 'sql-matrix.json'
            matrix = read(matrix_path)
            freeze_path = OLD_ADR / 'artifacts/design/freeze.json'
            frozen = read(freeze_path)
            schema_path = ROOT / frozen['code_root'] / '02_BACKEND/semantic_runtime/reference_build.py'
            assert sha(schema_path) == frozen['serving_files']['02_BACKEND/semantic_runtime/reference_build.py']
            prior_raw = ROOT / matrix['evidence_partition']['prior_source']
            inputs = [Path(__file__).resolve(), HERE/'sql_contract.py', matrix_path,
                      OLD/'sql_contract.py', OLD/'sql-matrix.json', freeze_path, schema_path,
                      prior_raw, OLD_ADR/'artifacts/run-001/sql-first-failure.json']
            input_hashes = {str(path.relative_to(ROOT)): sha(path) for path in inputs}
            for path in (OLD/'sql_contract.py', OLD/'sql-matrix.json'):
                assert input_hashes[str(path.relative_to(ROOT))] == frozen['files'][str(path.relative_to(ROOT))]
            emit({'kind': 'inputs', 'hashes': input_hashes, 'sqlite_version': sqlite3.sqlite_version})
            before, old_nodes = extract_fixture(OLD/'sql_contract.py')
            after, new_nodes = extract_fixture(HERE/'sql_contract.py')
            schema = schema_statements(schema_path)
            assert before['BASE_DDL'] == after['BASE_DDL'] and before['COLUMNS'] == after['COLUMNS']
            protected = ('_database', '_visible', '_queries', '_query', '_guard', '_point_plan', '_problems', '_cases')
            assert all(old_nodes[name] == new_nodes[name] for name in protected)
            checks['product_result_error_plan_contract_ast_unchanged'] = True
            partition = matrix['evidence_partition']
            observed_ids = set(partition['observed_case_ids'])
            primary_ids = set(partition['new_primary_case_ids'])
            assert len(observed_ids) == 1345 and len(primary_ids) == 237 and not observed_ids & primary_ids
            previous_hashes = prior_success_hashes(prior_raw, observed_ids, partition['prior_fixture_failure_case_id'])
            checks['prior_success_ids_and_setup_only_failure_verified'] = True
            expected_changed = set(partition['modified_fixture_case_ids'])
            assert len(expected_changed) == 18
            for case in after['_cases'](matrix):
                current = case
                old_rows, old_subject, old_focus = before['_fixture_rows'](case)
                new_rows, new_subject, new_focus = after['_fixture_rows'](case)
                assert (old_subject, old_focus) == (new_subject, new_focus)
                violations, null_duplicates = key_report(new_rows, after['COLUMNS'])
                old_violations, old_null_duplicates = key_report(old_rows, before['COLUMNS'])
                assert not violations, (case, violations)
                assert null_duplicates == old_null_duplicates
                modified = new_rows != old_rows
                assert modified == (case['id'] in expected_changed)
                if modified:
                    assert set(old_violations) == {'reference_end'}
                    assert {name for name in new_rows if new_rows[name] != old_rows[name]} == {'reference_end'}
                    assert case['category'] == 'source_boundary' and case['role'] == 'reference_end'
                    assert case['source_state'] != 'null_id' and case['multiplicity'] == 3
                    subject_edges = [row for row in new_rows['reference_end'] if row[1] == 'R10']
                    assert [row[0] for row in subject_edges] == [new_focus, 's-visible-1', 's-visible-2']
                    changed.append(case['id'])
                else:
                    assert not old_violations
                db_hash = construct(after, schema, case, new_rows)
                kind = 'observed_support' if case['id'] in observed_ids else 'new_primary'
                if kind == 'observed_support':
                    assert not modified and db_hash == previous_hashes[case['id']], case['id']
                    observed_count += 1
                else:
                    assert case['id'] in primary_ids
                    primary_count += 1
                if null_duplicates:
                    assert set(null_duplicates) == {'reference_end'}
                    assert case['category'] == 'source_boundary' and case['source_state'] == 'null_id'
                    assert case['role'] == 'reference_end' and case['multiplicity'] == 3
                    nullable.append(case['id'])
                seen.append(case['id'])
                emit({'kind': 'fixture', 'case': case, 'evidence_partition': kind,
                      'rows_sha256': hashlib.sha256(encoded(new_rows)).hexdigest(),
                      'main_database_sha256': db_hash, 'fixture_changed': modified,
                      'nullable_key_duplicates': null_duplicates,
                      'four_relation_columns_and_keys_valid': True,
                      'old_success_database_bytes_identical': kind == 'observed_support'})
            assert len(seen) == len(set(seen)) == 1582
            assert set(seen) == observed_ids | primary_ids
            assert set(changed) == expected_changed and len(nullable) == 6
            assert (observed_count, primary_count) == (1345, 237)
            assert all(sha(ROOT/path) == value for path,value in input_hashes.items())
            assert not any(name.startswith(('semantic_runtime', 'lawrag', '_adr1080_', '_adr1081_')) for name in sys.modules)
            checks.update(all1582_fixtures_constructed=True, all4_relation_columns_and_primary_keys_valid=True,
                only18_declared_fixture_rows_changed=True, nullable_duplicate6_cases_preserved=True,
                old1345_database_bytes_exact_to_recorded_success=True, input_hashes_unchanged=True,
                product_import_bind_consumer_calls_zero=True)
            result = {'status': 'PASS', 'checks': checks, 'constructed_fixtures': len(seen),
                      'observed_support_fixtures': observed_count, 'new_primary_fixtures': primary_count,
                      'changed_fixture_case_ids': changed, 'nullable_duplicate_case_ids': nullable}
        except BaseException as exc:
            failures.append({'type': type(exc).__name__, 'message': str(exc), 'case': current,
                             'traceback': traceback.format_exc()})
            emit({'kind': 'failure', 'failure': failures[-1]})
            result = {'status': 'FAIL', 'checks_before_failure': checks, 'constructed_fixtures': len(seen),
                      'observed_support_fixtures': observed_count, 'new_primary_fixtures': primary_count,
                      'changed_fixture_case_ids': changed, 'nullable_duplicate_case_ids': nullable,
                      'failures': failures}
        finally:
            result.update(input_hashes=input_hashes, raw_path=str(raw.relative_to(ROOT)),
                product_module_imports=0, product_selection_bind_calls=0, product_consumer_calls=0,
                baseline_candidate_result_comparisons=0, real_data_loads=0, external_model_calls=0,
                wall_seconds=time.perf_counter()-started,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                scope='Fixture/schema integrity only; no product equivalence or performance result.')
            emit({'kind': 'summary', 'result': result})
            with output.open('x', encoding='utf-8') as destination:
                json.dump(result, destination, ensure_ascii=False, indent=2)
                destination.write('\n')
    print(json.dumps({key:result.get(key) for key in ('status','constructed_fixtures','observed_support_fixtures','new_primary_fixtures','wall_seconds','peak_rss_kib')}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
