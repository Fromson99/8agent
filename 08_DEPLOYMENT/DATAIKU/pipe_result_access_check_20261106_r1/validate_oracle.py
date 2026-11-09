"""Run the delivered TXT sections on the loopback Oracle, using throwaway schemas only."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import secrets
import subprocess

import oracledb

OUT = Path(__file__).resolve().parent
TXT = OUT / 'DATAIKU_PIPE_RESULT_CHECK_R1.txt'
STAGE_SQL = OUT.parent / 'agent_layer_async_20261105_r1/AGENT_STAGE.sql'
text = TXT.read_text(encoding='utf-8')


def section(n):
    body = re.search(rf'-- ===== \[{n}\] 시작 =====\n(.*?)-- ===== \[{n}\] 끝 =====', text, re.S).group(1)
    lines = [l for l in body.splitlines() if not l.lstrip().startswith('--')]
    return '\n'.join(lines).strip()


S1, S2, S3 = section(1), section(2), section(3)
assert not S1.rstrip().endswith(';') and not S2.rstrip().endswith(';') and not S3.rstrip().endswith(';')
PREFLIGHT = """DECLARE n NUMBER; BEGIN
      SELECT COUNT(*) INTO n FROM {t} WHERE 1=0;
      IF FALSE THEN INSERT INTO {t}
        (JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT)
        VALUES(NULL,0,NULL,NULL,1,1); END IF;
    END;"""

info = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
assert info['State']['Running']
port = info['HostConfig']['PortBindings']['1521/tcp'][0]
assert port['HostIp'] == '127.0.0.1'
dsn = '127.0.0.1:' + port['HostPort'] + '/FREEPDB1'
password = dict(v.split('=', 1) for v in info['Config']['Env'])['ORACLE_PASSWORD']
admin = oracledb.connect(user='system', password=password, dsn=dsn)
admin.call_timeout = 20000

checks = []


def check(name, ok, detail=None):
    checks.append({'check': name, 'status': 'PASS' if ok else 'FAIL', 'detail': detail})


def rows(conn, sql):
    with conn.cursor() as c:
        c.execute(sql)
        return [list(r) for r in c.fetchall()] if c.description else None


def ora(conn, sql):
    try:
        rows(conn, sql)
        return None
    except oracledb.DatabaseError as e:
        return sorted(set(re.findall(r'ORA-\d{5}', str(e))))


# Real names, read-only: syntax and shape as delivered.
r = rows(admin, S1)
check('S1_real_names_runs', r is not None and r[0][0] == '1_CONNECTION' and any(x[0] == '4_BAIP04APP' for x in r),
      [x[0] for x in r])
check('S2_real_names_runs', rows(admin, S2) is not None)

tag = secrets.token_hex(3).upper()
own, gnt = 'A8_PRC_OWN_' + tag, 'A8_PRC_GNT_' + tag
pw_own, pw_gnt = secrets.token_hex(16), secrets.token_hex(16)
sub = lambda s: s.replace("'SIDDA'", f"'{own}'").replace('SIDDA.', own + '.').replace('BAIP04APP', gnt)
try:
    rows(admin, f'CREATE USER {own} IDENTIFIED BY "{pw_own}" DEFAULT TABLESPACE USERS QUOTA 8M ON USERS')
    rows(admin, f'GRANT CREATE SESSION, CREATE TABLE TO {own}')
    rows(admin, f'CREATE USER {gnt} IDENTIFIED BY "{pw_gnt}"')
    rows(admin, f'GRANT CREATE SESSION TO {gnt}')
    o = oracledb.connect(user=own, password=pw_own, dsn=dsn)
    g = oracledb.connect(user=gnt, password=pw_gnt, dsn=dsn)
    ddl = re.search(r'CREATE TABLE .*?\n\);', STAGE_SQL.read_text(), re.S).group(0).rstrip(';')
    rows(o, sub(ddl))
    t = own + '.LGL_PIPE_RESULT_A'

    before = rows(o, sub(S1))
    check('owner_sees_table', [own, 'LGL_PIPE_RESULT_A'] in [x[1:3] for x in before if x[0] == '2_TABLE'])
    check('before_grant_not_visible', [x[1:3] for x in before if x[0] == '4_' + gnt] == [['SELECT_NOT_VISIBLE', 'INSERT_NOT_VISIBLE']])
    check('grantee_select_ORA00942_before', ora(g, f'SELECT JOB_ID FROM {t} WHERE 1=0') == ['ORA-00942'])
    e = ora(g, PREFLIGHT.format(t=t))
    check('grantee_r6_preflight_fails_before', e is not None and 'ORA-00942' in e, e)
    check('S2_before_grant_zero_rows', rows(admin, sub(S2)) == [])

    rows(o, sub(S3))

    check('grantee_select_after', ora(g, f'SELECT JOB_ID FROM {t} WHERE 1=0') is None)
    check('grantee_r6_preflight_after', ora(g, PREFLIGHT.format(t=t)) is None)
    check('no_row_written', rows(o, f'SELECT COUNT(*) FROM {t}') == [[0]])
    after = rows(o, sub(S1))
    check('after_grant_granted', [x[1:3] for x in after if x[0] == '4_' + gnt] == [['SELECT_GRANTED', 'INSERT_GRANTED']])
    check('S3_grant_rows_listed', sorted(x[2] for x in after if x[0] == '3_GRANT' and x[1] == gnt) == ['INSERT', 'SELECT'])
    check('S2_after_grant_direct', sorted(x[2] for x in rows(admin, sub(S2)) if x[0] == 'DIRECT') == ['INSERT', 'SELECT'])
    o.close(); g.close()
finally:
    for u in (gnt, own):
        try:
            rows(admin, f'DROP USER {u} CASCADE')
        except oracledb.DatabaseError:
            pass
    left = rows(admin, f"SELECT COUNT(*) FROM DBA_USERS WHERE USERNAME IN ('{own}','{gnt}')")
    check('temp_users_dropped', left == [[0]])

result = {
    'format': 'pipe-result-access-check-validation-v1',
    'validated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    'oracle': rows(admin, "SELECT BANNER_FULL FROM V$VERSION WHERE ROWNUM=1")[0][0].splitlines()[0],
    'txt_sha256': hashlib.sha256(TXT.read_bytes()).hexdigest(),
    'scope': 'Loopback Oracle with throwaway owner/grantee substituted for SIDDA/BAIP04APP. '
             'The field Dataiku/ORDS DB was not accessed.',
    'checks': checks,
    'status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'FAIL',
}
(OUT / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(json.dumps({'status': result['status'], 'failed': [c for c in checks if c['status'] != 'PASS']}, ensure_ascii=False))
