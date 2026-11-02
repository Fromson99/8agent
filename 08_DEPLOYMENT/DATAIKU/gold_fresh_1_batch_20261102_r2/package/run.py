"""Dataiku handoff: schema -> rolled-back INSERT checks -> bound source/query load."""
from contextlib import redirect_stdout
from collections import deque
import fcntl
import hashlib
import io as stdio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'vendor'), str(HERE/'vendor/02_BACKEND')]
from gold_io import Contract, Database, Stop, canonical, digest, error_codes, literal
from legacy_gold_mapping import mapped_source, mapped_query

DEFAULT_OLD_JOB = Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
SOURCE_MAP = {
    'document': ('DOC_VER', 'DATASET_VERSION DOCUMENT_ID NAME SOURCE_ARTIFACT_SHA256 SOURCE_JSON',
                 'MNFST_HASH_VALU DOC_ID DOC_NAME DOC_HASH_VALU DOC_ADDN_IFMN_CTNT'),
    'source_unit': ('DOC_UNIT', 'DATASET_VERSION DOCUMENT_ID UNIT_ID PARENT_ID SOURCE_JSON',
                    'MNFST_HASH_VALU DOC_ID STRC_UNIT_ID UPPR_STRC_UNIT_ID STRC_UNIT_ADDN_IFMN_CTNT'),
    'block_payload': ('DOC_BLK', 'DATASET_VERSION DOCUMENT_ID BLOCK_ID UNIT_ID TEXT SOURCE_ARTIFACT_SHA256 SOURCE_JSON JSON_TEXT_ELIDED',
                      'MNFST_HASH_VALU DOC_ID BODY_SLC_ID STRC_UNIT_ID BODY_CTNT DOC_HASH_VALU BODY_SLC_ADDN_IFMN_CTNT ADD_INFO_TEXT_OMIT_YN'),
}


def read(path, limit=32*1024**2):
    with Path(path).open('rb') as f:
        raw = f.read(limit+1)
    if len(raw)>limit:
        raise Stop('METADATA_LIMIT')
    return json.loads(raw)


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024**2):
            h.update(chunk)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    with temp.open('w', encoding='utf-8') as f:
        f.write(canonical(value)); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_code():
    manifest = read(HERE/'CODE_MANIFEST.json')
    for name, sha in manifest['files'].items():
        path = (HERE/name).resolve()
        if HERE not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise Stop('PACKAGE_HASH_MISMATCH')
    return digest(manifest)


def resource_check(folder):
    usage = shutil.disk_usage(folder)
    if usage.free < max(512*1024**2, usage.total/10):
        raise Stop('DISK_90_PERCENT_OR_LOW_SPACE')
    if Path('/proc/meminfo').exists():
        values = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line}
        if values['MemAvailable'] < max(512*1024, values['MemTotal']/10):
            raise Stop('RAM_90_PERCENT_OR_LOW_SPACE')


class Progress:
    def __init__(self):
        self.phase = 'PREPARING'
        self.details = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)

    def emit(self, phase, **details):
        with self.lock:
            self.phase, self.details = phase, details
            print(canonical({'phase': phase, 'elapsed_s': round(time.monotonic()-self.started), **details}), flush=True)

    def heartbeat(self):
        while not self.stop.wait(15):
            with self.lock:
                print(canonical({'phase': self.phase, 'elapsed_s': round(time.monotonic()-self.started), **self.details}), flush=True)

    def set(self, phase, **details):
        with self.lock:
            self.phase, self.details = phase, details


def source_row(kind, row):
    if kind=='block_payload':
        flag = row['JSON_TEXT_ELIDED']
        if flag is not None and (type(flag) is not int or flag not in (0,1)):
            raise Stop('SOURCE_FLAG')
    return mapped_source(kind,row)


def query_row(release, row):
    from semantic_runtime.oracle_query_catalog import json_body
    if digest({k:v for k,v in row.items() if k!='sha256'}) != row['sha256']:
        raise Stop('QUERY_ROW_HASH')
    json_body(row['value'])  # Preserve the existing logical payload size guard.
    return mapped_query(release,row)


