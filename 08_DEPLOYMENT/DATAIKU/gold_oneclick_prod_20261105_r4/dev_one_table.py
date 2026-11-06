"""Single-table Dataiku notebook smoke test, using the verified R4 loader."""
from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory


def run_one_table(params, package):
    from prod_config import identifier, target
    sys.path[:0] = [str(package/'engine'), str(package/'engine/vendor'),
                    str(package/'engine/vendor/02_BACKEND')]
    from prod_pipeline import Contract, code_binding, connection
    from gold_io import Stop, canonical, digest, literal

    code_binding()
    owner = identifier(params['DEV_OWNER'])
    expected_user = identifier(params['EXPECTED_DB_USER'])
    if not params['ORACLE_CONNECTION'].strip():
        raise ValueError('개발계 ORACLE_CONNECTION을 입력하세요.')
    name = 'TST_B003_LGL_SRC_POST_R4'
    cfg = target({'TARGET_MODE':'GOLD', 'GOLD_OWNER':owner, 'TABLE_NAMES':{'SRC_POST':name}})
    db = connection({'params':params})
    try:
        login = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER FROM DUAL")
        if login != [{'LOGIN_USER':expected_user}]:
            raise Stop('DEVELOPMENT_DB_USER_MISMATCH:' + str(login))
        with TemporaryDirectory(prefix='gold-one-table-r4-') as directory:
            path = Path(directory)/'contract.json'
            path.write_text(json.dumps(cfg), encoding='utf-8')
            contract = Contract(path)
            table = contract.table('SRC_POST')
            tables = db.query('SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER=' + literal(owner)
                              + ' AND TABLE_NAME=' + literal(name))
            if not tables:
                ddl = ('CREATE TABLE ' + table + ' (BODY_POST_HASH_VALU VARCHAR2(100 BYTE) PRIMARY KEY,'
                       ' DTLS_HASH_VALU VARCHAR2(100 BYTE) NOT NULL, BODY_POST_IFMN_CTNT CLOB NOT NULL,'
                       ' RGSN_ASTM TIMESTAMP NOT NULL)')
                db.block('BEGIN EXECUTE IMMEDIATE ' + literal(ddl) + '; END;')
            profile = contract.bind_registration_time(db)
            contract.preflight(db, 'SRC_POST')
            if not profile['type'].startswith('TIMESTAMP(') or 'TIME ZONE' in profile['type']:
                raise Stop('DEV_TEST_EXPECTS_PLAIN_TIMESTAMP:' + canonical(profile))
            body = {'purpose':'Gold R4 등록일시 INSERT 시험', 'version':1}
            row = {'DOC_POST_HASH_VALU':digest(body),
                   'MNFST_HASH_VALU':digest('gold-registration-time-one-table-r4'),
                   'DOC_POST_IFMN_CTNT':canonical(body)}
            readback = ("SELECT BODY_POST_HASH_VALU, DTLS_HASH_VALU, BODY_POST_IFMN_CTNT,"
                        " TO_CHAR(RGSN_ASTM,'YYYY-MM-DD HH24:MI:SS.FF9') AS REGISTERED_AT FROM "
                        + table + ' WHERE BODY_POST_HASH_VALU=' + literal(row['DOC_POST_HASH_VALU']))
            records = db.query(readback)
            action = 'REUSED'
            if not records:
                sql, binds = contract.batch('SRC_POST', [row])
                db.block(sql, binds, transaction_managed=True)
                action = 'INSERTED'
                records = db.query(readback)
            if len(records) != 1:
                raise Stop('DEV_REGISTRATION_ROW_COUNT:' + str(len(records)))
            actual = dict(records[0])
            stamp = actual.pop('REGISTERED_AT')
            expected = {contract.col('SRC_POST', k):v for k,v in row.items()}
            if actual != expected or not stamp:
                raise Stop('DEV_REGISTRATION_ROW_MISMATCH:' + table)
            return {'status':'DEV_ONE_TABLE_PASS', 'table':table, 'action':action,
                    'registration_column':profile, 'sample_key':row['DOC_POST_HASH_VALU'],
                    'registered_at':stamp, 'matching_rows':len(records)}
    finally:
        db.close()
