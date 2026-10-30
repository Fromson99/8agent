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
from semantic_runtime.physical_mapping import names
from . import oracle_query_publish as pub, oracle_migration as migration
from .oracle_transfer_progress import tracking, report, check, sqlite_work

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


def export(generation,output,*,seconds=21600,chunk_bytes=CHUNK_BYTES,resume_r1=False,direct_parts=False,database_only=False):
    # The former timer-only heartbeat is replaced with named phase/real work telemetry.
    if type(database_only) is not bool or (database_only and direct_parts):
        raise io.DPError('EXPORT_PACKAGING: choose database_only or direct_parts')
    Path(output).mkdir(parents=True,exist_ok=True)
    with tracking(output,lambda status,**fields:event(output,status,**fields)) as progress:
        progress.deadline=time.time()+seconds
        return _export(generation,output,seconds=seconds,chunk_bytes=chunk_bytes,
                       resume_r1=resume_r1,direct_parts=direct_parts,database_only=database_only,progress=progress)


def _export(generation,output,*,seconds,chunk_bytes,resume_r1,direct_parts,database_only,progress):
    """Resume by reconciling deterministic row sequence; no input file is modified."""
    if not 1<=seconds<=21600:raise io.DPError('BUDGET: seconds must be 1..21600')
    with job(output) as folder:
        resources(folder);report('SOURCE_HASH_CHECK',generation=str(generation))
        event(folder,'INSPECTING_SOURCE',generation=str(generation))
        root,manifest,items,files,selected=immutable_inputs(generation)
        if folder.resolve().is_relative_to(root):raise io.DPError('OUTPUT_INSIDE_SOURCE: choose a separate workspace folder')
        identity={'generation':str(root),'files':files,'selection':io.digest(selected),
                  'transport_code':io.file_sha(__file__),'publisher_code':io.file_sha(pub.__file__)}
        state_path=folder/'export-state.json'
        state=bounded_json(state_path) if state_path.exists() else {'identity':identity,'deadline':time.time()+7*86400,'status':'NEW'}
        if state['identity']!=identity:
            if not resume_r1:raise io.DPError('EXPORT_BINDING: inputs/code differ; R1 partial needs explicit --resume-r1')
            state=adopt_r1(folder,state,identity)
        io.atomic_json(state_path,state)
        end=min(time.time()+seconds,state['deadline']);last=[0.0]
        progress.deadline=end
        def tick():
            if time.time()>end:raise io.BudgetPause('EXPORT_BUDGET: rerun same command; original deadline retained')
            if time.time()-last[0]>15:
                check();resources(folder);last[0]=time.time()
        report('SOURCE_ROW_HASHES')
        source=offline_source(root,manifest,items,selected,tick)
        source_id=io.digest(source)
        dbpath=folder/DB_NAME
        if dbpath.exists():
            report('VERIFY_EXISTING_DB');verified=verify_db(dbpath)
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
                tables={};sequence=0;added=0
                retained=db.execute('SELECT COUNT(*),COALESCE(MAX(seq),0) FROM query_row').fetchone()
                if retained[0]!=retained[1]:raise io.DPError('EXPORT_RESUME_GAP: retained rows are not a prefix')
                # Recheck the complete retained prefix with one ordered cursor.
                # New sequence numbers cannot exist beyond the verified maximum.
                prefix=db.execute('SELECT seq,kind,row_id,body FROM query_row WHERE seq<=? ORDER BY seq',(retained[1],))
                pending=[];pending_bytes=0
                def flush():
                    nonlocal pending_bytes
                    if pending:
                        db.executemany('INSERT INTO query_row VALUES(?,?,?,?)',pending)
                        pending.clear();pending_bytes=0
                event(folder,'RESUME_PREFIX',retained_rows=retained[0],mode='revalidate-every-row-no-reinsert')
                for relative,sha in paths.items():
                    tick();event(folder,'PROJECTING',asset=relative)
                    path=assets.checked_path(root,relative)
                    if relative!='store.sqlite':tables.update(pub.asset_schema(path,relative))
                    for row in pub.projected_rows(path,relative,source):
                        tick();sequence+=1;body=q.json_body(row)
                        if sequence<=retained[1]:
                            old=prefix.fetchone()
                            if old!=(sequence,row['kind'],row['row_id'],body):raise io.DPError('EXPORT_RESUME_CONFLICT: stored row differs')
                        else:
                            pending.append((sequence,row['kind'],row['row_id'],body));added+=1
                            pending_bytes+=len(body.encode('utf-8'))
                            if len(pending)>=1000 or pending_bytes>=4*1024**2:flush()
                        s=tables.setdefault(row['kind'],{'asset':relative,'rows':0,'chain':'0'*64})
                        s['rows']+=1;s['chain']=io.digest([s['chain'],row['row_id'],row['sha256']]);pub._column_shapes(s,row['value'])
                        if sequence%1000==0 or sequence==retained[0]:
                            flush()
                            db.commit();report(rows_checked=sequence,rows_added=added)
                            event(folder,'ROWS_CHECKED' if sequence<=retained[0] else 'ROWS_SAVED',rows=sequence,added=added)
                    flush();db.commit()
                    report(rows_checked=sequence,rows_added=added)
                    report('ASSET_HASH_CHECK',asset=relative)
                    if io.file_sha(path)!=sha:raise io.DPError('SOURCE_CHANGED: '+relative)
                if db.execute('SELECT COUNT(*) FROM query_row').fetchone()[0]!=sequence:raise io.DPError('EXPORT_EXTRA_ROWS: previous partial data differs')
                report('BUILD_MANIFEST');value=query_manifest(root,source,paths,tables,items)
                report('SOURCE_FINAL_HASH_CHECK')
                _,_,_,after,selection_after=immutable_inputs(root)
                if after!=files or selected!=selection_after:raise io.DPError('SOURCE_CHANGED: source/selection changed while exporting')
                for key,obj in {'format':FORMAT,'source_release':source,'query_manifest':value}.items():
                    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,io.canonical(obj)))
                db.commit()
            finally:db.close()
            report('VERIFY_DB');verify_db(partial)
            os.rename(partial,dbpath)
        if database_only:
            # The compute worker includes this verified DB in result.zip itself.
            # Do not also compress it into unused download parts first.
            report('DATABASE_READY',file=str(dbpath))
            result={'packaging':'database-only-v1','db_sha256':io.file_sha(dbpath),'db_bytes':dbpath.stat().st_size}
        else:
            result=(split_db_direct if direct_parts else split_db)(dbpath,folder,chunk_bytes=chunk_bytes)
        state.update(status='COMPLETE',source_release_id=source_id,**result);io.atomic_json(state_path,state)
        event(folder,'EXPORT_COMPLETE',**result)
        return result


