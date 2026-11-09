"""Run GOLD_MAIN_CHANNEL_R1.txt in a disposable loopback Oracle schema and read the
result with the frozen MAIN157 server function select_release (no ORDS, no model)."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys

import oracledb

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
FROZEN = ROOT / '08_DEPLOYMENT/RELEASES/agent-a-unified-20261105-r1'
sys.path.insert(0, str(FROZEN / 'code/02_BACKEND'))
from semantic_runtime.oracle_dp_io import DPError, digest  # noqa: E402
from semantic_runtime.oracle_gold_mapping import GoldMapping  # noqa: E402
from semantic_runtime.oracle_query_catalog import json_body, select_release  # noqa: E402

info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
assert info['State']['Running']
port = info['HostConfig']['PortBindings']['1521/tcp'][0]
assert port['HostIp'] == '127.0.0.1'
dsn = '127.0.0.1:' + port['HostPort'] + '/FREEPDB1'
password = dict(v.split('=', 1) for v in info['Config']['Env'])['ORACLE_PASSWORD']
oracledb.defaults.fetch_lobs = False
admin = oracledb.connect(user='system', password=password, dsn=dsn)
admin.call_timeout = 20000

delivery = (OUT / 'GOLD_MAIN_CHANNEL_R1.txt').read_text(encoding='utf-8')
statements = [v.strip() for v in re.split(r'^-- DKU_END_STATEMENT\s*$', delivery, flags=re.M) if v.strip()]
owner = 'A8_GOLDMAIN_' + secrets.token_hex(4).upper()
user_password = secrets.token_hex(24)
checks = []
record = {'status': 'RUNNING', 'oracle_version': admin.version, 'owner': owner,
          'delivery_sha256': hashlib.sha256(delivery.encode()).hexdigest(),
          'frozen_server_code': str(FROZEN.relative_to(ROOT)), 'checks': checks,
          'field_execution': False, 'external_models': 0}


def check(name, passed, **detail):
    checks.append({'name': name, 'passed': bool(passed), **detail})
    if not passed:
        raise AssertionError(name + ' ' + json.dumps(detail, ensure_ascii=False, default=str))


def rows(conn, sql, binds=None):
    with conn.cursor() as c:
        c.execute(sql, binds or {})
        if not c.description:
            return []
        return [dict(zip([d[0] for d in c.description], r)) for r in c]


class ServerSQL:
    """The serving read port: positional (name, value, type) binds, dict rows."""
    def __init__(self, conn):
        self.conn = conn
        self.schema_map = GoldMapping.load(owner=owner)

    def query(self, sql, binds, limit=None):
        return rows(self.conn, sql, {name: value for name, value, _ in binds})


def isolated(text):
    return text.replace("'SIDDG'", "'" + owner + "'").replace('SIDDG.', owner + '.')


def run_delivery(conn):
    block, select = (isolated(s) for s in statements)
    try:
        with conn.cursor() as c:
            c.execute(block)
        error = None
    except oracledb.DatabaseError as exc:
        conn.rollback()
        error = exc.args[0].code
    return error, rows(conn, select)


def publication(conn, tag, status='COMPLETE'):
    value = {'schema_version': 'oracle-query-release-v1', 'status': status, 'tag': tag,
             'source_release_id': hashlib.sha256(b's' + tag.encode()).hexdigest(),
             'dataset_version': hashlib.sha256(b'd' + tag.encode()).hexdigest()}
    release = digest(value)
    rows(conn, f'INSERT INTO {owner}.IDD_B003_LGL_SRCH_POST VALUES (:1, :2)', [release, json_body(value)])
    return release


def channel(conn, name, release):
    rows(conn, f'INSERT INTO {owner}.IDD_B003_LGL_SRCH_CHNL VALUES (:1, :2, 1)', [name, release])


def reset(conn):
    rows(conn, f'DELETE FROM {owner}.IDD_B003_LGL_SRCH_CHNL')
    rows(conn, f'DELETE FROM {owner}.IDD_B003_LGL_SRCH_POST')
    conn.commit()


created = False
conn = None
try:
    check('two_explicit_statements', len(statements) == 2 and statements[0].endswith('END;'),
          count=len(statements))
    rows(admin, f'CREATE USER {owner} IDENTIFIED BY "{user_password}" DEFAULT TABLESPACE USERS QUOTA 16M ON USERS')
    created = True
    rows(admin, f'GRANT CREATE SESSION, CREATE TABLE TO {owner}')
    conn = oracledb.connect(user=owner, password=user_password, dsn=dsn)
    conn.call_timeout = 20000
    # Exact registered physical shape of the two tables involved.
    rows(conn, f'''CREATE TABLE {owner}.IDD_B003_LGL_SRCH_POST (
        RFRN_POST_HASH_VALU VARCHAR2(100 BYTE) NOT NULL, RFRN_POST_IFMN_CTNT CLOB NOT NULL,
        CONSTRAINT X0_IDD_B003_LGL_SRCH_POST PRIMARY KEY (RFRN_POST_HASH_VALU))''')
    rows(conn, f'''CREATE TABLE {owner}.IDD_B003_LGL_SRCH_CHNL (
        RFRN_CHNL_NAME VARCHAR2(100 BYTE) NOT NULL, RFRN_POST_HASH_VALU VARCHAR2(100 BYTE) NOT NULL,
        CHAN_NO NUMBER(30,0) NOT NULL, CONSTRAINT X0_IDD_B003_LGL_SRCH_CHNL PRIMARY KEY (RFRN_CHNL_NAME))''')
    server = ServerSQL(conn)

    # 1. Loader state: one g19_ channel only. The frozen server default (main) fails.
    release = publication(conn, 'first')
    g19 = 'g19_' + release[:24]
    channel(conn, g19, release)
    conn.commit()
    try:
        select_release(server, channel='main')
        before = 'SELECTED'
    except DPError as exc:
        before = str(exc).split(':')[0]
    check('before_server_default_main_missing', before == 'QUERY_ACTIVE_MISSING', result=before)

    # 2. Delivery links main; the same server function now selects the loader publication.
    error, result = run_delivery(conn)
    check('delivery_links_main', error is None and result[0] == {'CHANNEL': 'main', 'QUERY_RELEASE_ID': release, 'CHAN_NO': 1},
          error=error, result=result)
    selected = select_release(server, channel='main')
    check('after_server_default_main_selects_loader_release',
          selected['release_id'] == release and selected['revision'] == 1 and selected['manifest']['status'] == 'COMPLETE',
          release_id=selected['release_id'], revision=selected['revision'])
    check('g19_channel_unchanged', select_release(server, channel=g19)['release_id'] == release)

    # 3. Rerun is a no-op.
    error, again = run_delivery(conn)
    check('rerun_no_change', error is None and again == result, error=error, result=again)

    # 4. main already pointing elsewhere is refused and left as is.
    reset(conn)
    first, other = publication(conn, 'first'), publication(conn, 'other')
    channel(conn, 'g19_' + first[:24], first)
    channel(conn, 'main', other)
    conn.commit()
    error, result = run_delivery(conn)
    kept = [r for r in result if r['CHANNEL'] == 'main']
    check('main_pointing_elsewhere_refused', error == 20903 and kept[0]['QUERY_RELEASE_ID'] == other, error=error)

    # 5. Two loader channels (reload) are refused; nothing inserted.
    reset(conn)
    a, b = publication(conn, 'a'), publication(conn, 'b')
    channel(conn, 'g19_' + a[:24], a)
    channel(conn, 'g19_' + b[:24], b)
    conn.commit()
    error, result = run_delivery(conn)
    check('two_g19_refused', error == 20901 and all(r['CHANNEL'] != 'main' for r in result), error=error)

    # 6. Channel without a COMPLETE publication is refused.
    reset(conn)
    missing = hashlib.sha256(b'missing').hexdigest()
    channel(conn, 'g19_' + missing[:24], missing)
    conn.commit()
    error, result = run_delivery(conn)
    check('missing_publication_refused', error == 20902 and len(result) == 1, error=error)
    reset(conn)
    pending = publication(conn, 'pending', status='RUNNING')
    channel(conn, 'g19_' + pending[:24], pending)
    conn.commit()
    error, result = run_delivery(conn)
    check('incomplete_publication_refused', error == 20902 and len(result) == 1, error=error)

    record['status'] = 'PASS'
except Exception as exc:  # keep the failure record
    record['status'] = 'FAIL'
    record['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
finally:
    if conn is not None:
        conn.close()
    if created:
        rows(admin, f'DROP USER {owner} CASCADE')
        record['temporary_owner_removed'] = not rows(admin, 'SELECT 1 FROM ALL_USERS WHERE USERNAME=:u', {'u': owner})
    admin.close()
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'VALIDATION.json').write_text(json.dumps(record, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'status': record['status'], 'checks': [(c['name'], c['passed']) for c in checks],
                      'error': record.get('error'), 'removed': record.get('temporary_owner_removed')}, ensure_ascii=False, indent=1))
