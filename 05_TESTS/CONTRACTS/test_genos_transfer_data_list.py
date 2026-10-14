"""Synthetic archive/NFS/Git/workflow connection tests; no GENOS connection."""
import asyncio
from contextlib import closing, redirect_stdout
import importlib.util
import importlib.machinery
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/data_transfer_list_20261007_r1'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path, loader=importlib.machinery.SourceFileLoader(name, str(path)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fields = module(ROOT / '05_TESTS/test_genos_nfs_data_probe.py', '_transfer_field_tests')
bundle = module(ROOT / '06_TOOLS/COMMANDS/genos_rag_data_bundle.py', '_transfer_bundle_test')
transfer = module(ROOT / '06_TOOLS/COMMANDS/genos_transfer_data_list.py', '_transfer_driver_test')
builder = module(OUT / 'build_delivery.py', '_transfer_builder_test')


@pytest.fixture
def fixture():
    f = fields.FieldContracts()
    f.setUp()
    try:
        # The manifest/logical paths remain the confirmed field paths.
        actual = f.base / bundle.GENERATION.relative_to('/')
        shutil.move(f.gen, actual)
        f.gen = actual
        with closing(sqlite3.connect(f.gen / 'store.sqlite')) as db, db:
            db.execute('CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,json TEXT)')
            rows = [('d1', '모의 금융 문서', {'document_metadata': {'team': 'risk_team'}}),
                    ('d2', '모의 별칭 문서', {'document_metadata': {'team': 'financial_team', 'aliases': [{'team': 'risk_team'}]}}),
                    ('d3', '다른 팀 제외 문서', {'document_metadata': {'team': 'other_team'}})]
            db.executemany('INSERT INTO document VALUES(?,?,?)', [(did, name, json.dumps(raw)) for did, name, raw in rows])
        manifest = json.loads((f.gen / 'manifest.json').read_text())
        manifest['store_sha256'] = bundle.sha(f.gen / 'store.sqlite')
        (f.gen / 'manifest.json').write_text(json.dumps(manifest))
        source = f.base / 'source-snapshot'
        source.mkdir()
        (source / 'nfs-root').mkdir()
        shutil.move(f.nfs, source / 'nfs-root/diamo')
        f.source = source
        f.destination = f.base / 'destination'
        (f.destination / 'nfs-root/diamo').mkdir(parents=True)
        f.remote = f.base / 'origin.git'
        subprocess.run(['git', 'init', '--bare', str(f.remote)], check=True, capture_output=True)
        fields.handoff.git(f.root, 'remote', 'add', 'origin', str(f.remote))
        f.transfer = f.root / 'TRANSFER'
        f.transfer.mkdir()
        # Use literal operator selections; ignore any stale ambient settings.
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()):
            rc = bundle.main(['pack', '--source-prefix', str(source), '--code-root', str(f.root),
                              '--writers-stopped', '--generation', str(bundle.GENERATION),
                              '--runtime', str(bundle.RUNTIME), '--state-unset', '--output-dir', str(f.transfer)])
        assert rc == 0
        f.data_zip = next(f.transfer.glob('genos-rag-data-*.zip'))
        f.parts = f.transfer / (f.data_zip.name + '.parts')
        env = {**os.environ, 'ZIP_TRANSFER_DIR': str(f.transfer)}
        result = subprocess.run(['bash', str(ROOT / '08_DEPLOYMENT/GENOS/handoffs/zip_parts_bash_20261007_r4/SPLIT_TRANSFER_ZIP.txt'), f.data_zip.name], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        f.delivery = f.base / 'delivery'
        f.delivery.mkdir()
        shutil.copyfile(OUT / 'BASELINE_SHA256.json', f.delivery / 'BASELINE_SHA256.json')
        # Build a real self-contained TXT using the same builder as the handoff.
        f.driver = f.delivery / (builder.NAME + '_RUN.txt')
        published = OUT / f.driver.name
        if published.exists():
            shutil.copyfile(published, f.driver)
        else:
            with patch.object(builder, 'OUT', f.delivery), redirect_stdout(io.StringIO()):
                builder.main()
        f.env = {**os.environ, 'GENOS_DEV': str(f.root), 'GENOS_DATA_ROOT': '/old/data',
                 'GENOS_STATE_DIR': '/old/state', 'GENOS_RUNTIME_DIR': '/old/runtime'}
        yield f
    finally:
        f.doCleanups()


def execute(f, *args, expected=0):
    r = subprocess.run(['bash', str(f.driver), *map(str, args)], env=f.env, text=True, capture_output=True, timeout=60)
    assert r.returncode == expected, r.stdout[-8000:] + r.stderr[-3000:]
    runs = list((f.delivery / 'transfer-nfs-list-logs').glob('run-*/STATUS.json'))
    status = json.loads(max(runs, key=lambda p: p.stat().st_mtime_ns).read_text())
    run = max(runs, key=lambda p: p.stat().st_mtime_ns).parent
    assert json.loads((run / 'EXIT_STATUS.json').read_text())['exit_code'] == expected
    return status, r


def test_actual_txt_join_restore_same_checkout_push_and_workflow_list(fixture):
    f = fixture
    initial = fields.handoff.git(f.root, 'rev-parse', 'HEAD')
    status, _ = execute(f, 'inspect', f.parts)
    assert status['status'] == 'CODE_SPACE_STAGES_PASS'
    assert fields.handoff.git(f.root, 'rev-parse', 'HEAD') == initial
    assert not list((f.destination / 'nfs-root/diamo').iterdir())
    status, _ = execute(f, 'all', f.parts, '--writers-stopped', '--team-id', 'risk_team', '--destination-prefix', f.destination)
    assert status['steps']['push']['status'] == 'PUSHED'
    commit = fields.handoff.git(f.root, 'rev-parse', 'HEAD')
    assert fields.handoff.git(f.root, 'ls-remote', 'origin', 'refs/heads/' + fields.handoff.git(f.root, 'branch', '--show-current')).split()[0] == commit
    for path in f.source.rglob('*'):
        if path.is_file():
            assert (f.destination / path.relative_to(f.source)).read_bytes() == path.read_bytes()
    cfg = json.loads((f.root / fields.probe.CONFIG).read_text())
    assert cfg['generation'] == str(f.destination / bundle.GENERATION.relative_to('/'))
    assert cfg['state'] is None and cfg['list_team_id'] == 'risk_team'
    settings = {'GENOS_GENERATION': cfg['generation'], 'GENOS_RUNTIME_DIR': cfg['runtime'], 'GENOS_NFS_LIST_TEAM_ID': 'risk_team'}
    served = fields.probe.probe(code_root=f.root, settings=settings, nfs_base=Path(cfg['nfs_base']), include_listing=True, limit=1)
    assert served['ok'], served
    docs = served['data_listing']['document_metadata']
    assert docs['total'] == 2 and docs['has_more'] is True and len(docs['documents']) == 1
    page = fields.probe.probe(code_root=f.root, settings=settings, nfs_base=Path(cfg['nfs_base']), include_listing=True, limit=1, offset=1)
    assert page['data_listing']['document_metadata']['documents'][0]['document_id'] == 'd2'
    assert '다른 팀 제외 문서' not in json.dumps(served, ensure_ascii=False)
    workflow = Path(status['steps']['prepare']['workflow_paste_all'])
    bridge = module(workflow, '_generated_list_bridge')
    class Response(io.BytesIO):
        code = 200
    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            assert payload['API_TYPE'] == 'NFS_DATA_PROBE' and payload['include_listing'] is True
            assert 'question' not in payload
            return Response(json.dumps({'data': {'body': served}}, ensure_ascii=False).encode())
    with patch.dict(os.environ, {'GENOS_BASE_URL': 'https://mock.invalid', 'GENOS_CODESERVING_ID': 'fixture-code', 'GENOS_CODE_KEY': 'fixture-credential'}, clear=True), patch.object(bridge.urllib.request, 'build_opener', return_value=Opener()):
        out = bridge.run({'offset': 0, 'limit': 1, 'question': 'not forwarded'})
    assert out['nfs_probe_pass'] is True
    assert '모의 금융 문서' in out['text'] and 'store.sqlite' in out['text']
    assert 'PRIVATE_FIXTURE_CONTENT' not in out['text']
    # Exercise the installed hook and actual HTTP bridge, not just a canned
    # positive response. The only HTTP server is a local synthetic gateway.
    entry = module(f.root / 'service.py', '_installed_transfer_entry')
    observed = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append((self.path, request))
            answer = asyncio.run(entry.service({}, request))
            self.send_response(answer['status'])
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'data': answer}).encode())
        def log_message(self, *args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict(os.environ, {**settings, 'GENOS_BASE_URL': 'http://127.0.0.1:' + str(server.server_port),
                                    'GENOS_CODESERVING_ID': 'fixture-code', 'GENOS_CODE_KEY': 'fixture-credential'}, clear=True):
            result = bridge.run({'question': 'not forwarded'})
        assert result['nfs_probe_pass'] is True, result
        assert '모의 금융 문서' in result['text'] and '모의 별칭 문서' in result['text']
        assert observed[0][0] == '/api/gateway/code_serving/fixture-code/json'
        assert 'question' not in observed[0][1]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    # Restoring matching files is safe to rerun, without a new code commit.
    previous = commit
    status2, _ = execute(f, 'restore', f.parts, '--writers-stopped', '--destination-prefix', f.destination)
    assert status2['steps']['restore']['copied_files'] == 0
    assert fields.handoff.git(f.root, 'rev-parse', 'HEAD') == previous


def test_restore_requires_stopped_writers_and_persists_failure(fixture):
    f = fixture
    status, _ = execute(f, 'all', f.parts, '--destination-prefix', f.destination, expected=1)
    assert status['status'] == 'FAILED' and '--writers-stopped' in status['error']
    assert not list((f.destination / 'nfs-root/diamo').iterdir())


def test_existing_different_nfs_file_is_preserved_before_code_install(fixture):
    f = fixture
    conflict = f.destination / bundle.RUNTIME.relative_to('/') / 'case-memory/cases-v4.sqlite'
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b'existing content to preserve')
    before = (f.root / 'service.py').read_bytes()
    status, _ = execute(f, 'all', f.parts, '--writers-stopped', '--destination-prefix', f.destination, expected=1)
    assert '기존 파일' in status['error']
    assert conflict.read_bytes() == b'existing content to preserve'
    assert (f.root / 'service.py').read_bytes() == before
    assert not (f.destination / bundle.GENERATION.relative_to('/')).exists()


