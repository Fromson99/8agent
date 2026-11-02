"""Small isolated Oracle integration contracts, no benchmark or corpus/model calls.

Creates only two randomly named, quota-bounded loopback test schemas and removes
only those exact schemas in finally. Existing SIDDS/SIDDA/Gold data is untouched.
"""
import copy
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
sys.path[:0]=[str(PACKAGE),str(PACKAGE/'vendor/02_BACKEND')]
from gold_io import Contract,Database,Stop,error_codes
import jdbc_transport
from types import SimpleNamespace
jdbc_transport.install(SimpleNamespace(Database=Database))


def main():
    import oracledb
    import pandas as pd
    metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task']=='legal-mapped-20261023' and metadata['State']['Running']
    ports=metadata['HostConfig']['PortBindings']['1521/tcp']
    assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
    password=dict(x.split('=',1) for x in metadata['Config']['Env'])['ORACLE_PASSWORD']
    result={'status':'RUNNING','field_database':False,'models':0,'existing_data_mutated':False,
            'created_schemas':[],'dropped_schemas':[],'checks':[]}
    conn=None;admin=None;restricted=None
    try:
        conn=oracledb.connect(dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1',user='system',password=password)
        conn.call_timeout=15000
        admin=conn
        result['oracle_version']=conn.version
        with conn.cursor() as c:
            # The Free limit is user data, not SYSTEM/SYSAUX/UNDO datafile allocation.
            # Keep the earlier conservative precheck failure in a separate receipt.
            c.execute("SELECT SUM(BYTES) FROM DBA_SEGMENTS WHERE OWNER NOT IN (SELECT USERNAME FROM DBA_USERS WHERE ORACLE_MAINTAINED='Y')")
            allocated=c.fetchone()[0] or 0
            c.execute("SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME='USERS'")
            free=c.fetchone()[0] or 0
            result['resource_guard']={'non_oracle_user_segment_bytes':allocated,'users_free_extent_bytes':free,
                                      'maximum_new_schema_quota_bytes':64*1024**2}
            if allocated+64*1024**2>12*1000**3*0.9 or free<128*1024**2:
                raise Stop('LOCAL_USER_DATA_90_PERCENT_GUARD')
            owners={}
            for old in ['SIDDS','SIDDA']:
                name='A8_G19_'+secrets.token_hex(5).upper()
                assert re.fullmatch('A8_G19_[A-F0-9]{10}',name)
                pw=secrets.token_hex(24)
                c.execute('CREATE USER '+name+' IDENTIFIED BY "'+pw+'" DEFAULT TABLESPACE USERS QUOTA 32M ON USERS')
                result['created_schemas'].append(name);owners[old]=name
        model=json.loads((PACKAGE/'contract.json').read_text())
        for table in model['tables'].values():
            table['owner']=owners[table['owner']]
            if table.get('create_sql'):
                table['create_sql']=table['create_sql'].replace('SIDDA.',owners['SIDDA']+'.')
            table['index_sql']=[s.replace('SIDDA.',owners['SIDDA']+'.') for s in table.get('index_sql',[])]
        class Executor:
            def query_to_df(self,query,pre_queries=None,post_queries=None,**kwargs):
                with conn.cursor() as c:
                    for sql in pre_queries or []:c.execute(sql)
                    c.execute(query)
                    cols=[x[0] for x in c.description]
                    rows=[[v.read() if isinstance(v,oracledb.LOB) else v for v in row] for row in c.fetchall()]
                    for sql in post_queries or []:c.execute(sql)
                    return pd.DataFrame(rows,columns=cols)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'contract.json';path.write_text(json.dumps(model))
            contract=Contract(path);db=Database(Executor())
            contract.create(db,lambda *a,**k:None)
            result['checks'].append('17_tables_exact_columns_pk_and_indexes')
            for key in contract.tables:contract.probe(db,key)
            result['checks'].append('17_insert_read_rollback_and_absence_checks')
            result['checks'].append('vector_float32_two_and_three_dimensions')
            rows=[]
            for i,text in enumerate([None,'','한글\n본문',"a'b"*2000]):
                rows.append({'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc'+str(i),'DOC_NAME':'법령'+str(i),
                             'DOC_HASH_VALU':'b'*64,'DOC_ADDN_IFMN_CTNT':text})
            sql,binds=contract.batch('DOC_VER',rows)
            db.block(sql,binds);db.block(sql,binds)
            assert db.query('SELECT COUNT(*) AS N FROM '+contract.table('DOC_VER'))==[{'N':4}]
            result['checks'].append('set_insert_idempotent_null_empty_unicode_large_clob')
            verify_sql,verify_binds=contract.batch('DOC_VER',rows,verify_only=True)
            db.block(verify_sql,verify_binds,rollback=True)
            result['checks'].append('independent_full_value_verification')
            bad=[dict(rows[0],DOC_NAME='충돌'),dict(rows[1],DOC_ID='must_not_commit')]
            bad_sql,bad_binds=contract.batch('DOC_VER',bad)
            try:db.block(bad_sql,bad_binds)
            except Exception as exc:
                assert 'ORA-20042' in error_codes(exc)
            else:raise AssertionError('conflict accepted')
            assert db.query('SELECT COUNT(*) AS N FROM '+contract.table('DOC_VER'))==[{'N':4}]
            result['checks'].append('conflicting_existing_row_rolls_back_new_rows')
            block={'MNFST_HASH_VALU':'a'*64,'DOC_ID':'doc0','BODY_SLC_ID':'blk','STRC_UNIT_ID':'unit',
                   'BODY_CTNT':'본문','DOC_HASH_VALU':'b'*64,'BODY_SLC_ADDN_IFMN_CTNT':'{}','ADD_INFO_TEXT_OMIT_YN':'Y'}
            s,b=contract.batch('DOC_BLK',[block]);db.block(s,b)
            s,b=contract.batch('DOC_BLK',[block],verify_only=True);db.block(s,b,rollback=True)
            result['checks'].append('gold_char_flag_insert_and_readback')
            publication={'DOC_POST_HASH_VALU':'c'*64,'MNFST_HASH_VALU':'a'*64,'DOC_POST_IFMN_CTNT':'{}'}
            s,b=contract.batch('SRC_POST',[publication]);db.block(s,b)
            assert db.query('SELECT COUNT(*) AS N FROM '+contract.table('SRC_POST')+' WHERE RGSN_AITM IS NOT NULL')==[{'N':1}]
            result['checks'].append('publication_timestamp_default')
            # The actual loader operations must work with SELECT + INSERT only.
            # No DELETE, LOCK ANY TABLE, or DBA role is granted to this account.
            reader='A8_G19_'+secrets.token_hex(5).upper();reader_pw=secrets.token_hex(24)
            with admin.cursor() as c:
                c.execute('CREATE USER '+reader+' IDENTIFIED BY "'+reader_pw+'"')
                result['created_schemas'].append(reader)
                c.execute('GRANT CREATE SESSION TO '+reader)
                for key in contract.tables:
                    c.execute('GRANT SELECT,INSERT ON '+contract.table(key)+' TO '+reader)
            restricted=oracledb.connect(dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1',user=reader,password=reader_pw)
            restricted.call_timeout=15000;conn=restricted
            contract.create(db,lambda *a,**k:None)
            for key in contract.tables:contract.probe(db,key)
            result['checks'].append('restricted_select_insert_account_all_17_preflight_and_rollback_probes')
            with conn.cursor() as c:
                c.execute('SELECT PRIVILEGE FROM SESSION_PRIVS');privileges=sorted(r[0] for r in c.fetchall())
                assert privileges==['CREATE SESSION'],privileges
            result['restricted_system_privileges']=privileges
            row=dict(rows[0],DOC_ID='restricted-insert',DOC_NAME='일반 적재 계정')
            s,b=contract.batch('DOC_VER',[row]);db.block(s,b)
            s,b=contract.batch('DOC_VER',[row],verify_only=True);db.block(s,b,rollback=True)
            result['checks'].append('restricted_insert_and_full_readback_without_delete_or_lock_any_privilege')
            try:db.block('BEGIN DELETE FROM '+contract.table('DOC_VER')+' WHERE 1=0; ROLLBACK; END;')
            except Exception as exc:assert 'ORA-01031' in error_codes(exc)
            else:raise AssertionError('test account unexpectedly has DELETE')
            assert db.query('SELECT COUNT(*) AS N FROM '+contract.table('DOC_VER'))==[{'N':5}]
            result['checks'].append('delete_permission_absent_but_new_table_load_succeeds')
            result['database_calls']=db.calls
            result['status']='PASS_NATIVE_ORACLE_CONTRACTS'
    except BaseException as exc:
        result.update(status='FAILED',error_type=type(exc).__name__,codes=error_codes(exc))
        raise
    finally:
        if restricted is not None:restricted.close()
        if admin is not None:
            admin.rollback()
            with admin.cursor() as c:
                for name in reversed(result['created_schemas']):
                    assert re.fullmatch('A8_G19_[A-F0-9]{10}',name)
                    c.execute('DROP USER '+name+' CASCADE')
                    result['dropped_schemas'].append(name)
            admin.close()
        (HERE/'NATIVE_CONTRACTS.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
