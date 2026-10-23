import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_service_20261022_r3/install_here_20261022_r1'
spec = importlib.util.spec_from_file_location('pipeline_install_here', DELIVERY / 'install_here.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
SCRIPT = DELIVERY / 'GENOS_PIPELINE_INSTALL_HERE_20261022_R1.txt'
ARCHIVE = DELIVERY.parent / installer.ARCHIVE


class InstallHereTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pipeline-install-contract-')
        self.root = Path(self.tmp.name) / 'DEV'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.git('config', 'user.name', 'Local Contract')
        self.git('config', 'user.email', 'local-contract@example.invalid')
        try:
            os.link(ARCHIVE, self.root / installer.ARCHIVE)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copyfile(ARCHIVE, self.root / installer.ARCHIVE)
        (self.root / 'service.py').write_text('# original code-space starter\n')
        (self.root / 'service.py').chmod(0o750)
        (self.root / 'user-note.txt').write_text('preserve user file')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def run_script(self, action='apply', ok=True, cwd=None):
        result = subprocess.run(['bash', str(SCRIPT), action], cwd=cwd or self.root,
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_final_txt_install_resume_stage_committed_check_and_rollback(self):
        self.assertIn('INSTALLED', self.run_script())
        backup = self.root / installer.STATE_DIR / 'backup/service.py'
        self.assertEqual(backup.read_text(), '# original code-space starter\n')
        self.assertEqual(installer.sha(self.root / 'CODE_PINS.json'), installer.CODE_SHA)
        self.assertFalse((self.root / installer.ARCHIVE[:-4]).exists())
        self.assertIn('INSTALLED', self.run_script())
        self.run_script('check', ok=False)
        self.assertIn('STAGED_CODE_FILES', self.run_script('stage'))
        staged = self.git('diff', '--cached', '--name-only').splitlines()
        self.assertEqual(len(staged), 1139)
        self.assertNotIn('user-note.txt', staged)
        self.assertNotIn(installer.ARCHIVE, staged)
        whitespace = subprocess.run(['git', '-C', str(self.root), 'diff', '--cached', '--check'],
                                    capture_output=True, text=True)
        # Sealed R2 already has these whitespace warnings; preserve the code hash.
        self.assertEqual(whitespace.returncode, 2)
        self.assertEqual(whitespace.stdout, (DELIVERY / 'BASELINE_R2_WHITESPACE.txt').read_text())
        self.git('commit', '-qm', 'Pipeline R2 fixture')
        self.assertIn('CODE_VERIFIED', self.run_script('check'))
        self.assertIn('ROLLED_BACK', self.run_script('rollback'))
        self.assertEqual((self.root / 'service.py').read_text(), '# original code-space starter\n')
        self.assertEqual((self.root / 'service.py').stat().st_mode & 0o777, 0o750)
        self.assertFalse((self.root / 'worker.py').exists())
        self.assertEqual((self.root / 'user-note.txt').read_text(), 'preserve user file')
        self.assertIn('ROLLED_BACK', self.run_script('rollback'))
        self.assertIn('INSTALLED', self.run_script())
        self.assertIn('CODE_VERIFIED', self.run_script('check'))

    def test_zip_tamper_stops_before_code_changes(self):
        target = self.root / installer.ARCHIVE
        target.unlink()
        shutil.copyfile(ARCHIVE, target)
        with target.open('ab') as f:
            f.write(b'tampered')
        self.assertIn('ZIP_HASH_MISMATCH', self.run_script(ok=False))
        self.assertFalse((self.root / 'worker.py').exists())
        self.assertEqual((self.root / 'service.py').read_text(), '# original code-space starter\n')

    def test_symlink_path_stops_before_code_changes(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (self.root / '02_BACKEND').symlink_to(outside, target_is_directory=True)
        self.assertIn('SYMLINK', self.run_script(ok=False))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / 'worker.py').exists())

    def test_user_edit_preserved_on_resume_and_rollback(self):
        self.run_script()
        (self.root / 'service.py').write_text('# user edit after installation\n')
        self.assertIn('USER_EDIT_CONFLICT', self.run_script(ok=False))
        self.assertIn('USER_EDIT_CONFLICT', self.run_script('rollback', ok=False))
        self.assertEqual((self.root / 'service.py').read_text(), '# user edit after installation\n')

    def test_interrupted_write_preserves_original_and_resumes(self):
        old_cwd = Path.cwd()
        real_replace = os.replace
        def interrupt(src, dst):
            if Path(dst) == self.root / 'service.py':
                raise OSError(errno.ENOSPC, 'contract injected disk full')
            return real_replace(src, dst)
        try:
            os.chdir(self.root)
            with patch.object(installer.os, 'replace', side_effect=interrupt):
                with self.assertRaises(OSError):
                    installer.run('apply')
        finally:
            os.chdir(old_cwd)
        self.assertEqual((self.root / 'service.py').read_text(), '# original code-space starter\n')
        state = json.loads((self.root / installer.STATE_DIR / 'status.json').read_text())
        self.assertEqual(state['errno'], errno.ENOSPC)
        self.assertEqual(state['status'], 'FAILED')
        self.assertEqual(list(self.root.rglob('.pipeline-install-*.tmp')), [])
        self.assertIn('INSTALLED', self.run_script())

    def test_backup_tamper_blocks_rollback(self):
        self.run_script()
        backup = self.root / installer.STATE_DIR / 'backup/service.py'
        backup.write_text('tampered backup')
        before = installer.sha(self.root / 'service.py')
        self.assertIn('BACKUP_HASH_MISMATCH', self.run_script('rollback', ok=False))
        self.assertEqual(installer.sha(self.root / 'service.py'), before)

    def test_lock_rejects_duplicate_invocation(self):
        audit = self.root / installer.STATE_DIR
        audit.mkdir()
        with (audit / 'install.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIn('INSTALL_ALREADY_RUNNING', self.run_script(ok=False))
        self.assertFalse((self.root / 'worker.py').exists())

    def test_requires_actual_checkout_root(self):
        sub = self.root / 'TRANSFER'
        sub.mkdir()
        self.assertIn('RUN_AT_GIT_ROOT', self.run_script(ok=False, cwd=sub))
        self.assertFalse((sub / 'service.py').exists())

    def test_stage_rejects_unrelated_staged_user_files(self):
        self.run_script()
        self.git('add', '--', 'user-note.txt')
        self.assertIn('OTHER_STAGED_FILES', self.run_script('stage', ok=False))
        self.assertEqual(self.git('diff', '--cached', '--name-only'), 'user-note.txt')

    def test_audit_symlink_is_rejected(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (self.root / installer.STATE_DIR).symlink_to(outside, target_is_directory=True)
        self.assertIn('SYMLINK', self.run_script(ok=False))
        self.assertEqual(list(outside.iterdir()), [])
