"""Push-only ingestion contracts; tiny synthetic data, no GENOS/model/Oracle calls."""
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[2]
DELIVERY = REPO / '08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r1'
sys.path.insert(0, str(DELIVERY / 'src'))
import transport as t
import export_inputs as exporter
import restore_inputs
import dataiku_run as dku
import worker
spec = importlib.util.spec_from_file_location('pipeline_only_service', DELIVERY / 'src/service.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def selection(dev, rows):
    value = {'schema_version': 'filename-search-selection-v2', 'latest_documents': rows,
             'excluded': [r for r in rows if not r['is_latest']],
             'exceptions': {'value': t.read(REPO / '00_SYSTEM/FILENAME_EXCEPTIONS.json')}}
    p = dev / '00_SYSTEM/SEARCH_SELECTION/generation.json'
    t.write(p, value)
    t.write(dev / '00_SYSTEM/GENOS_SERVING_PATHS.json', {'search_selection': {
        'path': str(p.relative_to(dev)), 'sha256': t.sha(p)}})
    return value


def support(dev, term_glossary):
    config = t.read(REPO / '00_SYSTEM/GLOSSARY_PIPELINE.json')
    draft = dev / '01_DATA' / config['current_draft']['path']
    knowledge = dev / '01_DATA' / config['knowledge_bundle']['path']
    shutil.copytree(term_glossary, draft)
    shutil.copytree(term_glossary.parent / 'knowledge', knowledge)
    report = t.read(draft / 'report.json')
    report.pop('knowledge_binding')
    t.write(draft / 'report.json', report)
    config['knowledge_bundle']['manifest_sha256'] = t.sha(knowledge / 'manifest.json')
    t.write(dev / '00_SYSTEM/GLOSSARY_PIPELINE.json', config)
    t.write(dev / '01_DATA/CATALOG/TEAM_LAYOUT.json', {'schema_version': 'team-raw-v1', 'files': {}})


def test_export_uses_rag_latest_hash_not_mtime_and_preserves_original(tmp_path, term_glossary):
    dev = tmp_path / 'dev'
    raw = dev / '01_DATA/RAW/internal/risk_team'
    raw.mkdir(parents=True)
    old, new, unknown = [raw / n for n in ['규정(20240101).docx', '규정(20250101).docx', '미등록.docx']]
    for p in [old, new, unknown]:
        p.write_text(p.name)
    os.utime(old, (time.time()+100, time.time()+100))
    selection(dev, [{'document_id': 'old', 'source_artifact_sha256': t.sha(old), 'is_latest': False},
                    {'document_id': 'new', 'source_artifact_sha256': t.sha(new), 'is_latest': True}])
    support(dev, term_glossary)
    before = {p: t.sha(p) for p in [old, new, unknown]}
    output = tmp_path / 'export'
    result = exporter.export(dev, output)
    with zipfile.ZipFile(output / 'RAW_INPUT.zip') as z:
        assert str(new.relative_to(dev)) in z.namelist()
        assert str(old.relative_to(dev)) not in z.namelist()
        assert str(unknown.relative_to(dev)) not in z.namelist()
    assert len(result['mapping']['omitted']) == 2
    assert all(t.sha(p) == digest for p, digest in before.items())
    restored = tmp_path / 'restored'
    assert restore_inputs.restore(output, restored)['status'] == 'RESTORED'
    assert restore_inputs.restore(output, restored)['status'] == 'RESTORED'
    (restored / new.relative_to(dev)).write_text('tampered')
    with pytest.raises(ValueError, match='RESTORE_CONFLICT'):
        restore_inputs.restore(output, restored)


def test_missing_latest_raw_is_reported_and_not_exported(tmp_path):
    dev = tmp_path / 'dev'
    (dev / '01_DATA/RAW').mkdir(parents=True)
    selection(dev, [{'document_id': 'missing', 'source_artifact_sha256': '0'*64, 'is_latest': True}])
    with pytest.raises(ValueError, match='LATEST_RAW_MISSING'):
        exporter.export(dev, tmp_path / 'out')
    assert not (tmp_path / 'out/RAW_INPUT.zip').exists()
    assert t.read(tmp_path / 'out/RAW_SELECTION_REPORT.json')['missing_latest_hashes'] == ['0'*64]


def test_named_20261021_zip_and_active_rag_disagreement(tmp_path):
    dev = tmp_path / 'dev'
    value = selection(dev, [])
    raw = json.dumps(value).encode()
    path = dev / 'GENOS_LATEST_SELECTION_DATA_20261021_R1.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('generation.json', raw)
        z.writestr('BUNDLE.json', json.dumps({'version': 'GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1',
                                            'selection_sha256': hashlib.sha256(raw).hexdigest()}))
    assert exporter.latest_mapping(dev, selection_file=path.name)[1] == value
    selection(dev, [{'document_id': 'new', 'source_artifact_sha256': '1'*64, 'is_latest': True}])
    with pytest.raises(ValueError, match='ZIP_DIFFERS_FROM_ACTIVE'):
        exporter.latest_mapping(dev, selection_file=path.name)
    (dev / '00_SYSTEM/GENOS_SERVING_PATHS.json').unlink()
    assert exporter.latest_mapping(dev)[1] == value


def test_damaged_zip_and_symlink_destination_are_rejected(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'original')
    archive = tmp_path / 'good.zip'
    t.pack({'data/a': source}, archive)
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive) as z, zipfile.ZipFile(bad, 'w') as out:
        out.writestr('TRANSPORT.json', z.read('TRANSPORT.json'))
        out.writestr('data/a', b'tampered')
    with pytest.raises(ValueError, match='RESTORE_HASH'):
        t.unpack(bad, tmp_path / 'out')
    assert not (tmp_path / 'out/data/a').exists()
    target = tmp_path / 'linked'
    target.mkdir()
    (target / 'data').symlink_to(tmp_path / 'out/data', target_is_directory=True)
    with pytest.raises(ValueError, match='SYMLINK_REFUSED'):
        t.unpack(archive, target)


