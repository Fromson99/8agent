"""Bind the consumer to the actual delivered producer, never the mutable worktree."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_RISK_BASIS_REVIEW_20261020_R4'
PRODUCER = HERE.with_name('basis_transfer_report_20261020_r1') / 'GENOS_BASIS_ARTIFACTS_20261020_R1.zip'
PREVIOUS = HERE.with_name('risk_basis_staging_20261020_r3') / 'GENOS_RISK_BASIS_REVIEW_20261020_R3.zip'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
put = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
assert sha(PRODUCER) == '84f2251639458427683aa2f53f6588d57c7944243fde7bfaf0a36257f3a4785e'
assert sha(PREVIOUS) == 'f81588f90b645bea0f50ae71c0ac2b30759b58ac3153bb10e4721236323e8788'
common = HERE / 'common'
common.mkdir(exist_ok=True)
with zipfile.ZipFile(PRODUCER) as z:
    producer = json.loads(z.read('CODE_REQUIREMENTS.json'))
    for name, expected in producer['tool'].items():
        data = z.read(name)
        assert hashlib.sha256(data).hexdigest() == expected
        (common / name).write_bytes(data)
    (common / 'CODE_REQUIREMENTS.json').write_bytes(z.read('CODE_REQUIREMENTS.json'))
with zipfile.ZipFile(PREVIOUS) as z:
    original = json.loads(z.read('CODE_MANIFEST.json'))
    for name in ('risk_basis_seed.py', 'risk_basis_staging.py', 'risk_basis_seed_cli.py'):
        data = z.read(name)
        assert hashlib.sha256(data).hexdigest() == original['files'][name]
        (HERE / name).write_bytes(data)
    (HERE / 'runner.py').write_bytes(z.read('runner.py'))
    (HERE / (NAME + '_RUN.txt')).write_bytes(z.read('GENOS_RISK_BASIS_REVIEW_20261020_R3_RUN.txt'))
assert original['checkout'] == producer['checkout']
for file in [*common.glob('*.py'), *HERE.glob('risk_basis_*.py'), HERE/'runner.py']:
    ast.parse(file.read_text(), filename=str(file), feature_version=(3, 11))
subprocess.run(['bash', '-n', str(HERE / (NAME + '_RUN.txt'))], check=True)
names = ['runner.py', 'risk_basis_seed.py', 'risk_basis_staging.py', 'risk_basis_seed_cli.py',
         NAME+'_RUN.txt', '읽어주세요.txt', 'PATCH_NOTES.txt'] + [
             'common/'+n for n in [*producer['tool'], 'CODE_REQUIREMENTS.json']]
manifest = {'schema': 'risk-basis-json-review-v4', 'checkout': producer['checkout'],
            'files': {n: sha(HERE/n) for n in names}, 'producer_archive': PRODUCER.name,
            'producer_sha256': sha(PRODUCER),
            'producer_tool_binding': {n: producer['tool'][n] for n in
                                     ('basis_batch.py', 'basis_batch_candidates.py')},
            'direct_sqlite_write': False, 'main_changed': False, 'genos_verified': False}
put(HERE/'CODE_MANIFEST.json', manifest)
archive = HERE / (NAME+'.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in [*names, 'CODE_MANIFEST.json']:
        assert Path(name).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
        z.write(HERE/name, name)
put(HERE/'SHA256.json', {'archive': archive.name, 'sha256': sha(archive),
                       'code_manifest_sha256': sha(HERE/'CODE_MANIFEST.json')})
print(json.dumps({'archive': str(archive), 'sha256': sha(archive), 'bytes': archive.stat().st_size,
                  'producer_tool_binding': manifest['producer_tool_binding']}))
