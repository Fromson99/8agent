"""Small synthetic SQL contract, isolated loopback Oracle schema only."""
import json
import math
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'package'))
import vector_stage as v
import jdbc_transport
from gold_io import Database,canonical,error_codes,digest
from types import SimpleNamespace as NS
from vector_reset import reset_previous


def main():
    import oracledb
    import pandas as pd
    meta=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert meta['Config']['Labels']['a8.task']=='legal-mapped-20261023' and meta['State']['Running']
    ports=meta['HostConfig']['PortBindings']['1521/tcp']
    assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
    password=dict(x.split('=',1) for x in meta['Config']['Env'])['ORACLE_PASSWORD']
    result={'status':'RUNNING','models':0,'field_dataiku':False,'existing_data_mutated':False,'checks':[]}
    conn=None;owner=None
    try:
        conn=oracledb.connect(dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1',user='system',password=password)
        conn.call_timeout=60000
        result['oracle_version']=conn.version
        with conn.cursor() as c:
            c.execute("SELECT SUM(BYTES) FROM DBA_SEGMENTS WHERE OWNER NOT IN (SELECT USERNAME FROM DBA_USERS WHERE ORACLE_MAINTAINED='Y')")
            allocated=c.fetchone()[0] or 0
            c.execute("SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME='USERS'")
            free=c.fetchone()[0] or 0
            if allocated+32*1024**2>12*1000**3*.9 or free<64*1024**2:raise RuntimeError('LOCAL_CAPACITY_GUARD')
            name='A8_VS3_'+secrets.token_hex(5).upper()
            c.execute('CREATE USER '+name+' IDENTIFIED BY "'+secrets.token_hex(24)+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
            owner=name;result['test_schema']=owner
        model=json.loads((HERE/'package/contract.json').read_text())
        model['tables']={k:t for k,t in model['tables'].items() if k in ('VCTR_ITEM','VCTR_POST','VCTR_HEAD')}
        for table in model['tables'].values():table['owner']=owner
        class Executor:
            def query_to_df(self,sql,pre_queries=None,post_queries=None,**kw):
                with conn.cursor() as c:
                    for statement in pre_queries or []:c.execute(statement)
                    c.execute(sql)
                    cols=[x[0] for x in c.description]
                    rows=[[x.read() if isinstance(x,oracledb.LOB) else x for x in r] for r in c.fetchall()]
                    for statement in post_queries or []:c.execute(statement)
                    return pd.DataFrame(rows,columns=cols)
        class DB(Database):block=jdbc_transport.block
        db=DB(Executor())
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'contract.json';path.write_text(json.dumps(model))
            contract=v.Contract(path)
            with conn.cursor() as c:
                for key in contract.tables:c.execute(contract.ddl(key))
            dim=1024
            vals=[math.sin(i+1) for i in range(dim)];norm=math.sqrt(sum(x*x for x in vals));vals=[x/norm for x in vals]
            rows=[{'VCTR_POST_ID':'p','VCTR_SEG_ID':'s'+str(i),'DOC_ID':'문서','SRC_UNIT_ID':'문서:조문',
                   'VCTR_META_CTNT':canonical({'text':"한글😀𠀀 ' \n"*200,'ordinal':i}),
                   'EMBD_VCTR_VALU':canonical([math.sin(i*dim+j+1)/(dim**.5) for j in range(dim)])} for i in range(512)]
            sql,binds=v.vector_sql(contract,rows,dim)
            assert all(x not in sql for x in ('COUNT(', 'NOT EXISTS','VECTOR_DISTANCE','DBMS_LOB.COMPARE'))
            result['payload_bytes']=len(binds[0][1].encode())
            assert result['payload_bytes']<=v.MAX_BYTES
            rendered=jdbc_transport.render(sql,binds,write=True)
            result['rendered_sql_bytes']=len(rendered.encode())
            assert 'LZ_UNCOMPRESS' in rendered
            db.block(sql,binds,transaction_managed=True)
            result['checks'].append('actual_gzip_jdbc_insert_512x1024_float32_unicode_clob')
            # Readback is test-only, never injected in the runtime loader.
            with conn.cursor() as c:
                c.execute('SELECT VCTR_SCTN_ID,VCTR_DTLS_IFMN_CTNT,VECTOR_DIMENSION_COUNT(EMBD_VCTR),VECTOR_DIMENSION_FORMAT(EMBD_VCTR),EMBD_VCTR FROM '+contract.table('VCTR_ITEM'))
                actual=c.fetchall()
                expected={r['VCTR_SEG_ID']:r for r in rows}
                assert len(actual)==512
                for sid,meta,n,fmt,vector in actual:
                    assert meta.read()==expected[sid]['VCTR_META_CTNT'] and n==1024 and fmt=='FLOAT32'
                    assert max(abs(float(a)-b) for a,b in zip(vector,json.loads(expected[sid]['EMBD_VCTR_VALU'])))<1e-6
            result['checks'].append('test_only_exact_meta_and_float32_vector_readback')
            assert contract.pending_count(db,'VCTR_ITEM',rows)==512
            missing=[dict(rows[0],VCTR_SEG_ID='absent')]
            assert contract.pending_count(db,'VCTR_ITEM',missing)==0
            assert contract.pending_count(db,'VCTR_ITEM',missing+rows[:1])==1
            result['checks'].append('pending_primary_keys_all_none_partial')
            bad=[dict(rows[0],VCTR_SEG_ID='must_rollback'),rows[0]]
            s,b=v.vector_sql(contract,bad,dim)
            try:db.block(s,b,transaction_managed=True)
            except Exception as exc:assert 'ORA-00001' in error_codes(exc)
            else:raise AssertionError('duplicate accepted')
            assert contract.pending_count(db,'VCTR_ITEM',[bad[0]])==0
            result['checks'].append('duplicate_pk_rolls_back_entire_batch')
            bad=[dict(rows[0],VCTR_SEG_ID='bad_dim',EMBD_VCTR_VALU='[1,0]')]
            s,b=v.vector_sql(contract,bad,dim)
            try:db.block(s,b,transaction_managed=True)
            except oracledb.DatabaseError:pass
            else:raise AssertionError('invalid dimensions accepted')
            assert contract.pending_count(db,'VCTR_ITEM',bad)==0
            result['checks'].append('oracle_dimension_mismatch_rollback')
            post=[{'VCTR_POST_ID':'p','VCTR_POST_IFMN_CTNT':canonical({'manifest':{'한글':'😀'},'completion':{'status':'READY'}})}]
            s,b=contract.batch('VCTR_POST',post);db.block(s,b,transaction_managed=True)
            assert contract.pending_count(db,'VCTR_POST',post)==1
            result['checks'].append('publication_insert_ack_and_pending_key')
            current={'schema_version':'gold-vector-manifest-preview-v1','query_id':'q','source_release_id':'s',
                     'dataset_version':'v','documents':['문서'],'profile':{'dimensions':1024},'segment_profile':v.POLICY}
            previous=dict(current,segment_profile='navigation-source-block-text-window800-step700-v1')
            old_pub=digest(previous)
            with conn.cursor() as c:
                c.execute('UPDATE '+contract.table('VCTR_ITEM')+' SET VCTR_POST_ID=:p',p=old_pub)
                c.execute('UPDATE '+contract.table('VCTR_POST')+' SET VCTR_POST_ID=:p',p=old_pub)
                c.execute('INSERT INTO '+contract.table('VCTR_HEAD')+' (RFRN_POST_HASH_VALU,VCTR_POST_ID,CHAN_ORD) VALUES(:q,:p,1)',q='q',p=old_pub)
            conn.commit()
            directory=Path(td)/'parent';directory.mkdir()
            work=directory/'r3';work.mkdir()
            old_cache=directory/'vectors-fast-r1'/old_pub;old_cache.mkdir(parents=True)
            v.loader.atomic(old_cache/'state.json',{'binding':{'manifest':previous},'rows':512})
            (old_cache/'embed-00000000.json').write_text('old cache')
            job=NS(state={'binding':{'manifest':current,'database':['isolated']}},contract=contract,
                   work=work,db=db,guard=lambda:None,progress=NS(emit=lambda *a,**kw:None))
            try:reset_previous(job,directory,v.loader)
            except oracledb.DatabaseError as exc:assert 'ORA-20071' in error_codes(exc)
            else:raise AssertionError('active publication deleted')
            assert old_cache.exists()
            assert contract.pending_count(db,'VCTR_ITEM',[dict(r,VCTR_POST_ID=old_pub) for r in rows])==512
            result['checks'].append('actual_reset_active_publication_refused')
            with conn.cursor() as c:c.execute('DELETE FROM '+contract.table('VCTR_HEAD'))
            conn.commit()
            untouched=[dict(rows[0],VCTR_POST_ID='unrelated'),dict(rows[0],VCTR_POST_ID=digest(current))]
            s,b=v.vector_sql(contract,untouched,dim);db.block(s,b,transaction_managed=True)
            reset_previous(job,directory,v.loader)
            assert not old_cache.exists()
            assert contract.pending_count(db,'VCTR_ITEM',[dict(rows[0],VCTR_POST_ID=old_pub)])==0
            assert contract.pending_count(db,'VCTR_ITEM',untouched)==2
            assert contract.pending_count(db,'VCTR_POST',[{'VCTR_POST_ID':old_pub}])==0
            calls=db.calls
            reset_previous(job,directory,v.loader)
            assert db.calls==calls
            result['checks'].append('actual_reset_scoped_to_old_publication_preserves_r3_other_rows_and_idempotent')
            result['status']='PASS'
    except BaseException as exc:
        result.update(status='FAILED',error_type=type(exc).__name__,codes=error_codes(exc));raise
    finally:
        if conn is not None:
            conn.rollback()
            if owner is not None:
                assert re.fullmatch(r'A8_VS3_[A-F0-9]{10}',owner)
                with conn.cursor() as c:c.execute('DROP USER '+owner+' CASCADE')
                result['test_schema_removed']=True
            conn.close()
        (HERE/'ORACLE_SQL_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
