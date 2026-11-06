"""Execute the attached development cell on the existing loopback development Oracle."""
import io
import json
import re
import sys
import types
from pathlib import Path

import oracledb
import pandas as pd

HERE = Path(__file__).resolve().parent
archive = HERE/'DATAIKU_GOLD_ONECLICK_PROD_20261105_R4.zip'
creds = json.loads((Path.home()/'.local/state/8-agent/gold-r12-1208/connection.json').read_text())
owner = 'A8_GR12_CM1208'
table = owner + '.TST_B003_LGL_SRC_POST_R4'
assert creds['user'] == owner and creds['dsn'] == '127.0.0.1:11524/FREEPDB1'
oracledb.defaults.fetch_lobs = False


class Folder:
    def __init__(self, key):
        assert key == 'dev-code'

    def list_paths_in_partition(self):
        return ['/' + archive.name]

    def get_download_stream(self, path):
        assert path == '/' + archive.name
        return io.BytesIO(archive.read_bytes())


class Executor:
    def __init__(self, connection):
        assert connection == 'dev-loopback'

    def query_to_df(self, query, pre_queries=(), post_queries=(), **kwargs):
        with conn.cursor() as cursor:
            for statement in pre_queries:
                assert table in statement
                assert not re.search(r'\b(?:ALTER|DROP|DELETE|UPDATE|TRUNCATE)\b', statement, re.I)
                if 'CREATE TABLE' in statement:
                    assert "'CREATE TABLE " + table + ' (' in statement
                    writes.append('CREATE_TEST_TABLE')
                else:
                    assert 'INSERT INTO ' + table + ' (' in statement
                    writes.append('INSERT_SAMPLE')
                cursor.execute(statement)
            cursor.execute(query)
            result = pd.DataFrame(cursor.fetchall(), columns=[c[0] for c in cursor.description])
            for statement in post_queries:
                assert statement in ('ROLLBACK', 'COMMIT')
                cursor.execute(statement)
            return result


shim = types.ModuleType('dataiku')
shim.Folder = Folder
shim.SQLExecutor2 = Executor
sys.modules['dataiku'] = shim
code = (HERE/'DATAIKU_GOLD_DEV_ONE_TABLE_RUN_R4.txt').read_text()
for key, value in {'CODE_FOLDER_ID':'dev-code', 'ORACLE_CONNECTION':'dev-loopback',
                   'EXPECTED_DB_USER':owner, 'DEV_OWNER':owner}.items():
    field = repr(key) + ": ''"
    assert code.count(field) == 1
    code = code.replace(field, repr(key) + ': ' + repr(value))
writes = []
with oracledb.connect(**creds) as conn:
    results = []
    for _ in range(2):
        context = {}
        exec(compile(code, '<delivered-dev-cell>', 'exec'), context)
        results.append(context['RESULT'])
    assert results[0]['action'] in ('INSERTED','REUSED') and results[1]['action']=='REUSED'
    assert results[0]['registered_at'] == results[1]['registered_at']
    with conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM '+table)
        count, = cursor.fetchone()
        assert count == 1
    value = {'results':results, 'writes':writes, 'table_rows':count, 'local_oracle':True,
             'dataiku_sdk':'LOCAL_SUBSTITUTE', 'retained_test_table':table}
    print(json.dumps(value,ensure_ascii=False))
