"""Small synthetic source -> real local Oracle stages; no field or model calls."""
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import types
HERE=Path(__file__).resolve().parent;ROOT=HERE/'package'
sys.path[:0]=[str(ROOT),str(ROOT/'engine')]
import flow_entry as entry
import flow_inputs
import gold_io
import run as loader

def main():
    import oracledb
    import pandas as pd
    metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task']=='legal-mapped-20261023' and metadata['State']['Running']
    ports=metadata['HostConfig']['PortBindings']['1521/tcp'];assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
    password=dict(x.split('=',1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
    conn=oracledb.connect(dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1',user='system',password=password)
    conn.call_timeout=30000
    result={'status':'RUNNING','field_calls':0,'real_models':0,'synthetic_embedding_calls':0,
            'created_schemas':[],'dropped_schemas':[],'checks':[],
            'fixture_generation':'/tmp/g19-flow-cold-compact-fixture/built/generation',
            'identity_adapter':'local SYSTEM exposed as expected login in fixture only'}
    try:
        with conn.cursor() as c:
            c.execute("SELECT SUM(BYTES) FROM DBA_SEGMENTS WHERE OWNER NOT IN (SELECT USERNAME FROM DBA_USERS WHERE ORACLE_MAINTAINED='Y')")
            used=c.fetchone()[0] or 0
            c.execute("SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME='USERS'");free=c.fetchone()[0] or 0
            assert used+64*1024**2<12*1000**3*.9 and free>128*1024**2
            owners={}
            for owner in ['SIDDS','SIDDA']:
                name='A8_GF_'+secrets.token_hex(5).upper();pw=secrets.token_hex(24)
                c.execute('CREATE USER '+name+' IDENTIFIED BY "'+pw+'" DEFAULT TABLESPACE USERS QUOTA 32M ON USERS')
                result['created_schemas'].append(name);owners[owner]=name
        value=json.loads((ROOT/'engine/contract.json').read_text())
        for t in value['tables'].values():
            t['owner']=owners[t['owner']]
            if t.get('create_sql'):t['create_sql']=t['create_sql'].replace('SIDDA.',owners['SIDDA']+'.')
            t['index_sql']=[s.replace('SIDDA.',owners['SIDDA']+'.') for s in t.get('index_sql',[])]
        original=gold_io.Contract
        with tempfile.TemporaryDirectory(prefix='gold-flow-native-') as temporary:
            path=Path(temporary)/'contract.json';path.write_text(json.dumps(value));contract=original(path)
            gold_io.Contract=loader.Contract=lambda p:contract
            class Executor:
                def query_to_df(self,query,pre_queries=None,post_queries=None,**kwargs):
                    with conn.cursor() as c:
                        for q in pre_queries or []:c.execute(q)
                        c.execute(query)
                        cols=[d[0] for d in c.description]
                        rows=[[v.read() if isinstance(v,oracledb.LOB) else v for v in row] for row in c.fetchall()]
                        for q in post_queries or []:c.execute(q)
                        if 'LOGIN_USER' in cols:
                            for row in rows:row[cols.index('LOGIN_USER')]='PIDD2APP'
                        return pd.DataFrame(rows,columns=cols)
            class Embedding:
                def __init__(self):self.texts=[]
                def add_text(self,text):self.texts.append(text)
                def execute(self):result['synthetic_embedding_calls']+=1;return self
                def get_embeddings(self):return [[1.,2.,3.] for _ in self.texts]
            project=types.SimpleNamespace(get_llm=lambda m:types.SimpleNamespace(new_embeddings=Embedding))
            sys.modules['dataiku']=types.SimpleNamespace(SQLExecutor2=lambda **kw:Executor(),
                 api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project))
            os.environ['G19_DIAGNOSTIC_FILE']=str(Path(temporary)/'errors.jsonl')
            os.environ['LEGAL_EMBED_LLM_ID']='synthetic-fixture';os.environ['LEGAL_EMBED_DIMENSIONS']='3'
            # Tiny retained fixture is kept to reproduce the local-input preparation proof.
            old=Path(result['fixture_generation']).parent/'oracle-import-r2'
            prepared=flow_inputs.prepare(old,loader.Progress())
            result['expected']={'source_rows':prepared['source_rows'],'query_rows':prepared['query_rows']}
            for stage in ['schema','source','query','verify','vector','report']:
                entry.execute(stage,{},old)
                result['checks'].append(stage)
            state=loader.read(entry.job_dir(old)/'state.json')
            assert state['status']=='SOURCE_QUERY_VERIFIED'
            calls=result['synthetic_embedding_calls']
            for stage in ['source','query','verify','vector']:
                entry.execute(stage,{},old)
            assert calls==result['synthetic_embedding_calls']
            result['checks'].append('resume_existing_source_query_and_cached_vectors_no_new_model')
            result['db_report']=entry.report_db(old)
            result['status']='PASS'
    finally:
        for name in result['created_schemas']:
            with conn.cursor() as c:c.execute('DROP USER '+name+' CASCADE')
            result['dropped_schemas'].append(name)
        conn.close()
        (HERE/'NATIVE_FLOW_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('NATIVE_FLOW_PASS',len(result['checks']))

if __name__=='__main__':main()
