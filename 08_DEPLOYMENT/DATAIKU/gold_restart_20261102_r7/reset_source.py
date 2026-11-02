"""One-time, backed-up reset of this failed R1 source generation only."""
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from decimal import Decimal
from numbers import Integral
import math

SOURCE_KEYS=('DOC_VER','DOC_UNIT','DOC_BLK')
SOURCE_KINDS={'DOC_VER':'document','DOC_UNIT':'source_unit','DOC_BLK':'block_payload'}
R6_HELPER_SHA256='06aa3054204427761c06397f9db1100fc3c6e4e8a08f9980e9036559931a5237'
BACKUP_TARGET_BYTES=4*1024**2


def count_integer(value,context):
    """COUNT may be a JDBC Decimal or pandas float; never truncate a fraction."""
    result=None
    if isinstance(value,Integral) and not isinstance(value,bool):result=int(value)
    elif isinstance(value,Decimal) and value.is_finite() and value==value.to_integral_value():result=int(value)
    elif isinstance(value,float) and math.isfinite(value) and value.is_integer() and abs(value)<=2**53-1:result=int(value)
    elif isinstance(value,str) and value.isascii() and value.isdigit():result=int(value)
    if result is None or result<0:
        raise ValueError('RESET_COUNT_INVALID:'+context+':type='+type(value).__name__+':value='+repr(value)[:100])
    return result


def source_limits(source):
    return {key:count_integer(source['source_rows'][kind]['rows'],'manifest.'+kind)
            for key,kind in SOURCE_KINDS.items()}


def backup_batches(pages,canonical):
    """Bound each JSON batch, without imposing an unrelated total backup cap."""
    for page in pages:
        batch=[];size=2
        for row in page:
            row_size=len(canonical(row).encode())+1
            if batch and size+row_size>BACKUP_TARGET_BYTES:
                yield batch;batch=[];size=2
            batch.append(row);size+=row_size
        if batch:yield batch


def r6_upgrade_allowed(control):
    return (control.get('reset_code_sha256')==R6_HELPER_SHA256 and
            control.get('schema')=='gold-source-reset-r6' and control.get('phase')=='BACKING_UP' and
            'manifest_sha256' not in control and 'last_confirmed_batch' not in control)


def upgrade_controller(loader,control_path,control,backup_root):
    """Only the known R6, before any deletion. Keep its original bytes and ID."""
    if not r6_upgrade_allowed(control) or (backup_root/'manifest.json').exists():
        raise ValueError('RESET_R6_UPGRADE_REQUIRES_BACKUP_ONLY_PHASE')
    previous=control_path.read_bytes();archive=backup_root/'control-r6-before-upgrade.json'
    if archive.exists():
        if archive.read_bytes()!=previous:raise ValueError('RESET_R6_CONTROL_BACKUP_CHANGED')
    else:
        with archive.open('xb') as stream:
            stream.write(previous);stream.flush();os.fsync(stream.fileno())
        sync_dir(backup_root)
    control.update(schema='gold-source-reset-r7',reset_code_sha256=raw_sha(__file__),
                   upgrade={'from_helper_sha256':R6_HELPER_SHA256,'previous_control_sha256':raw_sha(archive),
                            'at':time.time(),'reason':'exact count normalization and manifest-bound reset scope'})
    loader.atomic(control_path,control)
    emit('RESET_R6_UPGRADED',detail='삭제 전 중단된 R6 상태를 보존하고 같은 초기화를 이어갑니다.')


def sync_dir(path):
    descriptor=os.open(path,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def raw_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024**2):h.update(block)
    return h.hexdigest()


def emit(phase,**fields):print(json.dumps({'phase':phase,**fields},ensure_ascii=False),flush=True)