def grouped(iterator, max_rows=5000, max_bytes=2*1024**2):
    batch, size = [], 0
    for row in iterator:
        n = len(canonical(row).encode())
        if batch and (len(batch)>=max_rows or size+n>max_bytes):
            yield batch
            batch, size = [],0
        batch.append(row);size+=n
    if batch:
        yield batch


def resume_api():
    return SimpleNamespace(HERE=HERE, read=read, atomic=atomic, digest=digest,
                           Stop=Stop, query_row=query_row)


class Job:
    def __init__(self, db, contract, directory, binding, progress, retry_missing=False):
        self.db, self.contract, self.directory, self.progress = db,contract,directory,progress
        self.path = directory/'state.json'
        self.retry_missing = retry_missing
        self.state = read(self.path) if self.path.exists() else {
            'binding': binding, 'status':'NEW', 'deadline':time.time()+7*86400,
            'source':{}, 'query':{}, 'verify_source':{}, 'verify_query':{},
            'pending':None, 'phase':'NEW'}
        if self.state['binding'] != binding:
            from batch_resume import migrate
            self.state = migrate(resume_api(), self.path, self.state, binding, progress)
        self.save()

    def save(self):
        atomic(self.path,self.state)

    def guard(self):
        resource_check(self.directory)
        if time.time()>=self.state['deadline']:
            raise Stop('ORIGINAL_DEADLINE_EXPIRED')

    def batch(self,key,rows,next_progress=None,section=None,slot=None,verify_only=False):
        self.guard()
        sql,binds=self.contract.batch(key,rows,verify_only=verify_only)
        marker={'table':key,'rows':len(rows),'sha256':digest(rows),'verify_only':verify_only,
                'section':section,'slot':slot,'next':next_progress}
        pending=self.state.get('pending')
        if pending and pending!=marker:
            raise Stop('PENDING_BATCH_BINDING_MISMATCH')
        if pending and not verify_only:
            verify_sql,verify_binds=self.contract.batch(key,rows,verify_only=True)
            try:
                self.db.block(verify_sql,verify_binds,rollback=True)
            except Exception as exc:
                if 'ORA-20042' not in error_codes(exc) or not self.retry_missing:
                    raise Stop('PENDING_WRITE_REQUIRES_RECONCILIATION:'+','.join(error_codes(exc))) from exc
                # Explicit retry_missing mode only; immutable insert still rejects conflicts.
            else:
                if section:
                    self.state[section][slot]=next_progress
                self.state['pending']=None;self.save()
                return
        self.state['pending']=marker;self.save()
        try:
            seconds=self.db.block(sql,binds,rollback=verify_only)
        except BaseException:
            self.state['status']='WRITE_UNCONFIRMED' if not verify_only else 'VERIFY_FAILED'
            self.save();raise
        if section:
            self.state[section][slot]=next_progress
        self.state['pending']=None
        self.state['status']='LOADING' if not verify_only else 'VERIFYING'
        self.save()
        self.progress.set('VERIFY' if verify_only else 'LOAD',table=self.contract.table(key),
                          batch_rows=len(rows),request_s=round(seconds,2),rows=(next_progress or {}).get('rows'))


def object_binding(db,contract):
    conditions=['(OWNER='+literal(t['owner'])+' AND OBJECT_NAME='+literal(t['name'])+")" for t in contract.tables.values()]
    rows=db.query("SELECT OWNER,OBJECT_NAME,OBJECT_ID,DATA_OBJECT_ID FROM ALL_OBJECTS WHERE OBJECT_TYPE='TABLE' AND ("+
                  ' OR '.join(conditions)+') ORDER BY OWNER,OBJECT_NAME')
    if len(rows)!=len(contract.tables):
        raise Stop('OBJECT_IDENTITY_INCOMPLETE')
    return rows


