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
NAME = 'GENOS_MAIN123_FULL_OVERWRITE_20261030_R3'
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
        shutil.copyfile(OUT / (NAME + '.zip'), self.transfer / (NAME + '.zip'))
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


def drift(f, *, missing_js=False):
    # Older partial installations plus uncommitted/staged and untracked targets.
    for i, name in enumerate(sorted(f.spec['patch'])):
        target = f.dev / name
        if i % 11 == 0:
            target.unlink(missing_ok=True)
        elif i % 7 == 0:
            target.write_bytes(b'old field version before full overwrite\n')
    f.old.write_bytes(b'# staged field workflow change\n')
    f.git('add', '--', f.old.relative_to(f.dev).as_posix())
    f.new.write_bytes(b'# untracked field implementation\n')
    js = f.dev / '02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js'
    if missing_js:
        js.unlink()
    else:
        js.write_bytes(b'// old field app.js\n')
    (f.dev / '02_BACKEND/field_extra.py').write_text('# unrelated field file\n')
    f.before = f.snapshot()
    f.index_before = sha(f.dev / '.git/index')
    expected = json.loads((OUT / 'EXPECTED_PACKAGE.json').read_text())['code']
    missing = sum(not (f.dev / p).exists() for p in expected)
    different = sum((f.dev / p).is_file() and sha(f.dev / p) != h for p, h in expected.items())
    ok('fixture has many missing and differing targets', missing >= 20 and different >= 20)