def adopt_r1(folder,state,identity):
    """Only the sealed R1 code pair and identical data may replay an incomplete DB.

    This is not a bypass: export rederives and compares every retained row before
    adding new rows. Original receipt/deadline and upgrade audit are preserved.
    """
    old=state['identity'];old_data={k:v for k,v in old.items() if k not in {'transport_code','publisher_code'}}
    new_data={k:v for k,v in identity.items() if k not in {'transport_code','publisher_code'}}
    if old_data!=new_data or (old.get('transport_code'),old.get('publisher_code'))!=(
            'be1fde2bfbea99b4b1e057430f1214e6ab9657540cfe5f17ebc29bcca6eff215',
            '550a0d51134a7f61a0a8d467d01cd36ee7657ab6ef251205da36285672aa2629'):
        raise io.DPError('R1_UPGRADE_BINDING: only exact sealed R1 with unchanged source is supported')
    if state.get('status')=='COMPLETE' or (folder/DB_NAME).exists() or (folder/'query-data.zip').exists() or (folder/'download').exists():
        raise io.DPError('R1_UPGRADE_COMPLETE: preserve completed R1; use its original importer or a new output')
    if not (folder/(DB_NAME+'.partial')).is_file():raise io.DPError('R1_UPGRADE_PARTIAL: incomplete DB required')
    if time.time()>=state['deadline']:raise io.BudgetPause('R1_UPGRADE_EXPIRED: original deadline cannot be reset')
    saved=folder/'export-state.r1-preserved.json'
    if saved.exists() and bounded_json(saved)!=state:raise io.DPError('R1_UPGRADE_HISTORY: receipt differs')
    io.atomic_json(saved,state)
    updated={**state,'identity':identity,'upgrade_from':io.digest(state),'status':'R1_PREFIX_RECHECK_REQUIRED'}
    event(folder,'R1_UPGRADE',old_identity=old,new_identity=identity,deadline=state['deadline'],prefix_recheck=True)
    return updated


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
        with sqlite_work(db):return _verify_db(db)
    finally:db.close()


