"""New cumulative artifact; never rewrite any previously mailed archive."""
from pathlib import Path
import base64
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / '09_ARTIFACTS/HANDOFF/GENOS'
BASE = DIRECTORY / 'genos-staged-authoring-20260910.zip'
PATCH = DIRECTORY / 'genos-four-stage-20260910.zip'
BASE_SHA = '12ffbf176190cab87286f754dbc8daf314bdad4986667725495702c7a674fb9c'
INSTALLER_BASE = ROOT / '06_TOOLS/COMMANDS/genos_apply_staged_authoring.sh'
INSTALLER_SHA = '3480b8611a4caa919507bd704034b8b797ecaa75b2c72a1d17e0c15f1e7b2548'
FILES = [
    '02_BACKEND/lawrag/pipeline/genos_build.py',
    '02_BACKEND/lawrag/pipeline/genos_staged.py',
    '02_BACKEND/lawrag/pipeline/genos_stages.py',
    '02_BACKEND/lawrag/pipeline/genos_progress.py',
    '02_BACKEND/lawrag/pipeline/genos_raw_move.py',
    '06_TOOLS/pipeline.py',
    '06_TOOLS/COMMANDS/genos_data_stages.py',
    '06_TOOLS/COMMANDS/genos_data_stages.sh',
    '06_TOOLS/COMMANDS/genos_move_raw.py',
    '07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md',
]
sha = lambda b: hashlib.sha256(b).hexdigest()


def build():
    if sha(BASE.read_bytes()) != BASE_SHA or sha(INSTALLER_BASE.read_bytes()) != INSTALLER_SHA:
        raise ValueError('Immutable delivery base changed')
    with zipfile.ZipFile(BASE) as z:
        manifest = json.loads(z.read('patch-manifest.json'))
        content = {name: z.read(name) for name in manifest['files']}
    for record in manifest['files'].values():
        record['previous_sha256'] = sorted(set(record['previous_sha256'] + [record['sha256']]))
    for name in FILES:
        content[name] = (ROOT / name).read_bytes()
        record = manifest['files'].setdefault(name, {'allow_missing': True, 'previous_sha256': [], 'preserve_existing': False})
        record['sha256'] = sha(content[name])
    manifest.update(base_mail_id='1a089e67d5363b6c', base_archives={BASE.name: BASE_SHA},
                    scope='EXPLICIT_OFFLINE_FOUR_STAGE_NO_ACTIVE_SELECTION', models_called=False,
                    latest_guide='07_DOCS/REFERENCE/OPERATIONS/GENOS_FOUR_STAGE.md')
    for name, fingerprint in manifest['engine_dependencies'].items():
        if sha(content.get(name, (ROOT / name).read_bytes())) != fingerprint:
            raise ValueError('Runtime dependency drift: ' + name)
    content['patch-manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(PATCH, 'w') as z:
        for name, raw in sorted(content.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 10, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            z.writestr(info, raw)
    fingerprint = sha(PATCH.read_bytes())
    installer = INSTALLER_BASE.read_text().replace(BASE.name, PATCH.name).replace(BASE_SHA, fingerprint)
    installer = installer.replace("print('다음: cd '+str(root)+' && bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-staged-001 --exclude-internal --extraction-mode staged --check-only')",
        "print('다음: cd '+str(root)+' && .venv/bin/python 06_TOOLS/COMMANDS/genos_move_raw.py (먼저 이동 미리보기)')")
    target = DIRECTORY / 'genos_apply_four_stage.sh'
    target.write_text(installer)
    target.with_name(target.name + '.b64.txt').write_bytes(base64.encodebytes(installer.encode()))
    print(json.dumps({'path': str(PATCH), 'bytes': PATCH.stat().st_size, 'sha256': fingerprint,
                      'installer': str(target), 'files': len(manifest['files'])}))


if __name__ == '__main__':
    build()
