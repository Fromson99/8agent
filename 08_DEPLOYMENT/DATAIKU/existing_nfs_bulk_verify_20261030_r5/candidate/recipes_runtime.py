"""DSS Flow stages around the sealed GENOS R2 client and Oracle loaders."""
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import dataiku_run as client
import legacy_runner as legacy
import transport as t
from managed_job import ManagedJob, BudgetClient, bounded_read

VERSION = 'recipes-20261027-r1'
ROOT = Path(__file__).resolve().parent
EXPECTED = (ROOT / 'client/SERVICE_CODE_SHA256.txt').read_text().strip()


def read_json(folder, name, limit=64*1024*1024):
    with folder.get_download_stream(name) as stream:
        return json.loads(bounded_read(stream, limit))


def object_hash(folder, name, size):
    h, count = hashlib.sha256(), 0
    with folder.get_download_stream(name) as stream:
        for block in iter(lambda: stream.read(t.CHUNK), b''):
            count += len(block)
            if count > size:
                raise ValueError('S3_OBJECT_SIZE')
            h.update(block)
    if count != size:
        raise ValueError('S3_OBJECT_SIZE')
    return h.hexdigest()


def put_file(folder, name, path, known=None):
    """Never overwrite a different object; publication requires remote readback."""
    path = Path(path)
    expected, size = t.sha(path), path.stat().st_size
    if known is None:
        known = {p.lstrip('/') for p in folder.list_paths_in_partition()}
    if name not in known:
        with path.open('rb') as stream:
            folder.upload_stream(name, stream)
    if object_hash(folder, name, size) != expected:
        raise ValueError('S3_OBJECT_CONFLICT_OR_READBACK: ' + name)
    known.add(name)
    return {'path': name, 'sha256': expected, 'bytes': size}


def put_json(folder, name, value, work):
    path = Path(work) / ('record-' + uuid.uuid4().hex + '.json')
    t.write(path, value)
    return put_file(folder, name, path)


def input_receipts(landing):
    """Accept the exact original names or the browser's single '(1)' copy."""
    paths = {p.lstrip('/'): p for p in landing.list_paths_in_partition()}
    result = {}
    for name in ('RAW_INPUT.zip', 'PIPELINE_SUPPORT.zip'):
        candidates = [name, name.replace('.zip', ' (1).zip')]
        receipts = [name + '.receipt.json', name + '.receipt (1).json']
        actual = [paths[p] for p in candidates if p in paths]
        proof = [paths[p] for p in receipts if p in paths]
        if len(actual) != 1 or len(proof) != 1:
            raise ValueError('INPUT_NAME_AMBIGUOUS_OR_MISSING: ' + name)
        value = legacy.read_receipt(landing, proof[0], name)
        result[name] = {**value, 'remote': actual[0]}
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another endpoint.


class CheckedClient(client.Client):
    """Existing wire contract, one HTTP attempt, secret-free diagnostic codes."""
    def call(self, operation, **fields):
        parsed = urllib.parse.urlsplit(self.url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment):
            raise ValueError('HTTPS_ENDPOINT_REQUIRED')
        request = urllib.request.Request(self.url, method='POST',
            data=json.dumps({'API_TYPE': operation, **fields}).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token})
        try:
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=120) as response:
                payload = bounded_read(response, 4*t.CHUNK)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise RuntimeError('GENOS_HTTP_' + str(status)) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, ssl.SSLCertVerificationError): code = 'GENOS_TLS_CERTIFICATE'
            elif isinstance(reason, ssl.SSLError): code = 'GENOS_TLS'
            elif isinstance(reason, socket.gaierror): code = 'GENOS_DNS'
            elif isinstance(reason, (TimeoutError, socket.timeout)): code = 'GENOS_TIMEOUT'
            else: code = 'GENOS_NETWORK'
            raise RuntimeError(code) from None
        except (TimeoutError, socket.timeout):
            raise RuntimeError('GENOS_TIMEOUT') from None
        try:
            reply = json.loads(payload)
        except (ValueError, UnicodeError):
            raise RuntimeError('GENOS_NOT_JSON') from None
        if not isinstance(reply, dict) or reply.get('code') != 0 or not isinstance(reply.get('data'), dict):
            # Server text can contain capabilities/echoed request data. Keep a hash,
            # never arbitrary response text in a DSS public log.
            code = 'GENOS_REPLY_' + hashlib.sha256(payload).hexdigest()[:16]
            if isinstance(reply, dict) and isinstance(reply.get('error'), str):
                if reply['error'].split(':', 1)[0] in {'BUSY','INSTANCE_MISMATCH','CODE_MISMATCH','UNKNOWN_JOB','COMPUTE_INSTANCE_CHANGED','COMPUTE_HANDLE_GONE','COMPUTE_LEASE_EXPIRED','COMPUTE_CAPACITY','COMPUTE_AUTH','PREPROCESSOR_MODE_REQUIRED','PREPROCESSOR_ENDPOINT_REQUIRED','PREPROCESSOR_SHARED_ROOT_REQUIRED','PREPROCESSOR_CONFIG_INVALID','PREPROCESSOR_SHARED_ROOT_UNAVAILABLE','PREPROCESSOR_RESPONSE_MODE_INVALID','PREPROCESSOR_REVIEW_CONFIG_REQUIRED','AUDIT_NOT_READY','AUDIT_RECEIPT_REQUIRED','PREPROCESSOR_CONFIG_CHANGED'}:
                    code = 'GENOS_' + reply['error'].split(':', 1)[0]
            raise RuntimeError(code)
        return reply['data']