def _verify_db(db):
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
        if seq%10000==0:check();report(rows_verified=seq)
    if any(s!={k:value['tables'][kind][k] for k in ('rows','chain')} for kind,s in tables.items()):
        raise io.DPError('DB_CHAIN: row counts or content chain differ')
    return meta


class _PartsWriter:
    """Unseekable ZIP sink: no second complete compressed archive on disk."""
    def __init__(self,folder,chunk_bytes):
        self.folder=Path(folder);self.parts=self.folder/'download';self.parts.mkdir(exist_ok=True)
        self.chunk_bytes=chunk_bytes;self.entries=[];self.total=hashlib.sha256();self.position=0
        self.file=None;self.count=0;self.sha=None;self.temporary=None;self.failure=None
    def tell(self):return self.position
    def seek(self,*args):raise OSError('streaming ZIP')
    def flush(self):
        if self.file is not None:self.file.flush()
    def _finish(self):
        if self.file is None:return
        self.file.flush();os.fsync(self.file.fileno());self.file.close();self.file=None
        name=f'query-data.zip.part{len(self.entries)+1:06d}';target=self.parts/name
        value={'name':name,'bytes':self.count,'sha256':self.sha.hexdigest()}
        if target.exists():
            if target.stat().st_size!=self.count or io.file_sha(target)!=value['sha256']:
                raise io.DPError('PART_CONFLICT: '+name)
            self.temporary.unlink()  # Verified regenerated duplicate only.
        else:self.temporary.rename(target)
        self.entries.append(value);event(self.folder,'PART_READY',**value)
    def write(self,data):
        if self.failure is not None:raise self.failure
        try:return self._write(data)
        except BaseException as exc:
            self.failure=exc;raise
    def _write(self,data):
        check();resources(self.folder);view=memoryview(data);used=0
        while used<len(view):
            if self.file is None:
                self.temporary=self.folder/(f'query-data.zip.part{len(self.entries)+1:06d}.partial-'+uuid.uuid4().hex)
                self.file=self.temporary.open('xb');self.count=0;self.sha=hashlib.sha256()
            piece=view[used:used+min(len(view)-used,self.chunk_bytes-self.count)]
            self.file.write(piece);self.sha.update(piece);self.total.update(piece)
            self.count+=len(piece);self.position+=len(piece);used+=len(piece)
            if self.count==self.chunk_bytes:self._finish()
        return len(data)
    def finish(self):self._finish()
    def abort(self):
        if self.file is not None:self.file.close();self.file=None


