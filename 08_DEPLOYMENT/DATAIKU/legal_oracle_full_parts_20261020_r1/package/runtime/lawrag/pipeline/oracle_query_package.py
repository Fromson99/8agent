"""Offline query-row transport. Reuses the maintained projection and Oracle writer.

A SQLite DB is a transport container only. No serving data or pointer is changed.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid
import zipfile

from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q
from . import oracle_query_publish as pub, oracle_migration as migration

FORMAT = 'oracle-query-transport-v1'
CHUNK_BYTES = 49_000_000
DB_NAME = 'query-data.db'


def event(folder, status, **fields):
    with (Path(folder)/'events.jsonl').open('a', encoding='utf-8') as f:
        f.write(io.canonical({'at':time.time(),'status':status,**fields})+'\n')
        f.flush(); os.fsync(f.fileno())
    print(status, io.canonical(fields), flush=True)


@contextmanager
def job(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with (folder/'job.lock').open('a') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise io.DPError('IN_PROGRESS: this output is already in use') from None
        try:
            yield folder
        except BaseException as exc:
            status='PAUSED' if isinstance(exc,io.BudgetPause) else 'INTERRUPTED' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'FAILED'
            event(folder,status,error_type=type(exc).__name__,error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            raise


def resources(folder):
    free=shutil.disk_usage(folder).free
    if free<512*1024**2:raise io.BudgetPause('DISK_LOW: preserve files; free at least 512MiB before resuming')
    if Path('/proc/meminfo').exists():
        avail=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'))
        if avail<512*1024**2:raise io.BudgetPause('RAM_LOW: preserve files; stop other heavy jobs before resuming')
    return free


def bounded_json(path, maximum=32*1024**2):
    path=Path(path)
    if path.stat().st_size>maximum:raise io.DPError('METADATA_SIZE: oversized metadata')
    return json.loads(path.read_text(encoding='utf-8'))


def immutable_inputs(generation):
    root=Path(generation).resolve(strict=True)
    migration.source_binding(root/'store.sqlite')
    manifest,items=assets.inventory(root)
    files={'store.sqlite':manifest['store_sha256'],'manifest.json':io.file_sha(root/'manifest.json'),
           **{a['path']:a['sha256'] for a in items}}
    for relative,sha in files.items():
        path=assets.checked_path(root,relative)
        if relative.endswith('.sqlite'):
            for suffix in ('-wal','-journal'):
                side=Path(str(path)+suffix)
                if side.exists() and side.stat().st_size:raise io.DPError('SOURCE_MUTABLE: '+relative)
        if io.file_sha(path)!=sha:raise io.DPError('SOURCE_HASH: '+relative)
    selection=root.parent/'SEARCH_SELECTION'/(root.name+'.json')
    selected=bounded_json(selection) if selection.exists() else None
    if selected and (selected['store_sha256']!=manifest['store_sha256'] or selected['manifest_sha256']!=files['manifest.json']):
        raise io.DPError('SELECTION_BINDING: source selection differs')
    return root,manifest,items,files,selected


def offline_source(root,manifest,items,selected,tick=lambda:None):
    """Same deterministic descriptor as oracle_publish, checked against Oracle at import.

    This computes the expected release ID; it is NOT evidence that Oracle has it.
    """
    version=io.file_sha(root/'manifest.json');rows={}
    db=migration.source_open(root/'store.sqlite')
    try:
        migration.source_counts(db,manifest)
        for kind in io.TABLES:
            cursor=None;count=0;chain='0'*64
            while batch:=migration.source_batch(db,kind,version,cursor):
                tick();count+=len(batch);chain=migration.extend_chain(chain,batch)
                cursor=[batch[-1][k] for k in io.KEYS[kind] if k!='DATASET_VERSION']
            rows[kind]={'rows':count,'chain':chain}
    finally:db.close()
    return {'schema_version':assets.SCHEMA,'status':'COMPLETE','dataset_version':version,
            'source_manifest':manifest,'source_manifest_text':(root/'manifest.json').read_text(),
            'source_rows':rows,'assets':items,'search_selection':selected,
            'codec':'zlib-per-1MiB-part-v1','source_projection':'compact-source-v2-logical-rows-v1'}


def query_manifest(root,source,paths,tables,items):
    from . import oracle_query_navigation_publish
    from semantic_runtime import navigation_match,structure_navigation,inherited_navigation
    return {'schema_version':q.SCHEMA,'status':'COMPLETE','source_release_id':io.digest(source),
            'dataset_version':source['dataset_version'],'source_manifest':source['source_manifest'],
            'search_selection':source.get('search_selection'),'assets':paths,'tables':tables,
            'projection':'sqlite-logical-rows-and-fts5-positions-v1','metadata':pub.asset_metadata(root,items),
            'selection_proof':pub.selection_proof(root,source['source_manifest']),
            'publisher_sha256':io.file_sha(pub.__file__),
            'navigation_compilers':{m.__name__:io.file_sha(m.__file__) for m in
                                   (oracle_query_navigation_publish,navigation_match,structure_navigation,inherited_navigation)}}


def export(generation,output,*,seconds=21600,chunk_bytes=CHUNK_BYTES):
    """Resume by reconciling deterministic row sequence; no input file is modified."""
    if not 1<=seconds<=21600:raise io.DPError('BUDGET: seconds must be 1..21600')
    with job(output) as folder:
        resources(folder);event(folder,'INSPECTING_SOURCE',generation=str(generation))
        root,manifest,items,files,selected=immutable_inputs(generation)
        if folder.resolve().is_relative_to(root):raise io.DPError('OUTPUT_INSIDE_SOURCE: choose a separate workspace folder')
        identity={'generation':str(root),'files':files,'selection':io.digest(selected),
                  'transport_code':io.file_sha(__file__),'publisher_code':io.file_sha(pub.__file__)}
        state_path=folder/'export-state.json'
        state=bounded_json(state_path) if state_path.exists() else {'identity':identity,'deadline':time.time()+7*86400,'status':'NEW'}
        if state['identity']!=identity:raise io.DPError('EXPORT_BINDING: inputs/code differ; preserve the old output')
        io.atomic_json(state_path,state)
        end=min(time.time()+seconds,state['deadline']);last=[0.0]
        def tick():
            if time.time()>end:raise io.BudgetPause('EXPORT_BUDGET: rerun same command; original deadline retained')
            if time.time()-last[0]>15:
                resources(folder);last[0]=time.time();event(folder,'EXPORT_RUNNING')
        source=offline_source(root,manifest,items,selected,tick)
        source_id=io.digest(source)
        dbpath=folder/DB_NAME
        if dbpath.exists():
            verified=verify_db(dbpath)
            if verified['source_release']!=source:raise io.DPError('EXPORT_BINDING: completed DB differs')
        else:
            partial=folder/(DB_NAME+'.partial')
            db=sqlite3.connect(partial)
            try:
                db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA cache_size=-16384');db.execute('PRAGMA temp_store=FILE')
                db.execute('CREATE TABLE IF NOT EXISTS query_row(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,row_id TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(kind,row_id))')
                db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,body TEXT NOT NULL)');db.commit()
                paths={'store.sqlite':manifest['store_sha256'],**{a['path']:a['sha256'] for a in items if a['path'].endswith('.sqlite')}}
                tables={};sequence=0
                for relative,sha in paths.items():
                    tick();event(folder,'PROJECTING',asset=relative)
                    path=assets.checked_path(root,relative)
                    if relative!='store.sqlite':tables.update(pub.asset_schema(path,relative))
                    for row in pub.projected_rows(path,relative,source):
                        tick();sequence+=1;body=q.json_body(row)
                        old=db.execute('SELECT kind,row_id,body FROM query_row WHERE seq=?',(sequence,)).fetchone()
                        if old is not None:
                            if old!=(row['kind'],row['row_id'],body):raise io.DPError('EXPORT_RESUME_CONFLICT: stored row differs')
                        else:db.execute('INSERT INTO query_row VALUES(?,?,?,?)',(sequence,row['kind'],row['row_id'],body))
                        s=tables.setdefault(row['kind'],{'asset':relative,'rows':0,'chain':'0'*64})
                        s['rows']+=1;s['chain']=io.digest([s['chain'],row['row_id'],row['sha256']]);pub._column_shapes(s,row['value'])
                        if sequence%1000==0:db.commit();event(folder,'ROWS_SAVED',rows=sequence)
                    db.commit()
                    if io.file_sha(path)!=sha:raise io.DPError('SOURCE_CHANGED: '+relative)
                if db.execute('SELECT COUNT(*) FROM query_row').fetchone()[0]!=sequence:raise io.DPError('EXPORT_EXTRA_ROWS: previous partial data differs')
                value=query_manifest(root,source,paths,tables,items)
                _,_,_,after,selection_after=immutable_inputs(root)
                if after!=files or selected!=selection_after:raise io.DPError('SOURCE_CHANGED: source/selection changed while exporting')
                for key,obj in {'format':FORMAT,'source_release':source,'query_manifest':value}.items():
                    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,io.canonical(obj)))
                db.commit()
            finally:db.close()
            verify_db(partial)
            os.rename(partial,dbpath)
        result=split_db(dbpath,folder,chunk_bytes=chunk_bytes)
        state.update(status='COMPLETE',source_release_id=source_id,**result);io.atomic_json(state_path,state)
        event(folder,'EXPORT_COMPLETE',**result)
        return result


def row_stream(db):
    for seq,kind,rid,body in db.execute('SELECT seq,kind,row_id,body FROM query_row ORDER BY seq'):
        if len(body)>q.MAX_JSON_BYTES:raise io.DPError('ROW_SIZE: transport row exceeds bound')
        row=json.loads(body)
        if set(row)!={'kind','row_id','document_id','lookup_id','owner_id','target_id','value','sha256'}:raise io.DPError('ROW_SHAPE: unexpected fields')
        if kind!=row['kind'] or rid!=row['row_id'] or io.digest({k:v for k,v in row.items() if k!='sha256'})!=q.pin(row['sha256']):
            raise io.DPError('ROW_HASH: row envelope differs')
        # Reuse field validation without assuming the original unhashed key is present.
        q.record(kind,row['value'],key=None,**{k:row[k] for k in ('document_id','lookup_id','owner_id','target_id')});q.pin(rid)
        yield seq,row


def verify_db(path):
    path=Path(path).resolve(strict=True)
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('PRAGMA cache_size=-16384');db.execute('PRAGMA temp_store=FILE')
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise io.DPError('DB_INTEGRITY: failed')
        objects={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if objects!={'metadata','query_row'}:raise io.DPError('DB_OBJECTS: unexpected transport tables/views')
        meta={k:json.loads(v) for k,v in db.execute('SELECT key,body FROM metadata')}
        if meta.get('format')!=FORMAT or set(meta)!={'format','source_release','query_manifest'}:raise io.DPError('DB_FORMAT: incomplete transport DB')
        source=meta['source_release'];value=meta['query_manifest']
        if (source.get('schema_version')!=assets.SCHEMA or source.get('status')!='COMPLETE'
                or hashlib.sha256(source['source_manifest_text'].encode()).hexdigest()!=source['dataset_version']
                or json.loads(source['source_manifest_text'])!=source['source_manifest']):
            raise io.DPError('SOURCE_DESCRIPTOR: inconsistent source manifest')
        if (value['schema_version']!=q.SCHEMA or value['status']!='COMPLETE' or value['source_release_id']!=io.digest(source)
                or value['dataset_version']!=source['dataset_version'] or value['source_manifest']!=source['source_manifest']):
            raise io.DPError('DB_BINDING: query/source release differ')
        tables={k:{'rows':0,'chain':'0'*64} for k in value['tables']};last=0
        for seq,row in row_stream(db):
            if seq!=last+1 or row['kind'] not in tables:raise io.DPError('DB_SEQUENCE: missing/extra row kind')
            last=seq;s=tables[row['kind']];s['rows']+=1;s['chain']=io.digest([s['chain'],row['row_id'],row['sha256']])
        if any(s!={k:value['tables'][kind][k] for k in ('rows','chain')} for kind,s in tables.items()):
            raise io.DPError('DB_CHAIN: row counts or content chain differ')
        return meta
    finally:db.close()


def split_db(dbpath,folder,*,chunk_bytes=CHUNK_BYTES):
    if not 1<=chunk_bytes<=CHUNK_BYTES:raise io.DPError('PART_SIZE: must be <=49000000 bytes')
    folder=Path(folder);archive=folder/'query-data.zip';dbpath=Path(dbpath)
    dbsha=io.file_sha(dbpath)
    if not archive.exists():
        tmp=folder/('query-data.zip.partial-'+uuid.uuid4().hex)
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            z.write(dbpath,DB_NAME)
        os.rename(tmp,archive)
    # Re-read the member to detect stale/mutated completed archives.
    with zipfile.ZipFile(archive) as z:
        if z.namelist()!=[DB_NAME]:raise io.DPError('ZIP_MEMBERS: unexpected members')
        with z.open(DB_NAME) as f:
            h=hashlib.sha256()
            while block:=f.read(1024**2):h.update(block)
            if h.hexdigest()!=dbsha:raise io.DPError('ZIP_HASH: archive does not match DB')
    parts=folder/'download';parts.mkdir(exist_ok=True);entries=[];whole=hashlib.sha256();idx=0
    with archive.open('rb') as f:
        while True:
            first=f.read(min(1024**2,chunk_bytes))
            if not first:break
            idx+=1;name=f'query-data.zip.part{idx:06d}';target=parts/name
            resources(folder)
            temp=folder/(name+'.partial-'+uuid.uuid4().hex);h=hashlib.sha256();count=0
            with temp.open('wb') as out:
                block=first
                while block:
                    out.write(block);h.update(block);whole.update(block);count+=len(block)
                    if count==chunk_bytes:break
                    block=f.read(min(1024**2,chunk_bytes-count))
                out.flush();os.fsync(out.fileno())
            sha=h.hexdigest()
            if target.exists():
                if target.stat().st_size!=count or io.file_sha(target)!=sha:raise io.DPError('PART_CONFLICT: preserve existing part '+name)
                temp.unlink()  # Verified regenerated duplicate only.
            else:os.rename(temp,target)
            entries.append({'name':name,'bytes':count,'sha256':sha})
    value={'format':FORMAT,'archive':'query-data.zip','archive_bytes':archive.stat().st_size,
           'archive_sha256':whole.hexdigest(),'db_bytes':dbpath.stat().st_size,'db_sha256':dbsha,'parts':entries}
    if io.file_sha(archive)!=whole.hexdigest():raise io.DPError('ZIP_CHANGED: source archive changed during split')
    io.atomic_json(parts/'parts-manifest.json',value)
    return {'download_dir':str(parts.resolve()),'parts':len(entries),'archive_bytes':value['archive_bytes'],
            'db_sha256':dbsha,'query_release_id':io.digest(verify_db(dbpath)['query_manifest'])}


def restore(parts,output):
    """Strict order/size/hash verification. No byte trimming or unverified extractall."""
    parts=Path(parts);info=bounded_json(parts/'parts-manifest.json')
    if info.get('format')!=FORMAT or info.get('archive')!='query-data.zip':raise io.DPError('PART_FORMAT: unknown manifest')
    q.pin(info['archive_sha256']);q.pin(info['db_sha256'])
    entries=info['parts']
    if not isinstance(entries,list) or not 1<=len(entries)<=100000:raise io.DPError('PART_LIST: invalid parts')
    names=[x['name'] for x in entries]
    if names!=[f'query-data.zip.part{i:06d}' for i in range(1,len(entries)+1)]:raise io.DPError('PART_ORDER: invalid or duplicate part names')
    if set(p.name for p in parts.glob('query-data.zip.part*') if not p.name.endswith('.partial'))!=set(names):raise io.DPError('PART_SET: missing or extra parts')
    if sum(x['bytes'] for x in entries)!=info['archive_bytes']:raise io.DPError('PART_SIZE: total differs')
    with job(output) as folder:
        if resources(folder)<info['archive_bytes']+info['db_bytes']+512*1024**2:raise io.BudgetPause('DISK_LOW: need ZIP + extracted DB + 512MiB free')
        final=folder/DB_NAME
        if final.exists():
            if io.file_sha(final)!=info['db_sha256']:raise io.DPError('RESTORE_CONFLICT: existing DB differs')
            verify_db(final);return str(final)
        attempt=uuid.uuid4().hex;archive=folder/('query-data.zip.partial-'+attempt);total=hashlib.sha256()
        with archive.open('xb') as out:
            for entry in entries:
                path=parts/entry['name'];q.pin(entry['sha256'])
                if path.is_symlink() or not path.is_file() or not 0<entry['bytes']<=CHUNK_BYTES or path.stat().st_size!=entry['bytes']:
                    raise io.DPError('PART_SIZE: missing/changed part '+entry['name'])
                h=hashlib.sha256()
                with path.open('rb') as f:
                    while block:=f.read(1024**2):h.update(block);total.update(block);out.write(block)
                if h.hexdigest()!=entry['sha256']:raise io.DPError('PART_HASH: '+entry['name'])
                event(folder,'PART_VERIFIED',part=entry['name'])
            out.flush();os.fsync(out.fileno())
        if total.hexdigest()!=info['archive_sha256']:raise io.DPError('ARCHIVE_HASH: joined ZIP differs')
        temporary=folder/(DB_NAME+'.partial-'+attempt);h=hashlib.sha256()
        with zipfile.ZipFile(archive) as z:
            if z.namelist()!=[DB_NAME] or z.getinfo(DB_NAME).file_size!=info['db_bytes']:raise io.DPError('ZIP_MEMBERS: only the declared DB is allowed')
            with z.open(DB_NAME) as src,temporary.open('xb') as dst:
                count=0
                while block:=src.read(1024**2):
                    count+=len(block)
                    if count>info['db_bytes']:raise io.DPError('DB_SIZE: decompressed size exceeds declaration')
                    h.update(block);dst.write(block)
                dst.flush();os.fsync(dst.fileno())
        if h.hexdigest()!=info['db_sha256']:raise io.DPError('DB_HASH: restored DB differs')
        meta=verify_db(temporary);os.rename(temporary,final)
        archive.rename(folder/('verified-query-data-'+attempt+'.zip'))
        io.atomic_json(folder/'restore-receipt.json',{'status':'VERIFIED','db_sha256':info['db_sha256'],'query_release_id':io.digest(meta['query_manifest'])})
        return str(final)


def import_db(client,dbpath,*,target_binding,directory,action='check',seconds=3600):
    if action not in {'check','publish','status'}:raise io.DPError('ACTION: check / publish / status')
    if not 1<=seconds<=21600:raise io.DPError('BUDGET: seconds must be 1..21600')
    dbpath=Path(dbpath).resolve(strict=True)
    meta=verify_db(dbpath);value=meta['query_manifest'];rid=io.digest(value);sha=io.file_sha(dbpath)
    with job(directory) as folder:
        resources(folder)
        identity={'target_binding':target_binding,'source_release_id':value['source_release_id'],
                  'query_release_id':rid,'db_sha256':sha}
        receipt=folder/'state.json'
        state=bounded_json(receipt) if receipt.exists() else {'identity':identity,'deadline':time.time()+7*86400,'status':'NEW'}
        if state['identity']!=identity:raise io.DPError('IMPORT_BINDING: source, package or target changed; preserve the prior log')
        io.atomic_json(receipt,state)
        sql=io.SQL(client,journal=folder/'calls.jsonl',binding=io.digest(identity),seconds=max(0,min(seconds,state['deadline']-time.time())))
        try:
            if assets.get_release(sql,value['source_release_id'])!=meta['source_release']:raise io.DPError('SOURCE_RELEASE: Oracle source is not this generation')
            checked=pub.schema(sql,create=False)
            if checked['status']!='READY':raise io.DPError('QUERY_SCHEMA: missing query tables/indexes '+str(checked.get('missing')))
            if action=='check':
                return {'status':'READY_TO_IMPORT','source_release_id':value['source_release_id'],'release_id':rid,'rows':sum(x['rows'] for x in value['tables'].values()),'active_changed':False}
            if action=='status':
                if state['status']!='COMPLETE' or q.read_release(sql,rid)!=value:raise io.DPError('IMPORT_NOT_COMPLETE: publish and full readback required')
            else:
                state.update(status='UPLOADING',verified_rows=0);io.atomic_json(receipt,state)
            db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
            try:
                batch=[];size=0;verified=0;last=0.0
                def flush():
                    nonlocal verified,last
                    if not batch:return
                    if action=='publish':q.insert_records(sql,rid,batch)
                    pub._verify_batch(sql,rid,batch);verified+=len(batch)
                    state['verified_rows']=verified;io.atomic_json(receipt,state)
                    if time.monotonic()-last>15:
                        resources(folder);last=time.monotonic();event(folder,'ORACLE_ROWS_VERIFIED',rows=verified)
                for _,row in row_stream(db):
                    length=len(q.json_body(row))
                    if batch and (len(batch)>=20 or size+length>4*1024**2):flush();batch=[];size=0
                    batch.append(row);size+=length
                flush()
            finally:db.close()
            for kind,spec in value['tables'].items():
                actual=sql.query(f'SELECT COUNT(*) AS N FROM {q.ROW} WHERE RELEASE_ID=:release AND KIND=:kind',
                                 [('release',rid,'VARCHAR2'),('kind',kind,'VARCHAR2')],limit=1)
                if actual!=[{'N':spec['rows']}]:raise io.DPError('QUERY_ROW_COUNT: '+kind)
            # Also reject undeclared kinds, not merely wrong counts within expected kinds.
            count=sql.query(f'SELECT COUNT(*) AS N FROM {q.ROW} WHERE RELEASE_ID=:release',[('release',rid,'VARCHAR2')],limit=1)
            if count!=[{'N':sum(x['rows'] for x in value['tables'].values())}]:raise io.DPError('QUERY_TOTAL_COUNT: unexpected rows')
            if io.file_sha(dbpath)!=sha:raise io.DPError('DB_CHANGED: transport DB changed during upload')
            if action=='publish':
                stmt=(f'DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM {q.RELEASE} WHERE RELEASE_ID=:release; '
                      f'IF n=0 THEN INSERT INTO {q.RELEASE}(RELEASE_ID,MANIFEST_JSON) VALUES(:release,:body); END IF; '
                      'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
                sql.request(stmt,[('release',rid,'VARCHAR2'),('body',q.json_body(value),'CLOB')],write=True)
            if q.read_release(sql,rid)!=value:raise io.DPError('QUERY_RELEASE_READBACK: manifest differs')
            state.update(status='COMPLETE',active_changed=False);io.atomic_json(receipt,state)
            event(folder,'IMPORT_VERIFIED',release_id=rid,rows=verified)
            return {'status':'COMPLETE' if action=='publish' else 'QUERY_PUBLICATION_VERIFIED','release_id':rid,'active_changed':False,'rows':verified}
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc,io.BudgetPause) else 'FAILED',error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            io.atomic_json(receipt,state);raise