def remote_client(variables):
    for key in ('LEGAL_PIPELINE_URL', 'LEGAL_PIPELINE_TOKEN'):
        if not isinstance(variables.get(key), str) or not variables[key].strip():
            raise ValueError('PROJECT_VARIABLE_REQUIRED: ' + key)
    return CheckedClient(variables['LEGAL_PIPELINE_URL'], variables['LEGAL_PIPELINE_TOKEN'])


def connection(variables, output, work):
    result = {'operation': 'HEALTH', 'oracle_written': False, 'documents_sent': 0,
              'checked_at': time.time(), 'expected_code_sha256': EXPECTED}
    try:
        remote = remote_client(variables)
        result['endpoint_sha256'] = hashlib.sha256(remote.url.encode()).hexdigest()
        start = time.monotonic()
        health = remote.call('HEALTH')
        result['elapsed_seconds'] = round(time.monotonic()-start, 3)
        observed = health.get('code_sha256')
        result['observed_code_sha256'] = observed if isinstance(observed, str) and re.fullmatch(r'[0-9a-f]{64}', observed) else 'INVALID'
        if health.get('code_sha256') != EXPECTED:
            raise ValueError('DEPLOYED_CODE_MISMATCH')
        if not isinstance(health.get('instance'), str) or not health['instance']:
            raise ValueError('GENOS_HEALTH_CONTRACT')
        result['status'] = 'CONNECTED_CODE_MATCH'
    except Exception as exc:
        result.update(status='FAILED', error=legacy._redact(str(exc), (variables.get('LEGAL_PIPELINE_TOKEN',''),)))
        put_json(output, 'checks/' + uuid.uuid4().hex + '.json', result, work)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        raise
    put_json(output, 'checks/' + uuid.uuid4().hex + '.json', result, work)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def raw_manifest(raw_folder, receipt):
    sha = receipt['sha256']
    record = read_json(raw_folder, 'snapshots/' + sha + '/manifest.json')
    if record['archive_sha256'] != sha or record['archive_bytes'] != receipt['bytes']:
        raise ValueError('RAW_SNAPSHOT_BINDING')
    return record


def unpack_raw(landing, output, work):
    receipt = input_receipts(landing)['RAW_INPUT.zip']
    archive = work / 'RAW_INPUT.zip'
    legacy.download(landing, receipt['remote'], archive, receipt['sha256'], receipt['bytes'], work)
    extracted = work / 'raw'
    manifest = t.unpack(archive, extracted, prefixes=('01_DATA/RAW/', '01_DATA/INPUT_MAPPING/'))
    prefix = 'snapshots/' + receipt['sha256']
    known = {p.lstrip('/') for p in output.list_paths_in_partition()}
    files = {}
    for name, item in sorted(manifest['files'].items()):
        path = t.checked(extracted, name)
        saved = put_file(output, prefix + '/files/' + name, path, known)
        if saved['sha256'] != item['sha256']:
            raise ValueError('RAW_CHANGED_AFTER_EXTRACT')
        files[name] = saved
    record = {'archive_sha256': receipt['sha256'], 'archive_bytes': receipt['bytes'],
              'files': files, 'format': 'legal-raw-s3-v1'}
    put_json(output, prefix + '/manifest.json', record, work)
    return {'status': 'RAW_SAVED', 'files': len(files), 'prefix': prefix, 'oracle_written': False}