def inputs(old_job,progress):
    from lawrag.pipeline import oracle_migration as migration, oracle_query_package as pack
    from lawrag.pipeline.oracle_deferred_import import prepared_descriptor
    from strict_resume import source_descriptor
    full=read(old_job/'full-state.json')
    root=Path(full['identity']['generation']).resolve(strict=True)
    if old_job.parent not in root.parents or root.name!='generation':
        raise Stop('INPUT_GENERATION_OUTSIDE_RETAINED_JOB')
    progress.emit('INPUT_HASH_CHECK')
    root,manifest,items,files,selected=pack.immutable_inputs(root)
    db=migration.source_open(root/'store.sqlite')
    try:
        counts=migration.source_counts(db,manifest)
    finally:
        db.close()
    progress.emit('REUSE_PREPARED_DESCRIPTOR')
    # These helpers print only short notices; no full data or old logs are emitted.
    source=source_descriptor(root,manifest,items,files,selected,old_job,full['identity']['target'],counts)
    paths,tables=prepared_descriptor(root,source,files,old_job,strict=True)
    query=pack.query_manifest(root,source,paths,tables,items)
    if full['deferred']['plan']['source_release_id']!=digest(source) or full['deferred']['plan']['query_release_id']!=digest(query):
        raise Stop('PRIOR_DESCRIPTOR_RELEASE_MISMATCH')
    return root,files,source,query,paths


def load_sources(job,root,source,*,initial=False,verify_only=False):
    from lawrag.pipeline import oracle_migration as migration
    from semantic_runtime.oracle_dp_io import KEYS
    binding,_=migration.source_binding(root/'store.sqlite')
    db=migration.source_open(root/'store.sqlite')
    try:
        for kind in SOURCE_MAP:
            section='verify_source' if verify_only else 'source'
            current=job.state[section].get(kind,{'cursor':None,'rows':0,'chain':'0'*64})
            if initial and current['rows']>=1000:
                continue
            while True:
                job.guard();migration.unchanged(binding)
                combined=[];size=0;cursor=current['cursor']
                while len(combined)<1000:
                    part=migration.source_batch(db,kind,source['dataset_version'],cursor,batch_rows=100)
                    if not part:
                        break
                    n=len(canonical(part).encode())
                    if combined and size+n>2*1024**2:
                        break
                    combined.extend(part);size+=n
                    cursor=[part[-1][c] for c in KEYS[kind] if c!='DATASET_VERSION']
                if not combined:
                    break
                key=SOURCE_MAP[kind][0]
                nxt={'cursor':cursor,'rows':current['rows']+len(combined),
                     'chain':migration.extend_chain(current['chain'],combined)}
                job.batch(key,[source_row(kind,r)[1] for r in combined],next_progress=nxt,
                          section=section,slot=kind,verify_only=verify_only)
                current=nxt
                if initial and current['rows']>=1000:
                    break
            if not initial:
                expected=source['source_rows'][kind]
                if current['rows']!=expected['rows'] or current['chain']!=expected['chain']:
                    raise Stop('SOURCE_CHAIN_OR_COUNT:'+kind)
                key=SOURCE_MAP[kind][0]
                actual=job.db.query('SELECT COUNT(*) AS N FROM '+job.contract.table(key)+' WHERE '+
                                    job.contract.col(key,'MNFST_HASH_VALU')+'='+literal(source['dataset_version']))
                if actual!=[{'N':expected['rows']}]:
                    raise Stop('SOURCE_REMOTE_COUNT:'+kind)
            job.progress.emit('SOURCE_CHECKED' if verify_only else 'SOURCE_ACK',table=SOURCE_MAP[kind][0],rows=current['rows'])
    finally:
        db.close()