@pytest.mark.parametrize('bad', ['../escape', '/absolute', 'a/../escape', 'a\\escape', 'C:escape'])
def test_unsafe_archive_paths_rejected_before_write(tmp_path, bad):
    zpath = tmp_path / 'bad.zip'
    with zipfile.ZipFile(zpath, 'w') as z:
        z.writestr(bad, 'x')
        z.writestr('TRANSPORT.json', json.dumps({'format': t.FORMAT, 'files': {bad: {'bytes': 1, 'sha256': hashlib.sha256(b'x').hexdigest()}}}))
    with pytest.raises(ValueError, match='UNSAFE_PATH'):
        t.unpack(zpath, tmp_path / 'out')
    assert not (tmp_path / 'escape').exists()


@pytest.fixture
def remote(tmp_path, monkeypatch):
    root = tmp_path / 'service'
    root.mkdir()
    t.write(root / 'CODE_PINS.json', {'files': {}})
    monkeypatch.setattr(api, 'ROOT', root)
    monkeypatch.setenv('PIPELINE_SCRATCH', str(tmp_path / 'scratch'))
    health = api.handle({'API_TYPE': 'HEALTH'})
    auth = {'job_id': '1'*32, 'job_token': '2'*64, 'instance': health['instance'], 'code_sha256': health['code_sha256']}
    def call(op, **fields):
        result = asyncio.run(api.service({}, {'API_TYPE': op, **auth, **fields}))
        if result['code']:
            raise ValueError(result['error'])
        return result['data']
    block = b'hello'
    archives = {slot: {'bytes': len(block), 'sha256': hashlib.sha256(block).hexdigest()} for slot in ['raw', 'support']}
    deadline = time.time()+300
    call('START', archives=archives, deadline=deadline)
    return call, auth, archives, deadline, tmp_path / 'scratch' / auth['job_id']


