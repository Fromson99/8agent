"""Package only maintained command additions; retain previous handoffs."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_STABLE_COMMANDS_20261021_R1'
sha = lambda b: hashlib.sha256(b).hexdigest()
contractpath = ROOT / '00_SYSTEM/BASIS_COMMANDS.json'
contract = json.loads(contractpath.read_text())
contract['files'] = {n: sha((ROOT / n).read_bytes()) for n in contract['files']}
contractpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n')
names = ['00_SYSTEM/BASIS_COMMANDS.json', *contract['files'], '07_DOCS/REFERENCE/OPERATIONS/GENOS_STABLE_COMMANDS.txt']
base = ROOT / '08_DEPLOYMENT/GENOS/handoffs/main95_comparison_scope_20261020_r1/code.zip'
allowed, payload = {}, {}
with zipfile.ZipFile(base) as z:
    for name in names:
        raw = (ROOT / name).read_bytes()
        if name.endswith('.py'):
            ast.parse(raw, filename=name, feature_version=(3, 11))
        target = HERE / 'payload' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        payload[name] = sha(raw)
        allowed[name] = [sha(z.read(name))] if name in z.namelist() else [None]
package = {'schema_version': 'genos-stable-commands-patch-v1', 'revision': NAME,
           'payload': payload, 'allowed_before': allowed, 'base_code_zip_sha256': sha(base.read_bytes()),
           'runtime_data_modified': False, 'main_changed': False, 'field_verified': False}
(HERE / 'PACKAGE.json').write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n')
shutil.copyfile(ROOT / names[-1], HERE / 'COMMANDS.txt')
for name in ('installer.py',):
    ast.parse((HERE / name).read_bytes(), filename=name, feature_version=(3, 11))
subprocess.run(['bash', '-n', str(HERE / 'GENOS_STABLE_COMMANDS_RUN.txt')], check=True)
files = ['installer.py', 'GENOS_STABLE_COMMANDS_RUN.txt', 'PACKAGE.json', 'COMMANDS.txt',
         *['payload/' + n for n in names]]
archive = HERE / (NAME + '.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in files:
        z.write(HERE / name, name)
(HERE / 'SHA256SUMS.txt').write_text('\n'.join(sha((HERE / n).read_bytes()) + '  ' + n
    for n in [NAME + '.zip', 'GENOS_STABLE_COMMANDS_RUN.txt', 'COMMANDS.txt']) + '\n')
print(json.dumps({'zip': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes())}))
