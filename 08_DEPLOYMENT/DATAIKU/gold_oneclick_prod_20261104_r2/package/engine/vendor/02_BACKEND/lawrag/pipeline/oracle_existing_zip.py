"""Read historical GENOS data ZIPs; restore only their explicitly selected generation.

Never execute archived code or restore runtime/NFS. Reuse the full Oracle importer.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import stat
import time
import uuid
import zipfile
from . import oracle_full_package as full, oracle_query_package as transport
from .oracle_transfer_progress import tracking, report, check
from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as assets, oracle_query_catalog as q

FORMATS = {'genos-rag-data-path-preserving-v1', 'genos-rag-data-live-v2'}
PART_FORMAT = 'genos-existing-zip-parts-v1'
CHUNK_BYTES = 49_000_000


def absolute(name):
    p=PurePosixPath(name)
    if not p.is_absolute() or '..' in p.parts or str(p)!=name or '\\' in name:
        raise io.DPError('LEGACY_PATH: invalid absolute source path')
    return p


def inspect_archive(archive):
    with zipfile.ZipFile(archive) as z:
        seen=set()
        for m in z.infolist():
            n=m.filename.rstrip('/'); mode=m.external_attr>>16
            if assets.safe_relative(n)!=n or n in seen or m.flag_bits&1 or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise io.DPError('ZIP_MEMBER: unsafe/duplicate/encrypted member')
            seen.add(n)
        candidates=[n for n in seen if len(PurePosixPath(n).parts)==2 and n.endswith('/DATA_MANIFEST.json')]
        if len(candidates)!=1:raise io.DPError('LEGACY_FORMAT: one top-level DATA_MANIFEST.json required')
        meta_name=candidates[0];prefix=meta_name.rsplit('/',1)[0]
        if any(n.split('/')[0]!=prefix for n in seen):raise io.DPError('ZIP_ROOT: multiple roots')
        if z.getinfo(meta_name).file_size>32*1024**2:raise io.DPError('METADATA_SIZE')
        raw=z.read(meta_name);meta=json.loads(raw)
        if meta.get('schema_version') not in FORMATS:raise io.DPError('LEGACY_FORMAT: unsupported archive')
        if meta.get('archive_restore_eligible') is not True:raise io.DPError('ARCHIVE_NOT_ELIGIBLE: inspect source change report')
        generation=absolute(meta['generation']);q.pin(meta['generation_manifest_sha256'])
        selection=generation.parent/'SEARCH_SELECTION'/(generation.name+'.json')
        files={};payload={};excluded=0
        for source,item in meta['files'].items():
            p=absolute(source)
            if item['kind']=='directory':continue
            if item['kind']!='file':raise io.DPError('LEGACY_FILE_TYPE')
            if p.is_relative_to(generation):dest='generation/'+str(p.relative_to(generation))
            elif p==selection:dest='SEARCH_SELECTION/generation.json'
            else:excluded+=1;continue
            if assets.safe_relative(dest)!=dest:raise io.DPError('FILE_PATH')
            member=prefix+'/payload/'+source.lstrip('/')
            q.pin(item['sha256'])
            if type(item['bytes']) is not int or item['bytes']<0:raise io.DPError('FILE_SIZE')
            if member not in seen or z.getinfo(member).is_dir() or z.getinfo(member).file_size!=item['bytes']:
                raise io.DPError('ZIP_SIZE_OR_MISSING: '+dest)
            files[dest]={'bytes':item['bytes'],'sha256':item['sha256']};payload[dest]=member
        if not {'generation/manifest.json','generation/store.sqlite'}<=files.keys():raise io.DPError('GENERATION_MISSING')
        if files['generation/manifest.json']['sha256']!=meta['generation_manifest_sha256']:raise io.DPError('MANIFEST_BINDING')
        # Reject undeclared files in the selected generation (including WAL/journals).
        gen_prefix=prefix+'/payload/'+str(generation).lstrip('/')+'/'
        selection_member=prefix+'/payload/'+str(selection).lstrip('/')
        for m in z.infolist():
            if not m.is_dir() and (m.filename.startswith(gen_prefix) or m.filename==selection_member) and m.filename not in payload.values():
                raise io.DPError('UNDECLARED_GENERATION_FILE: '+m.filename)
        return {'status':'ARCHIVE_INSPECTED','archive_format':meta['schema_version'],
                'generation_in_zip':str(generation),'data_manifest_sha256':hashlib.sha256(raw).hexdigest(),
                'dataset_version':meta['generation_manifest_sha256'],'files':files,'members':payload,
                'selected_bytes':sum(v['bytes'] for v in files.values()),'excluded_file_count':excluded,
                'live_snapshot':meta['schema_version'].endswith('live-v2'),
                'latest_generation_verified':False,'metadata':meta}


def _hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as src:
        count=0
        while block:=src.read(1024**2):
            check();h.update(block);count+=len(block);report(bytes_done=count)
    return h.hexdigest()


def restore(archive,output,*,expected_sha=None,seconds=21600):
    if not 1<=seconds<=21600:raise io.DPError('BUDGET: seconds 1..21600')
    archive=Path(archive)
    if archive.is_symlink() or not archive.is_file():raise io.DPError('ARCHIVE_PATH')
    archive=archive.resolve();signature=(archive.stat().st_size,archive.stat().st_mtime_ns)
    with transport.job(output) as folder, tracking(output,lambda s,**kw:transport.event(output,s,**kw)) as progress:
        receipt=folder/'restore-state.json'
        state=transport.bounded_json(receipt) if receipt.exists() else {'deadline':time.time()+7*86400}
        progress.deadline=min(time.time()+seconds,state['deadline'])
        try:
            report('ZIP_HASH',file=archive.name,bytes_total=archive.stat().st_size);digest=_hash(archive)
            if expected_sha:
                q.pin(expected_sha)
                if expected_sha!=digest:raise io.DPError('ZIP_HASH: expected hash differs')
            info=inspect_archive(archive)
            identity={'archive_sha256':digest,'metadata_sha256':info['data_manifest_sha256'],'code':io.file_sha(__file__)}
            if state.get('identity',identity)!=identity:raise io.DPError('RESTORE_BINDING: input/code changed')
            state.update(identity=identity,status='RESTORING');io.atomic_json(receipt,state)
            io.atomic_json(folder/'legacy-data-manifest.json',info['metadata'])
            needed=sum(v['bytes'] for n,v in info['files'].items() if not assets.checked_path(folder,n).exists())
            if transport.resources(folder)<needed+512*1024**2:raise io.BudgetPause('DISK_LOW: generation plus 512MiB required')
            with zipfile.ZipFile(archive) as z:
                for name,item in info['files'].items():
                    check();report('RESTORE_FILE',file=name,bytes_total=item['bytes'])
                    path=assets.checked_path(folder,name);path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists():
                        if path.stat().st_size!=item['bytes'] or _hash(path)!=item['sha256']:raise io.DPError('RESTORE_CONFLICT: '+name)
                        transport.event(folder,'FILE_REUSED',file=name);continue
                    temp=path.with_name(path.name+'.partial-'+uuid.uuid4().hex)
                    with z.open(info['members'][name]) as src,temp.open('xb') as dst:
                        actual=full._copy(src,dst,folder=folder,limit=item['bytes'],tick=check)
                    if actual!=item:raise io.DPError('FILE_HASH: '+name)
                    temp.rename(path);transport.event(folder,'FILE_RESTORED',file=name)
            report('GENERATION_VERIFY');check()
            root,paths,inventory=full.inventory(folder/'generation')
            # Inventory validates generation/asset binding; unused files remain accounted in legacy provenance.
            for name,item in inventory['files'].items():
                if info['files'].get(name)!=item:raise io.DPError('GENERATION_BINDING: '+name)
            if (archive.stat().st_size,archive.stat().st_mtime_ns)!=signature:raise io.DPError('ARCHIVE_CHANGED')
            marker={**inventory,'format':full.RESTORED_FORMAT,'archive_sha256':digest,
                    'data_manifest_sha256':info['data_manifest_sha256'],'generation_in_zip':info['generation_in_zip'],
                    'archive_format':info['archive_format'],'excluded_file_count':info['excluded_file_count']}
            io.atomic_json(folder/'full-manifest.json',marker);full.verify_restored(folder)
            result={'status':'RESTORED_AND_VERIFIED','generation':str(root),'source_counts':inventory['source_counts'],
                    'archive_sha256':digest,'dataset_version':inventory['dataset_version'],
                    'excluded_file_count':info['excluded_file_count'],'latest_generation_verified':False}
            state.update(status='COMPLETE',result=result);io.atomic_json(receipt,state);return result
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc,io.BudgetPause) else 'FAILED',error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            io.atomic_json(receipt,state);raise


def import_generation(client,folder,**kwargs):
    logs=Path(kwargs['directory']);logs.mkdir(parents=True,exist_ok=True)
    with tracking(logs,lambda s,**kw:transport.event(logs,s,**kw)) as progress:
        progress.deadline=time.time()+kwargs.get('seconds',3600)
        report('ORACLE_INPUT_VERIFY')
        return full.import_generation(client,folder,**kwargs)


def split(archive,output,*,chunk_bytes=CHUNK_BYTES):
    if not 1<=chunk_bytes<=CHUNK_BYTES:raise io.DPError('PART_SIZE')
    archive=Path(archive).resolve(strict=True)
    with transport.job(output) as folder:
        before=(archive.stat().st_size,archive.stat().st_mtime_ns);total=hashlib.sha256();parts=[]
        with archive.open('rb') as src:
            while src.tell()<before[0]:
                name=f'data.zip.part{len(parts)+1:06d}';path=folder/name;temp=folder/(name+'.partial-'+uuid.uuid4().hex)
                h=hashlib.sha256();size=0
                with temp.open('xb') as dst:
                    while size<chunk_bytes:
                        transport.resources(folder);block=src.read(min(1024**2,chunk_bytes-size))
                        if not block:break
                        dst.write(block);size+=len(block);h.update(block);total.update(block)
                item={'name':name,'bytes':size,'sha256':h.hexdigest()}
                if path.exists():
                    if path.is_symlink() or path.stat().st_size!=size or io.file_sha(path)!=item['sha256']:raise io.DPError('PART_CONFLICT')
                    temp.unlink()  # Verified regenerated duplicate only.
                else:temp.rename(path)
                parts.append(item);transport.event(folder,'PART_READY',**item)
        if (archive.stat().st_size,archive.stat().st_mtime_ns)!=before or io.file_sha(archive)!=total.hexdigest():raise io.DPError('ARCHIVE_CHANGED')
        value={'format':PART_FORMAT,'archive_name':archive.name,'archive_bytes':before[0],'archive_sha256':total.hexdigest(),'parts':parts}
        validate_parts(value);io.atomic_json(folder/'parts-manifest.json',value);return value


def validate_parts(value):
    if value.get('format')!=PART_FORMAT:raise io.DPError('PART_FORMAT: use parts made by this package')
    q.pin(value['archive_sha256']);parts=value['parts']
    if not 1<=len(parts)<=100000:raise io.DPError('PART_LIST')
    for i,item in enumerate(parts,1):
        if item['name']!=f'data.zip.part{i:06d}' or type(item['bytes']) is not int or not 0<item['bytes']<=CHUNK_BYTES:raise io.DPError('PART_ORDER_SIZE')
        q.pin(item['sha256'])
    if sum(i['bytes'] for i in parts)!=value['archive_bytes']:raise io.DPError('PART_TOTAL')


def join(parts,output):
    parts=Path(parts);info=transport.bounded_json(parts/'parts-manifest.json');validate_parts(info)
    if {p.name for p in parts.glob('data.zip.part*') if '.partial-' not in p.name}!={i['name'] for i in info['parts']}:raise io.DPError('PART_SET')
    output=Path(output);output.mkdir(parents=True,exist_ok=True);target=output/'joined-data.zip'
    with transport.job(output):
        if target.exists():
            if target.is_symlink() or io.file_sha(target)!=info['archive_sha256']:raise io.DPError('ZIP_CONFLICT')
            return str(target)
        temp=output/('joined-data.zip.partial-'+uuid.uuid4().hex);h=hashlib.sha256()
        with temp.open('xb') as dst:
            for item in info['parts']:
                p=parts/item['name']
                if p.is_symlink() or p.stat().st_size!=item['bytes']:raise io.DPError('PART_SIZE')
                ph=hashlib.sha256()
                with p.open('rb') as src:
                    while block:=src.read(1024**2):
                        transport.resources(output);dst.write(block);h.update(block);ph.update(block)
                if ph.hexdigest()!=item['sha256']:raise io.DPError('PART_HASH')
        if h.hexdigest()!=info['archive_sha256']:raise io.DPError('ZIP_HASH')
        temp.rename(target);return str(target)
