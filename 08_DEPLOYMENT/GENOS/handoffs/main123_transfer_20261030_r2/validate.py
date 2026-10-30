from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_MAIN123_TRANSFER_20261030_R2'
RUN = NAME + '_RUN.txt'
R1 = 'GENOS_MAIN123_FULL_20261030_R1'
SOURCE = OUT.parent / 'main123_full_20261030_r1' / (R1 + '.zip')
checks, logs = [], []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ok(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


class Fixture:
    def __init__(self, base, nested):
        self.dev = base / 'workspace'
        self.transfer = self.dev / 'TRANSFER' if nested else base / 'TRANSFER'
        self.transfer.mkdir(parents=True)
        self.dev.mkdir(exist_ok=True)
        self.home = base / 'home/genos'
        self.home.mkdir(parents=True)
        (self.home / 'DEV').symlink_to(self.dev, target_is_directory=True)
        self.package = self.transfer / NAME
        shutil.copyfile(SOURCE, self.transfer / SOURCE.name)
        shutil.copyfile(OUT / RUN, self.transfer / RUN)
        with zipfile.ZipFile(SOURCE) as z:
            self.release = json.loads(z.read('SELECTED_RELEASE_RECORD.json'))['release']
            self.spec = json.loads(z.read('PACKAGE.json'))
            for name, expected in self.release['files'].items():
                source = ROOT / self.release['code_root'] / name
                assert sha(source) == expected
                target = self.dev / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            for name in self.spec['patch']:
                target = self.dev / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read('payload/' + name))
        (self.dev / '01_DATA').mkdir()
        (self.dev / '01_DATA/keep.txt').write_text('preserve fixture data')
        (self.dev / '.env').write_text('TEST_ONLY=preserve')
        (self.dev / '.gitignore').write_text('/TRANSFER/\n')
        self.old = self.dev / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
        self.old.write_bytes(b'# prior committed version\n' + self.old.read_bytes())
        self.new = self.dev / '02_BACKEND/semantic_runtime/ontology_work/recorded_fields.py'
        self.new.unlink()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Package test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture baseline')
        self.before = self.snapshot()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.dev), *args], env=self.env,
                              capture_output=True, check=True, timeout=30)

    def snapshot(self):
        return {p.relative_to(self.dev).as_posix(): sha(p) for p in self.dev.rglob('*')
                if p.is_file() and not {'.git', 'TRANSFER'}.intersection(p.relative_to(self.dev).parts)}

    def run(self, args=(), success=True, contains=None):
        result = subprocess.run(['bash', './' + RUN, *args], cwd=self.transfer,
                                env=self.env, capture_output=True, text=True, timeout=120)
        logs.append({'args': list(args), 'nested': self.transfer.parent == self.dev,
                     'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        ok('actual one-command TXT ' + repr(list(args)) + (' succeeds' if success else ' refuses'),
           (result.returncode == 0) == success)
        if contains:
            ok('diagnostic ' + contains, contains in result.stdout + result.stderr)
        return result


def validate():
    with tempfile.TemporaryDirectory(prefix='main123-transfer-r2-validation-') as temporary:
        base = Path(temporary)
        f = Fixture(base / 'nested', True)
        archive = f.transfer / SOURCE.name
        raw_zip = archive.read_bytes()
        archive.write_bytes(b'invalid fixture zip')
        f.run(success=False, contains='R1 ZIP hash mismatch')
        ok('bad ZIP leaves code and package untouched', f.snapshot() == f.before and not f.package.exists())
        archive.write_bytes(raw_zip)
        with zipfile.ZipFile(SOURCE) as z:
            z.extractall(f.transfer / R1)
        old_run = subprocess.run(['bash', str(f.transfer / R1 / (R1 + '_RUN.txt')), 'apply'],
                                 cwd=f.transfer, env=f.env, capture_output=True, text=True, timeout=120)
        logs.append({'r1_photo_reproduction': True, 'exit': old_run.returncode,
                     'stdout': old_run.stdout, 'stderr': old_run.stderr})
        ok('exact R1 photo failure reproduced before any code changes', old_run.returncode == 2 and
           'Extract outside the DEV checkout' in old_run.stdout + old_run.stderr and f.snapshot() == f.before)
        old_state = f.transfer / R1 / 'INSTALL_STATE.json'
        old_state.write_text('{"status":"prepared"}')
        f.run(success=False, contains='R1 installation state already exists')
        ok('prior installer state preserved', old_state.read_text() == '{"status":"prepared"}')
        old_state.unlink()
        f.package.symlink_to(f.transfer / R1, target_is_directory=True)
        f.run(success=False, contains='Symlink path refused')
        f.package.unlink()
        with (f.transfer / '.main123-transfer-r2.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.run(success=False, contains='Resource temporarily unavailable')
        prior = f.old.read_bytes()
        f.old.write_bytes(prior + b'# local edit\n')
        edited = f.snapshot()
        f.run(success=False, contains='Local changes preserved')
        ok('check failure never enters apply', not (f.package / 'INSTALL_STATE.json').exists() and f.snapshot() == edited)
        f.old.write_bytes(prior)
        js = f.dev / '02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js'
        js_raw = js.read_bytes()
        js.write_bytes(js_raw + b'\n')
        f.run(success=False, contains='Required MAIN123 file differs')
        js.write_bytes(js_raw)
        f.run(contains='APPLIED MAIN123')
        ok('all 489 selected code files match after default command',
           all(sha(f.dev / p) == h for p, h in f.release['files'].items()))
        ok('data and env unchanged', all(sha(f.dev / p) == f.before[p] for p in ['01_DATA/keep.txt', '.env']))
        ok('R1 package and failure logs retained in TRANSFER', (f.transfer / R1 / 'runner.py').is_file() and
           bool(list((f.transfer / 'main123-full-r1-logs').glob('*.log'))))
        state_path = f.package / 'INSTALL_STATE.json'
        saved = state_path.read_bytes()
        backup_before = {p.relative_to(f.package).as_posix(): sha(p) for p in (f.package / 'backup').rglob('*') if p.is_file()}
        f.run(contains='REUSE_PACKAGE')
        ok('repeat preserves original state and every backup byte', saved == state_path.read_bytes() and
           backup_before == {p.relative_to(f.package).as_posix(): sha(p) for p in (f.package / 'backup').rglob('*') if p.is_file()})
        # Simulate an interrupted apply with a mixture of before/after bytes.
        f.old.write_bytes((f.package / 'backup' / f.old.relative_to(f.dev)).read_bytes())
        f.new.unlink()
        state = json.loads(saved)
        state['status'] = 'prepared'
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        f.run(contains='APPLIED MAIN123')
        ok('partial application resumes with original backup/state', state_path.read_bytes() == saved and
           all(sha(f.dev / p) == h for p, h in f.release['files'].items()))
        archive.rename(archive.with_suffix('.saved'))
        f.run(['check'], contains='REUSE_PACKAGE')
        archive.with_suffix('.saved').rename(archive)
        payload = f.package / 'payload' / f.old.relative_to(f.dev)
        payload_raw = payload.read_bytes()
        payload.write_bytes(payload_raw + b'\n')
        installed = f.snapshot()
        f.run(success=False, contains='R2 package file changed')
        ok('tampered package refuses without changing checkout', f.snapshot() == installed)
        payload.write_bytes(payload_raw)
        alternative = base / 'another-dev'
        alternative.mkdir()
        subprocess.run(['git', 'init', '-q', str(alternative)], env=f.env, check=True)
        f.run(['check', '--root', str(alternative)], success=False, contains='DEV target changed')
        f.git('add', '-A', '--', *f.spec['patch'])
        f.git('-c', 'user.name=Package test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture apply')
        f.run(['gate-code'], contains='CODE_GATE_PASS')
        current = f.old.read_bytes()
        f.old.write_bytes(current + b'# later user edit\n')
        before_refusal = f.snapshot()
        f.run(['rollback'], success=False, contains='Newer changes exist')
        ok('rollback refusal makes no partial restoration', f.snapshot() == before_refusal)
        f.old.write_bytes(current)
        f.run(['rollback'], contains='ROLLED_BACK_CODE')
        ok('rollback restores exact pre-install code set and bytes', f.snapshot() == f.before)
        f.run(success=False, contains='This delivery was rolled back')
        ok('every wrapper run retains log and exit code',
           len(list((f.transfer / 'main123-transfer-r2-logs').glob('*.exit'))) == len([l for l in logs if not l.get('r1_photo_reproduction')]))
        # Verify location rejection directly on the same installed runner implementation.
        module_spec = importlib.util.spec_from_file_location('tested_main123_runner', f.package / 'runner.py')
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        for candidate in [f.dev, f.dev.parent, f.dev / '.git/package', f.dev / '02_BACKEND']:
            module.HERE = candidate
            rejected = False
            try:
                module.validate_package_location(f.dev, f.spec)
            except ValueError:
                rejected = True
            ok('location overlap refused: ' + candidate.name, rejected)
        outside = Fixture(base / 'outside', False)
        outside.run(contains='APPLIED MAIN123')
        outside.run(['rollback'], contains='ROLLED_BACK_CODE')
        ok('external TRANSFER remains supported', outside.snapshot() == outside.before)


try:
    validate()
finally:
    (OUT / 'VALIDATION_COMMAND_LOGS.json').write_text(json.dumps(logs, ensure_ascii=False, indent=2) + '\n')
    summary = {'passed': sum(row['passed'] for row in checks),
               'failed': sum(not row['passed'] for row in checks), 'checks': checks,
               'model_calls': 0, 'field_genos_verified': False}
    (OUT / 'VALIDATION.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'checks'}))
