"""Isolated loopback Oracle contract test; only freshly created random fixture tables."""
import copy,json,secrets,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent/'gold_shape_silver_20261102_r1/package'
sys.path[:0]=[str(HERE),str(PACKAGE),str(PACKAGE/'vendor/02_BACKEND')]
import reset_source
from gold_io import Contract,Database
import jdbc_transport
from types import SimpleNamespace
jdbc_transport.install(SimpleNamespace(Database=Database))
import oracledb
import pandas as pd
oracledb.defaults.fetch_lobs=False

def main():
    metadata=json.loads(subprocess.check_output(['docker','inspect','a8-legal-mapped-20261023']))[0]
    assert metadata['Config']['Labels']['a8.task']=='legal-mapped-20261023' and metadata['State']['Running']
    ports=metadata['HostConfig']['PortBindings']['1521/tcp'];assert len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
    password=dict(v.split('=',1) for v in metadata['Config']['Env'])['ORACLE_PASSWORD']
    def connect():
        connection=oracledb.connect(user='system',password=password,dsn='127.0.0.1:'+ports[0]['HostPort']+'/FREEPDB1')
        connection.call_timeout=15000
        return connection
    conn=connect()
    created=[];checks=[]
    name='A8_RST_'+secrets.token_hex(5).upper();guard=name+'_G'
    contract=Contract(PACKAGE/'contract.json');contract.tables['DOC_VER']['owner']='SYSTEM';contract.tables['DOC_VER']['name']=name
    def execute(sql):
        with conn.cursor() as cursor:cursor.execute(sql)
    class Executor:
        def query_to_df(self,sql,pre_queries=(),post_queries=(),**kwargs):
            with conn.cursor() as cursor:
                for stmt in pre_queries:cursor.execute(stmt)
                cursor.execute(sql)
                result=pd.DataFrame(cursor.fetchall(),columns=[v[0] for v in cursor.description])
                for stmt in post_queries:cursor.execute(stmt)
                return result
    db=Database(Executor())
    def put(rows):db.block(*contract.batch('DOC_VER',rows))
    def delete(rows):db.block(*reset_source.delete_sql(contract,'DOC_VER',rows,{}))
    def n():return db.query('SELECT COUNT(*) AS N FROM SYSTEM.'+name)[0]['N']
    a={'MNFST_HASH_VALU':'v1','DOC_ID':'a','DOC_NAME':'alpha','DOC_HASH_VALU':'a'*64,'DOC_ADDN_IFMN_CTNT':'가나다'*2500}
    b={**a,'DOC_ID':'b','DOC_NAME':'beta','DOC_ADDN_IFMN_CTNT':''}
    other={**a,'MNFST_HASH_VALU':'v2','DOC_ID':'a','DOC_NAME':'other generation'}
    try:
        execute(contract.ddl('DOC_VER'));created.append(name)
        execute('CREATE TABLE SYSTEM.'+guard+' (PUBID VARCHAR2(100))');created.append(guard)
        reset_source.gates=lambda c,b:[('SYSTEM.'+guard,"PUBID='q'")]
        put([a,b,other]);assert n()==3
        exported=[row for batch in reset_source.source_batches(db,contract,'DOC_VER','v1') for row in batch]
        if exported != [a,b]:
            print('BACKUP_FIELD_DIFFERENCES', [{k:{'actual_type':type(got.get(k)).__name__,'actual_length':len(str(got.get(k))),'expected_type':type(want.get(k)).__name__,'expected_length':len(str(want.get(k)))} for k in want if got.get(k)!=want.get(k)} for got,want in zip(exported,[a,b])])
        assert exported==[a,b] and reset_source.source_count(db,contract,'DOC_VER','v1')==2
        checks.append('backup reader preserves long Unicode and empty CLOB with exact source counts')
        delete([a]);assert n()==2;checks.append('delete only exact backed-up PK, preserve other generation and other row')
        delete([a]);assert n()==2;checks.append('commit response-loss retry is a no-op for absent backed-up row')
        try:delete([{**b,'DOC_NAME':'wrong backup'}])
        except Exception as exc:assert 'ORA-20061' in str(exc)
        else:raise AssertionError('conflict must stop')
        assert n()==2;checks.append('changed content rejected and existing rows preserved')
        delete([b]);assert n()==1;checks.append('empty CLOB comparison and deletion succeeds')
        execute("INSERT INTO SYSTEM."+guard+" VALUES ('q')");conn.commit()
        try:delete([other])
        except Exception as exc:assert 'ORA-20060' in str(exc)
        else:raise AssertionError('publication must stop')
        assert n()==1;checks.append('publication guard stops deletion')
        execute('DELETE FROM SYSTEM.'+guard);conn.commit()
        # One good and one changed row in a single batch: all remain after refusal.
        put([a,b]);assert n()==3
        try:delete([a,{**b,'DOC_NAME':'wrong'}])
        except Exception as exc:assert 'ORA-20061' in str(exc)
        else:raise AssertionError('mixed conflict must stop')
        assert n()==3;checks.append('mixed batch conflict causes no partial delete')
        delete([a,b]);assert n()==1;checks.append('multirow batch with long Unicode CLOB verified')
        many=[{**a,'MNFST_HASH_VALU':'v3','DOC_ID':str(i).zfill(3),'DOC_ADDN_IFMN_CTNT':'page'} for i in range(45)]
        put(many)
        pages=list(reset_source.source_batches(db,contract,'DOC_VER','v3'))
        assert [len(p) for p in pages]==[45]
        assert [r for p in pages for r in p]==many
        delete(many);assert n()==1
        checks.append('keyset backup pagination includes all 45 rows once and keeps other generation')
        # Bind values exercise the real renderer, not a mocked literal serializer.
        special="한글😀𠀀 quote' backslash\\; -- :payload /* */\n\r\t"
        odd={**a,'MNFST_HASH_VALU':'special','DOC_NAME':special,'DOC_ADDN_IFMN_CTNT':special*120}
        put([odd])
        assert [r for p in reset_source.source_batches(db,contract,'DOC_VER','special') for r in p]==[odd]
        db.block(*contract.batch('DOC_VER',[odd],verify_only=True),rollback=True)
        delete([odd]);assert n()==1
        checks.append('UTF8_HEX insert readback verify delete preserves quotes slash newlines and supplementary Unicode')
        many=[{**b,'MNFST_HASH_VALU':'pages','DOC_ID':str(i).zfill(4),'DOC_ADDN_IFMN_CTNT':'small'} for i in range(405)]
        put(many)
        pages=list(reset_source.source_batches(db,contract,'DOC_VER','pages'))
        assert [len(p) for p in pages]==[200,200,5] and [r for p in pages for r in p]==many
        delete(many);assert n()==1
        checks.append('200-row keyset pages cover 405 rows exactly')
        large={**b,'MNFST_HASH_VALU':'large','DOC_ADDN_IFMN_CTNT':special*40000}
        put([large])
        assert [r for p in reset_source.source_batches(db,contract,'DOC_VER','large') for r in p]==[large]
        db.block(*contract.batch('DOC_VER',[large],verify_only=True),rollback=True)
        delete([large]);assert n()==1
        checks.append('multi-megabyte Unicode CLOB survives insert readback verification and delete without truncation')
        limited=[{**b,'MNFST_HASH_VALU':'bytepage','DOC_ID':str(i),'DOC_ADDN_IFMN_CTNT':'가'*400000} for i in range(3)]
        put(limited)
        pages=list(reset_source.source_batches(db,contract,'DOC_VER','bytepage'))
        assert [len(p) for p in pages]==[1,1,1] and [r for p in pages for r in p]==limited
        for page in pages:delete(page)
        assert n()==1
        checks.append('byte-bound pages preserve whole large rows while limiting combined payload')
        report={'status':'PASS','checks':checks,'oracle_version':conn.version,'loopback_only':True,
                'existing_user_data_mutated':False,'real_model_calls':0,'helper_sha256':reset_source.raw_sha(HERE/'reset_source.py'),
                'transport_sha256':reset_source.raw_sha(HERE/'jdbc_transport.py')}
    finally:
        try:conn.rollback()
        except oracledb.Error:
            conn=connect()
        for table in reversed(created):
            assert table in (name,guard)
            execute('DROP TABLE SYSTEM.'+table+' PURGE')
        conn.close()
    report['created_and_removed_fixture_tables']=created
    (HERE/'NATIVE_VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
