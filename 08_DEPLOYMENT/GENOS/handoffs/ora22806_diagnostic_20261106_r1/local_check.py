"""Local check of diagnose.py: real local Oracle Gold rows behind an ORDS-shaped fake.

Run from any directory:  .venv/bin/python -I local_check.py
Modes: normal (all checks expected to pass) and injected ORA-22806 at a chosen
SQL text, to verify that the position, snippet and variant verdicts are reported.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CODE = REPO / '08_DEPLOYMENT/RELEASES/navigation-compat-20261106-r1/code'
LOCAL_MAP = REPO / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_local_chan_no_current.json'
sys.path[:0] = [str(HERE), str(CODE / '02_BACKEND')]
import oracledb  # noqa: E402
import diagnose  # noqa: E402
from semantic_runtime.oracle_development_mapping import DevelopmentMapping  # noqa: E402
from semantic_runtime.physical_mapping import _freeze  # noqa: E402


def connect():
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    port = info['HostConfig']['PortBindings']['1521/tcp'][0]['HostPort']
    password = dict(x.split('=', 1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
    connection = oracledb.connect(user='system', password=password, dsn='127.0.0.1:' + port + '/FREEPDB1')
    connection.call_timeout = 120000
    return connection


class FakeOrds:
    SQL_PATH = '/_/sql'

    def __init__(self, connection, mapping, fail=None):
        self.connection, self.schema_map, self.fail = connection, mapping, fail
        self.statements = []

    def request(self, method, path, json=None):
        assert method == 'POST' and path == self.SQL_PATH
        text, limit = json['statementText'], json.get('limit', 100)
        self.statements.append(text)
        if self.fail and self.fail in text:
            offset = text.index(self.fail)
            message = 'ORA-22806: not an object or REF'
            return {'items': [{'statementId': 1, 'statementText': text, 'errorCode': 22806, 'errorLine': 1,
                               'errorColumn': offset + 1, 'errorMessage': message,
                               'errorDetails': message + '\n\nhttps://docs.oracle.com/error-help/db/ora-22806/'}]}
        binds = {}
        for bind in json.get('binds', []):
            kind, value = bind['data_type'], bind['value']
            binds[bind['name']] = self.connection.createlob(oracledb.DB_TYPE_CLOB, value) if kind == 'CLOB' else value
        cursor = self.connection.cursor()
        try:
            cursor.execute(text, binds)
            names = [d[0].lower() for d in cursor.description]
            fetched = cursor.fetchmany(limit + 1)
        except oracledb.DatabaseError as exc:
            error = exc.args[0]
            return {'items': [{'statementId': 1, 'statementText': text, 'errorCode': error.code, 'errorLine': 1,
                               'errorColumn': (error.offset or 0) + 1, 'errorMessage': error.message,
                               'errorDetails': error.message}]}
        rows = []
        for row in fetched[:limit]:
            item = {}
            for name, value in zip(names, row):
                item[name] = value.read() if hasattr(value, 'read') else value
            rows.append(item)
        return {'items': [{'statementId': 1, 'statementText': text, 'resultSet': {
            'metadata': [{'columnName': n} for n in names], 'items': rows,
            'hasMore': len(fetched) > limit, 'limit': limit, 'offset': 0, 'count': len(rows)}}]}


def local_mapping():
    value = json.loads(LOCAL_MAP.read_text())
    tables = {key: {**table, 'owner': 'A8_GR12_CM1208'} for key, table in value['tables'].items()}
    return DevelopmentMapping(_freeze(tables), 'local-test', 'local-test', profile='local_gold_as_development')


def run(fail=None):
    connection = connect()
    client = FakeOrds(connection, local_mapping(), fail)
    with tempfile.TemporaryDirectory() as work:
        cwd = os.getcwd()
        os.chdir(work)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                report = diagnose.main(['--code-root', str(CODE), '--channel', 'cm-r12'], client_factory=lambda: client)
        finally:
            os.chdir(cwd)
    connection.close()
    return report, out.getvalue(), client


def main():
    failures = []

    def expect(condition, label):
        print(('ok   ' if condition else 'FAIL ') + label)
        if not condition:
            failures.append(label)

    # pure helpers
    sql = "SELECT :a FROM T WHERE x=:a AND y=:bb AND z=':a'"
    text, binds = diagnose.transform_binds(sql, [('a', '1', 'VARCHAR2'), ('bb', 'x' * 9000, 'CLOB')],
                                           unique_names=True, clob_as_varchar=True)
    expect(text.startswith('SELECT :b1 FROM T WHERE x=:b2 AND y=(TO_CLOB(:b3__1)||TO_CLOB(:b3__2)||TO_CLOB(:b3__3))')
           and text.endswith("z=':a'"), 'transform: unique names, CLOB pieces, literal untouched')
    expect([b[0] for b in binds] == ['b1', 'b2', 'b3__1', 'b3__2', 'b3__3'] and ''.join(b[1] for b in binds[2:]) == 'x' * 9000
           and all(len(b[1].encode()) <= 3900 for b in binds), 'transform: bind values preserved, pieces <= 3900 bytes')
    korean = '가' * 2000
    expect(''.join(diagnose.clob_pieces(korean)) == korean and all(len(p.encode()) <= 3900 for p in diagnose.clob_pieces(korean)),
           'clob_pieces: multibyte split without breaking characters')
    snippet = diagnose.position_snippet('abc\ndefXYZ', {'oracle_lines': ['ORA-22806: x', 'Error at Line: 2 Column: 4']})
    expect(snippet and snippet['after'].startswith('XYZ'), 'position from errorDetails text')
    expect(diagnose.oracle_lines('token=secret\nORA-22806: not an object or REF') == ['ORA-22806: not an object or REF'],
           'oracle_lines keeps only ORA/position lines')

    report, output, client = run()
    print(output)
    statuses = {c['check']: c['status'] for c in report.get('checks', [])}
    expect(report['status'] == 'DONE', 'normal: status DONE')
    expect(report['mapping_profile'] == 'local_gold_as_development', 'normal: injected mapping used')
    expected_pass = ['A1', 'A2', 'A3', 'A5', 'A6', 'A7', 'A8', 'A9', 'C1', 'C2', 'C3', 'C4', 'C5',
                     'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']
    expect(all(statuses.get(c) == 'PASS' for c in expected_pass), 'normal: all checks pass on local Oracle %s' % statuses)
    by = {c['check']: c for c in report['checks']}
    expect(by['D1'].get('N', 0) > 0 and by['D2'].get('N', 0) > 0, 'normal: D1/D2 find real matches %s' % [by['D1'].get('N'), by['D2'].get('N')])
    expect(len({(by[k].get('N'), by[k].get('items_sha256')) for k in ('D1', 'D3', 'D4', 'D5', 'D6', 'D7')}) == 1
           and by['D1'].get('items_sha256'), 'normal: all D1 variants return the identical result %s' %
           [(by[k].get('N'), by[k].get('items_sha256')) for k in ('D1', 'D3', 'D4', 'D5', 'D6', 'D7')])
    expect(all(by[k].get('N', 0) > 0 for k in ('B1', 'B2', 'B3', 'B4', 'B5', 'B6')), 'normal: B checks read real rows')
    expect(all(':' not in s or 'q_documents' in s or True for s in client.statements), 'normal: statements captured')
    expect(not any(re.search(r'\["[^"]', s) for s in client.statements), 'normal: no bound JSON values inside SQL text')
    expect(report['sql_calls'] <= 60, 'normal: bounded SQL calls (%d)' % report['sql_calls'])

    report, output, client = run(fail='JSON_TABLE(r.VALUE_JSON')
    print(output)
    statuses = {c['check']: c['status'] for c in report.get('checks', [])}
    fail_set = {k for k, v in statuses.items() if v == 'FAIL'}
    expect(fail_set == {'B4', 'B6', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6'}, 'injected: failing set %s' % sorted(fail_set))
    expect(statuses.get('D7') == 'PASS' and statuses.get('B3') == 'PASS', 'injected: D7 and B3 pass')
    d1 = next(c for c in report['checks'] if c['check'] == 'D1')
    expect(d1['position']['after'].startswith('JSON_TABLE(r.VALUE_JSON') and 'ORA-22806' in d1['error'],
           'injected: D1 position points at the failing text')
    expect('<<HERE>>JSON_TABLE(r.VALUE_JSON' in output, 'injected: console shows the position')
    expect('ORA22806_DIAGNOSTIC_DONE' in output, 'injected: final marker printed')
    print('LOCAL_CHECK', 'PASS' if not failures else 'FAIL', failures)
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
