from pathlib import Path
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

H = Path(__file__).resolve().parent
R = H.parents[3]
N = 'GENOS_MAIN95_IGNORE_REPAIR_20261021_R1'
base = H / 'final-runtime-02'; base.mkdir(exist_ok=False)
root = base / 'checkout'; root.mkdir()
with zipfile.ZipFile(H.with_name('main95_comparison_scope_20261020_r1') / 'code.zip') as z:
    z.extractall(root)
transfer = base / 'actual TRANSFER'; transfer.mkdir()
shutil.copyfile(H / (N + '.zip'), transfer / (N + '.zip'))
shutil.copyfile(H / (N + '_RUN.txt'), transfer / (N + '_RUN.txt'))
env = {**os.environ, 'PATH': str(R / '.venv/bin') + ':' + os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'}
trace = []
def run(args):
    p = subprocess.run(list(map(str, args)), cwd=transfer, env=env, capture_output=True, text=True, timeout=120)
    trace.append({'args': list(map(str, args)), 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    (H / 'FINAL_TRACE.json.gz').write_bytes(gzip.compress(json.dumps(trace, ensure_ascii=False).encode(), mtime=0))
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout
def git(*args): return run(['git', '-C', root, *args])
git('init', '-q'); git('config', 'user.name', 'Synthetic Final'); git('config', 'user.email', 'test@example.invalid')
git('add', '.'); git('commit', '-qm', 'base MAIN95')
original_exclude = (root / '.git/info/exclude').read_bytes()
trash = root / '.Trash-1001/files/AUDIT.csv'; trash.parent.mkdir(parents=True); trash.write_bytes(b'x,y\r\n')
git('add', '.')
index_before = (root / '.git/index').read_bytes()
# Complete independent execution TXT must extract once and retain state thereafter.
command = ['bash', './' + N + '_RUN.txt']
run([*command, 'repair', '--root', root]); after = (root / '.git/index').read_bytes()
run([*command, 'repair', '--root', root]); assert (root / '.git/index').read_bytes() == after
assert '.Trash' not in git('ls-files').strip() and trash.read_bytes() == b'x,y\r\n'
run([*command, 'undo-stage', '--root', root]); assert (root / '.git/index').read_bytes() == index_before
run([*command, 'undo', '--root', root]); assert (root / '.git/info/exclude').read_bytes() == original_exclude
run([*command, 'repair', '--root', root]); git('commit', '-qm', 'ignore repair')
run([*command, 'gate', '--root', root])
spec = json.loads((transfer / N / 'PATCH_SPEC.json').read_text())
for n, digest in spec['payload_hashes'].items():
    assert hashlib.sha256((transfer / N / n).read_bytes()).hexdigest() == digest
with zipfile.ZipFile(H / (N + '.zip')) as z:
    assert z.testzip() is None
    assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
    assert z.read(N + '_RUN.txt') == (H / (N + '_RUN.txt')).read_bytes()
result = {'status': 'PASS', 'commands': len(trace), 'outer_zip_sha256': hashlib.sha256((H / (N + '.zip')).read_bytes()).hexdigest(),
          'javascript_files': 0, 'standalone_txt_identical': True, 'exact_index_rollback': True,
          'files_preserved': True, 'main95_code_gate': True, 'field_verified': False,
          'product_script_sha256': hashlib.sha256((H / 'apply_ignore.py').read_bytes()).hexdigest()}
(H / 'FINAL_VERIFICATION.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
