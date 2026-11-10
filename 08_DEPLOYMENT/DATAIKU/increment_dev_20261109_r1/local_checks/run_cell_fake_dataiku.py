"""가짜 dataiku 모듈로 DATAIKU_INCREMENT_R1.txt 셀을 그대로 실행 (ACTION=check)."""
import json, secrets, subprocess, sys, types, io, shutil
from pathlib import Path
ROOT = Path('/home/jin/8-AGENT')
PKG = ROOT/'08_DEPLOYMENT/DATAIKU/increment_dev_20261109_r1'
code_dir = Path('/tmp/cellcheck/code'); shutil.rmtree(code_dir, ignore_errors=True); code_dir.mkdir()
shutil.copy(ROOT/'08_DEPLOYMENT/DATAIKU/agent_layer_zip_20261105_r6/DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip', code_dir)
shutil.copy(PKG/'INCREMENT_CODE_R1.zip', code_dir)
for d in ('drop','state','input'): (Path('/tmp/cellcheck')/d).mkdir(exist_ok=True)
import oracledb, pandas
oracledb.defaults.fetch_lobs = False
info = json.loads(subprocess.check_output(["docker","inspect","a8-legal-mapped-20261023"]))[0]
pw = [e.split("=",1)[1] for e in info["Config"]["Env"] if e.startswith(("ORACLE_PWD=","ORACLE_PASSWORD="))][0]
admin = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user="system", password=pw); c = admin.cursor()
user = "A8_INCC_"+secrets.token_hex(3).upper(); upw = "P"+secrets.token_hex(10)
c.execute(f'CREATE USER {user} IDENTIFIED BY "{upw}"'); c.execute(f"GRANT CREATE SESSION TO {user}")
conn = oracledb.connect(dsn="127.0.0.1:11524/FREEPDB1", user=user, password=upw)
class Folder:
    roots = {'CODE': code_dir, 'DROP': Path('/tmp/cellcheck/drop'), 'STATE': Path('/tmp/cellcheck/state'), 'INPUT': Path('/tmp/cellcheck/input')}
    def __init__(self, fid): self.root = self.roots[fid]
    def list_paths_in_partition(self): return ['/'+str(p.relative_to(self.root)) for p in self.root.rglob('*') if p.is_file()]
    def get_download_stream(self, path): return open(self.root/path.lstrip('/'), 'rb')
    def upload_stream(self, path, stream):
        p = self.root/path.lstrip('/'); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(stream.read())
    def delete_path(self, path): (self.root/path.lstrip('/')).unlink()
class Exec:
    def __init__(self, connection): pass
    def query_to_df(self, sql, pre_queries=None, post_queries=None, **_):
        cur = conn.cursor()
        try:
            for s in pre_queries or []: cur.execute(s)
            cur.execute(sql); names=[d[0] for d in cur.description]
            rows=[dict(zip(names,r)) for r in cur.fetchall()]
            for s in post_queries or []:
                conn.commit() if s.strip().upper()=='COMMIT' else cur.execute(s)
        except Exception: conn.rollback(); raise
        return pandas.DataFrame(rows, columns=names)
CFG = {'project':'TEST_LEAGAL','INPUT_FOLDER_ID':'INPUT','SUPPORT_FOLDER_ID':'INPUT','AGENT_CONNECTION':'AIDP',
       'TARGET_CONNECTION':'AIDP','GOLD_OWNER':'SIDDS','WORK_DIR':'/tmp/cellcheck/work','ENVIRONMENT':'PROD',
       'INPUT_MODE':'ZIP','folders':{'submit':'INPUT','wait':'INPUT','load':'INPUT'}}
recipe_code = "PARAMS = {'CODE_FOLDER_ID': 'CODE'}\n# bootstrap\nfrom flow_runtime import run\nrun('wait'," + repr(CFG) + ")\n"
class Settings:
    def get_code(self): return recipe_code
class Recipe:
    def get_settings(self): return Settings()
class Project:
    project_key = 'TEST_LEAGAL'
    def get_recipe(self, name): assert name == 'LGL_AGENT_R6_PROD_02_WAIT_AGENT'; return Recipe()
class Client:
    def get_default_project(self): return Project()
dk = types.ModuleType('dataiku'); dk.Folder = Folder; dk.SQLExecutor2 = Exec; dk.api_client = lambda: Client()
dk.get_custom_variables = lambda: {}
sys.modules['dataiku'] = dk
cell = (PKG/'DATAIKU_INCREMENT_R1.txt').read_text(encoding='utf-8')
cell = cell.replace("'CODE_FOLDER_ID': '',", "'CODE_FOLDER_ID': 'CODE',").replace("'DROP_FOLDER_ID': '',","'DROP_FOLDER_ID': 'DROP',").replace("'STATE_FOLDER_ID': '',","'STATE_FOLDER_ID': 'STATE',")
try:
    ns = {}
    exec(compile(cell, 'DATAIKU_INCREMENT_R1.txt', 'exec'), ns)
    r = ns['RESULT']
    print('cell ran; ok=', r['ok'], 'checks', len(r['checks']), 'first', r['checks'][0])
    assert not r['ok'] and r['checks'][0]['table'] == 'SIDDS.LGL_G19_DOC_VER_S_1'
    ns2 = {}
    exec(compile(cell.replace("'ACTION': 'check'", "'ACTION': 'status'").replace("'CHANNEL': 'main'", "'CHANNEL': 'g19_7c1f8f4931c8be61b914f5bc'"), 'c', 'exec'), ns2)
except Exception as e:
    print('STATUS stop:', type(e).__name__, str(e)[:160])
finally:
    conn.close(); c.execute(f"DROP USER {user} CASCADE"); print('dropped', user)