def split_db_direct(dbpath,folder,*,chunk_bytes=CHUNK_BYTES):
    if not 1<=chunk_bytes<=CHUNK_BYTES:raise io.DPError('PART_SIZE')
    folder=Path(folder);dbpath=Path(dbpath)
    if (folder/'query-data.zip').exists():
        raise io.DPError('ZIP_ALREADY_EXISTS: preserve earlier archive; use original splitter')
    report('DB_HASH_BEFORE_ZIP',file=str(dbpath));dbsha=io.file_sha(dbpath);size=dbpath.stat().st_size
    writer=_PartsWriter(folder,chunk_bytes);read=0;h=hashlib.sha256()
    report('ZIP_DIRECT_TO_PARTS',file=str(dbpath),bytes_done=0,bytes_total=size)
    try:
        with zipfile.ZipFile(writer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
            # Fixed metadata makes an interrupted compression reproducible;
            # previously completed parts are byte-compared before reuse.
            info=zipfile.ZipInfo(DB_NAME,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.file_size=size
            dst=archive.open(info,'w',force_zip64=True)
            try:
                with dbpath.open('rb') as src:
                    while block:=src.read(1024**2):
                        check();resources(folder);dst.write(block);h.update(block);read+=len(block)
                        report(bytes_done=read,bytes_total=size,compressed_bytes=writer.position)
            except BaseException as exc:
                writer.failure=exc;raise
            finally:dst.close()
        writer.finish()
    except BaseException:writer.abort();raise
    if read!=size or h.hexdigest()!=dbsha:raise io.DPError('DB_CHANGED: input changed during compression')
    report('ZIP_PART_HASH_CHECK')
    for item in writer.entries:
        check();path=writer.parts/item['name']
        if path.stat().st_size!=item['bytes'] or io.file_sha(path)!=item['sha256']:raise io.DPError('PART_HASH: '+item['name'])
    if {p.name for p in writer.parts.glob('query-data.zip.part*')}!={e['name'] for e in writer.entries}:
        raise io.DPError('PART_SET: unexpected old parts; preserve them')
    value={'format':FORMAT,'archive':'query-data.zip','archive_bytes':writer.position,
           'archive_sha256':writer.total.hexdigest(),'db_bytes':size,'db_sha256':dbsha,'parts':writer.entries,
           'archive_storage':'direct-parts-no-standalone-zip'}
    report('VERIFY_DB_BEFORE_MANIFEST');meta=verify_db(dbpath)
    io.atomic_json(writer.parts/'parts-manifest.json',value)
    return {'download_dir':str(writer.parts.resolve()),'parts':len(writer.entries),'archive_bytes':writer.position,
            'db_sha256':dbsha,'query_release_id':io.digest(meta['query_manifest']),
            'archive_storage':value['archive_storage']}


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
        rows_map=names(sql,'query_row',q.ROW)
        release_map=names(sql,'query_release',q.RELEASE)
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
                actual=sql.query(f'SELECT COUNT(*) AS N FROM {rows_map.table} WHERE {rows_map.c("RELEASE_ID") }=:release AND {rows_map.c("KIND") }=:kind',
                                 [('release',rid,'VARCHAR2'),('kind',kind,'VARCHAR2')],limit=1)
                if actual!=[{'N':spec['rows']}]:raise io.DPError('QUERY_ROW_COUNT: '+kind)
            # Also reject undeclared kinds, not merely wrong counts within expected kinds.
            count=sql.query(f'SELECT COUNT(*) AS N FROM {rows_map.table} WHERE {rows_map.c("RELEASE_ID") }=:release',[('release',rid,'VARCHAR2')],limit=1)
            if count!=[{'N':sum(x['rows'] for x in value['tables'].values())}]:raise io.DPError('QUERY_TOTAL_COUNT: unexpected rows')
            if io.file_sha(dbpath)!=sha:raise io.DPError('DB_CHANGED: transport DB changed during upload')
            if action=='publish':
                stmt=(f'DECLARE n NUMBER; BEGIN SELECT COUNT(*) INTO n FROM {release_map.table} WHERE {release_map.c("RELEASE_ID") }=:release; '
                      f'IF n=0 THEN INSERT INTO {release_map.table}({release_map.c("RELEASE_ID")},{release_map.c("MANIFEST_JSON")}) VALUES(:release,:body); END IF; '
                      'COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
                sql.request(stmt,[('release',rid,'VARCHAR2'),('body',q.json_body(value),'CLOB')],write=True)
            if q.read_release(sql,rid)!=value:raise io.DPError('QUERY_RELEASE_READBACK: manifest differs')
            state.update(status='COMPLETE',active_changed=False);io.atomic_json(receipt,state)
            event(folder,'IMPORT_VERIFIED',release_id=rid,rows=verified)
            return {'status':'COMPLETE' if action=='publish' else 'QUERY_PUBLICATION_VERIFIED','release_id':rid,'active_changed':False,'rows':verified}
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc,io.BudgetPause) else 'FAILED',error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            io.atomic_json(receipt,state);raise
