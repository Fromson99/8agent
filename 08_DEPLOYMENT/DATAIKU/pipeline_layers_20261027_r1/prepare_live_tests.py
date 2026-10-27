"""Adapt the established tiny Oracle E2E to split owners; never contact field systems."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=(ROOT/'05_TESTS/CONTRACTS/mapped_pipeline_live_runner.py').read_text()
start=source.index("c=oracledb.connect(")
end=source.index("\nspec=importlib.util.spec_from_file_location",start)
setup='''# Reuse only the isolated, loopback-only task database; no field credentials.
import secrets
import subprocess
details=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
assert details['Config']['Labels']['a8.task']=='legal-mapped-20261023'
assert details['HostConfig']['PortBindings']['1521/tcp']==[{'HostIp':'127.0.0.1','HostPort':'11524'}]
settings=dict(item.split('=',1) for item in details['Config']['Env'])
admin=oracledb.connect(user='system',password=settings['ORACLE_PASSWORD'],dsn='127.0.0.1:11524/FREEPDB1')
test_user='A8_LAYER_'+secrets.token_hex(6).upper()
test_password=secrets.token_hex(24)
old_counts={}
with admin.cursor() as cur:
    cur.execute("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME IN ('LGL_DOC_VER','LGL_DOC_UNIT','LGL_DOC_BLK','LGL_FILE_PART','LGL_SRC_PBLS','LGL_SRCH_PBLS','LGL_SRCH_ROW','LGL_SRCH_CHNL','LGL_EXEC_ST')")
    old_tables=[row[0] for row in cur.fetchall()]
    for table in old_tables:
        cur.execute('SELECT COUNT(*) FROM SIDDA.'+table);old_counts[table]=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME='SIDDS'")
    if not cur.fetchone()[0]:
        cur.execute('CREATE USER SIDDS IDENTIFIED BY "'+secrets.token_hex(24)+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS ACCOUNT LOCK')
    for typ,key,name,statement in schema.ddl():
        owner=schema.owners[schema.tables[key]['role']]
        cur.execute('SELECT COUNT(*) FROM ALL_OBJECTS WHERE OWNER=:o AND OBJECT_NAME=:n AND OBJECT_TYPE=:t',o=owner,n=name,t=typ)
        if not cur.fetchone()[0]:cur.execute(statement)
    for key,table in schema.tables.items():
        quote=lambda text:"'"+text.replace("'","''")+"'"
        cur.execute('COMMENT ON TABLE '+schema.names(key).table+' IS '+quote(table['description']))
        for col in table['columns'].values():cur.execute('COMMENT ON COLUMN '+schema.names(key).table+'.'+col['name']+' IS '+quote(col['description']))
    cur.execute('CREATE USER '+test_user+' IDENTIFIED BY "'+test_password+'"')
    cur.execute('GRANT CREATE SESSION TO '+test_user)
    for key in schema.tables:
        privileges='SELECT' if key in ('query_state','query_active') else 'SELECT, INSERT'
        cur.execute('GRANT '+privileges+' ON '+schema.names(key).table+' TO '+test_user)
c=oracledb.connect(user=test_user,password=test_password,dsn='127.0.0.1:11524/FREEPDB1')
assert c.dsn=='127.0.0.1:11524/FREEPDB1'
'''
source=source[:start]+setup+source[end:]
source=source.replace("with c.cursor() as cur:cur.execute('DROP INDEX SIDDA.LGL_SRCH_ROW_KEY_IX')",
                      "with admin.cursor() as cur:cur.execute('DROP INDEX SIDDS.LGL_SRCH_ROW_KEY_IX_S')")
source=source.replace("with c.cursor() as cur:\n    cur.execute(next(sql for typ,k,n,sql in schema.ddl() if n=='LGL_SRCH_ROW_KEY_IX'))",
                      "with admin.cursor() as cur:\n    cur.execute(next(sql for typ,k,n,sql in schema.ddl() if n=='LGL_SRCH_ROW_KEY_IX_S'))")
source=source.replace("assert not any('SIDDA.LEGAL_' in s for s in Executor.statements)",
'''assert not any('SIDDA.LEGAL_' in s or 'INTO SIDDA.LGL_' in s for s in Executor.statements)
assert all('SIDDS.LGL_' in s for s in Executor.statements)
with admin.cursor() as cur:
    for table,count in old_counts.items():
        cur.execute('SELECT COUNT(*) FROM SIDDA.'+table);assert cur.fetchone()[0]==count
''')
source=source.replace("'status':'PASS','oracle'", "'status':'PASS','old_sidda_counts_unchanged':old_counts,'target_tables':{k:schema.names(k).table for k in schema.tables},'oracle'")
source=source.replace('c.close()',"c.close()\nwith admin.cursor() as cur:cur.execute('DROP USER '+test_user)\nadmin.close()")
(HERE/'live_runner.py').write_text(source)
source=(ROOT/'05_TESTS/CONTRACTS/test_dataiku_pipeline_mapped_live.py').read_text()
source=source.replace("DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1'",
                      "DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_layers_20261027_r1'\nSERVICE_DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_mapped_20261023_r1'")
source=source.replace('A8_MAPPED_ORACLE_LIVE','A8_LAYERS_ORACLE_LIVE')
source=source.replace('DATAIKU_PIPELINE_CLIENT_20261023_R1','DATAIKU_PIPELINE_CLIENT_20261027_R1')
source=source.replace("zipfile.ZipFile(DELIVERY/(archive+'.zip'))", "zipfile.ZipFile((SERVICE_DELIVERY if archive.startswith('GENOS_') else DELIVERY)/(archive+'.zip'))")
source=source.replace("ROOT/'05_TESTS/CONTRACTS/mapped_pipeline_live_runner.py'","DELIVERY/'live_runner.py'")
(ROOT/'05_TESTS/CONTRACTS/test_dataiku_pipeline_layers_live.py').write_text(source)