def load_query(job,root,files,source,query,paths,*,verify_only=False):
    from lawrag.pipeline import oracle_query_publish as pub
    from batch_resume import limits, remaining, restore_pending
    max_rows, max_bytes = limits()
    job.progress.emit('QUERY_BATCH_POLICY', max_rows=max_rows, max_bytes=max_bytes)
    release=digest(query)
    for relative,sha in paths.items():
        path=(root/relative).resolve(strict=True)
        if root not in path.parents or file_hash(path)!=sha:
            raise Stop('QUERY_INPUT_HASH:'+relative)
        section='verify_query' if verify_only else 'query'
        if job.state[section].get(relative,{}).get('complete') is True:
            job.progress.emit('QUERY_FILE_CHECKPOINT_REUSED',asset=relative,verified=verify_only)
            continue
        done=job.state[section].get(relative,{}).get('rows',0)
        iterator=remaining(resume_api(), iter(pub.projected_rows(path,relative,source)), done, job.guard)
        current=restore_pending(resume_api(),job,iterator,section,relative,done,release,verify_only)
        for batch in grouped(iterator,max_rows=max_rows,max_bytes=max_bytes):
            job.guard()
            through=current+len(batch)
            values=[query_row(release,row) for row in batch]
            job.batch('SRCH_ROW',values,next_progress={'rows':through},section=section,
                      slot=relative,verify_only=verify_only)
            current=through
        if current<done:
            raise Stop('QUERY_CURSOR_EXCEEDS_INPUT')
        if file_hash(path)!=sha:
            raise Stop('QUERY_INPUT_CHANGED:'+relative)
        job.state[section][relative]={'rows':current,'complete':True};job.save()
        job.progress.emit('QUERY_FILE_CHECKED' if verify_only else 'QUERY_FILE_ACK',asset=relative,rows=current)
    expected=sum(t['rows'] for t in query['tables'].values())
    actual=job.db.query('SELECT COUNT(*) AS N FROM '+job.contract.table('SRCH_ROW')+' WHERE '+
                        job.contract.col('SRCH_ROW','RFRN_POST_HASH_VALU')+'='+literal(release))
    if actual!=[{'N':expected}]:
        raise Stop('QUERY_REMOTE_COUNT')


def publish(job,root,files,source,query):
    from lawrag.pipeline.oracle_query_package import immutable_inputs
    if immutable_inputs(root)[3]!=files:
        raise Stop('FINAL_SOURCE_CHANGED')
    # A dedicated test channel is immutable per dataset; no existing service pointer is updated.
    channel='g19_'+digest(query)[:24]
    rows=[('SRC_POST',{'DOC_POST_HASH_VALU':digest(source),'MNFST_HASH_VALU':source['dataset_version'],
                      'DOC_POST_IFMN_CTNT':canonical(source)}),
          ('SRCH_POST',{'RFRN_POST_HASH_VALU':digest(query),'RFRN_POST_IFMN_CTNT':canonical(query)}),
          ('SRCH_CHNL',{'RFRN_CHNL_NAME':channel,'RFRN_POST_HASH_VALU':digest(query),'CHAN_NO':1})]
    published=job.state.setdefault('publication',{})
    for key,row in rows:
        if key not in published:
            job.batch(key,[row],next_progress={'rows':1},section='publication',slot=key)
    job.state.update(status='SOURCE_QUERY_VERIFIED',source_release_id=digest(source),query_release_id=digest(query),test_channel=channel)
    job.save()
    job.progress.emit('SOURCE_QUERY_VERIFIED',channel=channel,query_release_id=digest(query),
                      ontology='NO_APPROVED_INPUT_SUPPLIED',vector='EMBEDDING_NOT_RUN',serving='NOT_SWITCHED')