@pytest.mark.parametrize('member', ['../escape', '/absolute', 'folder/../escape', 'folder\\escape'])
def test_unsafe_zip_is_rejected_before_extraction(tmp_path, member):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(member, 'bad')
    with pytest.raises(ValueError):
        transfer.unpack(archive, tmp_path / 'out')
    assert not list((tmp_path / 'out').iterdir())


def test_wrong_serving_environment_withholds_document_listing(fixture):
    f = fixture
    status, _ = execute(f, 'all', f.parts, '--writers-stopped', '--team-id', 'risk_team', '--destination-prefix', f.destination, '--no-push')
    cfg = json.loads((f.root / fields.probe.CONFIG).read_text())
    settings = {'GENOS_GENERATION': cfg['generation'], 'GENOS_RUNTIME_DIR': cfg['runtime'], 'GENOS_NFS_LIST_TEAM_ID': 'other_team'}
    report = fields.probe.probe(code_root=f.root, settings=settings, nfs_base=Path(cfg['nfs_base']), include_listing=True)
    assert report['ok'] is False and 'data_listing' not in report


def test_unknown_team_fails_before_prepared_commit(fixture):
    f = fixture
    initial = fields.handoff.git(f.root, 'rev-parse', 'HEAD')
    status, _ = execute(f, 'all', f.parts, '--writers-stopped', '--team-id', 'absent_team', '--destination-prefix', f.destination, expected=1)
    assert status['status'] == 'FAILED'
    assert fields.handoff.git(f.root, 'rev-parse', 'HEAD') == initial


