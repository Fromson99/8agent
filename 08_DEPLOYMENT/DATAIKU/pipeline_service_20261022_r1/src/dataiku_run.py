"""Dataiku push client and existing Oracle loaders. No local index rebuild."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.request
import uuid
import transport as t

ROOT = Path(__file__).resolve().parent


class Client:
    def __init__(self, url, token):
        if not url.startswith('https://') or not token:
            raise ValueError('HTTPS_URL_AND_TOKEN_REQUIRED')
        self.url, self.token = url, token

    def call(self, operation, **fields):
        body = json.dumps({'API_TYPE': operation, **fields}).encode('utf-8')
        request = urllib.request.Request(self.url, data=body, method='POST', headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        # Uncertain HTTP results are reconciled by resuming the same job/offset.
        # No hidden retry at multiple layers, TLS verification stays enabled.
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read(4*t.CHUNK+1)
                if len(payload) > 4*t.CHUNK:
                    raise ValueError('RESPONSE_TOO_LARGE')
                value = json.loads(payload)
        except Exception as exc:
            raise RuntimeError('TRANSPORT_UNCERTAIN: rerun the same job directory; ' + type(exc).__name__) from None
        if not isinstance(value, dict) or value.get('code') != 0 or not isinstance(value.get('data'), dict):
            message = value.get('error', 'unexpected envelope') if isinstance(value, dict) else 'unexpected envelope'
            raise RuntimeError('PIPELINE_REPLY: ' + str(message))
        return value['data']


def process(client, input_root, support_zip, job_dir, *, expected_code_sha256, poll_seconds=5):
    input_root, support_zip, folder = Path(input_root), Path(support_zip), Path(job_dir)
    folder.mkdir(parents=True, exist_ok=True)
    with t.lock(folder / 'client.lock'):
        marker = folder / 'client.json'
        if not marker.exists():
            health = client.call('HEALTH')
            if health['code_sha256'] != expected_code_sha256:
                raise ValueError('DEPLOYED_CODE_MISMATCH')
            raw = folder / 'RAW_INPUT.zip'
            paths = {str(p.relative_to(input_root)): p for base in ['01_DATA/RAW', '01_DATA/INPUT_MAPPING']
                     for p in t.files(input_root / base)}
            receipt = t.pack(paths, raw, metadata={'source': 'Dataiku filesystem snapshot; includes newly uploaded internal files'})
            state = {'job_id': uuid.uuid4().hex, 'job_token': secrets.token_hex(32), 'instance': health['instance'],
                     'code_sha256': expected_code_sha256, 'deadline': time.time()+7*86400,
                     'archives': {'raw': {'sha256': receipt['sha256'], 'bytes': receipt['bytes']},
                                  'support': {'sha256': t.sha(support_zip), 'bytes': support_zip.stat().st_size}},
                     'input_root': str(input_root.resolve()), 'support_zip': str(support_zip.resolve()), 'status': 'NEW'}
            t.write(marker, state)
        state = t.read(marker)
        if (state['code_sha256'] != expected_code_sha256 or state['input_root'] != str(input_root.resolve())
                or state['support_zip'] != str(support_zip.resolve())):
            raise ValueError('CLIENT_BINDING_CHANGED')
        auth = {k: state[k] for k in ['job_id', 'job_token', 'instance', 'code_sha256']}
        def call(operation, **fields):
            return client.call(operation, **auth, **fields)
        if state['status'] != 'DOWNLOADED':
            remote = call('START', archives=state['archives'], deadline=state['deadline'])
            if remote['status'] == 'UPLOADING':
                for slot, path in [('raw', folder / 'RAW_INPUT.zip'), ('support', support_zip)]:
                    if t.sha(path) != state['archives'][slot]['sha256']:
                        raise ValueError('INPUT_CHANGED: use a new explicit Dataiku job')
                    offset = remote['received'].get(slot, 0)
                    with path.open('rb') as f:
                        f.seek(offset)
                        for block in iter(lambda: f.read(t.CHUNK), b''):
                            remote = call('UPLOAD', slot=slot, offset=offset,
                                          sha256=hashlib.sha256(block).hexdigest(),
                                          file_content_base64=base64.b64encode(block).decode('ascii'))
                            offset += len(block)
                remote = call('EXECUTE')
            while remote['status'] == 'RUNNING':
                state.update(status='RUNNING', phase=remote.get('phase'))
                t.write(marker, state)
                print('PIPELINE', state['job_id'], state['phase'], flush=True)
                if time.time() >= state['deadline']:
                    call('CANCEL')
                    raise RuntimeError('DEADLINE_EXHAUSTED')
                time.sleep(poll_seconds)
                remote = call('STATUS')
            if remote['status'] != 'COMPLETE':
                state.update(status=remote['status'], remote=remote)
                t.write(marker, state)
                raise RuntimeError('PIPELINE_' + remote['status'] + ': ' + remote.get('error', 'inspect remote job'))
            receipt = remote['result']
            target = folder / 'result.zip'
            temp = folder / 'result.zip.partial'
            if not target.exists():
                offset = temp.stat().st_size if temp.exists() else 0
                with temp.open('ab') as dst:
                    while offset < receipt['bytes']:
                        result = call('DOWNLOAD', file_name='result.zip', offset=offset)
                        block = base64.b64decode(result['file_content_base64'], validate=True)
                        if (result['offset'] != offset or not block or len(block) != result['bytes']
                                or hashlib.sha256(block).hexdigest() != result['sha256']):
                            raise ValueError('RETURN_CHUNK_HASH')
                        dst.write(block)
                        dst.flush()
                        os.fsync(dst.fileno())
                        offset += len(block)
                if offset != receipt['bytes'] or t.sha(temp) != receipt['sha256']:
                    raise ValueError('RETURN_ARCHIVE_HASH: preserve partial; do not load Oracle')
                temp.rename(target)
            if target.stat().st_size != receipt['bytes'] or t.sha(target) != receipt['sha256']:
                raise ValueError('RETURN_ARCHIVE_HASH')
            state.update(status='DOWNLOADED', result=receipt)
            t.write(marker, state)
        target = folder / 'result.zip'
        if t.sha(target) != state['result']['sha256']:
            raise ValueError('LOCAL_RESULT_CHANGED')
        restored = folder / 'returned'
        manifest = t.unpack(target, restored, prefixes=('generation/', 'SEARCH_SELECTION/', 'query/', 'audit/'))
        if manifest['metadata']['code_sha256'] != expected_code_sha256:
            raise ValueError('RETURN_CODE_BINDING')
        t.write(restored / 'transport-manifest.json', manifest)
        # Result is durable in Dataiku; the serving scratch can now be removed.
        if not state.get('scratch_released'):
            call('ACK', result_sha256=state['result']['sha256'])
            state['scratch_released'] = True
            t.write(marker, state)
        return restored


def load_oracle(client, returned, job_dir, *, target_binding, seconds=21600):
    """Source -> verified asset release -> GENOS-precomputed query rows. Append only."""
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from lawrag.pipeline import oracle_migration as source, oracle_publish as assets
    from lawrag.pipeline import oracle_query_package as query, oracle_query_publish as query_publish
    from semantic_runtime import oracle_dp_io as io, oracle_dp_assets as asset_io
    returned, logs = Path(returned), Path(job_dir) / 'oracle'
    info = t.read(returned / 'transport-manifest.json')
    for name, item in info['files'].items():
        if t.sha(t.checked(returned, name)) != item['sha256']:
            raise ValueError('RETURNED_FILE_CHANGED: ' + name)
    generation = returned / 'generation'
    with t.lock(logs / 'orchestrator.lock'):
        marker = logs / 'load.json'
        identity = {'target': target_binding, 'result_manifest': t.digest(info)}
        state = t.read(marker) if marker.exists() else {'identity': identity, 'deadline': time.time()+7*86400}
        if state['identity'] != identity:
            raise ValueError('ORACLE_TARGET_CHANGED')
        t.write(marker, state)
        end = min(time.time()+seconds, state['deadline'])
        def remaining():
            n = int(end-time.time())
            if n < 1:
                raise io.BudgetPause('LOAD_BUDGET: resume same Dataiku job')
            return min(n, 21600)
        try:
            # Check all seven tables before any insert; no DDL, truncate or delete.
            sql = io.SQL(client, journal=logs / 'schema.jsonl', binding=target_binding, seconds=remaining())
            io.check_source_tables(sql)
            for table, columns in [(asset_io.PART_TABLE, 'ASSET_SHA256,PART_NO,RAW_BYTES,PART_SHA256,DATA_B64'),
                                   (asset_io.RELEASE_TABLE, 'RELEASE_ID,DATASET_VERSION,RELEASE_JSON')]:
                sql.query(f'SELECT {columns} FROM {table} WHERE 1=0')
            if query_publish.schema(sql, create=False)['status'] != 'READY':
                raise ValueError('QUERY_SCHEMA_NOT_READY')
            results = {}
            for action in ['run', 'verify']:
                results[action] = source.transfer(client, generation / 'store.sqlite', target_binding=target_binding,
                         directory=logs / 'source', action=action, seconds=remaining())
                if results[action]['status'] == 'PAUSED':
                    raise io.BudgetPause('SOURCE_PAUSED')
            asset = assets.publish(client, source=generation / 'store.sqlite', transfer_receipt=results['verify']['receipt'],
                      target_binding=target_binding, directory=logs / 'assets', seconds=remaining())
            if asset['status'] != 'COMPLETE':
                raise io.BudgetPause('ASSET_PAUSED')
            # Resumed publisher receipts cannot substitute for current Oracle bytes.
            meta = query.verify_db(returned / 'query/query-data.db')
            verify = io.SQL(client, journal=logs / 'asset-readback.jsonl', binding=target_binding, seconds=remaining())
            expected = meta['source_release']
            if asset_io.get_release(verify, asset['release_id']) != expected:
                raise ValueError('SOURCE_RELEASE_READBACK')
            for item in expected['assets']:
                h = hashlib.sha256()
                size = 0
                for number in range(item['parts']):
                    block = asset_io.get_part(verify, item['sha256'], number)
                    if block is None:
                        raise ValueError('ASSET_MISSING')
                    size += len(block)
                    h.update(block)
                if size != item['bytes'] or h.hexdigest() != item['sha256']:
                    raise ValueError('ASSET_READBACK')
            query_state = logs / 'query/state.json'
            query_action = 'status' if query_state.exists() and t.read(query_state).get('status') == 'COMPLETE' else 'publish'
            result = query.import_db(client, returned / 'query/query-data.db', target_binding=target_binding,
                      directory=logs / 'query', action=query_action, seconds=remaining())
            # Query importer rereads every row; the source/assets were reread above.
            state.update(status='COMPLETE', source_release_id=asset['release_id'], query=result,
                         active_changed=False, state_migrated=False)
            t.write(marker, state)
            return state
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc, io.BudgetPause) else 'FAILED',
                         error=str(exc) if isinstance(exc, (io.DPError, ValueError)) else type(exc).__name__)
            t.write(marker, state)
            raise


def run_dataiku(input_root, support_zip, job_dir):
    import dataiku
    from dataiku import SQLExecutor2
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient
    variables = dataiku.get_custom_variables()
    remote = Client(variables['LEGAL_PIPELINE_URL'], variables['LEGAL_PIPELINE_TOKEN'])
    expected = (ROOT / 'SERVICE_CODE_SHA256.txt').read_text().strip()
    returned = process(remote, input_root, support_zip, job_dir, expected_code_sha256=expected)
    connection = variables['LEGAL_ORACLE_CONNECTION']
    oracle = DataikuClient(SQLExecutor2(connection=connection), connection, dataiku.default_project_key())
    binding, _ = oracle.identity()
    return load_oracle(oracle, returned, job_dir, target_binding=binding)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root', required=True, type=Path)
    p.add_argument('--support-zip', required=True, type=Path)
    p.add_argument('--job-dir', required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(run_dataiku(a.input_root, a.support_zip, a.job_dir), ensure_ascii=False))