def run(action='start',old_job=None,retry_missing=False):
    from batch_resume import limits
    limits()  # Reject invalid tuning before opening a connection or writing anything.
    if action not in {'start','load','verify_publish'}:
        raise Stop('ACTION')
    code_hash=verify_code()
    old_job=Path(old_job or DEFAULT_OLD_JOB).resolve(strict=True)
    # Existing code/data and old failed receipts stay immutable.
    contract=Contract(HERE/'contract.json')
    directory=old_job.parent/('gold-shape-'+contract.sha256[:12])
    directory.mkdir(exist_ok=True)
    progress=Progress();progress.thread.start()
    job=None
    with (directory/'job.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            resource_check(directory)
            import dataiku
            db=Database(dataiku.SQLExecutor2(connection='AIDP'))
            identity=db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            if len(identity)!=1 or identity[0]['LOGIN_USER']!='PIDD2APP':
                raise Stop('EXPECTED_PIDD2APP_CONNECTION')
            progress.emit('TARGET_CONNECTED',user=identity[0]['LOGIN_USER'])
            contract.create(db,progress.emit)
            for key in contract.tables:
                progress.emit('INSERT_ROLLBACK_CHECK',table=contract.table(key))
                seconds=contract.probe(db,key)
                progress.emit('INSERT_ROLLBACK_PASS',table=contract.table(key),seconds=round(seconds,2))
            progress.emit('INSERT_GATE_PASS',tables=len(contract.tables),warning='작은 INSERT 성공은 대량 적재 공간 보장이 아님')
            if not (directory/'state.json').exists():
                # A new _1 run must start on empty targets. Reruns use this
                # contract's own checkpoint and never reset populated tables.
                for key in contract.tables:
                    if db.query('SELECT COUNT(*) AS N FROM '+contract.table(key)) != [{'N':0}]:
                        raise Stop('NEW_SUFFIX_TABLE_ALREADY_HAS_ROWS:'+contract.table(key))
                progress.emit('NEW_SUFFIX_EMPTY_TARGETS',tables=len(contract.tables),suffix='_1')
            root,files,source,query,paths=inputs(old_job,progress)
            binding={'code':code_hash,'contract':contract.sha256,'database':identity,'objects':object_binding(db,contract),
                     'generation':str(root),'files':files,'source_release':digest(source),'query_release':digest(query)}
            job=Job(db,contract,directory,binding,progress,retry_missing=retry_missing)
            if job.state['status']=='SOURCE_QUERY_VERIFIED':
                progress.emit('ALREADY_VERIFIED_RECORD',current_database_reverified=False)
                return
            if action=='start' and job.state['status']=='LOADED_UNVERIFIED':
                progress.emit('ALREADY_LOADED_UNVERIFIED',next_action='verify_publish')
                return
            if action=='start' and job.state.get('pending'):
                raise Stop('PENDING_BATCH_USE_SAME_LOAD_OR_VERIFY_ACTION')
            if action=='verify_publish' and job.state['status'] not in {'LOADED_UNVERIFIED','VERIFYING','VERIFY_FAILED','WRITE_UNCONFIRMED','SOURCE_QUERY_VERIFIED'}:
                raise Stop('LOAD_FIRST')
            if action=='verify_publish' and job.state.get('verification_finished'):
                publish(job,root,files,source,query)
                return
            load_sources(job,root,source,initial=action=='start',verify_only=action=='verify_publish')
            if action=='start':
                job.state['status']='INITIAL_SOURCE_LOADED';job.save()
                progress.emit('INITIAL_SOURCE_LOADED',counts={k:v['rows'] for k,v in job.state['source'].items()},next_action='load',full_load=False)
                return
            load_query(job,root,files,source,query,paths,verify_only=action=='verify_publish')
            if action=='load':
                job.state['status']='LOADED_UNVERIFIED';job.save()
                progress.emit('LOADED_UNVERIFIED',next_action='verify_publish',published=False)
            else:
                job.state['verification_finished']=True;job.save()
                publish(job,root,files,source,query)
        except BaseException as exc:
            if job:
                job.state['last_error']={'type':type(exc).__name__,'codes':error_codes(exc),'phase':progress.phase,'time':time.time()}
                if job.state.get('pending'):
                    job.state['status']='WRITE_UNCONFIRMED'
                job.save()
            progress.emit('STOPPED',error_type=type(exc).__name__,codes=error_codes(exc),
                          detail=str(exc)[:180] if isinstance(exc,Stop) else '상세 원인은 ORA/PLS 코드와 해당 단계로 확인',
                          next_action='후속 셀 실행 중지 · 현재 화면 캡처')
            raise
        finally:
            progress.stop.set();progress.thread.join(timeout=2)


if __name__=='__main__':
    try:
        run(sys.argv[1] if len(sys.argv)>1 else 'start',os.environ.get('G19_OLD_JOB_DIR'),
            retry_missing=os.environ.get('G19_RETRY_MISSING')=='1')
    except BaseException as exc:
        print(canonical({'phase':'EXECUTION_FAILED','error_type':type(exc).__name__,
                         'codes':error_codes(exc),'detail':str(exc)[:180] if isinstance(exc,(Stop,FileNotFoundError)) else '위 단계와 오류 코드를 확인하세요.'}),flush=True)
        sys.exit(1)