def test_default_lists_actual_files_without_other_team_titles(fixture):
    f = fixture
    status, _ = execute(f, 'all', f.parts, '--writers-stopped', '--destination-prefix', f.destination, '--no-push')
    cfg = json.loads((f.root / fields.probe.CONFIG).read_text())
    report = fields.probe.probe(code_root=f.root, settings={'GENOS_GENERATION': cfg['generation'], 'GENOS_RUNTIME_DIR': cfg['runtime']},
                                nfs_base=Path(cfg['nfs_base']), include_listing=True)
    assert report['ok'] and report['data_listing']['document_metadata']['listed'] is False
    assert 'store.sqlite' in json.dumps(report)
    assert '다른 팀 제외 문서' not in json.dumps(report, ensure_ascii=False)
    bad = fields.probe.probe(code_root=f.root, settings={'GENOS_GENERATION': cfg['generation'], 'GENOS_RUNTIME_DIR': cfg['runtime']},
                             nfs_base=Path(cfg['nfs_base']), include_listing=True, limit=201)
    assert bad['ok'] is False and 'data_listing' not in bad


def test_live_archive_needs_review_flag_and_ineligible_archive_never_copies(fixture):
    f = fixture
    archive = f.transfer / 'live-fixture.zip'
    with zipfile.ZipFile(f.data_zip) as src, zipfile.ZipFile(archive, 'w') as dst:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename.endswith('/DATA_MANIFEST.json'):
                metadata = json.loads(raw)
                metadata['schema_version'] = bundle.LIVE_FORMAT
                metadata['archive_restore_eligible'] = False
                raw = json.dumps(metadata).encode()
            dst.writestr(info, raw)
    status, _ = execute(f, 'restore', archive, '--writers-stopped', '--destination-prefix', f.destination, expected=1)
    assert '--accept-live-archive' in status['error']
    status, _ = execute(f, 'restore', archive, '--writers-stopped', '--accept-live-archive', '--destination-prefix', f.destination, expected=1)
    assert '자동 복원하지' in status['error']
    assert not list((f.destination / 'nfs-root/diamo').iterdir())
