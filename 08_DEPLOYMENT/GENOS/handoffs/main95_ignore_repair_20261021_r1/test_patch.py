from pathlib import Path
import base64
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

import pytest

H = Path(__file__).resolve().parent
R = H.parents[3]
N = 'GENOS_MAIN95_IGNORE_REPAIR_20261021_R1'
BASE = H.with_name('main95_comparison_scope_20261020_r1')
ATTEMPT = os.environ.get('PATCH_TEST_ATTEMPT', '01')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


@pytest.fixture
def setup(tmp_path, request):
    root = tmp_path / 'physical checkout'; root.mkdir()
    with zipfile.ZipFile(BASE / 'code.zip') as z:
        z.extractall(root)
    transfer = tmp_path / 'uploaded TRANSFER'; transfer.mkdir()
    shutil.copyfile(H / (N + '.zip'), transfer / (N + '.zip'))
    env = {**os.environ, 'PATH': str(R / '.venv/bin') + ':' + os.environ['PATH'],
           'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1'}
    trace = []
    def run(args, ok=True):
        value = subprocess.run(list(map(str, args)), cwd=transfer, env=env,
                               capture_output=True, text=True, timeout=120)
        trace.append({'args': list(map(str, args)), 'exit': value.returncode,
                      'stdout': value.stdout, 'stderr': value.stderr})
        (H / ('TRACE_' + ATTEMPT + '_' + request.node.name + '.json.gz')).write_bytes(
            gzip.compress(json.dumps(trace, ensure_ascii=False).encode(), mtime=0))
        assert (value.returncode == 0) == ok, value.stdout + value.stderr
        return value
    def git(*args, ok=True): return run(['git', '-C', root, *args], ok)
    git('init', '-q'); git('config', 'user.name', 'Synthetic Test')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    (root / 'user-note.txt').write_text('base\n')
    git('add', '.'); git('commit', '-qm', 'synthetic MAIN95')
    index = root / '.git/index'; exclude = root / '.git/info/exclude'
    before_exclude = exclude.read_bytes()
    run(['python3', '-m', 'zipfile', '-e', './' + N + '.zip', './' + N])
    package = transfer / N
    alias = tmp_path / 'DEV'; alias.symlink_to(root, target_is_directory=True)
    def action(name, ok=True):
        return run(['bash', './' + N + '/' + N + '_RUN.txt', name, '--root', alias], ok)
    yield root, package, run, git, action, index, exclude, before_exclude
    (H / ('RUN_' + ATTEMPT + '_' + request.node.name + '.json')).write_text(json.dumps(
        {'status': 'TRACE_COMPLETE_NOT_TEST_VERDICT', 'commands': len(trace), 'intentional_failures': sum(x['exit'] != 0 for x in trace),
         'patch_zip_sha256': sha((H / (N + '.zip')).read_bytes()), 'field_verified': False}, indent=2))


def test_full_cycle_and_future_overwrite(setup):
    root, package, run, git, action, index, exclude, before_exclude = setup
    originals = {n: (root / n).read_bytes() for n in ('.gitignore', 'genosIgnore')}
    trash = root / '.Trash-1001/files/a [x].csv'; trash.parent.mkdir(parents=True)
    trash.write_bytes(b'original,data\r\n')
    transfer_db = root / 'QUERY_TRANSFER_20261021_R1/query-data.db'
    transfer_db.parent.mkdir(); transfer_db.write_bytes(b'SYNTHETIC DB')
    (root / 'user-note.txt').write_text('intentional staged user change\n')
    git('add', '.')
    assert '.Trash-1001' in git('diff', '--cached', '--name-only').stdout
    preindex = index.read_bytes()
    action('check'); assert index.read_bytes() == preindex
    action('apply'); action('apply'); assert index.read_bytes() == preindex
    action('clean-stage'); after = index.read_bytes()
    paths = git('diff', '--cached', '--name-only').stdout.splitlines()
    assert set(paths) == {'.gitignore', 'genosIgnore', 'user-note.txt'}
    assert trash.read_bytes() == b'original,data\r\n' and transfer_db.read_bytes() == b'SYNTHETIC DB'
    action('clean-stage'); assert index.read_bytes() == after
    action('undo-stage'); assert index.read_bytes() == preindex
    action('clean-stage'); action('gate', False)
    git('commit', '-qm', 'apply MAIN95 ignore repair and preserved user change')
    action('gate')
    gate = json.loads((package / 'CODE_GATE.json').read_text())
    assert gate['status'] == 'MAIN95_PLUS_IGNORE_CODE_MATCH' and gate['code_files'] == 1313
    fixed = {n: (root / n).read_bytes() for n in originals}
    # Reproduce an old cumulative overwriting both tracked ignore files.
    for n, raw in originals.items(): (root / n).write_bytes(raw)
    fresh = root / '.Trash-1002/files/new.csv'; fresh.parent.mkdir(parents=True); fresh.write_text('keep\n')
    git('add', '.')
    assert '.Trash-' not in git('ls-files').stdout and 'QUERY_TRANSFER_' not in git('ls-files').stdout
    for n, raw in fixed.items(): (root / n).write_bytes(raw)
    action('undo')
    assert all((root / n).read_bytes() == raw for n, raw in originals.items())
    assert exclude.read_bytes() == before_exclude
    assert trash.exists() and transfer_db.exists() and fresh.exists()


