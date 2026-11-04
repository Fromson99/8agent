"""User-authorized local Gold RGLT_DOC_ID width change, with journal and inverse DDL.

No row rewriting, table renames, MAIN promotion, field deployment or model calls.
Only the active local mapping is replaced after all six alterations are verified.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys

import gold_vctr_sctn_rename as existing

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-gold-docid100-local'
KEYS=('DOC_VER','DOC_UNIT','DOC_BLK','SRCH_ROW','ONTL_ANC','VCTR_ITEM')
TARGET='mapping_local_docid100_current.json'
REVISION='20261104-local-docid100-r1'
connect=existing.connect
save_file=existing.prior.save


def save(name,value): save_file(OUT/name,value)


def event(**value):
    existing.prior.OUT=OUT
    existing.prior.event(**value)


def quiescent(db,mapping):
    with db.cursor() as c:
        c.execute("SELECT SYS_CONTEXT('USERENV','SID') FROM DUAL")
        sid=int(c.fetchone()[0])
    reader=json.loads((Path.home()/'.local/state/8-agent/gold-r12-1208/readonly-connection.json').read_text())['user'].upper()
    with existing.admin.admin_connection() as admin,admin.cursor() as c:
        c.execute('SELECT SID,SERIAL#,USERNAME,STATUS FROM V$SESSION WHERE USERNAME IN (:owner,:reader) AND SID<>:sid',
                  owner=mapping.owner,reader=reader,sid=sid)
        sessions=[list(r) for r in c]
        c.execute('SELECT O.OBJECT_NAME,L.SESSION_ID,L.LOCKED_MODE FROM V$LOCKED_OBJECT L JOIN DBA_OBJECTS O ON O.OBJECT_ID=L.OBJECT_ID WHERE O.OWNER=:owner',owner=mapping.owner)
        locks=[list(r) for r in c]
        c.execute('SELECT OWNER,NAME,TYPE,REFERENCED_NAME FROM DBA_DEPENDENCIES WHERE REFERENCED_OWNER=:owner',owner=mapping.owner)
        dependencies=[list(r) for r in c if r[3] in {mapping.tables[k]['name'] for k in KEYS}]
    result={'sessions':sessions,'locks':locks,'dependent_objects':dependencies}
    if sessions or locks or dependencies:
        save('concurrency-blocked-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json',result)
        raise RuntimeError('Gold in use or dependent objects exist; preserve current state')
    return result


def snapshot(db,mapping):
    result=existing.snapshot(db,mapping)
    result['document_id_distribution']={}
    with db.cursor() as c:
        for key in KEYS:
            table=mapping.physical_table(key);column=mapping.column(key,'DOC_ID')
            c.execute('SELECT '+column+',COUNT(*),LENGTHB('+column+') FROM '+table+' GROUP BY '+column+' ORDER BY '+column+' NULLS FIRST')
            rows=[list(r) for r in c]
            if len(rows)>10000: raise RuntimeError('Unexpected local document scope')
            if any(size is not None and size>100 for _,_,size in rows):
                raise RuntimeError('RGLT_DOC_ID_OVER_100:'+key)
            result['document_id_distribution'][key]=rows
    return result


def expected_after(before,mapping):
    value=deepcopy(before)
    tables={mapping.tables[k]['name'] for k in KEYS}
    edited=0
    for row in value['columns']:
        if row[0] in tables and row[1]=='DOC_ID':
            assert row[3]=='VARCHAR2' and row[4]==1000
            row[4]=100;edited+=1
    assert edited==6
    return value


def plan():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists(): raise RuntimeError('Plan already exists; inspect without overwriting')
    source,source_sha=connect.active_mapping()
    original=connect.read(source);target=deepcopy(original)
    target['revision']=REVISION
    for key in KEYS:
        column=target['tables'][key]['columns']['DOC_ID']
        assert column['name']=='RGLT_DOC_ID' and column['type']=='VARCHAR2(1000 BYTE)'
        column['type']='VARCHAR2(100 BYTE)'
    assert original['owner']=='A8_GR12_CM1208'
    save('before-active-mapping.json',connect.read(HERE/'ACTIVE_MAPPING.json'))
    save('before-mapping.json',original);save('target-mapping.json',target)
    before_map=connect.load_mapping(source)
    connect.load_mapping(OUT/'target-mapping.json')
    with existing.writer() as db:
        before_map.preflight(db)
        save('concurrency-plan.json',quiescent(db,before_map))
        before=snapshot(db,before_map);save('plan-before.json',before)
        expected_after(before,before_map)
        ddl=[]
        with db.cursor() as c:
            for key in KEYS:
                c.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM DUAL",name=before_map.tables[key]['name'])
                ddl.append(c.fetchone()[0])
        (OUT/'before-ddl.sql').write_text('\n'.join(ddl))
    steps=[{'key':key,'table':before_map.tables[key]['name'],
            'forward':'ALTER TABLE '+before_map.physical_table(key)+' MODIFY (RGLT_DOC_ID VARCHAR2(100 BYTE))',
            'reverse':'ALTER TABLE '+before_map.physical_table(key)+' MODIFY (RGLT_DOC_ID VARCHAR2(1000 BYTE))'} for key in KEYS]
    result={'owner':before_map.owner,'old_mapping_file':str(source.relative_to(ROOT)),'old_mapping_sha256':source_sha,
            'pointer_sha256':connect.sha(HERE/'ACTIVE_MAPPING.json'),
            'target_mapping_sha256':connect.sha(OUT/'target-mapping.json'),'steps':steps,
            'user_request':'아 등록으로 되어있구나 이거 로컬에서도 수정할수 있나?',
            'scope':'RGLT_DOC_ID six columns 1000 BYTE to 100 BYTE; table names and other columns unchanged'}
    save('plan.json',result)
    (OUT/'apply.sql').write_text(';\n'.join(s['forward'] for s in steps)+';\n')
    (OUT/'rollback.sql').write_text(';\n'.join(s['reverse'] for s in reversed(steps))+';\n')
    print(json.dumps({'status':'PLAN_READY','columns':6,'rows':{k:before['row_counts'][k] for k in KEYS},
                      'max_id_bytes':max(s or 0 for rows in before['document_id_distribution'].values() for _,_,s in rows)}))


def restore_after_failure(plan,error):
    failures=[]
    # Query actual dictionary state, including an ALTER whose acknowledgement was lost.
    with existing.writer() as db:
        for step in reversed(plan['steps']):
            try:
                with db.cursor() as c:
                    c.execute("SELECT DATA_LENGTH FROM USER_TAB_COLUMNS WHERE TABLE_NAME=:name AND COLUMN_NAME='RGLT_DOC_ID'",name=step['table'])
                    row=c.fetchone()
                    if row==(100,):
                        event(status='REVERSING',sql=step['reverse']);c.execute(step['reverse'])
                        event(status='REVERSED',sql=step['reverse'])
                    elif row!=(1000,): raise RuntimeError('Unexpected rollback width:'+repr(row))
            except Exception as exc:failures.append({'table':step['table'],'error':str(exc)})
        if not failures:
            old=connect.load_mapping(ROOT/plan['old_mapping_file']);old.preflight(db)
            assert snapshot(db,old)==connect.read(OUT/'before.json')
            save_file(HERE/'ACTIVE_MAPPING.json',connect.read(OUT/'before-active-mapping.json'))
    save('failed.json',{'error':str(error),'rollback_errors':failures,'rollback_verified':not failures})
    if failures:raise RuntimeError('Rollback incomplete: inspect failed.json; do not retry') from error


def apply():
    if (OUT/'ddl-events.jsonl').exists() or (OUT/'completed.json').exists():
        raise RuntimeError('Existing DDL attempt; inspect journal instead of automatic retry')
    p=connect.read(OUT/'plan.json')
    assert connect.sha(HERE/'ACTIVE_MAPPING.json')==p['pointer_sha256']
    assert connect.sha(ROOT/p['old_mapping_file'])==p['old_mapping_sha256']
    assert connect.sha(OUT/'target-mapping.json')==p['target_mapping_sha256']
    old=connect.load_mapping(ROOT/p['old_mapping_file']);new=connect.load_mapping(OUT/'target-mapping.json')
    try:
        with existing.writer() as db:
            old.preflight(db);save('concurrency-apply.json',quiescent(db,old))
            before=snapshot(db,old);save('before.json',before)
            assert before==connect.read(OUT/'plan-before.json'),'DB changed since planning'
            with db.cursor() as c:c.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
            for number,step in enumerate(p['steps'],1):
                quiescent(db,old)
                event(status='STARTED',number=number,sql=step['forward'])
                with db.cursor() as c:c.execute(step['forward'])
                event(status='APPLIED',number=number,sql=step['forward'])
                print(json.dumps({'status':'COLUMN_ALTERED','table':step['table'],'number':number}),flush=True)
            new.preflight(db)
            after=snapshot(db,new);save('after.json',after)
            assert after==expected_after(before,old),'Unexpected data/objects/keys/indexes/publications change'
            save('database-verified.json',{'status':'PASS','columns_changed':6,'mapping_tables_verified':13,'mapping_columns_verified':60,
                 'only_expected_six_widths_changed':True,'id_distributions_unchanged':True,
                 'row_counts_objects_keys_indexes_grants_publication_hashes_unchanged':True,
                 'target_mapping_sha256':p['target_mapping_sha256']})
            assert connect.sha(HERE/'ACTIVE_MAPPING.json')==p['pointer_sha256'],'Mapping changed concurrently'
            save_file(HERE/TARGET,connect.read(OUT/'target-mapping.json'))
            save_file(HERE/'ACTIVE_MAPPING.json',{'schema_version':'gold-active-physical-map-v1','mapping_file':TARGET,
                       'sha256':connect.sha(HERE/TARGET),'migration_receipt':str((OUT/'database-verified.json').relative_to(ROOT))})
            chosen,chosen_sha=connect.active_mapping()
            assert chosen==HERE/TARGET and chosen_sha==p['target_mapping_sha256']
    except BaseException as exc:
        if (OUT/'ddl-events.jsonl').exists():
            event(status='FAILED',error_type=type(exc).__name__,error=str(exc))
            restore_after_failure(p,exc)
        else:save('pre-ddl-failed.json',{'error':str(exc),'ddl':0})
        raise
    result={'status':'WIDTH_100_AND_MAPPING_ACTIVATED','owner':new.owner,'changed_columns':6,
            'active_mapping':TARGET,'sha256':chosen_sha,'data_values_modified':False,'tables_renamed':False,
            'row_counts':after['row_counts'],'finished_utc':datetime.now(timezone.utc).isoformat()}
    save('completed.json',result);print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['plan','apply']);args=parser.parse_args()
    lock_path=Path.home()/'.local/state/8-agent/gold-r12-1208/schema-migration.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        {'plan':plan,'apply':apply}[args.action]()
