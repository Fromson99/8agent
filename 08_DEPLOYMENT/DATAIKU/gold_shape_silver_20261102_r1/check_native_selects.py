"""Read-only SQL expression checks against the labelled loopback Oracle container.

No CREATE/INSERT/UPDATE/DELETE/DDL is executed by this checker.
"""
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
from gold_io import Contract,canonical


def main():
    import oracledb
    metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task']=='legal-mapped-20261023'
    ports=metadata['HostConfig']['PortBindings']['1521/tcp']
    assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
    password=dict(x.split('=',1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
    contract=Contract(HERE/'package/contract.json')
    result={'status':'RUNNING','read_only':True,'field_database':False,'checks':[]}
    with oracledb.connect(dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1',user='system',password=password) as connection:
        connection.call_timeout=15000
        result['oracle_version']=connection.version
        with connection.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            for key in ['DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST','SRCH_ROW','SRCH_POST','SRCH_CHNL']:
                row={}
                for name,c in contract.tables[key]['columns'].items():
                    if c['default']:continue
                    row[name]=1 if c['type'].startswith('NUMBER') else ('N' if c['type'].startswith('CHAR') else '{}한글' if c['type']=='CLOB' else 'test')
                sql,binds=contract.batch(key,[row])
                source=sql.split(' FROM ',1)[1].split(' WHERE NOT EXISTS',1)[0]
                cur.setinputsizes(payload=oracledb.DB_TYPE_CLOB)
                cur.execute('SELECT COUNT(*) FROM '+source,payload=binds[0][1])
                assert cur.fetchone()[0]==1
                result['checks'].append('generated_json_table_'+key)
            for text in [None,'','한글\n본문']:
                row={'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc','DOC_NAME':'법령','DOC_HASH_VALU':None,'DOC_ADDN_IFMN_CTNT':text}
                sql,binds=contract.batch('DOC_VER',[row])
                source=sql.split(' FROM ',1)[1].split(' WHERE NOT EXISTS',1)[0]
                cur.execute('SELECT CASE WHEN s.c4e=1 THEN 0 ELSE DBMS_LOB.GETLENGTH(s.c4) END FROM '+source,payload=binds[0][1])
                assert cur.fetchone()[0]==(None if text is None else len(text))
            result['checks'].append('null_empty_korean_clob_distinction')
            cur.execute("SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)),VECTOR_DIMENSION_FORMAT(TO_VECTOR('[1,0]',2,FLOAT32)) FROM DUAL")
            assert cur.fetchone()==(2,'FLOAT32')
            result['checks'].append('native_vector_expression')
        connection.rollback()
    result['status']='PASS_READ_ONLY_EXPRESSIONS'
    (HERE/'NATIVE_READ_ONLY.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
