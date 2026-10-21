"""Publish verified source version + declared serving assets to Oracle; no NFS mutation."""
from __future__ import annotations
import fcntl
import hashlib
import json
from pathlib import Path
import time

from semantic_runtime.oracle_dp_io import SQL, DPError, BudgetPause, atomic_json, digest, file_sha
from semantic_runtime.oracle_dp_assets import inventory, put_part, put_release, checked_path, PART_BYTES, SCHEMA
from .oracle_migration import source_binding, unchanged, signature, SOURCE


def publish(client, *, source, transfer_receipt, target_binding, directory, seconds=3600):
    binding, manifest=source_binding(source)
    transfer=json.loads(Path(transfer_receipt).read_text())
    if (transfer.get('status')!='VERIFIED' or transfer['binding']!={**binding,'target_binding':target_binding}
            or transfer.get('pending') is not None or set(transfer.get('tables',{}))!={'document','source_unit','block_payload'}):
        raise DPError('TRANSFER_FIRST: run full source transfer and ACTION="verify" with this same target/source')
    root=Path(binding['source_path']).parent
    # Only small explicit file-list metadata and declared serving files are read.
    manifest,assets=inventory(root)
    selection=root.parent/'SEARCH_SELECTION'/(root.name+'.json')
    selection_value=json.loads(selection.read_text()) if selection.is_file() else None
    if selection_value and (selection_value['store_sha256']!=manifest['store_sha256'] or
                            selection_value['manifest_sha256']!=binding['dataset_version']):
        raise DPError('SELECTION_BINDING: source selection differs')
    source_rows={k:{'rows':v['rows'],'chain':v['chain']} for k,v in transfer['tables'].items()}
    value={'schema_version':SCHEMA,'status':'COMPLETE','dataset_version':binding['dataset_version'],
           'source_manifest':manifest,'source_manifest_text':(root/'manifest.json').read_text(),
           'source_rows':source_rows,'assets':assets,'search_selection':selection_value,
           'codec':'zlib-per-1MiB-part-v1','source_projection':'compact-source-v2-logical-rows-v1'}
    release_id=digest(value)
    folder=Path(directory)/release_id;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'publish.lock').open('a') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise DPError('IN_PROGRESS: release publication is already running') from None
        receipt=folder/'state.json'
        state=json.loads(receipt.read_text()) if receipt.exists() else {
            'release_id':release_id,'target_binding':target_binding,'deadline':time.time()+7*86400,'files':{}}
        if state['release_id']!=release_id or state['target_binding']!=target_binding:
            raise DPError('PUBLISH_BINDING: resume differs')
        sql=SQL(client,journal=folder/'calls.jsonl',binding=target_binding,
                seconds=max(0,min(seconds,state['deadline']-time.time())))
        try:
            for asset in assets:
                path=checked_path(root,asset['path']);before=signature(path)
                progress=state['files'].get(asset['path'],{})
                start=progress.get('next_part',0)
                if progress and progress['file_signature']!=before:
                    raise DPError('ASSET_CHANGED: input changed since prior upload')
                with path.open('rb') as f:
                    f.seek(start*PART_BYTES)
                    for number in range(start,asset['parts']):
                        raw=f.read(PART_BYTES)
                        expected=min(PART_BYTES,asset['bytes']-number*PART_BYTES)
                        if len(raw)!=expected:raise DPError('ASSET_CHANGED: file length changed')
                        put_part(sql,asset['sha256'],number,raw)
                        if signature(path)!=before:raise DPError('ASSET_CHANGED: input changed during upload')
                        state['files'][asset['path']]={'next_part':number+1,'file_signature':before}
                        state['status']='UPLOADING';atomic_json(receipt,state)
                        if number==start or (number+1)%100==0:
                            print(f'{asset["path"]}: {number+1}/{asset["parts"]} parts verified',flush=True)
                if file_sha(path)!=asset['sha256']:raise DPError('ASSET_HASH: input changed before publication')
                state['files'][asset['path']]={'next_part':asset['parts'],'file_signature':before,'verified':True}
                atomic_json(receipt,state)
            unchanged(binding)
            if selection_value!=(json.loads(selection.read_text()) if selection.is_file() else None):
                raise DPError('SELECTION_CHANGED: selection changed during publication')
            result=put_release(sql,value)
            state.update(status='COMPLETE',completed_at=time.time());atomic_json(receipt,state)
            print('DP_RELEASE_ID='+result,flush=True)
            print('Oracle 원문 버전과 색인 자산 게시 완료. DP 서빙 배포/워크플로우 확인은 별도입니다.',flush=True)
            return {'status':'COMPLETE','release_id':result,'receipt':str(receipt)}
        except BudgetPause as exc:
            state.update(status='PAUSED',reason=str(exc));atomic_json(receipt,state)
            return {'status':'PAUSED','receipt':str(receipt)}
        except Exception as exc:
            message=str(exc) if isinstance(exc,DPError) else type(exc).__name__
            state.update(status='FAILED',error=message);atomic_json(receipt,state)
            sql.event('PUBLISH_FAILED',error=message)
            raise DPError(message+'; publication receipt='+str(receipt)) from None


def from_notebook(desk, transfer_receipt, *, source=SOURCE, seconds=3600):
    check=desk.require_connection()
    if desk.recovery_required or getattr(check.client,'deadline',None) is not None:
        raise DPError('R6_STATE: prior hold or another running cell')
    return publish(check.client,source=source,transfer_receipt=transfer_receipt,target_binding=desk.binding(),
        directory=Path(desk.settings.get('log_dir') or './ords_notebook_logs')/'legal_dp_publish',seconds=seconds)
