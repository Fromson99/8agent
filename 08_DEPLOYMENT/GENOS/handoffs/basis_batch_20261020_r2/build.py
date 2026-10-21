"""Repackage the sealed R1 code; change only installer and handoff metadata."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('basis_batch_20261020_r1')
NAME = 'GENOS_BASIS_BATCH_20261020_R2'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

assert not (HERE / 'EMAIL_SENT.json').exists()
prior = json.loads((OLD / 'PACKAGE.json').read_text())
sealed = json.loads((OLD / 'SEALED.json').read_text())
for name, record in sealed['files'].items():
    assert sha(OLD / name) == record['sha256'], name
for name in prior['patch']:
    assert sha(HERE / 'payload' / name) == prior['code'][name], name
    assert (HERE / 'payload' / name).read_bytes() == (OLD / 'payload' / name).read_bytes()
files = ['runner.py', NAME + '_RUN.txt', NAME + '_WORKFLOW_PASTE_ALL.txt',
         'GUIDE_UTF8.txt', 'VALIDATION.json']
files += ['payload/' + name for name in prior['patch']]
for name in files:
    if name.endswith('.py'):
        ast.parse((HERE / name).read_bytes(), filename=name, feature_version=(3, 11))
subprocess.run(['bash', '-n', str(HERE / (NAME + '_RUN.txt'))], check=True)
spec = {**prior, 'version': NAME, 'supersedes': prior['version'],
        'prior_package_sha256': sha(OLD / 'PACKAGE.json'),
        'payload': {name: sha(HERE / name) for name in files},
        'correction': 'Resolve DEV entry symlink; verify and bind physical Git checkout'}
(HERE / 'PACKAGE.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
files.append('PACKAGE.json')
with zipfile.ZipFile(HERE / (NAME + '.zip'), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in sorted(files):
        assert Path(name).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
        info = zipfile.ZipInfo(name, (2026, 10, 20, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, (HERE / name).read_bytes())
record = {'zip_sha256': sha(HERE / (NAME + '.zip')),
          'bytes': (HERE / (NAME + '.zip')).stat().st_size,
          'patch_files': len(prior['patch']), 'code_identical_to_R1': True,
          'bound_code_files': len(prior['code']), 'javascript_files': 0}
(HERE / 'BUILD.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
