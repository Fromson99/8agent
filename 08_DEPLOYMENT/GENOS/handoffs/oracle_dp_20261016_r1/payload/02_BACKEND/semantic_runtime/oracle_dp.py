"""Oracle-backed immutable source/index cache, selected explicitly by DP=oracle.

Oracle source tables supply every source row. Navigation/fulltext/glossary assets
are fetched from the same pinned Oracle release. No NFS source fallback exists.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time

from .oracle_dp_io import (DPError, SQL, OWNER, TABLES, COLUMNS, KEYS, atomic_json,
                          canonical, digest, file_sha, read_rows, check_source_tables)
from .oracle_dp_assets import get_release, get_part, checked_path, PART_BYTES

SCHEMA = 'oracle-dp-cache-v1'
CHAIN_START = '0'*64
_VERIFIED = {}


def enabled(environment=None):
    env=os.environ if environment is None else environment
    value=env.get('DP','').strip().lower()
    if value in ('','0','false','nfs'):return False
    if value in ('1','true','oracle'):return True
    raise DPError('DP_CONFIG: DP must be oracle/1 or nfs/0')


def environment_binding(environment=None):
    env=os.environ if environment is None else environment
    names=('DP','DP_RELEASE_ID','DP_CACHE_DIR','ORACLE_ORDS_BASE_URL','LLMOPS_ORDS_BASE_URL',
           'ORACLE_ORDS_SCHEMA','ORACLE_ORDS_CLIENT_ID','ORACLE_ORDS_CLIENT_SECRET')
    return digest({k:env.get(k,'') for k in names})


def client_from_environment():
    from genos.ords import ORDSClient
    required=('ORACLE_ORDS_SCHEMA','ORACLE_ORDS_CLIENT_ID','ORACLE_ORDS_CLIENT_SECRET')
    missing=[k for k in required if not os.environ.get(k,'').strip()]
    if missing:raise DPError('DP_CONFIG: missing '+', '.join(missing))
    options={'schema':os.environ[required[0]],'auth_key':tuple(os.environ[k] for k in required[1:]),
             'timeout':60,'verify':True}
    # Match the successful R6 SDK_DEFAULT contract; do not substitute the table owner for the alias.
    if os.environ.get('ORACLE_ORDS_BASE_URL','').strip():
        options['base_url']=os.environ['ORACLE_ORDS_BASE_URL'].strip()
    try:return ORDSClient(**options)
    except Exception as exc:raise DPError('DP_CONNECT: '+type(exc).__name__) from None


def source_page(sql, kind, version, cursor=None):
    keys=[c for c in KEYS[kind] if c!='DATASET_VERSION']
    bindings=[('v',version,'VARCHAR2')]
    where='DATASET_VERSION=:v'
    binary=lambda expression:f"NLSSORT({expression},'NLS_SORT=BINARY')"
    if cursor:
        choices=[]
        for i,col in enumerate(keys):
            choices.append('('+' AND '.join([f'{binary(keys[j])}={binary(":k"+str(j))}' for j in range(i)]+
                                           [f'{binary(col)}>{binary(":k"+str(i))}'])+')')
            bindings.append(('k'+str(i),cursor[i],'VARCHAR2'))
        where+=' AND ('+' OR '.join(choices)+')'
    order='ORDER BY '+','.join(binary(c) for c in keys)+' FETCH FIRST 100 ROWS ONLY'
    return read_rows(sql,kind,where,bindings,limit=100,order=order)


def create_source(path):
    db=sqlite3.connect(path)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
      CREATE TABLE IF NOT EXISTS source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id));
      CREATE TABLE IF NOT EXISTS block_payload(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,json_text_elided INTEGER,PRIMARY KEY(document_id,block_id));
      CREATE INDEX IF NOT EXISTS block_range ON block_payload(document_id,CAST(block_id AS INTEGER));
      CREATE INDEX IF NOT EXISTS block_owner ON block_payload(document_id,unit_id,CAST(block_id AS INTEGER));
      CREATE VIEW IF NOT EXISTS source_block AS SELECT document_id,block_id,unit_id,text,source_artifact_sha256,
        CASE WHEN json_text_elided THEN json_set(json,'$.text',text) ELSE json END AS json FROM block_payload;
    ''')
    db.row_factory=sqlite3.Row
    return db


def download_source(sql, release, work, state, save):
    db=create_source(work/'store.sqlite')
    try:
        for kind in TABLES:
            progress=state.setdefault('source',{}).setdefault(kind,{'cursor':None,'rows':0,'chain':CHAIN_START})
            columns=[c for c in COLUMNS[kind] if c!='DATASET_VERSION']
            physical=['json' if c=='SOURCE_JSON' else c.lower() for c in columns]
            keys=[c for c in KEYS[kind] if c!='DATASET_VERSION']
            while rows:=source_page(sql,kind,release['dataset_version'],progress['cursor']):
                for row in rows:
                    db.execute(f'INSERT OR IGNORE INTO {kind} ({",".join(physical)}) VALUES ({",".join("?" for _ in physical)})',
                               [row[c] for c in columns])
                    found=db.execute(f'SELECT * FROM {kind} WHERE '+ ' AND '.join(c.lower()+'=?' for c in keys),[row[c] for c in keys]).fetchone()
                    if dict(found)!={p:row[c] for p,c in zip(physical,columns)}:
                        raise DPError('CACHE_SOURCE_CONFLICT: resumed cache differs from Oracle')
                db.commit()  # A crash before the JSON checkpoint rechecks these same immutable rows.
                for row in rows:progress['chain']=digest([progress['chain'],row])
                progress['rows']+=len(rows);progress['cursor']=[rows[-1][c] for c in keys];save()
            expected=release['source_rows'][kind]
            if progress['rows']!=expected['rows'] or progress['chain']!=expected['chain']:
                raise DPError('ORACLE_SOURCE_HASH: incomplete/changed version; not published as a cache')
            if db.execute(f'SELECT COUNT(*) FROM {kind}').fetchone()[0]!=expected['rows']:
                raise DPError('CACHE_SOURCE_COUNT: cache contains unexpected rows')
            # A checkpoint is progress, not proof that a partially built local file stayed intact.
            chain=CHAIN_START
            for record in db.execute(f'SELECT * FROM {kind} ORDER BY '+','.join(c.lower() for c in keys)):
                row={c:release['dataset_version'] if c=='DATASET_VERSION' else
                     record['json' if c=='SOURCE_JSON' else c.lower()] for c in COLUMNS[kind]}
                chain=digest([chain,row])
            if chain!=expected['chain']:
                raise DPError('CACHE_SOURCE_HASH: local source rows differ from the published logical digest')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise DPError('CACHE_SQLITE: reconstructed source failed integrity check')
    finally:db.close()


def download_assets(sql, release, work, state, save):
    for asset in release['assets']:
        target=checked_path(work,asset['path']);target.parent.mkdir(parents=True,exist_ok=True)
        progress=state.setdefault('assets',{}).setdefault(asset['path'],{'next_part':0})
        completed=progress['next_part']
        expected_size=min(completed*PART_BYTES,asset['bytes'])
        if target.exists() and target.stat().st_size<expected_size:
            raise DPError('CACHE_PARTIAL: file is shorter than durable checkpoint')
        if not target.exists() and completed:
            raise DPError('CACHE_PARTIAL: durable checkpoint file missing')
        with target.open('r+b' if target.exists() else 'w+b') as f:
            # Discard only an uncheckpointed tail in this task's private incomplete cache.
            f.truncate(expected_size);f.seek(expected_size)
            for number in range(completed,asset['parts']):
                raw=get_part(sql,asset['sha256'],number)
                length=min(PART_BYTES,asset['bytes']-number*PART_BYTES)
                if raw is None or len(raw)!=length:raise DPError('ASSET_MISSING: pinned Oracle asset part missing')
                f.write(raw);f.flush();os.fsync(f.fileno())
                progress['next_part']=number+1;save()
        if target.stat().st_size!=asset['bytes'] or file_sha(target)!=asset['sha256']:
            raise DPError('CACHE_ASSET_HASH: downloaded asset differs from pinned release')


def bind_cache_generation(release, work, release_id):
    """Proven equivalent source rows, new SQLite byte hash, explicit derived manifests.

    All original manifests are preserved under oracle_origin. Index database bytes
    are unchanged; only source-file bindings are updated after row-chain proof.
    """
    source=copy.deepcopy(release['source_manifest'])
    original=release['source_manifest_text'].encode()
    if hashlib.sha256(original).hexdigest()!=release['dataset_version'] or json.loads(original)!=source:
        raise DPError('ORIGIN_MANIFEST: source manifest identity differs')
    origin=work/'oracle_origin';origin.mkdir(exist_ok=True)
    (origin/'manifest.json').write_bytes(original)
    source['store_sha256']=file_sha(work/'store.sqlite')
    source['oracle_dp']={'schema_version':SCHEMA,'release_id':release_id,'dataset_version':release['dataset_version'],
                         'origin_store_sha256':release['source_manifest']['store_sha256'],
                         'source_row_chains':release['source_rows'],'index_bytes_unchanged':True}
    navpath=checked_path(work,source['navigation']['path'])/'manifest.json'
    oldnav=json.loads(navpath.read_text());(origin/'navigation.json').write_bytes(navpath.read_bytes())
    original_digest=digest({k:v for k,v in release['source_manifest'].items() if k not in {'navigation','fulltext','fulltext_derivation'}})
    if oldnav['source_store_sha256']!=release['source_manifest']['store_sha256'] or oldnav['source_manifest_sha256']!=original_digest:
        raise DPError('ORIGIN_NAVIGATION: source/index binding differs')
    nav={**oldnav,'source_store_sha256':source['store_sha256'],
         'source_manifest_sha256':digest({k:v for k,v in source.items() if k not in {'navigation','fulltext','fulltext_derivation'}})}
    atomic_json(navpath,nav);source['navigation']['manifest_sha256']=file_sha(navpath)
    if source.get('fulltext'):
        path=checked_path(work,source['fulltext']['path'])/'manifest.json'
        fulltext=json.loads(path.read_text());(origin/'fulltext.json').write_bytes(path.read_bytes())
        if fulltext['source_store_sha256']!=oldnav['source_store_sha256'] or fulltext['navigation_index_sha256']!=oldnav['index_sha256']:
            raise DPError('ORIGIN_FULLTEXT: source/index binding differs')
        fulltext['source_store_sha256']=source['store_sha256']
        if 'navigation_manifest_sha256' in fulltext:fulltext['navigation_manifest_sha256']=file_sha(navpath)
        if 'source_manifest_sha256' in fulltext:
            # Same construction order as the fulltext builder: source before its final fulltext pin.
            fulltext['source_manifest_sha256']=hashlib.sha256((canonical({k:v for k,v in source.items() if k!='fulltext'})+'\n').encode()).hexdigest()
        atomic_json(path,fulltext);source['fulltext']['manifest_sha256']=file_sha(path)
    atomic_json(work/'manifest.json',source)
    if release.get('search_selection') is not None:
        selection=copy.deepcopy(release['search_selection'])
        atomic_json(origin/'search_selection.json',selection)
        selection['store_sha256']=source['store_sha256'];selection['manifest_sha256']=file_sha(work/'manifest.json')
        atomic_json(work.parent/'SEARCH_SELECTION'/(work.name+'.json'),selection)
    return source


def verify_runtime(generation):
    # This is the existing full Store/TermIndex/fulltext/glossary verification path.
    from lawrag.pipeline.term_serving_bundle import verify_assets
    return verify_assets(generation)


def prepare(sql, release_id, directory, *, verifier=verify_runtime):
    release=get_release(sql,release_id)
    folder=Path(directory).resolve()/release_id
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'cache.lock').open('a') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise DPError('CACHE_BUSY: another process is preparing this release') from None
        complete=folder/'complete'
        ready=complete/'READY.json';generation=complete/'generation'
        if ready.exists():
            proof=json.loads(ready.read_text())
            if proof['release_id']!=release_id or proof['target_binding']!=sql.binding:
                raise DPError('CACHE_BINDING: cached target differs')
            for name,sha in proof['files'].items():
                path=checked_path(complete,name)
                stat=path.stat();signature=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
                key=(str(path),signature,sha)
                if key not in _VERIFIED:
                    if file_sha(path)!=sha:raise DPError('CACHE_HASH: completed cache changed')
                    _VERIFIED[key]=True
            verifier(generation)
            return generation,{'cache_hit':True,'release_id':release_id,'dataset_version':release['dataset_version']}
        if complete.exists():raise DPError('CACHE_PUBLISH: final cache lacks its atomic completion receipt')
        workroot=folder/'partial';work=workroot/'generation';work.mkdir(parents=True,exist_ok=True)
        originals=workroot/'assets';originals.mkdir(exist_ok=True)
        checkpoint=folder/'download.json'
        state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'release_id':release_id,'target_binding':sql.binding,'deadline':time.time()+7*86400}
        if state['release_id']!=release_id or state['target_binding']!=sql.binding:
            raise DPError('CACHE_BINDING: partial cache target differs')
        sql.deadline=min(sql.deadline,time.monotonic()+max(0,state['deadline']-time.time()))
        save=lambda:atomic_json(checkpoint,state)
        save()
        try:
            check_source_tables(sql)
            download_source(sql,release,work,state,save)
            download_assets(sql,release,originals,state,save)
            for asset in release['assets']:
                src=checked_path(originals,asset['path']);dst=checked_path(work,asset['path'])
                dst.parent.mkdir(parents=True,exist_ok=True)
                # All objects here belong to this incomplete build. Original downloads remain immutable.
                if dst.exists():dst.unlink()
                os.link(src,dst)
            bind_cache_generation(release,work,release_id)
            verifier(work)
            files={str(p.relative_to(workroot)):file_sha(p) for p in work.rglob('*') if p.is_file()}
            selection=workroot/'SEARCH_SELECTION'/'generation.json'
            if selection.exists():files['SEARCH_SELECTION/generation.json']=file_sha(selection)
            atomic_json(workroot/'READY.json',{'schema_version':SCHEMA,'release_id':release_id,'target_binding':sql.binding,'files':files})
            # Generation, selection and completion receipt become visible in a single directory rename.
            os.rename(workroot,complete)
            return generation,{'cache_hit':False,'release_id':release_id,'dataset_version':release['dataset_version']}
        except Exception as exc:
            sql.event('CACHE_FAILED',error=str(exc) if isinstance(exc,DPError) else type(exc).__name__)
            raise


def resolve(root):
    release_id=os.environ.get('DP_RELEASE_ID','').strip()
    if not release_id:raise DPError('DP_CONFIG: DP_RELEASE_ID from completed Oracle publication is required')
    cache=Path(os.environ.get('DP_CACHE_DIR','/var/tmp/8-agent-oracle-dp')).expanduser().resolve()
    cache.mkdir(parents=True,exist_ok=True)
    from .observability import environment_facts
    if environment_facts(cache).get('mount_type') in ('nfs','nfs4','cifs','smb3','tmpfs','ramfs'):
        raise DPError('DP_CACHE_DIR: disk-backed local cache directory required')
    # SQLite now reads verified local files. OS page cache avoids an additional whole-file disk mirror.
    os.environ.setdefault('GENOS_RESIDENT_DATA','off')
    target=environment_binding()
    directory=cache/target[:24];directory.mkdir(parents=True,exist_ok=True)
    client=client_from_environment()
    sql=SQL(client,journal=directory/(release_id+'.jsonl'),binding=target,seconds=3600)
    generation,receipt=prepare(sql,release_id,directory)
    return Path(root),generation,{'mode':'oracle-dp','data_provider':'oracle','dp_environment_binding':target,
        'generation_id':json.loads((generation/'manifest.json').read_text())['generation_id'],
        'data_manifest_sha256':file_sha(generation/'manifest.json'),'nfs_source_used':False,**receipt}
