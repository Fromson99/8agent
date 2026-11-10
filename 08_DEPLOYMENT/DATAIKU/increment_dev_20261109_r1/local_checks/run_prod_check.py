"""PROD_DELETE_CHECK_R1.txt 를 가짜 dataiku로 그대로 실행 — 운영 이름(IDD_B003_LGL_*) 표를 가진 계정 / 권한 없는 계정."""
import io, json, secrets, subprocess, sys, types, zipfile, tempfile, contextlib
from pathlib import Path
ROOT = Path('/home/jin/8-AGENT'); PKG = ROOT/'08_DEPLOYMENT/DATAIKU/increment_dev_20261109_r1'
import oracledb, pandas
info = json.loads(subprocess.check_output(["docker","inspect","a8-legal-mapped-20261023"]))[0]
pw = [e.split("=",1)[1] for e in info["Config"]["Env"] if e.startswith(("ORACLE_PWD=","ORACLE_PASSWORD="))][0]
admin = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user="system", password=pw); c = admin.cursor()
owner = "A8_PRDO_"+secrets.token_hex(3).upper(); other = "A8_PRDX_"+secrets.token_hex(3).upper(); upw = "P"+secrets.token_hex(10)
tmp = Path(tempfile.mkdtemp())
with zipfile.ZipFile(ROOT/'08_DEPLOYMENT/DATAIKU/agent_layer_zip_20261105_r6/DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip') as z: z.extractall(tmp)
sys.path[:0] = [str(tmp), str(tmp/'engine')]
from prod_config import target
tgt = target({'TARGET_MODE': 'GOLD', 'GOLD_OWNER': owner})
results = {}
try:
    c.execute(f'CREATE USER {owner} IDENTIFIED BY "{upw}" QUOTA 16M ON USERS'); c.execute(f"GRANT CREATE SESSION, CREATE TABLE TO {owner}")
    c.execute(f'CREATE USER {other} IDENTIFIED BY "{upw}"'); c.execute(f"GRANT CREATE SESSION TO {other}")
    oc = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user=owner, password=upw); cur = oc.cursor()
    for key in ('DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST','SRCH_POST','SRCH_ROW','SRCH_CHNL','VCTR_POST','VCTR_ITEM','VCTR_HEAD'):
        t = tgt['tables'][key]
        cols = ','.join(col['name']+' '+col['type'] for col in t['columns'].values())
        cur.execute(f"CREATE TABLE {owner}.{t['name']} ({cols})")
    cur.execute(f"CREATE TABLE {owner}.LGL_PIPE_RESULT_A (JOB_ID VARCHAR2(32), SEQ_NO NUMBER)")
    for label, user in (('owner', owner), ('no_grant', other)):
        conn = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user=user, password=upw)
        class Exec:
            def __init__(self, connection): pass
            def query_to_df(self, sql, pre_queries=None, post_queries=None, **_):
                k = conn.cursor()
                try:
                    for s in pre_queries or []: k.execute(s)
                    k.execute(sql); names=[d[0] for d in k.description]; rows=k.fetchall()
                    for s in post_queries or []: conn.rollback() if s=='ROLLBACK' else k.execute(s)
                except Exception: conn.rollback(); raise
                return pandas.DataFrame(rows, columns=names)
        dk = types.ModuleType('dataiku'); dk.SQLExecutor2 = Exec; sys.modules['dataiku'] = dk
        cell = (PKG/'PROD_DELETE_CHECK_R1.txt').read_text(encoding='utf-8')
        cell = cell.replace("GOLD_OWNER = 'SIDDG'", f"GOLD_OWNER = '{owner}'").replace("AGENT_TABLE = 'SIDDA.LGL_PIPE_RESULT_A'", f"AGENT_TABLE = '{owner}.LGL_PIPE_RESULT_A'")
        out = io.StringIO()
        with contextlib.redirect_stdout(out): exec(compile(cell, 'PROD_DELETE_CHECK_R1.txt', 'exec'), {})
        text = out.getvalue(); results[label] = text.strip().splitlines()[-1]
        print(f'--- {label}\n' + text)
        conn.close()
    oc.close()
    assert results == {'owner': 'PROD_INCREMENT_PRIVILEGES PASS', 'no_grant': 'PROD_INCREMENT_PRIVILEGES FAIL'}, results
    print('PROD_CELL_LOCAL_CHECK PASS')
finally:
    for u in (owner, other): c.execute(f"DROP USER {u} CASCADE")
