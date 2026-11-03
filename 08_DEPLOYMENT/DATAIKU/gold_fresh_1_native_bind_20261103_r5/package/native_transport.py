"""Permission-checked AIDP credentials; persistent Oracle connection, real binds.
No literal fallback, installation, permission changes, target DDL, or retry.
"""
import hashlib
import importlib
import json
import os
import re
import time
from gold_io import Stop
from jdbc_transport import TOKEN

IDENTITY_SQL = """SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER,
 SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME,
 SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME,
 SYS_CONTEXT('USERENV','CON_NAME') AS CON_NAME,
 SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS CURRENT_SCHEMA,
 SYS_CONTEXT('USERENV','CURRENT_EDITION_NAME') AS EDITION_NAME,
 SYS_CONTEXT('USERENV','PROXY_USER') AS PROXY_USER,
 SESSIONTIMEZONE AS SESSION_TZ FROM DUAL"""
NLS_KEYS = ('NLS_NUMERIC_CHARACTERS', 'NLS_DATE_FORMAT', 'NLS_TIMESTAMP_FORMAT',
            'NLS_TIMESTAMP_TZ_FORMAT', 'NLS_DATE_LANGUAGE', 'NLS_SORT', 'NLS_COMP',
            'NLS_CALENDAR', 'NLS_LENGTH_SEMANTICS')
NLS_SQL = "SELECT PARAMETER,VALUE FROM NLS_SESSION_PARAMETERS WHERE PARAMETER IN (" + ','.join("'"+k+"'" for k in NLS_KEYS) + ')'


def codes(exc):
    return ','.join(dict.fromkeys(re.findall(r'(?:ORA|PLS|DPY|DPI)-\d{4,5}', str(exc))))


def dsn_from_params(params, driver, override=''):
    """Basic TCP URLs or DSS host/port/db (Oracle SID) only.
    DSS schemas vary. Unrecognized configuration stops. A credential-free
    ORACLE_DSN override must still pass the live JDBC/native identity comparison.
    """
    if not isinstance(params, dict):
        raise Stop('NATIVE_CONNECTION_PARAMS_UNAVAILABLE')
    urls = {v for v in params.values() if isinstance(v, str) and v.startswith('jdbc:oracle:')}
    if override:
        raw = override.strip()
    elif len(urls) == 1:
        raw = next(iter(urls))
    elif len(urls) > 1:
        raise Stop('NATIVE_MULTIPLE_JDBC_URLS_SET_ORACLE_DSN')
    else:
        host, port, sid = params.get('host'), params.get('port', 1521), params.get('db')
        if not (isinstance(host, str) and isinstance(sid, str)):
            raise Stop('NATIVE_DSN_REQUIRED_SET_ORACLE_DSN')
        raw = 'jdbc:oracle:thin:@' + host + ':' + str(port) + ':' + sid
    if raw.startswith('jdbc:oracle:thin:@'):
        raw = raw[len('jdbc:oracle:thin:@'):]
    if raw.startswith('//'): raw = raw[2:]
    match = re.fullmatch(r'([A-Za-z0-9_.-]+):(\d{1,5})([/:])([A-Za-z0-9_.$#-]+)', raw)
    if not match or not (1 <= int(match[2]) <= 65535):
        raise Stop('NATIVE_DSN_UNSUPPORTED_BASIC_TCP_ONLY')
    host, port, separator, target = match.groups()
    if separator == ':':
        return driver.makedsn(host, int(port), sid=target)
    return host + ':' + port + '/' + target


