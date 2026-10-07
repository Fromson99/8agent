"""Synthetic NFS, Git and workflow contracts; no GENOS/model access."""
import asyncio
from contextlib import closing, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


probe = module(ROOT / '02_BACKEND/semantic_runtime/nfs_data_probe.py', 'tested_probe')
handoff = module(ROOT / '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py', 'tested_handoff')

FILES = (handoff.PROBE, handoff.WORKFLOW, '06_TOOLS/COMMANDS/genos_nfs_probe_handoff.py',
         '06_TOOLS/COMMANDS/genos_rag_data_bundle.py', '06_TOOLS/COMMANDS/genos_pack_rag_data.sh')


def fixture_db(path, table, column='json', text='PRIVATE_FIXTURE_CONTENT'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE "' + table + '" ("' + column + '" TEXT)')
        db.execute('INSERT INTO "' + table + '" VALUES(?)', (text,))


class FieldContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'DEV'
        self.root.mkdir()
        self.nfs = self.base / 'nfs-root/diamo'
        self.gen = self.nfs / '8-agent/term-releases/fixture/generation'
        self.runtime = self.nfs / '8-agent/runtime'
        self.runtime.mkdir(parents=True)
        self.gen.mkdir(parents=True)
        fixture_db(self.gen / 'store.sqlite', 'source_block', 'text')
        fixture_db(self.gen / 'navigation/navigation.sqlite', 'source')
        fixture_db(self.gen / 'fulltext/units.sqlite', 'unit')
        fixture_db(self.gen / 'glossary/dictionary.sqlite', 'entry')
        fixture_db(self.gen / 'glossary/bundle/nodes.sqlite', 'node')
        fixture_db(self.gen / 'glossary/cache/c1.sqlite', 'entry')
        fixture_db(self.runtime / 'case-memory/cases-v4.sqlite', 'sw_knowledge', 'payload')
        docs = {'navigation/manifest.json': {'schema_version': 'term-navigation-index-v7'},
                'fulltext/manifest.json': {'schema_version': 'semantic-unit-fulltext-v1'},
                'glossary/bundle/manifest.json': {'schema_version': 'glossary-serving-v2'},
                'glossary/cache/c1.json': {'binding': {}}}
        for name, value in docs.items():
            (self.gen / name).write_text(json.dumps(value))
        (self.gen / 'manifest.json').write_text(json.dumps({'schema_version': 'term-source-generation-v2', 'generation_id': 'fixture',
            'navigation': {'path': 'navigation', 'manifest_sha256': probe.sha(self.gen / 'navigation/manifest.json')},
            'fulltext': {'path': 'fulltext', 'manifest_sha256': probe.sha(self.gen / 'fulltext/manifest.json')},
            'glossary': {'schema_version': 'glossary-serving-v2', 'bundle': 'glossary/bundle', 'dictionary': 'glossary/dictionary.sqlite',
                         'cache': 'glossary/cache', 'cache_receipt': 'c1.json',
                         'cache_receipt_sha256': probe.sha(self.gen / 'glossary/cache/c1.json'),
                         'manifest_sha256': probe.sha(self.gen / 'glossary/bundle/manifest.json')}}))
        (self.root / 'service.py').write_text('from pathlib import Path\n_ROOT=Path(__file__).resolve().parent\nasync def service(config,data):\n    """Existing service"""\n    return {"normal":True}\n')
        stream = self.root / '08_DEPLOYMENT/GENOS/stream_app.py'
        stream.parent.mkdir(parents=True)
        stream.write_text('from pathlib import Path\nROOT=Path(__file__).resolve().parents[2]\nasync def service(config,data):\n    return {"normal":True}\n')
        (self.root / '.gitignore').write_text('TRANSFER/\n__pycache__/\n')
        handoff.git(self.root, 'init')
        handoff.git(self.root, 'config', 'user.name', 'Synthetic Test')
        handoff.git(self.root, 'config', 'user.email', 'synthetic@example.invalid')
        handoff.git(self.root, 'add', '.')
        handoff.git(self.root, 'commit', '-m', 'Fixture base')
        self.archive = self.base / 'tool.zip'
        manifest = {'format': '8agent-code/1', 'id': probe.REVISION, 'files': []}
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name in FILES:
                raw = (ROOT / name).read_bytes()
                z.writestr(name, raw)
                manifest['files'].append({'path': name, 'bytes': len(raw), 'sha256': handoff.digest(raw)})
            z.writestr('CODE_MANIFEST.json', handoff.encoded(manifest))
        self.logs = self.base / 'logs'
        self.original = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.gen.rglob('*') if p.is_file()}

    def execute(self, *args):
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()):
            return handoff.main([*map(str, args), '--code-root', str(self.root), '--log-dir', str(self.logs)])

    def prepare(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 0)
        self.cfg = json.loads((self.root / probe.CONFIG).read_text())
        self.binding = json.loads(Path(self.cfg['receipt_path']).read_text())

    def report(self, **kwargs):
        env = {'GENOS_GENERATION': str(self.gen), 'GENOS_RUNTIME_DIR': str(self.runtime)}
        return probe.probe(code_root=self.root, settings=env, nfs_base=self.nfs, **kwargs)

    def test_codespace_commit_shared_code_and_sql_are_bound_and_read_only(self):
        self.prepare()
        report = self.report()
        self.assertTrue(report['ok'], report)
        self.assertEqual(self.binding['commit'], handoff.git(self.root, 'rev-parse', 'HEAD'))
        self.assertTrue(all((Path(self.cfg['receipt_path']).parent / 'code' / name).is_file() for name in self.binding['code_files']))
        for name, (raw, mtime) in self.original.items():
            self.assertEqual(Path(name).read_bytes(), raw)
            self.assertEqual(Path(name).stat().st_mtime_ns, mtime)
        self.assertNotIn('PRIVATE_FIXTURE_CONTENT', json.dumps(report))
        self.assertFalse(report['full_generation_integrity_verified'])

    def test_install_idempotence_and_preserves_non_probe_dispatch(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        before = (self.root / 'service.py').read_bytes()
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        self.assertEqual((self.root / 'service.py').read_bytes(), before)
        entry = module(self.root / 'service.py', 'synthetic_serving_entry')
        self.assertEqual(asyncio.run(entry.service({}, {'API_TYPE': 'PING'})), {'normal': True})

    def test_dev_symlink_alias_install_prepare_read_and_push_use_actual_checkout(self):
        actual = self.root
        alias = self.base / 'home/genos/DEV'
        alias.parent.mkdir(parents=True)
        alias.symlink_to(actual, target_is_directory=True)
        self.root = alias
        self.prepare()
        self.assertEqual(self.binding['prepared_checkout'], str(actual))
        self.assertTrue(self.report()['ok'])
        remote = self.base / 'alias-remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        handoff.git(actual, 'remote', 'add', 'origin', str(remote))
        self.assertEqual(self.execute('push'), 0)
        self.assertTrue(alias.is_symlink())
        branch = handoff.git(actual, 'branch', '--show-current')
        self.assertEqual(handoff.git(actual, 'ls-remote', 'origin', 'refs/heads/' + branch).split()[0], self.binding['commit'])
        for name, (raw, mtime) in self.original.items():
            self.assertEqual(Path(name).read_bytes(), raw)
            self.assertEqual(Path(name).stat().st_mtime_ns, mtime)

    def test_dev_alias_does_not_allow_symlinked_code_or_data_files(self):
        alias = self.base / 'alias-DEV'
        alias.symlink_to(self.root, target_is_directory=True)
        self.root = alias
        service = self.root / 'service.py'
        original = service.read_bytes()
        outside = self.base / 'outside-service.py'
        outside.write_bytes(original)
        service.unlink()
        service.symlink_to(outside)
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 1)
        self.assertEqual(outside.read_bytes(), original)
        service.unlink()
        service.write_bytes(original)
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        db = self.gen / 'store.sqlite'
        saved = self.base / 'outside-store.sqlite'
        saved.write_bytes(db.read_bytes())
        db.unlink()
        db.symlink_to(saved)
        commit = handoff.git(self.root, 'rev-parse', 'HEAD')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 1)
        self.assertEqual(handoff.git(self.root, 'rev-parse', 'HEAD'), commit)

    def test_nfs_mount_entry_alias_keeps_logical_data_paths_and_allows_read_and_push(self):
        actual = self.base / 'actual-shared-volume'
        shutil.move(self.nfs, actual)
        self.nfs.symlink_to(actual, target_is_directory=True)
        self.prepare()
        self.assertEqual(self.cfg['generation'], str(self.gen))
        self.assertEqual(self.cfg['runtime'], str(self.runtime))
        self.assertTrue(self.nfs.is_symlink())
        report = self.report()
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['nfs_mount_entry']['actual_root'], str(actual))
        self.assertTrue(report['nfs_mount_entry']['aliases'])
        remote = self.base / 'mount-alias-remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        handoff.git(self.root, 'remote', 'add', 'origin', str(remote))
        self.assertEqual(self.execute('push'), 0)
        for name, (raw, mtime) in self.original.items():
            self.assertEqual(Path(name).read_bytes(), raw)
            self.assertEqual(Path(name).stat().st_mtime_ns, mtime)

    def test_link_under_selected_nfs_root_reports_exact_path_and_phase_before_commit(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        original = self.gen
        actual = self.base / 'other-generation'
        shutil.move(original, actual)
        original.symlink_to(actual, target_is_directory=True)
        commit = handoff.git(self.root, 'rev-parse', 'HEAD')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 1)
        status = json.loads(next(self.logs.glob('prepare-*/STATUS.json')).read_text())
        self.assertEqual(status['phase'], 'select_data_paths')
        self.assertIn(str(self.gen), status['error'])
        self.assertEqual(handoff.git(self.root, 'rev-parse', 'HEAD'), commit)

    def test_broken_nfs_mount_entry_has_failure_stage_and_preserves_code(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        shutil.rmtree(self.nfs)
        self.nfs.symlink_to(self.base / 'missing-volume', target_is_directory=True)
        commit = handoff.git(self.root, 'rev-parse', 'HEAD')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 1)
        status = json.loads(next(self.logs.glob('prepare-*/STATUS.json')).read_text())
        self.assertEqual(status['phase'], 'nfs_mount_entry')
        self.assertEqual(handoff.git(self.root, 'rev-parse', 'HEAD'), commit)

    def test_explicit_field_paths_bypass_old_codespace_dev_current_and_state_settings(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        (self.root / '.env').write_text('GENOS_DATA_ROOT="$HOME/DEV/GENOS_DATA"\nGENOS_RUNTIME_DIR=/home/genos/DEV/GENOS_DATA/runtime\nGENOS_STATE_DIR=/home/genos/DEV/GENOS_DATA/state\n')
        handoff.git(self.root, 'add', '.env')
        handoff.git(self.root, 'commit', '-m', 'Synthetic stale codespace path settings', '--', '.env')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime,
                                     '--nfs-base', self.nfs, '--state-unset'), 0)
        cfg = json.loads((self.root / probe.CONFIG).read_text())
        self.assertEqual(cfg['generation'], str(self.gen))
        self.assertEqual(cfg['runtime'], str(self.runtime))
        self.assertIsNone(cfg['state'])

    def test_bad_attachment_hash_modifies_nothing(self):
        before = (self.root / 'service.py').read_bytes()
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', '0' * 64), 1)
        self.assertEqual((self.root / 'service.py').read_bytes(), before)

    def test_serving_environment_not_inherited_reports_failure(self):
        self.prepare()
        report = probe.probe(code_root=self.root, settings={}, nfs_base=self.nfs)
        self.assertFalse(report['ok'])
        self.assertTrue(any(row['name'] == 'serving_path_environment' and row['status'] == 'FAIL' for row in report['checks']))

    def test_codespace_reads_prepared_paths_with_old_dev_environment_but_serving_rejects_it(self):
        self.prepare()
        old_env = {'GENOS_DATA_ROOT': '/home/genos/DEV/GENOS_DATA',
                   'GENOS_RUNTIME_DIR': '/home/genos/DEV/GENOS_DATA/runtime',
                   'GENOS_STATE_DIR': '/home/genos/DEV/GENOS_DATA/state'}
        report = probe.probe(code_root=self.root, stage='code-space', settings=old_env, nfs_base=self.nfs)
        self.assertTrue(report['ok'], report)
        report = probe.probe(code_root=self.root, stage='code-serving', settings=old_env, nfs_base=self.nfs)
        self.assertFalse(report['ok'])

    def test_code_tampering_and_wrong_head_cannot_pass(self):
        self.prepare()
        (self.root / 'service.py').write_text((self.root / 'service.py').read_text() + '# change\n')
        self.assertFalse(self.report()['ok'])
        self.assertEqual(self.execute('push'), 1)

    def test_shared_code_missing_is_detected(self):
        self.prepare()
        (Path(self.cfg['receipt_path']).parent / 'code' / handoff.PROBE).unlink()
        self.assertFalse(self.report()['ok'])

    def test_generation_metadata_and_data_sample_changes_detected(self):
        self.prepare()
        (self.gen / 'manifest.json').write_text((self.gen / 'manifest.json').read_text() + '\n')
        self.assertFalse(self.report()['ok'])

    def test_runtime_sidecar_fails_without_creating_or_changing_db(self):
        self.prepare()
        db = self.runtime / 'case-memory/cases-v4.sqlite'
        before = db.read_bytes()
        Path(str(db) + '-wal').write_bytes(b'active marker')
        self.assertFalse(self.report()['ok'])
        self.assertEqual(db.read_bytes(), before)
        self.assertFalse(Path(str(db) + '-shm').exists())

    def test_unrelated_staged_work_is_preserved_and_not_committed(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        other = self.root / 'other.txt'
        other.write_text('unrelated work')
        handoff.git(self.root, 'add', 'other.txt')
        before = handoff.git(self.root, 'rev-parse', 'HEAD')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 1)
        self.assertEqual(handoff.git(self.root, 'rev-parse', 'HEAD'), before)
        self.assertEqual(other.read_text(), 'unrelated work')

    def test_existing_remote_push_pins_exact_prepared_commit(self):
        self.prepare()
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        handoff.git(self.root, 'remote', 'add', 'origin', str(remote))
        self.assertEqual(self.execute('push'), 0)
        branch = handoff.git(self.root, 'branch', '--show-current')
        self.assertEqual(handoff.git(self.root, 'ls-remote', 'origin', 'refs/heads/' + branch).split()[0], self.binding['commit'])

    def test_missing_source_database_stops_before_commit(self):
        self.assertEqual(self.execute('install', '--archive', self.archive, '--zip-sha256', probe.sha(self.archive)), 0)
        (self.gen / 'store.sqlite').unlink()
        before = handoff.git(self.root, 'rev-parse', 'HEAD')
        self.assertEqual(self.execute('prepare', '--generation', self.gen, '--runtime', self.runtime, '--nfs-base', self.nfs), 1)
        self.assertEqual(handoff.git(self.root, 'rev-parse', 'HEAD'), before)


