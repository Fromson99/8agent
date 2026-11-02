"""Reuse local/cached NFS bytes first. Fetch missing bytes through the existing API."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

GENERATION = '/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation'
SERVICE_SHA = '4128545aa472ea5af38ff50fffb3e65b89cb8c6322940d1f60abbf683c1ae0a9'
CACHE = '_pipeline/existing-nfs-v1/snapshots/'

def bounded(stream, limit):
    data = stream.read(limit + 1)
    if len(data) > limit: raise ValueError('NFS_RESPONSE_TOO_LARGE')
    return data

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('NFS_REDIRECT_REFUSED')

class Wire:
    def __init__(self, variables):
        self.url = os.environ.get('LEGAL_PIPELINE_URL') or variables.get('LEGAL_PIPELINE_URL', '')
        self.token = os.environ.get('LEGAL_PIPELINE_TOKEN') or variables.get('LEGAL_PIPELINE_TOKEN', '')
        p = urllib.parse.urlsplit(self.url)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or not self.token:
            raise ValueError('NFS_CONNECTION_REQUIRED: LEGAL_PIPELINE_URL / LEGAL_PIPELINE_TOKEN 설정 필요')

    def call(self, operation, **fields):
        if operation not in {'EXISTING_NFS_INFO', 'EXISTING_NFS_READ'}: raise ValueError('NFS_READ_ONLY')
        req = urllib.request.Request(self.url, method='POST',
            data=json.dumps(dict(API_TYPE=operation, code_sha256=SERVICE_SHA, **fields)).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        # One attempt per read. Retry the recipe to reuse durable chunks; never retry a write here.
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as response:
                value = json.loads(bounded(response, 8 * 1024**2))
        except urllib.error.HTTPError as exc:
            code = exc.code; exc.close()
            raise RuntimeError('NFS_HTTP_' + str(code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('NFS_NETWORK_READ_FAILED: 같은 단계 재실행 시 수신 완료 조각 재사용') from None
        if not isinstance(value, dict) or value.get('code') != 0 or not isinstance(value.get('data'), dict):
            raise ValueError('NFS_SERVICE_REJECTED')
        return value['data']

def folder_inventory(folder):
    return {p.lstrip('/') for p in folder.list_paths_in_partition()}

def read_json(folder, name):
    with folder.get_download_stream(name) as f: return json.loads(bounded(f, 32 * 1024**2))

def receive(old_job, variables, folders, emit):
    from lawrag.pipeline import oracle_existing_nfs as nfs, oracle_full_package as full
    import run as loader
    local = old_job.parent
    local.mkdir(parents=True, exist_ok=True)
    # Complete local generations need no remote credentials or HTTP calls.
    local_info = None
    if (local / 'full-manifest.json').is_file():
        marker = loader.read(local / 'full-manifest.json')
        info = marker.get('nfs_snapshot')
        if info: nfs.validate_info(info, code_sha256=SERVICE_SHA, generation=GENERATION)
        from semantic_runtime.oracle_dp_assets import checked_path
        declared = info['files'] if info else marker['files']
        missing = any(not checked_path(local, name).is_file() for name in declared)
        if not missing:
            full.verify_restored(local)
            emit('LOCAL_REUSED', origin='Dataiku 로컬', downloaded_bytes=0)
            return {'origin': 'LOCAL_REUSED', 'root': str(local / 'generation'), 'downloaded_bytes': 0}
        local_info = info
    inventories = [(f, folder_inventory(f)) for f in folders]
    infos = {local_info['snapshot_sha256']: local_info} if local_info else {}
    for folder, names in inventories:
        for name in sorted(names):
            if name.startswith(CACHE) and name.endswith('/inventory.json'):
                info = read_json(folder, name)
                nfs.validate_info(info, code_sha256=SERVICE_SHA, generation=GENERATION)
                infos[info['snapshot_sha256']] = info
    if len(infos) > 1: raise ValueError('NFS_MULTIPLE_SNAPSHOTS: 별도 세대 선택 필요')
    wire = None
    if infos:
        info = next(iter(infos.values()))
        origin = 'DATAIKU_CACHE_RESTORED'
    else:
        wire = Wire(variables)
        info = wire.call('EXISTING_NFS_INFO')
        nfs.validate_info(info, code_sha256=SERVICE_SHA, generation=GENERATION)
        origin = 'NFS_API_RECEIVED'
    prefix = CACHE + info['snapshot_sha256'] + '/'
    destination = folders[0]
    destination.upload_stream(prefix + 'inventory.json', io.BytesIO(json.dumps(info).encode()))
    total = sum(v['bytes'] for v in info['files'].values())
    done = downloaded = 0
    started = time.monotonic()
    from semantic_runtime.oracle_dp_assets import checked_path
    for name, item in info['files'].items():
        path = checked_path(local, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.stat().st_size != item['bytes'] or loader.file_hash(path) != item['sha256']:
                raise ValueError('NFS_LOCAL_CONFLICT:' + name)
            done += item['bytes']; continue
        loader.resource_check(local)
        import shutil
        if shutil.disk_usage(local).free < item['bytes'] + 512*1024**2:
            raise ValueError('NFS_LOCAL_SPACE_REQUIRED:' + name)
        partial = path.with_name(path.name + '.flow-partial')
        if partial.is_symlink(): raise ValueError('NFS_PARTIAL_SYMLINK')
        h = hashlib.sha256(); offset = 0
        file_key = hashlib.sha256(name.encode()).hexdigest()
        with partial.open('wb') as target:
            while offset < item['bytes']:
                length = min(nfs.CHUNK, item['bytes'] - offset)
                key = prefix + 'chunks/' + file_key + '/' + str(offset).zfill(16)
                cached = next(((f, ns) for f, ns in inventories if key+'.bin' in ns and key+'.json' in ns), None)
                if cached:
                    folder, _ = cached
                    receipt = read_json(folder, key + '.json')
                    with folder.get_download_stream(key + '.bin') as stream: block = bounded(stream, nfs.CHUNK)
                else:
                    if wire is None:
                        wire = Wire(variables)
                        current = wire.call('EXISTING_NFS_INFO')
                        nfs.validate_info(current, code_sha256=SERVICE_SHA, generation=GENERATION)
                        if current != info: raise ValueError('NFS_SNAPSHOT_CHANGED')
                    value = wire.call('EXISTING_NFS_READ', snapshot_sha256=info['snapshot_sha256'], file=name, offset=offset)
                    block = base64.b64decode(value['content'], validate=True)
                    if (value['snapshot_sha256'] != info['snapshot_sha256'] or value['file'] != name or
                        value['offset'] != offset or value['total_bytes'] != item['bytes'] or value['bytes'] != length or
                        value['sha256'] != hashlib.sha256(block).hexdigest()): raise ValueError('NFS_RESPONSE_BINDING')
                    receipt = {'file': name, 'offset': offset, 'bytes': length, 'sha256': hashlib.sha256(block).hexdigest()}
                    destination.upload_stream(key+'.bin', io.BytesIO(block))
                    destination.upload_stream(key+'.json', io.BytesIO(json.dumps(receipt).encode()))
                    downloaded += len(block)
                if receipt != {'file': name, 'offset': offset, 'bytes': length, 'sha256': hashlib.sha256(block).hexdigest()} or len(block) != length:
                    raise ValueError('NFS_CHUNK_HASH:' + name)
                target.write(block); h.update(block); offset += length
                emit('RECEIVING', bytes_done=done+offset, bytes_total=total, downloaded_bytes=downloaded,
                     asset=name, elapsed_s=time.monotonic()-started)
            target.flush(); os.fsync(target.fileno())
        if h.hexdigest() != item['sha256']: raise ValueError('NFS_FILE_HASH:' + name)
        partial.replace(path); done += item['bytes']
    nfs.finish_received(local, info)
    return {'origin': origin, 'root': str(local/'generation'), 'bytes': total, 'downloaded_bytes': downloaded}

def prepare(old_job, progress):
    import run as loader
    from lawrag.pipeline import oracle_query_package as pack, oracle_deferred_import as deferred
    marker = old_job/'flow-inputs.json'
    if (old_job/'full-state.json').exists():
        values = loader.inputs(old_job, progress)
        origin = 'EXISTING_PREPARATION_REUSED'
    elif marker.exists():
        values = load_prepared(old_job, progress)
        origin = 'FLOW_PREPARATION_REUSED'
    else:
        old_job.mkdir(parents=True, exist_ok=True)
        root, manifest, items, files, selected = pack.immutable_inputs(old_job.parent/'generation')
        source = pack.offline_source(root, manifest, items, selected, lambda: loader.resource_check(old_job))
        paths, tables = deferred.prepared_descriptor(root, source, files, old_job, strict=False)
        query = pack.query_manifest(root, source, paths, tables, items)
        body = {'root': str(root), 'files': files, 'source': source, 'query': query, 'paths': paths,
                'loader_code': loader.verify_code(), 'kind': 'LOCAL_INPUT_PLAN_NOT_DB_VERIFIED'}
        loader.atomic(marker, dict(body, checksum=loader.digest(body)))
        values = (root, files, source, query, paths)
        origin = 'NEW_LOCAL_PREPARATION'
    root, files, source, query, paths = values
    return {'origin': origin, 'root': str(root), 'source_release': loader.digest(source),
            'query_release': loader.digest(query), 'source_rows': sum(v['rows'] for v in source['source_rows'].values()),
            'query_rows': sum(v['rows'] for v in query['tables'].values())}

def load_prepared(old_job, progress):
    import run as loader
    from lawrag.pipeline import oracle_query_package as pack
    v = loader.read(old_job/'flow-inputs.json'); body = {k:x for k,x in v.items() if k!='checksum'}
    if loader.digest(body) != v['checksum'] or v['loader_code'] != loader.verify_code():
        raise ValueError('FLOW_INPUT_DESCRIPTOR_CHANGED')
    root, _, _, files, _ = pack.immutable_inputs(old_job.parent/'generation')
    if str(root) != v['root'] or files != v['files']: raise ValueError('FLOW_INPUT_FILES_CHANGED')
    for name, sha in v['paths'].items():
        p = (root/name).resolve(strict=True)
        if root not in p.parents or loader.file_hash(p) != sha: raise ValueError('FLOW_QUERY_FILE_CHANGED')
    progress.emit('FLOW_PREPARED_INPUTS_REUSED')
    return root, files, v['source'], v['query'], v['paths']

def install_inputs(loader):
    original = loader.inputs
    def inputs(old_job, progress):
        if (old_job/'full-state.json').exists(): return original(old_job, progress)
        return load_prepared(old_job, progress)
    loader.inputs = inputs