def test_committed_data_is_not_silently_removed(setup):
    root, package, run, git, action, index, *_ = setup
    p = root / '.Trash-1001/old.csv'; p.parent.mkdir(); p.write_text('old\n')
    git('add', '.'); git('commit', '-qm', 'synthetic committed trash')
    action('apply'); before = index.read_bytes(); head = git('rev-parse', 'HEAD').stdout
    action('clean-stage', False)
    assert index.read_bytes() == before and git('rev-parse', 'HEAD').stdout == head and p.exists()
    assert json.loads((package / 'COMMITTED_DATA.json').read_text())['action'] == 'NONE'


def test_code_or_package_tampering_is_rejected(setup):
    root, package, run, git, action, index, *_ = setup
    old = (root / 'service.py').read_bytes(); (root / 'service.py').write_bytes(old + b'\n# drift\n')
    original_ignore = (root / '.gitignore').read_bytes()
    action('check', False); assert (root / '.gitignore').read_bytes() == original_ignore
    (root / 'service.py').write_bytes(old)
    (package / 'IGNORE_RULES.txt').write_text('# modified\n')
    action('apply', False); assert (root / '.gitignore').read_bytes() == original_ignore


def test_later_index_and_ignore_edits_are_preserved(setup):
    root, package, run, git, action, index, *_ = setup
    action('apply'); action('clean-stage')
    (root / 'user-note.txt').write_text('later change\n'); git('add', '--', 'user-note.txt')
    before = index.read_bytes(); action('undo-stage', False); assert index.read_bytes() == before
    p = root / '.gitignore'; p.write_bytes(p.read_bytes() + b'\nuser-custom/\n'); current = p.read_bytes()
    action('undo', False); assert p.read_bytes() == current


def test_interrupted_profile_and_index_transactions_recover(setup):
    root, package, run, git, action, index, *_ = setup
    crash = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import apply_ignore as m
old=m.write;target=Path(sys.argv[2])/'.gitignore'
def fail(path,raw):
 old(path,raw)
 if Path(path)==target:os._exit(77)
m.write=fail
sys.argv=['apply_ignore.py','apply','--root',sys.argv[2]];m.main()
'''
    assert run(['python3', '-c', crash, package, root], False).returncode == 77
    action('apply')
    crash2 = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import apply_ignore as m
old=os.replace;target=Path(sys.argv[2])/'.git/index'
def fail(a,b):
 old(a,b)
 if Path(b)==target:os._exit(77)
os.replace=fail
sys.argv=['apply_ignore.py','clean-stage','--root',sys.argv[2]];m.main()
'''
    assert run(['python3', '-c', crash2, package, root], False).returncode == 77
    assert json.loads((package / 'STAGE_STATE.json').read_text())['phase'] == 'PREPARED'
    action('clean-stage')
    assert json.loads((package / 'STAGE_STATE.json').read_text())['phase'] == 'APPLIED'
    action('undo-stage'); action('undo')


def test_existing_index_lock_is_respected(setup):
    root, package, run, git, action, index, *_ = setup
    action('apply'); before = index.read_bytes()
    lock = Path(str(index) + '.lock'); lock.write_text('other git operation')
    action('clean-stage', False)
    assert index.read_bytes() == before and lock.read_text() == 'other git operation'


def test_generation_gate_preserves_existing_verifier_failure(setup):
    root, package, run, git, action, index, *_ = setup
    action('apply'); action('clean-stage'); git('commit', '-qm', 'ignore repair')
    # Missing selected generation is a failure, never a code-only success.
    run(['bash', './' + N + '/' + N + '_RUN.txt', 'gate-sqlite', '--root', root,
         '--generation', root / 'MISSING_GENERATION'], False)
    assert not (package / 'CODE_GATE.json').exists()


def test_index_lock_created_after_commit_is_preserved(setup):
    root, package, run, git, action, index, *_ = setup
    action('apply')
    script = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import apply_ignore as m
old=os.replace;target=Path(sys.argv[2])/'.git/index'
def concurrent(a,b):
 old(a,b)
 if Path(b)==target:Path(str(target)+'.lock').write_text('next git owner')
os.replace=concurrent
sys.argv=['apply_ignore.py','clean-stage','--root',sys.argv[2]];m.main()
'''
    run(['python3', '-c', script, package, root])
    assert Path(str(index) + '.lock').read_text() == 'next git owner'