class WorkflowContracts(unittest.TestCase):
    def workflow(self):
        result = module(ROOT / handoff.WORKFLOW, 'tested_workflow')
        result.EXPECTED_PROBE_ID = 'fixture-id'
        result.EXPECTED_COMMIT = 'a' * 40
        return result

    def execute(self, report, status=200):
        workflow = self.workflow()
        class Response:
            code = status
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, size): return json.dumps({'data': {'body': report}}).encode()
        class Opener:
            def open(self, request, timeout):
                assert request.get_header('Authorization') == 'Bearer FAKE_TEST_TOKEN'
                assert json.loads(request.data)['API_TYPE'] == 'NFS_DATA_PROBE'
                return Response()
        env = {'GENOS_BASE_URL': 'https://genos.invalid', 'GENOS_CODESERVING_ID': '123',
               'GENOS_CODESERVING_TOKEN': 'FAKE_TEST_TOKEN'}
        with patch.dict(os.environ, env, clear=True), patch.object(workflow.urllib.request, 'build_opener', return_value=Opener()):
            return workflow.run({'question': 'PRIVATE_USER_INPUT_NEVER_SENT'})

    def test_nested_gateway_and_positive_identity(self):
        report = {'response_schema': probe.REVISION, 'probe_id': 'fixture-id', 'expected_commit': 'a' * 40,
                  'stage': 'code-serving', 'ok': True, 'checks': []}
        out = self.execute(report)
        self.assertTrue(out['nfs_probe_pass'])
        self.assertNotIn('FAKE_TEST_TOKEN', json.dumps(out))
        self.assertNotIn('PRIVATE_USER_INPUT', json.dumps(out))

    def test_http_200_wrong_revision_cannot_pass(self):
        report = {'response_schema': probe.REVISION, 'probe_id': 'wrong-id', 'expected_commit': 'a' * 40,
                  'stage': 'code-serving', 'ok': True, 'checks': []}
        self.assertFalse(self.execute(report)['nfs_probe_pass'])

    def test_failed_report_is_not_hidden(self):
        report = {'response_schema': probe.REVISION, 'probe_id': 'fixture-id', 'expected_commit': 'a' * 40,
                  'stage': 'code-serving', 'ok': False,
                  'checks': [{'name': 'source_store', 'path': '/nfs-root/diamo/missing', 'status': 'FAIL', 'error_type': 'FileNotFoundError'}]}
        out = self.execute(report, 503)
        self.assertFalse(out['nfs_probe_pass'])
        self.assertIn('FileNotFoundError', out['text'])


if __name__ == '__main__':
    unittest.main()
