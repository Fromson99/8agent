"""User-requested vector section ID column rename in the existing local Gold only.

Preserve historical migration records, data and types. Oracle DDL is journalled
and reversed on failure before activating an atomically replaced mapping pointer.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-vctr-sctn-rename'
OLD, NEW = 'VCTR_SEG_ID', 'VCTR_SCTN_ID'
TARGET_NAME = 'mapping_local_vctr_current.json'
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import connect
import gold_physical_rename as prior


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admin = load_module('gold_dtls_existing_admin',ROOT/'06_TOOLS/maintenance/publish_gold_ontology_samples.py')


def save(name, value):
    prior.save(OUT/name,value)


def event(**value):
    prior.OUT = OUT
    prior.event(**value)


def concurrency(db, mapping):
    with db.cursor() as c:
        c.execute("SELECT SYS_CONTEXT('USERENV','SID') FROM DUAL")
        sid = int(c.fetchone()[0])
    reader = json.loads((Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json').read_text())['user'].upper()
    with admin.admin_connection() as audit, audit.cursor() as c:
        c.execute('SELECT SID,SERIAL#,USERNAME,STATUS FROM V$SESSION WHERE USERNAME IN (:owner,:reader) AND SID<>:sid',owner=mapping.owner,reader=reader,sid=sid)
        sessions = [list(r) for r in c]
        c.execute('SELECT O.OBJECT_NAME,L.SESSION_ID,L.LOCKED_MODE FROM V$LOCKED_OBJECT L JOIN DBA_OBJECTS O ON O.OBJECT_ID=L.OBJECT_ID WHERE O.OWNER=:owner',owner=mapping.owner)
        locks = [list(r) for r in c]
        c.execute('SELECT OWNER,NAME,TYPE,REFERENCED_NAME FROM DBA_DEPENDENCIES WHERE REFERENCED_OWNER=:owner AND REFERENCED_NAME=:a',
                  owner=mapping.owner,a=mapping.tables['VCTR_ITEM']['name'])
        deps = [list(r) for r in c]
    result = {'sessions':sessions,'locks':locks,'dependent_objects':deps}
    if sessions or locks or deps:
        save('concurrency-blocked.json',result)
        raise RuntimeError('Gold is in use or has dependent objects; no DDL executed')
    return result


def snapshot(db, mapping):
    result = prior.snapshot(db,mapping)
    aliases = {t['name']:{c['name']:logical for logical,c in t['columns'].items()} for t in mapping.tables.values()}
    with db.cursor() as c:
        c.execute('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_ID,DATA_TYPE,DATA_LENGTH,DATA_PRECISION,DATA_SCALE,CHAR_USED,NULLABLE,DATA_DEFAULT FROM USER_TAB_COLUMNS ORDER BY TABLE_NAME,COLUMN_ID')
        result['columns'] = [[r[0],aliases.get(r[0],{}).get(r[1],r[1]),*r[2:]] for r in c]
        c.execute('SELECT TABLE_NAME,CONSTRAINT_NAME,COLUMN_NAME,POSITION FROM USER_CONS_COLUMNS ORDER BY TABLE_NAME,CONSTRAINT_NAME,POSITION')
        result['constraint_columns'] = [[r[0],r[1],aliases.get(r[0],{}).get(r[2],r[2]),r[3]] for r in c]
        c.execute('SELECT TABLE_NAME,INDEX_NAME,COLUMN_NAME,COLUMN_POSITION,DESCEND FROM USER_IND_COLUMNS ORDER BY TABLE_NAME,INDEX_NAME,COLUMN_POSITION')
        result['index_columns'] = [[r[0],r[1],aliases.get(r[0],{}).get(r[2],r[2]),*r[3:]] for r in c]
        c.execute('SELECT TABLE_NAME,INDEX_NAME,UNIQUENESS,STATUS,PARTITIONED,TABLESPACE_NAME FROM USER_INDEXES ORDER BY TABLE_NAME,INDEX_NAME')
        result['indexes'] = [list(r) for r in c]
        result['ontology_hashes'] = {}
        for key in ['ONTL_POST','ONTL_HEAD','ONTL_ANC']:
            table = mapping.tables[key]
            cols = list(table['columns'])
            c.execute('SELECT '+','.join(cols)+' FROM '+mapping.table(key)+' ORDER BY '+','.join(table['primary_key']))
            digest = hashlib.sha256(); count=0
            for row in c:
                digest.update(json.dumps(list(row),ensure_ascii=False,default=str,separators=(',',':')).encode());digest.update(b'\n');count+=1
            result['ontology_hashes'][key] = {'rows':count,'sha256':digest.hexdigest()}
    with db.cursor() as c:
        c.execute('SELECT VCTR_POST_ID,VCTR_SEG_ID,DOC_ID,SRC_UNIT_ID,VCTR_META_CTNT FROM '+mapping.table('VCTR_ITEM')+' ORDER BY VCTR_POST_ID,VCTR_SEG_ID')
        digest=hashlib.sha256();count=0
        for row in c:
            digest.update(json.dumps(list(row),ensure_ascii=False,default=str,separators=(',',':')).encode());digest.update(b'\n');count+=1
        result['vector_identifiers_metadata']={'rows':count,'sha256':digest.hexdigest()}
    return result


def writer():
    import oracledb
    oracledb.defaults.fetch_lobs=False
    p=Path.home()/'.local/state/8-agent/gold-r12-1208/connection.json'
    if p.stat().st_mode & 0o077: raise RuntimeError('Private credentials required')
    cfg=json.loads(p.read_text())
    if cfg['dsn'].split(':')[0] not in ('127.0.0.1','localhost'): raise RuntimeError('Local target only')
    db=oracledb.connect(**cfg);db.call_timeout=60000
    with db.cursor() as c:
        c.execute("SELECT SYS_CONTEXT('USERENV','SESSION_USER'),SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM DUAL")
        if c.fetchone()!=('A8_GR12_CM1208','A8_GR12_CM1208'): raise RuntimeError('Unexpected DB owner')
    return db


def plan():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists(): raise RuntimeError('Existing plan; inspect before replacing')
    old_path,old_sha=connect.active_mapping()
    original=connect.read(old_path); new=deepcopy(original)
    registration=connect.read(HERE/'mapping_r18_registration.json')
    new['revision']='20261030-vctr-sctn-preserved-types-r1'
    changes=[]
    for key,table in new['tables'].items():
        registered=registration['tables'][key]
        if table['name']!=registered['name']: raise RuntimeError('Unexpected table name difference')
        for logical,col in table['columns'].items():
            target=registered['columns'][logical]['name']
            if col['name']!=target:
                if (col['name'],target)!=(OLD,NEW): raise RuntimeError('Unexpected physical name change')
                changes.append({'key':key,'table':table['name'],'logical':logical})
                col['name']=target
    assert [s['key'] for s in changes]==['VCTR_ITEM']
    save('before-active-mapping.json',connect.read(HERE/'ACTIVE_MAPPING.json'))
    save('before-mapping.json',original)
    save('target-mapping.json',new)
    old=connect.load_mapping(old_path);target=connect.load_mapping(OUT/'target-mapping.json')
    with writer() as db:
        old.preflight(db)
        save('concurrency-preflight.json',concurrency(db,old))
        save('plan-before.json',snapshot(db,old))
    steps=[{'forward':f'ALTER TABLE {old.owner}.{s["table"]} RENAME COLUMN {OLD} TO {NEW}',
            'reverse':f'ALTER TABLE {old.owner}.{s["table"]} RENAME COLUMN {NEW} TO {OLD}'} for s in changes]
    value={'owner':old.owner,'old_mapping_file':str(old_path.relative_to(ROOT)),'old_mapping_sha256':old_sha,
           'pointer_sha256':connect.sha(HERE/'ACTIVE_MAPPING.json'),'target_mapping_sha256':connect.sha(OUT/'target-mapping.json'),
           'registration_sha256':connect.sha(HERE/'mapping_r18_registration.json'),'steps':steps,'user_request':'우리 최종 테이블테 골드테이블에 벡터구간ID를 VCTR_SCTN_ID이걸로 해줘'}
    save('plan.json',value)
    (OUT/'apply.sql').write_text(';\n'.join(s['forward'] for s in steps)+';\n')
    (OUT/'rollback.sql').write_text(';\n'.join(s['reverse'] for s in reversed(steps))+';\n')
    print(json.dumps({'status':'PLAN_READY','owner':old.owner,'column_renames':1,'steps':steps},ensure_ascii=False))


def apply():
    if (OUT/'ddl-events.jsonl').exists() or (OUT/'completed.json').exists(): raise RuntimeError('Existing attempt; inspect journal')
    p=connect.read(OUT/'plan.json')
    assert connect.sha(HERE/'ACTIVE_MAPPING.json')==p['pointer_sha256']
    assert connect.sha(ROOT/p['old_mapping_file'])==p['old_mapping_sha256']
    assert connect.sha(OUT/'target-mapping.json')==p['target_mapping_sha256']
    assert connect.sha(HERE/'mapping_r18_registration.json')==p['registration_sha256']
    old=connect.load_mapping(ROOT/p['old_mapping_file']);new=connect.load_mapping(OUT/'target-mapping.json')
    completed=[]
    with writer() as db:
        old.preflight(db)
        save('concurrency-before-apply.json',concurrency(db,old))
        before=snapshot(db,old);save('before.json',before)
        assert before==connect.read(OUT/'plan-before.json'),'DB changed after planning'
        with db.cursor() as c:
            c.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
            ddl=[]
            for t in old.tables.values():
                c.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM DUAL",name=t['name']);ddl.append(c.fetchone()[0])
        (OUT/'before-ddl.sql').write_text('\n'.join(ddl))
        pointer_activated=False
        try:
            for number,step in enumerate(p['steps'],1):
                concurrency(db,old)
                event(status='STARTED',number=number,sql=step['forward'])
                with db.cursor() as c:c.execute(step['forward'])
                completed.append(step);event(status='APPLIED',number=number,sql=step['forward'])
            new.preflight(db)
            after=snapshot(db,new);save('after.json',after)
            assert before==after,'Data/object/metadata/PK/index/ontology state changed'
            save('database-verified.json',{'status':'PASS','column_renames':1,'table_renames':0,'before_after_equal':True,
                 'columns_verified':60,'tables_verified':13,'target_mapping_sha256':p['target_mapping_sha256']})
            assert connect.sha(HERE/'ACTIVE_MAPPING.json')==p['pointer_sha256'],'Active pointer changed concurrently'
            prior.save(HERE/TARGET_NAME,connect.read(OUT/'target-mapping.json'))
            prior.save(HERE/'ACTIVE_MAPPING.json',{'schema_version':'gold-active-physical-map-v1','mapping_file':TARGET_NAME,
                       'sha256':connect.sha(HERE/TARGET_NAME),'migration_receipt':str((OUT/'database-verified.json').relative_to(ROOT))})
            pointer_activated=True
            chosen,sha=connect.active_mapping()
            assert chosen==HERE/TARGET_NAME and sha==p['target_mapping_sha256']
        except BaseException as exc:
            event(status='FAILED',error_type=type(exc).__name__,error=str(exc))
            failures=[]
            for step in reversed(completed):
                try:
                    with db.cursor() as c:c.execute(step['reverse'])
                    event(status='REVERSED',sql=step['reverse'])
                except Exception as error:failures.append({'sql':step['reverse'],'error':str(error)})
            if not failures:
                old.preflight(db)
                prior.save(HERE/'ACTIVE_MAPPING.json',connect.read(OUT/'before-active-mapping.json'))
            save('failed.json',{'error':str(exc),'completed':len(completed),'rollback_errors':failures,'pointer_had_activated':pointer_activated})
            raise
    save('completed.json',{'status':'RENAMED_AND_MAPPING_ACTIVATED','owner':new.owner,'column_renames':1,
         'active_mapping':TARGET_NAME,'active_mapping_sha256':connect.sha(HERE/TARGET_NAME),'row_counts':after['row_counts'],
         'data_values_modified':False,'finished_utc':datetime.now(timezone.utc).isoformat()})
    print(json.dumps(connect.read(OUT/'completed.json'),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['plan','apply']);args=parser.parse_args()
    lock_path=Path.home()/'.local/state/8-agent/gold-r12-1208/schema-migration.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        {'plan':plan,'apply':apply}[args.action]()