def gates(contract,binding):
    """Bound publication/search predicates; never broad deletes."""
    from gold_io import literal
    source=binding['source_release'];query=binding['query_release']
    cases=[('SRC_POST','DOC_POST_HASH_VALU',source),('SRCH_POST','RFRN_POST_HASH_VALU',query),
           ('SRCH_ROW','RFRN_POST_HASH_VALU',query),('SRCH_CHNL','RFRN_POST_HASH_VALU',query),
           ('VCTR_HEAD','RFRN_POST_HASH_VALU',query)]
    result=[(contract.table(k),contract.col(k,col)+'='+literal(value)) for k,col,value in cases]
    result.append((contract.table('VCTR_POST'),"JSON_VALUE("+contract.col('VCTR_POST','VCTR_POST_IFMN_CTNT')+
                   ",'$.manifest.query_id' RETURNING VARCHAR2(100) ERROR ON ERROR)="+literal(query)))
    return result


def zero_publications(db,contract,binding):
    for table,where in gates(contract,binding):
        if db.query('SELECT COUNT(*) AS N FROM '+table+' WHERE '+where)!=[{'N':0}]:
            raise ValueError('RESET_REFUSED_ALREADY_SEARCHED_OR_PUBLISHED:'+table)


def delete_sql(contract,key,rows,binding):
    """Verify exact backup contents and delete those PKs in one transaction."""
    sql,binds=contract.batch(key,rows,verify_only=True)
    prefix='SELECT COUNT(*) INTO n FROM '
    clause=sql[sql.index(prefix)+len(prefix):sql.index('; IF n<>:expected')]
    source,rest=clause.split(' JOIN ',1)
    target,equal=rest.split(' WHERE ',1)
    table=contract.table(key)
    expected=table+' t ON ('
    if not target.startswith(expected) or not target.endswith(')'):
        raise ValueError('RESET_VERIFIER_SHAPE')
    pk=target[len(expected):-1]
    references=gates(contract,binding)
    locks=sorted({table,*[t for t,w in references]})
    text='DECLARE present_n NUMBER; matched_n NUMBER; ref_n NUMBER; BEGIN '
    text+=' '.join('LOCK TABLE '+t+' IN SHARE ROW EXCLUSIVE MODE NOWAIT;' for t in locks)+' '
    for t,where in references:
        text+='SELECT COUNT(*) INTO ref_n FROM '+t+' WHERE '+where+"; IF ref_n<>0 THEN RAISE_APPLICATION_ERROR(-20060,'RESET_REFERENCED'); END IF; "
    text+='SELECT COUNT(*) INTO present_n FROM '+source+' JOIN '+target+'; '
    text+='SELECT COUNT(*) INTO matched_n FROM '+clause+'; '
    text+="IF present_n<>matched_n OR present_n>:expected THEN RAISE_APPLICATION_ERROR(-20061,'RESET_BACKUP_CONTENT_CHANGED'); END IF; "
    text+='DELETE FROM '+table+' t WHERE EXISTS (SELECT 1 FROM '+source+' WHERE '+pk+' AND '+equal+'); '
    text+="IF SQL%ROWCOUNT<>present_n THEN RAISE_APPLICATION_ERROR(-20062,'RESET_DELETE_COUNT_CHANGED'); END IF; COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;"
    return text,binds


def source_count(db,contract,key,version):
    from gold_io import literal
    raw=db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE '+contract.col(key,'MNFST_HASH_VALU')+'='+literal(version))[0]['N']
    count=count_integer(raw,contract.table(key))
    emit('RESET_TABLE_COUNT',table=contract.table(key),rows=count,returned_type=type(raw).__name__)
    return count


def source_batches(db,contract,key,version):
    from gold_io import literal
    columns=contract.tables[key]['columns']
    keys=contract.tables[key]['primary_key']
    cursor=None
    while True:
        where=contract.col(key,'MNFST_HASH_VALU')+'='+literal(version)
        if cursor is not None:
            alternatives=[]
            for i,name in enumerate(keys):
                terms=[contract.col(key,keys[j])+'='+literal(cursor[j]) for j in range(i)]
                terms.append(contract.col(key,name)+'>'+literal(cursor[i]))
                alternatives.append('('+' AND '.join(terms)+')')
            where+=' AND ('+' OR '.join(alternatives)+')'
        fields=','.join(contract.col(key,name)+' AS '+name for name in columns)
        empty_flags={name:'RESET_EMPTY_'+str(i) for i,(name,c) in enumerate(columns.items()) if c['type']=='CLOB'}
        for name,alias in empty_flags.items():
            column=contract.col(key,name)
            fields+=',CASE WHEN '+column+' IS NOT NULL AND DBMS_LOB.GETLENGTH('+column+')=0 THEN 1 ELSE 0 END AS '+alias
        rows=db.query('SELECT '+fields+' FROM '+contract.table(key)+' WHERE '+where+' ORDER BY '+
                      ','.join(contract.col(key,name) for name in keys)+' FETCH FIRST 20 ROWS ONLY',limit=20)
        if not rows:return
        for row in rows:
            for name,alias in empty_flags.items():
                flag=row.pop(alias)
                if flag not in (0,1):raise ValueError('RESET_EMPTY_CLOB_FLAG_INVALID')
                if flag==1:row[name]=''
        contract.validate(key,rows)
        yield rows
        cursor=[rows[-1][name] for name in keys]