def fetch(connection, sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        names = [d[0].upper() for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def connect_checked(db):
    # Raise outside except: downstream diagnostics also walk __context__.
    failure = None
    try:
        driver = importlib.import_module('oracledb')
    except Exception:
        failure = 'NATIVE_DRIVER_REQUIRED_ORACLEDB'
    if failure: raise Stop(failure)
    try:
        import dataiku
        info = dataiku.api_client().get_connection('AIDP').get_info(contextual_project_key='LEGAL_RAG')
        if str(info.get_type()).lower() != 'oracle':
            raise Stop('NATIVE_AIDP_ORACLE_CONNECTION_REQUIRED')
        credential = info.get_basic_credential()
        params = info.get_resolved_params() or info.get_params()
    except Exception:
        failure = 'NATIVE_AIDP_DETAILS_UNAVAILABLE_CHECK_CONNECTION_READ_PERMISSION'
    if failure: raise Stop(failure)
    if (not isinstance(credential, dict) or not isinstance(credential.get('user'), str)
            or not isinstance(credential.get('password'), str) or not credential['password']):
        raise Stop('NATIVE_BASIC_CREDENTIAL_REQUIRED')
    if credential['user'].upper() != 'PIDD2APP':
        raise Stop('NATIVE_EXPECTED_PIDD2APP_NO_PROXY_AUTH')
    dsn = dsn_from_params(params, driver, os.environ.get('G19_ORACLE_DSN', ''))
    expected = db.query(IDENTITY_SQL)
    nls = db.query(NLS_SQL)
    if len(expected) != 1 or expected[0]['LOGIN_USER'] != 'PIDD2APP' or expected[0]['PROXY_USER'] is not None:
        raise Stop('NATIVE_EXPECTED_PIDD2APP_NO_PROXY_AUTH')
    connection = None
    try:
        connection = driver.connect(user=credential['user'], password=credential['password'], dsn=dsn,
                                    tcp_connect_timeout=10, retry_count=0, stmtcachesize=100)
        connection.call_timeout = 120000
        connection.autocommit = False
        actual = fetch(connection, IDENTITY_SQL)
        def identity(rows):
            return [{k: v for k, v in row.items() if k != 'SESSION_TZ'} for row in rows]
        if identity(actual) != identity(expected):
            failure = 'NATIVE_JDBC_TARGET_IDENTITY_MISMATCH'
        elif {r['PARAMETER'] for r in nls} != set(NLS_KEYS):
            failure = 'NATIVE_JDBC_NLS_INCOMPLETE'
        else:
            with connection.cursor() as cursor:
                for row in nls:
                    cursor.execute('ALTER SESSION SET '+row['PARAMETER']+"='"+row['VALUE'].replace("'", "''")+"'")
                cursor.execute("ALTER SESSION SET TIME_ZONE='"+expected[0]['SESSION_TZ'].replace("'", "''")+"'")
            if (fetch(connection, IDENTITY_SQL) != expected
                    or sorted(fetch(connection, NLS_SQL), key=lambda r: r['PARAMETER']) != sorted(nls, key=lambda r: r['PARAMETER'])):
                failure = 'NATIVE_SESSION_SETTINGS_MISMATCH'
    except Exception as exc:
        failure = 'NATIVE_CONNECT_OR_SESSION_FAILED:' + codes(exc)
    finally:
        credential = params = info = None
    if failure:
        if connection is not None:
            try: connection.close()
            except Exception: pass
        raise Stop(failure)
    db.native = connection
    db.native_driver = driver
    db.native_broken = False
    print(json.dumps({'phase': 'NATIVE_CONNECTION_VERIFIED', 'connection': 'AIDP',
                      'login': 'PIDD2APP', 'identity_matches_jdbc': True,
                      'session_settings_match': True, 'driver_version': driver.__version__,
                      'table_writes': 0}), flush=True)


def validate_binds(sql, binds):
    values = {}
    for name, value, kind in binds:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name in values:
            raise Stop('NATIVE_BIND_DUPLICATE_OR_INVALID')
        if kind not in {'CLOB', 'VARCHAR2', 'NUMBER'}: raise Stop('NATIVE_BIND_TYPE')
        if value is not None:
            if kind == 'NUMBER':
                if type(value) is not int: raise Stop('NATIVE_INTEGER_REQUIRED')
            elif type(value) is not str or '\0' in value: raise Stop('NATIVE_TEXT_REQUIRED')
            elif kind == 'VARCHAR2' and len(value.encode('utf-8')) > 4000: raise Stop('NATIVE_VARCHAR2_LIMIT')
        values[name] = (value, kind)
    used = {m[1] for m in TOKEN.finditer(sql) if m[1]}
    if used != set(values): raise Stop('NATIVE_BIND_NAMES_MISMATCH')
    return values


def block(db, sql, binds=(), rollback=False, transaction_managed=False):
    if db.native_broken: raise Stop('NATIVE_CONNECTION_UNCONFIRMED_RESTART_REQUIRED')
    values = validate_binds(sql, binds)
    db.calls += 1
    started = time.monotonic()
    raw = sql.encode('utf-8')
    metadata = {'mode': 'NATIVE_CLOB_BIND', 'sql_bytes': len(raw),
                'sql_sha256': hashlib.sha256(raw).hexdigest(),
                'payload_bytes': sum(len(v.encode('utf-8')) for v, _ in values.values() if isinstance(v, str))}
    failure = None
    try:
        with db.native.cursor() as cursor:
            types = {'CLOB': db.native_driver.DB_TYPE_CLOB, 'NUMBER': db.native_driver.DB_TYPE_NUMBER,
                     'VARCHAR2': db.native_driver.DB_TYPE_VARCHAR}
            cursor.setinputsizes(**{n: types[k] for n, (_, k) in values.items()})
            parameters = {n: db.native.createlob(types[k]) if k == 'CLOB' and v == '' else v
                          for n, (v, k) in values.items()}
            cursor.execute(sql, parameters)
            if not transaction_managed:
                if rollback: db.native.rollback()
                else: db.native.commit()
            parameters.clear()
        elapsed = time.monotonic() - started
        db.last_transport = dict(metadata, request_s=round(elapsed, 4))
        return elapsed
    except BaseException as exc:
        db.native_broken = True
        failure = 'NATIVE_EXECUTION_UNCONFIRMED:' + codes(exc)
        try: db.native.rollback()
        except Exception: pass
    metadata.update(phase='NATIVE_BLOCK_FAILED', elapsed_seconds=round(time.monotonic()-started, 3))
    print(json.dumps(metadata), flush=True)
    raise Stop(failure)


def close(db):
    connection = getattr(db, 'native', None)
    if connection is not None:
        db.native = None
        try: connection.close()
        except Exception: pass


def install(loader):
    if getattr(loader.Database, '_g8_native_transport', False): return
    original = loader.Database.__init__
    def initialize(db, executor):
        original(db, executor)
        connect_checked(db)
    loader.Database.__init__ = initialize
    loader.Database.block = block
    loader.Database.close = close
    loader.Database._g8_native_transport = True
