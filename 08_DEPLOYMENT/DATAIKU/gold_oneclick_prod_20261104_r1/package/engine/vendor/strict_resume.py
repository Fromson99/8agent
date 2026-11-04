"""Resume only from retained local input/receipts; never fetch or rebuild."""
import json
from pathlib import Path
import re


def local_snapshot(store, local, *, expected_code, generation):
    from lawrag.pipeline import oracle_existing_nfs as nfs
    from semantic_runtime.oracle_dp_assets import checked_path
    from lawrag.pipeline.oracle_query_package import bounded_json
    marker=Path(local)/'full-manifest.json'
    if not marker.is_file():raise ValueError('RESUME_LOCAL_DATA_MISSING: no automatic download')
    value=bounded_json(marker)
    info=value.get('nfs_snapshot')
    if not isinstance(info,dict):raise ValueError('RESUME_SNAPSHOT_REQUIRED')
    nfs.validate_info(info,code_sha256=expected_code,generation=generation)
    if (store.value.get('snapshot_sha256')!=info['snapshot_sha256'] or
            value.get('files')!=info['files'] or value.get('dataset_version')!=info['dataset_version']):
        raise ValueError('RESUME_SNAPSHOT_BINDING')
    for relative,item in info['files'].items():
        path=checked_path(Path(local),relative)
        if not path.is_file() or path.stat().st_size!=item['bytes']:
            raise ValueError('RESUME_LOCAL_DATA_MISSING: no automatic download')
    print('RESUME_LOCAL_INPUTS_FOUND: NFS 요청 없이 기존 로컬 수신 자료 사용',flush=True)
    return info


def require_preparation(attempt):
    from lawrag.pipeline.oracle_query_package import bounded_json
    from semantic_runtime.oracle_dp_io import digest
    attempt=Path(attempt)
    if not (attempt/'full-state.json').is_file():raise ValueError('RESUME_IMPORT_RECEIPT_REQUIRED')
    path=attempt/'projection-descriptor-r7.json'
    if not path.is_file():raise ValueError('RESUME_PREPARATION_REQUIRED: no automatic full preparation')
    saved=bounded_json(path);body={k:v for k,v in saved.items() if k!='checksum'}
    if saved.get('checksum')!=digest(body):raise ValueError('RESUME_PREPARATION_CHECKSUM')
    return body


def source_descriptor(root, manifest, items, files, selected, logs, target_binding, counts):
    from lawrag.pipeline import oracle_migration as migration
    from lawrag.pipeline.oracle_query_package import bounded_json
    from semantic_runtime import oracle_dp_assets as assets,oracle_dp_io as io
    saved=require_preparation(logs)
    if saved.get('binding',{}).get('files')!=files:
        raise io.DPError('RESUME_PREPARATION_FILES_CHANGED')
    binding,_=migration.source_binding(Path(root)/'store.sqlite')
    binding['target_binding']=target_binding
    for path in sorted((Path(logs)/'source').glob('*/state.json')):
        state=bounded_json(path)
        # A later remote verification failure does not erase the completed local
        # descriptor. It certifies no Oracle contents: verify still reads anew.
        completed=state.get('status') in {'VERIFIED','SOURCE_STAGED','SOURCE_COMPLETE'}
        prior_completion=(state.get('status') in {'FAILED','PAUSED'}
            and type(state.get('completed_at')) in (int,float)
            and state.get('source_hash_verified') is True and state.get('counts')==counts)
        if (state.get('binding')!=binding or state.get('pending') is not None
                or not (completed or prior_completion)):continue
        tables=state.get('tables',{})
        if set(tables)!=set(io.TABLES):continue
        rows={}
        for kind in io.TABLES:
            value=tables[kind]
            if type(value.get('rows')) is not int or value['rows']!=counts[kind] or not re.fullmatch('[0-9a-f]{64}',str(value.get('chain',''))):break
            rows[kind]={'rows':value['rows'],'chain':value['chain']}
        if len(rows)!=len(io.TABLES):continue
        source={'schema_version':assets.SCHEMA,'status':'COMPLETE',
            'dataset_version':files['manifest.json'],'source_manifest':manifest,
            'source_manifest_text':(Path(root)/'manifest.json').read_text(),
            'source_rows':rows,'assets':items,'search_selection':selected,
            'codec':'zlib-per-1MiB-part-v1','source_projection':'compact-source-v2-logical-rows-v1'}
        if io.digest(source)!=saved.get('binding',{}).get('source'):continue
        migration.unchanged(binding)
        print('RESUME_SOURCE_DESCRIPTOR_REUSED: 원문 행 전체 재계산 생략',flush=True)
        return source
    raise io.DPError('RESUME_COMPLETED_SOURCE_RECEIPT_REQUIRED: no automatic source scan')