def load_backup(path,expected_sha,limit=64*1024**2):
    if raw_sha(path)!=expected_sha:raise ValueError('RESET_BACKUP_HASH_CHANGED')
    with gzip.open(path,'rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('RESET_BACKUP_BATCH_SIZE')
    return json.loads(raw)


def reset_if_needed(loader,package,old_job):
    import dataiku
    contract=loader.Contract(package/'contract.json')
    directory=old_job.parent/('gold-shape-'+contract.sha256[:12])
    if not (directory/'state.json').exists():raise ValueError('RESET_REQUIRES_EXISTING_FAILED_JOB')
    with (directory/'job.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state_path=directory/'state.json';control_path=directory/'reset-r6.json'
        state=loader.read(state_path)
        control=loader.read(control_path) if control_path.exists() else None
        upgrading=bool(control and control.get('reset_code_sha256')!=raw_sha(__file__))
        if upgrading and not r6_upgrade_allowed(control):raise ValueError('RESET_HELPER_CHANGED_OR_R6_ALREADY_DELETING')
        if control and state.get('reset_id')==control['id']:
            if state['binding']!=control['binding']:raise ValueError('RESET_NEW_STATE_BINDING_CHANGED')
            if control['phase'] not in {'DB_CLEARED','STATE_RESET'}:raise ValueError('RESET_PHASE_CONFLICT')
            control['phase']='STATE_RESET';loader.atomic(control_path,control)
            emit('RESET_ALREADY_DONE',detail='새 적재분을 지우지 않고 이어갑니다.')
            return
        if control and control['phase']=='STATE_RESET':raise ValueError('RESET_STATE_MARKER_MISSING')
        if state.get('status') not in {'WRITE_UNCONFIRMED','INITIAL_SOURCE_LOADED','LOADING','FAILED'}:
            raise ValueError('RESET_NOT_INITIAL_SOURCE_STAGE')
        if any(state.get(k) for k in ('query','verify_source','verify_query','publication')) or state.get('verification_finished'):
            raise ValueError('RESET_REFUSED_LATER_STAGE_STATE')
        pending=state.get('pending')
        if pending and (pending.get('section')!='source' or pending.get('table') not in SOURCE_KEYS):
            raise ValueError('RESET_REFUSED_NON_SOURCE_PENDING')
        if (directory/'vectors').exists() and any((directory/'vectors').iterdir()):
            raise ValueError('RESET_REFUSED_VECTOR_HISTORY')
        binding=state['binding']
        if binding['code']!=loader.verify_code() or binding['contract']!=contract.sha256:
            raise ValueError('RESET_CODE_OR_CONTRACT_CHANGED')
        db=loader.Database(dataiku.SQLExecutor2(connection='AIDP'))
        identity=db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
        if identity!=binding['database'] or identity[0]['LOGIN_USER']!='PIDD2APP':raise ValueError('RESET_DATABASE_CHANGED')
        if loader.object_binding(db,contract)!=binding['objects']:raise ValueError('RESET_OBJECT_CHANGED')
        class Progress:
            def emit(self,phase,**fields):emit(phase,**fields)
        root,files,source,query,paths=loader.inputs(old_job,Progress())
        if (str(root)!=binding['generation'] or files!=binding['files'] or loader.digest(source)!=binding['source_release'] or loader.digest(query)!=binding['query_release']):
            raise ValueError('RESET_SOURCE_BINDING_CHANGED')
        version=source['dataset_version']
        limits=source_limits(source)
        from gold_io import literal
        for key in SOURCE_KEYS:
            contract.preflight(db,key)
            t=contract.tables[key]
            foreign=db.query("SELECT c.OWNER,c.TABLE_NAME,c.CONSTRAINT_NAME FROM ALL_CONSTRAINTS c JOIN ALL_CONSTRAINTS p ON p.OWNER=c.R_OWNER AND p.CONSTRAINT_NAME=c.R_CONSTRAINT_NAME WHERE c.CONSTRAINT_TYPE='R' AND c.STATUS='ENABLED' AND p.OWNER="+literal(t['owner'])+' AND p.TABLE_NAME='+literal(t['name']))
            if foreign:raise ValueError('RESET_REFUSED_INBOUND_FOREIGN_KEY:'+contract.table(key))
        zero_publications(db,contract,binding)
        loader.resource_check(directory)
        state_hash=raw_sha(state_path)
        if control:
            if control['binding']!=binding or control['old_state_sha256']!=state_hash:raise ValueError('RESET_ORIGINAL_STATE_CHANGED')
            backup_root=directory/'reset-backups'/control['id']
            if raw_sha(backup_root/'old-state.json')!=state_hash:raise ValueError('RESET_STATE_BACKUP_CHANGED')
            if upgrading:upgrade_controller(loader,control_path,control,backup_root)
        else:
            identifier=uuid.uuid4().hex
            backup_root=directory/'reset-backups'/identifier;backup_root.mkdir(parents=True)
            original=state_path.read_bytes()
            with (backup_root/'old-state.json').open('xb') as stream:
                stream.write(original);stream.flush();os.fsync(stream.fileno())
            sync_dir(backup_root);sync_dir(backup_root.parent);sync_dir(directory)
            if raw_sha(backup_root/'old-state.json')!=state_hash:raise ValueError('RESET_STATE_BACKUP_FAILED')
            control={'schema':'gold-source-reset-r7','id':identifier,'binding':binding,'old_state_sha256':state_hash,
                     'phase':'BACKING_UP','created_at':time.time(),'original_deadline':state.get('deadline'),
                     'reset_code_sha256':raw_sha(__file__)}
            loader.atomic(control_path,control)
        if control['phase']=='BACKING_UP':
            counts={key:source_count(db,contract,key,version) for key in SOURCE_KEYS}
            emit('RESET_SCOPE',tables={contract.table(k):n for k,n in counts.items()},
                 source_limits={contract.table(k):n for k,n in limits.items()},dataset_version=version,backup=str(backup_root))
            for key,count in counts.items():
                if count>limits[key]:
                    raise ValueError('RESET_COUNT_EXCEEDS_BOUND_SOURCE:'+contract.table(key)+
                                     ':actual='+str(count)+':expected_max='+str(limits[key]))
            attempt=backup_root/('snapshot-'+uuid.uuid4().hex);attempt.mkdir()
            batches=[];total_bytes=0
            for key in SOURCE_KEYS:
                seen=0
                for rows in backup_batches(source_batches(db,contract,key,version),loader.canonical):
                    loader.resource_check(directory)
                    payload=loader.canonical(rows).encode();total_bytes+=len(payload)
                    if len(payload)>64*1024**2:raise ValueError('RESET_SINGLE_ROW_EXCEEDS_64MIB_BACKUP_FORMAT:'+contract.table(key))
                    name=key+'-'+str(len(batches)).zfill(6)+'.json.gz';path=attempt/name
                    with path.open('xb') as raw:
                        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as compressed:compressed.write(payload)
                        raw.flush();os.fsync(raw.fileno())
                    checksum=raw_sha(path)
                    restored=load_backup(path,checksum)
                    if loader.digest(restored)!=loader.digest(rows):raise ValueError('RESET_BACKUP_RESTORE_MISMATCH')
                    sql,binds=contract.batch(key,restored,verify_only=True);db.block(sql,binds,rollback=True)
                    batches.append({'key':key,'path':str(path.relative_to(backup_root)),'sha256':checksum,'rows':len(rows)})
                    seen+=len(rows)
                    emit('RESET_BACKUP',table=contract.table(key),rows=seen,total=counts[key])
                if seen!=counts[key] or source_count(db,contract,key,version)!=seen:raise ValueError('RESET_SNAPSHOT_COUNT_CHANGED')
            manifest={'binding':binding,'version':version,'counts':counts,'bytes':total_bytes,'batches':batches}
            sync_dir(attempt)
            loader.atomic(backup_root/'manifest.json',manifest)
            control.update(phase='PREPARED',manifest_sha256=raw_sha(backup_root/'manifest.json'))
            loader.atomic(control_path,control)
        if raw_sha(backup_root/'manifest.json')!=control['manifest_sha256']:raise ValueError('RESET_MANIFEST_CHANGED')
        manifest=loader.read(backup_root/'manifest.json')
        if manifest['binding']!=binding or manifest['version']!=version:raise ValueError('RESET_BACKUP_BINDING_CHANGED')
        # Validate the complete retained backup before the first/resumed deletion.
        for entry in manifest['batches']:
            path=(backup_root/entry['path']).resolve()
            if backup_root.resolve() not in path.parents:raise ValueError('RESET_BACKUP_PATH')
            rows=load_backup(path,entry['sha256'])
            if (entry['key'] not in SOURCE_KEYS or len(rows)!=entry['rows'] or
                any(r['MNFST_HASH_VALU']!=version for r in rows)):
                raise ValueError('RESET_BACKUP_SCOPE')
        if control['phase'] in {'PREPARED','DELETING'}:
            control['phase']='DELETING';loader.atomic(control_path,control)
            for index,entry in enumerate(manifest['batches']):
                loader.resource_check(directory)
                if raw_sha(state_path)!=state_hash:raise ValueError('RESET_STATE_CHANGED_DURING_DELETE')
                path=(backup_root/entry['path']).resolve()
                if backup_root.resolve() not in path.parents:raise ValueError('RESET_BACKUP_PATH')
                rows=load_backup(path,entry['sha256'])
                if len(rows)!=entry['rows'] or entry['key'] not in SOURCE_KEYS or any(r['MNFST_HASH_VALU']!=version for r in rows):
                    raise ValueError('RESET_BACKUP_SCOPE')
                sql,binds=delete_sql(contract,entry['key'],rows,binding)
                db.block(sql,binds)
                # Re-running an unacknowledged committed batch sees absent PKs and removes nothing.
                control['last_confirmed_batch']=index;loader.atomic(control_path,control)
                emit('RESET_DELETE_CONFIRMED',table=contract.table(entry['key']),batch=index+1,total_batches=len(manifest['batches']))
            zero_publications(db,contract,binding)
            if any(source_count(db,contract,key,version)!=0 for key in SOURCE_KEYS):
                raise ValueError('RESET_UNBACKED_ROWS_REMAIN')
            control['phase']='DB_CLEARED';loader.atomic(control_path,control)
        if control['phase']!='DB_CLEARED':raise ValueError('RESET_PHASE_UNKNOWN')
        zero_publications(db,contract,binding)
        if any(source_count(db,contract,key,version)!=0 for key in SOURCE_KEYS):raise ValueError('RESET_ROWS_APPEARED_AFTER_CLEAR')
        if raw_sha(state_path)!=state_hash:raise ValueError('RESET_STATE_CHANGED_BEFORE_RESTART')
        now=time.time()
        fresh={'binding':binding,'status':'NEW','deadline':now+7*86400,'source':{},'query':{},'verify_source':{},
               'verify_query':{},'pending':None,'phase':'NEW','reset_id':control['id'],'reset_at':now,
               'reset_parent_state_sha256':state_hash}
        loader.atomic(state_path,fresh)
        control.update(phase='STATE_RESET',new_deadline=fresh['deadline']);loader.atomic(control_path,control)
        emit('RESET_COMPLETE',backup=str(backup_root),detail='이번 세대 원문만 비웠습니다. 새 적재를 처음부터 시작합니다.')