def validate():
    handoff = json.loads((OUT / 'HANDOFF.json').read_text())
    for row in handoff['attachments']:
        ok('attachment hash: ' + row['filename'], sha(Path(row['path'])) == row['sha256'])
    with zipfile.ZipFile(OUT / (NAME + '.zip')) as archive:
        names = archive.namelist()
        ok('flat archive has no nested ZIP or excluded JS extensions',
           len(names) == len(set(names)) and all(Path(n).suffix.lower() not in {'.zip', '.js', '.jsx', '.mjs', '.cjs'} for n in names))
        spec = json.loads(archive.read('PACKAGE.json'))
        ok('all 492 code files supplied with no preexisting dependency',
           set(spec['code']) == set(spec['patch']) == set(spec['payload_paths']) and len(spec['code']) == 492 and
           json.loads(archive.read('CODE_MANIFEST.json'))['required_files'] == [])
        ok('all archive payload bytes match target code hashes',
           all(hashlib.sha256(archive.read(spec['payload_paths'][p])).hexdigest() == h for p, h in spec['code'].items()))
    with tempfile.TemporaryDirectory(prefix='main123-full-r3-validation-') as temporary:
        base = Path(temporary)
        f = Fixture(base / 'nested', True)
        # Reproduce the user's exact second photo on the previous delivery.
        shutil.copyfile(SOURCE, f.transfer / SOURCE.name)
        r2_name = 'GENOS_MAIN123_TRANSFER_20261030_R2_RUN.txt'
        shutil.copyfile(OUT.parent / 'main123_transfer_20261030_r2' / r2_name, f.transfer / r2_name)
        js = f.dev / '02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js'
        js.write_bytes(b'// older installed viewer\n')
        old_run = subprocess.run(['bash', './' + r2_name], cwd=f.transfer, env=f.env,
                                 capture_output=True, text=True, timeout=120)
        logs.append({'r2_photo_reproduction': True, 'exit': old_run.returncode,
                     'stdout': old_run.stdout, 'stderr': old_run.stderr})
        ok('exact R2 photo failure reproduced', old_run.returncode == 2 and
           'Required MAIN123 file differs: 02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js' in old_run.stdout + old_run.stderr)
        prior_package = f.transfer / 'GENOS_MAIN123_TRANSFER_20261030_R2'
        prior_state = prior_package / 'INSTALL_STATE.json'
        prior_state.write_text('{"fixture":"preserve prior incomplete installation"}\n')
        prior_bytes = {p.relative_to(prior_package).as_posix(): sha(p) for p in prior_package.rglob('*') if p.is_file()}
        (f.transfer / SOURCE.name).unlink()  # Test fixture only: R3 must be independent.
        drift(f)
        package_zip = f.transfer / (NAME + '.zip')
        original_zip = package_zip.read_bytes()
        package_zip.write_bytes(b'wrong archive')
        f.run(success=False, contains='R3 ZIP hash mismatch')
        ok('wrong ZIP changes no code or installer state', f.snapshot() == f.before and not f.package.exists())
        package_zip.write_bytes(original_zip)
        f.package.symlink_to(prior_package, target_is_directory=True)
        f.run(success=False, contains='Symlink path refused')
        f.package.unlink()
        with (f.transfer / '.main123-full-overwrite-r3.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.run(success=False, contains='Resource temporarily unavailable')
        # All location checks precede writes, including code destination symlinks.
        original_new = f.new.read_bytes()
        f.new.unlink()
        f.new.symlink_to(f.dev / '01_DATA/keep.txt')
        f.run(success=False, contains='Symlink path refused')
        f.new.unlink()
        f.new.write_bytes(original_new)
        f.run(['check'], contains='CHECK_PASS MAIN123')
        ok('precheck accepts old/dirty/untracked/missing targets without applying',
           f.snapshot() == f.before and not (f.package / 'INSTALL_STATE.json').exists())
        # Inject a real write failure after four replaced files, while retaining
        # the unchanged delivery and its actual runner entry point.
        inject = r'''
import importlib.util, json, pathlib, sys
package, root = map(pathlib.Path, sys.argv[1:])
loader=importlib.util.spec_from_file_location('r3_actual_runner',package/'runner.py')
module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
spec=json.loads((package/'PACKAGE.json').read_text())
targets={str(root/p) for p in spec['code']};original=module.write;count=0
def fail_during_apply(path,value):
 global count
 if str(path) in targets:
  count+=1
  if count==5: raise OSError('INJECTED_DISK_WRITE_FAILURE_AFTER_FOUR_FILES')
 return original(path,value)
module.write=fail_during_apply
sys.argv=['runner.py','apply','--root',str(root)]
try: module.main()
except OSError as exc:
 print(str(exc));sys.exit(17)
'''
        failed = subprocess.run([str(ROOT / '.venv/bin/python'), '-c', inject, str(f.package), str(f.dev)],
                                cwd=f.transfer, env=f.env, capture_output=True, text=True, timeout=120)
        logs.append({'injected_actual_write_failure': True, 'exit': failed.returncode,
                     'stdout': failed.stdout, 'stderr': failed.stderr})
        ok('actual write failure preserves partial state and reports failure', failed.returncode == 17 and
           'INJECTED_DISK_WRITE_FAILURE_AFTER_FOUR_FILES' in failed.stdout and
           json.loads((f.package / 'INSTALL_STATE.json').read_text())['status'] == 'prepared')
        saved_prepared = json.loads((f.package / 'INSTALL_STATE.json').read_text())
        ok('every original file backed up before first code replacement',
           all((row['before'] == f.before.get(p)) and
               (row['before'] is None or sha(f.package / 'backup' / p) == row['before'])
               for p, row in saved_prepared['files'].items()))
        f.run(contains='APPLIED MAIN123 FULL R3')
        ok('all 492 installed files match after resuming single command', all(sha(f.dev / p) == h for p, h in spec['code'].items()))
        ok('git index and unrelated files preserved during overwrite', sha(f.dev / '.git/index') == f.index_before and
           all(sha(f.dev / p) == f.before[p] for p in ['01_DATA/keep.txt', '.env', '02_BACKEND/field_extra.py']))
        ok('old R2 package and incomplete state retained byte-for-byte', prior_bytes ==
           {p.relative_to(prior_package).as_posix(): sha(p) for p in prior_package.rglob('*') if p.is_file()})
        saved = (f.package / 'INSTALL_STATE.json').read_bytes()
        backups = {p.relative_to(f.package).as_posix(): sha(p) for p in (f.package / 'backup').rglob('*') if p.is_file()}
        f.run(contains='REUSE_PACKAGE')
        ok('repeat preserves original backup and state', saved == (f.package / 'INSTALL_STATE.json').read_bytes() and backups ==
           {p.relative_to(f.package).as_posix(): sha(p) for p in (f.package / 'backup').rglob('*') if p.is_file()})
        raw = f.old.read_bytes()
        f.old.write_bytes(raw + b'# edit after installation\n')
        changed = f.snapshot()
        f.run(success=False, contains='Checkout changed after preparation')
        f.run(['rollback'], success=False, contains='Newer changes exist')
        ok('later edits are not silently overwritten or partially rolled back', f.snapshot() == changed)
        f.old.write_bytes(raw)
        backup = f.package / 'backup' / f.old.relative_to(f.dev)
        backup_raw = backup.read_bytes()
        backup.write_bytes(backup_raw + b'changed')
        f.run(['rollback'], success=False, contains='Backup changed')
        backup.write_bytes(backup_raw)
        payload = f.package / spec['payload_paths']['02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js']
        payload_raw = payload.read_bytes()
        payload.write_bytes(payload_raw + b'changed')
        f.run(success=False, contains='R3 package file changed')
        payload.write_bytes(payload_raw)
        alternative = base / 'another-dev'
        alternative.mkdir()
        subprocess.run(['git', 'init', '-q', str(alternative)], env=f.env, check=True)
        f.run(['check', '--root', str(alternative)], success=False, contains='DEV target changed')
        package_zip.unlink()
        f.run(['check'], contains='REUSE_PACKAGE')
        # Commit only declared files; user extras stay untracked as in the field.
        f.git('add', '-A', '--', *spec['patch'])
        f.git('-c', 'user.name=Package test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'full replacement fixture')
        f.run(['gate-code'], contains='GENOS_RELEASE_GATE PASS')
        f.run(['rollback'], contains='ROLLED_BACK_CODE')
        ok('rollback restores exact dirty/missing/untracked pre-install bytes', f.snapshot() == f.before)
        f.run(success=False, contains='This delivery was rolled back')
        ok('every wrapper execution retained a persistent log and exit file',
           len(list((f.transfer / 'main123-full-overwrite-r3-logs').glob('*.exit'))) ==
           len([r for r in logs if 'args' in r]))
        # Fresh one-command installation with app.js entirely absent, in an
        # external TRANSFER with no old ZIPs, packages, or prior installer state.
        outside = Fixture(base / 'outside', False)
        drift(outside, missing_js=True)
        outside.run(contains='APPLIED MAIN123 FULL R3')
        ok('fresh single-command install supplies missing JS and all code',
           all(sha(outside.dev / p) == h for p, h in spec['code'].items()))
        outside.run(['rollback'], contains='ROLLED_BACK_CODE')
        ok('fresh rollback restores absent JS and prior code set', outside.snapshot() == outside.before and
           not (outside.dev / '02_BACKEND/lawrag/api/viewer/legal_knowledge/app.js').exists())


try:
    validate()
finally:
    (OUT / 'VALIDATION_COMMAND_LOGS.json').write_text(json.dumps(logs, ensure_ascii=False, indent=2) + '\n')
    summary = {'passed': sum(row['passed'] for row in checks), 'failed': sum(not row['passed'] for row in checks),
               'checks': checks, 'model_calls': 0, 'field_genos_verified': False}
    (OUT / 'VALIDATION.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'checks'}))