def materialize(raw, record, work):
    destination = work / 'inputs'
    for name, item in record['files'].items():
        if not name.startswith(('01_DATA/RAW/', '01_DATA/INPUT_MAPPING/')):
            raise ValueError('RAW_SCOPE')
        path = t.checked(destination, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy.download(raw, item['path'], path, item['sha256'], item['bytes'], work)
    return destination


def context(cfg, receipts, variables):
    import dataiku
    from lawrag.pipeline.oracle_query_dataiku import DataikuClient
    from semantic_runtime.physical_mapping import SchemaMap
    schema = SchemaMap.load(ROOT/'client/physical_mapping.yaml',
                            expected_sha256=t.read(ROOT/'client/MAPPING_BINDING.json')['yaml_sha256'])
    connection_name = variables.get('LEGAL_ORACLE_CONNECTION', 'AIDP')
    if connection_name != 'AIDP':
        raise ValueError('CONNECTION_CHANGED')
    oracle = DataikuClient(dataiku.SQLExecutor2(connection=connection_name), connection_name,
                          dataiku.default_project_key(), schema_map=schema)
    binding, _ = oracle.identity()
    remote = remote_client(variables)
    identity = {'version': VERSION, 'input': {
        'landing': cfg['landing'], 'raw': cfg['raw'],
        'archives': {n: {k:r[k] for k in ('sha256', 'bytes')} for n,r in receipts.items()}},
        'database': binding, 'service_code': EXPECTED,
        'service_url_sha256': hashlib.sha256(remote.url.encode()).hexdigest()}
    return oracle, binding, remote, identity


def structured_record(store):
    return {'status': 'STRUCTURED', 'state_sha256': t.digest(store.value),
            'binding': store.value['binding'], 'result_blob': store.value['result_blob'],
            'deadline': store.value['deadline'], 'oracle_written': False}


def structure(cfg, folders, variables, work, job_name):
    from semantic_runtime import oracle_dp_io as dbio
    receipts = input_receipts(folders['landing'])
    oracle, binding, remote, identity = context(cfg, receipts, variables)
    store = ManagedJob(folders['structured'], job_name, identity)
    job = work / 'job'
    try:
        if store.value.get('phase') != 'STRUCTURED':
            bounded = BudgetClient(oracle, store)
            oracle.schema_map.preflight(dbio.SQL(bounded, journal=work/'preflight.jsonl', binding=binding))
            record = raw_manifest(folders['raw'], receipts['RAW_INPUT.zip'])
            inputs = materialize(folders['raw'], record, work)
            support = receipts['PIPELINE_SUPPORT.zip']
            support_path = work / 'PIPELINE_SUPPORT.zip'
            legacy.download(folders['landing'], support['remote'], support_path,
                            support['sha256'], support['bytes'], work)
            store.restore(job)
            client.process(remote, inputs, support_path, job, expected_code_sha256=EXPECTED,
                           checkpoint=store.checkpoint_client, deadline=store.value['deadline'])
            store.value['phase'] = 'STRUCTURED'
            store.save()
        # No ACK here: returned bytes and capability remain available to the loader.
        record = structured_record(store)
        put_json(folders['structured'], 'jobs/'+job_name+'/structured.json', record, work)
        return {k:v for k,v in record.items() if k != 'binding'}
    except BaseException:
        # process checkpoints its durable state. Never replace it with a new job.
        raise


class ReadOnlyFolder:
    def __init__(self, folder): self.folder = folder
    def list_paths_in_partition(self): return self.folder.list_paths_in_partition()
    def get_download_stream(self, name): return self.folder.get_download_stream(name)
    def upload_stream(self, *args): raise ValueError('UPSTREAM_STAGE_NOT_READY')


def seed_load(store, upstream):
    """Persist original global bounds before any SQL can be sent."""
    source = upstream.value
    if 'seeded_from' not in store.value:
        store.value.update(deadline=source['deadline'], reserved_sql_calls=source['reserved_sql_calls'],
                           client=copy.deepcopy(source['client']), seeded_from=t.digest(source))
        store.save()
    if (store.value['seeded_from'] != t.digest(source)
            or store.value['deadline'] != source['deadline']
            or store.value['reserved_sql_calls'] < source['reserved_sql_calls']):
        raise ValueError('UPSTREAM_OR_BUDGET_CHANGED')


def load(cfg, folders, variables, work, job_name):
    receipts = input_receipts(folders['landing'])
    oracle, binding, remote, identity = context(cfg, receipts, variables)
    upstream = ManagedJob(ReadOnlyFolder(folders['structured']), job_name, identity)
    proof = read_json(folders['structured'], 'jobs/'+job_name+'/structured.json')
    if upstream.value.get('phase') != 'STRUCTURED' or proof != structured_record(upstream):
        raise ValueError('UPSTREAM_NOT_STRUCTURED_OR_CHANGED')
    store = ManagedJob(folders['load'], job_name, {**identity, 'structured_state': proof['state_sha256']})
    seed_load(store, upstream)
    bounded = BudgetClient(oracle, store)
    job = work / 'job'
    job.mkdir(parents=True, exist_ok=True)
    upstream.get_blob(proof['result_blob'], job/'result.zip')
    returned = job/'returned'
    manifest = t.unpack(job/'result.zip', returned, prefixes=('generation/', 'SEARCH_SELECTION/', 'query/', 'audit/'))
    if manifest['metadata']['code_sha256'] != EXPECTED:
        raise ValueError('RETURN_CODE_BINDING')
    t.write(returned/'transport-manifest.json', manifest)
    attempt = job/'oracle-attempt'
    try:
        result = client.load_oracle(bounded, returned, attempt, target_binding=binding, deadline=store.value['deadline'])
        paths = {str(p.relative_to(attempt)):p for p in t.files(attempt) if p.suffix in ('.json','.jsonl')}
        snapshot = job/'receipts.zip'
        t.pack(paths, snapshot, metadata={'target': binding, 'result_sha256': proof['result_blob']['sha256']})
        store.value.update(phase='LOAD_VERIFIED', oracle_written=True, load_receipt=result,
                           receipt_blob=store.put_blob(snapshot))
        store.save()
        state = store.value['client']
        if not state.get('scratch_released'):
            auth = {k:state[k] for k in ('job_id','job_token','instance','code_sha256')}
            remote.call('ACK', **auth, result_sha256=state['result']['sha256'])
            state['scratch_released'] = True
        store.value['phase'] = 'COMPLETE'
        store.save()
        summary = {'status': 'COMPLETE', 'oracle_written': True,
                   'source_release_id': result['source_release_id'],
                   'query_release_id': result['query']['release_id'], 'query_rows': result['query']['rows'],
                   'target': 'SIDDS.*_S', 'active_changed': False, 'state_migrated': False}
        put_json(folders['load'], 'jobs/'+job_name+'/complete.json', summary, work)
        return summary
    except BaseException as exc:
        store.value.update(phase=('LOAD_VERIFIED_ACK_PENDING' if store.value.get('phase') == 'LOAD_VERIFIED' else 'STOPPED'),
                           last_error=type(exc).__name__)
        try:
            if attempt.exists():
                snapshot = job/('failure-receipts-'+uuid.uuid4().hex+'.zip')
                paths = {str(p.relative_to(attempt)):p for p in t.files(attempt) if p.suffix in ('.json','.jsonl')}
                t.pack(paths, snapshot, metadata={'failure': type(exc).__name__})
                store.value['failure_receipt_blob'] = store.put_blob(snapshot)
            store.save()
        except Exception:
            print('CHECKPOINT_SAVE_FAILED; local journals retained', flush=True)
        raise


def execute(stage, cfg, work):
    import dataiku
    if dataiku.default_project_key() != 'LEGAL_RAG':
        raise ValueError('PROJECT_MISMATCH')
    variables = dataiku.get_custom_variables()
    job_name = variables.get('LEGAL_RECIPE_JOB_NAME', 'recipes_20261027_r1')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', job_name):
        raise ValueError('JOB_NAME')
    # Only instantiate folders declared by this recipe; DSS enforces the Flow scope.
    roles = {'connection': ('connection',), 'unpack': ('landing','raw'),
             'structure': ('landing','raw','structured'), 'load': ('landing','structured','load')}[stage]
    folders = {key:dataiku.Folder(cfg[key]) for key in roles}
    out = folders[{'connection':'connection','unpack':'raw','structure':'structured','load':'load'}[stage]]
    try:
        if stage == 'connection': return connection(variables, out, work)
        if stage == 'unpack': result = unpack_raw(folders['landing'], out, work)
        elif stage == 'structure': result = structure(cfg, folders, variables, work, job_name)
        else: result = load(cfg, folders, variables, work, job_name)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    except BaseException as exc:
        # Existing diagnostic redaction retains useful SQL/transport failure chains.
        try:
            legacy.report_failure(exc, work=work, action=stage, job_name=job_name, folder=out, phase=stage)
        except Exception:
            print('DIAGNOSTIC_SAVE_FAILED; original local records retained', flush=True)
        raise