def test_api_duplicate_chunks_conflict_deadline_auth_and_release(remote):
    call, auth, archives, deadline, folder = remote
    chunk = dict(slot='raw', offset=0, sha256=archives['raw']['sha256'], file_content_base64=base64.b64encode(b'hello').decode())
    assert call('UPLOAD', **chunk)['received']['raw'] == 5
    assert call('UPLOAD', **chunk)['received']['raw'] == 5
    with pytest.raises(ValueError, match='CHUNK_CONFLICT'):
        call('UPLOAD', **{**chunk, 'sha256': hashlib.sha256(b'other').hexdigest(), 'file_content_base64': base64.b64encode(b'other').decode()})
    with pytest.raises(ValueError, match='JOB_AUTH'):
        call('STATUS', job_token='3'*64)
    with pytest.raises(ValueError, match='JOB_INPUT_CONFLICT'):
        call('START', archives=archives, deadline=deadline+10)
    assert call('STATUS')['deadline'] == deadline
    with pytest.raises(ValueError, match='INPUT_INCOMPLETE'):
        call('EXECUTE')
    call('CANCEL')
    assert call('ACK', discard_failed_attempt=True)['status'] == 'RELEASED'
    assert not (folder / 'RAW_INPUT.zip').exists()
    assert call('ACK', discard_failed_attempt=True)['status'] == 'RELEASED'


def test_api_code_and_instance_change_reject_resume(remote):
    call, *_ = remote
    with pytest.raises(ValueError, match='CODE_BINDING_CHANGED'):
        call('STATUS', code_sha256='0'*64)
    with pytest.raises(ValueError, match='INSTANCE_CHANGED'):
        call('STATUS', instance='changed')


def test_api_execute_deduplicates_running_worker_and_preserves_expired_deadline(remote):
    call, _, _, _, folder = remote
    state = t.read(folder / 'state.json')
    state.update(status='RUNNING', worker=api.pid_identity(os.getpid()))
    t.write(folder / 'state.json', state)
    assert call('EXECUTE')['status'] == 'RUNNING'
    call('CANCEL')
    assert (folder / 'cancel.json').is_file()
    state['deadline'] = time.time()-1
    t.write(folder / 'state.json', state)
    with pytest.raises(ValueError, match='DEADLINE_EXHAUSTED'):
        call('EXECUTE')
    state['worker'] = [999999999, 'missing', 'missing']
    t.write(folder / 'state.json', state)
    assert call('STATUS')['status'] == 'INTERRUPTED'


def test_supervisor_loss_cannot_delete_a_live_child_workspace(remote):
    call, _, _, _, folder = remote
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
    try:
        state = t.read(folder / 'state.json')
        state.update(status='RUNNING', worker=[999999999, 'missing', 'missing'], child=api.pid_identity(child.pid))
        t.write(folder / 'state.json', state)
        assert call('STATUS')['status'] == 'INTERRUPTED'
        with pytest.raises(ValueError, match='CHILD_STILL_RUNNING'):
            call('ACK', discard_failed_attempt=True)
        call('CANCEL')
        child.wait(timeout=5)
        assert call('ACK', discard_failed_attempt=True)['status'] == 'RELEASED'
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


def test_exact_packaged_full_native_xml_pipeline(tmp_path, term_glossary, monkeypatch):
    """Only knowledge config is fixture-bound. All executable code is the delivery's bytes."""
    package = tmp_path / 'code'
    with zipfile.ZipFile(DELIVERY / 'GENOS_PIPELINE_SERVICE_20261022_R1.zip') as z:
        z.extractall(package)
    package = package / 'GENOS_PIPELINE_SERVICE_20261022_R1'
    dev = tmp_path / 'dev'
    support(dev, term_glossary)
    raw = dev / '01_DATA/RAW/external/test_team/모의법.xml'
    raw.parent.mkdir(parents=True)
    raw.write_text('''<?xml version="1.0" encoding="UTF-8"?><법령><기본정보><법령명_한글>모의법</법령명_한글><법령ID>999</법령ID><시행일자>20261022</시행일자></기본정보><조문><조문단위 조문키="0001001"><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>정의</조문제목><조문내용>제1조(정의) 영업일은 은행이 영업하는 날을 말한다.</조문내용></조문단위><조문단위 조문키="0002001"><조문번호>2</조문번호><조문여부>조문</조문여부><조문제목>신청</조문제목><조문내용>제2조(신청) 신청인은 제1조에 따른 영업일에 신청한다.</조문내용></조문단위></조문></법령>''')
    selection(dev, [])
    exported = tmp_path / 'export'
    exporter.export(dev, exported)
    shutil.copyfile(dev / '00_SYSTEM/GLOSSARY_PIPELINE.json', package / '00_SYSTEM/GLOSSARY_PIPELINE.json')
    pins = t.read(package / 'CODE_PINS.json')
    pins['files']['00_SYSTEM/GLOSSARY_PIPELINE.json'] = t.sha(package / '00_SYSTEM/GLOSSARY_PIPELINE.json')
    t.write(package / 'CODE_PINS.json', pins)
    inputs = tmp_path / 'inputs'
    restore_inputs.restore(exported, inputs)
    monkeypatch.setattr(api, 'ROOT', package)
    monkeypatch.setenv('PIPELINE_SCRATCH', str(tmp_path / 'scratch'))
    class LocalClient:
        def call(self, operation, **fields):
            result = asyncio.run(api.service({}, {'API_TYPE': operation, **fields}))
            if result['code']:
                raise ValueError(result['error'])
            return result['data']
    try:
        returned = dku.process(LocalClient(), inputs, exported / 'PIPELINE_SUPPORT.zip', tmp_path / 'job',
                               expected_code_sha256=t.sha(package / 'CODE_PINS.json'), poll_seconds=.2)
    except BaseException:
        for log in (tmp_path / 'scratch').rglob('*.log'):
            print(log.name, log.read_text(errors='replace')[-10000:])
        raise
    assert (returned / 'generation/fulltext/units.sqlite').is_file()
    assert (returned / 'query/query-data.db').is_file()
    receipt = t.read(returned / 'audit/release.json')
    assert receipt['serving_verified'] and receipt['offline_e2e'] == 'PASS'
    assert receipt['document_count'] == 1 and receipt['model_calls'] == 0
    assert not receipt['activated']
    assert t.read(tmp_path / 'job/client.json')['scratch_released']
    assert not list((tmp_path / 'scratch').rglob('store.sqlite'))
    from test_oracle_dp_runtime import AssetOracle
    from test_oracle_query_catalog import Oracle as QueryOracle
    from test_oracle_query_schema import SchemaOracle
    from semantic_runtime import oracle_query_catalog as q
    source, query, schema = AssetOracle(), QueryOracle(), SchemaOracle()
    schema.created = {s.split()[2].split('.')[1] for s in q.DDL}
    class Oracle:
        SQL_PATH = '/sql'
        def request(self, method, path, json):
            sql = json['statementText']
            if 'WHERE 1=0' in sql:
                return {'items': [{'resultSet': {'items': [], 'hasMore': False, 'offset': 0}}]}
            target = schema if 'ALL_' in sql and ':owner' in sql else query if 'LEGAL_RAG_QUERY_' in sql else source
            return target.request(method, path, json)
    from semantic_runtime.oracle_dp_io import DPError
    source.mode = 'after_timeout'
    with pytest.raises(DPError, match='WRITE_UNCONFIRMED'):
        dku.load_oracle(Oracle(), returned, tmp_path / 'job', target_binding='synthetic')
    source.mode = 'normal'
    result = dku.load_oracle(Oracle(), returned, tmp_path / 'job', target_binding='synthetic')
    assert result['status'] == 'COMPLETE' and result['query']['rows'] > 0
    assert source.parts and source.releases and query.rows and query.releases
    assert not query.active and not query.states
    before = (source.writes, query.writes, result['deadline'])
    resumed = dku.load_oracle(Oracle(), returned, tmp_path / 'job', target_binding='synthetic')
    assert (source.writes, query.writes, resumed['deadline']) == before
    with pytest.raises(ValueError, match='ORACLE_TARGET_CHANGED'):
        dku.load_oracle(Oracle(), returned, tmp_path / 'job', target_binding='changed')
