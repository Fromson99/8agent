"""Correct the user-confirmed CPU allocation, retaining sealed R9 behavior."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent / 'pipeline_speed_20261028_r9'
SERVICE = 'GENOS_DATAIKU_COMPUTE_20261029_R10'
PACKAGE = 'DATAIKU_COMPUTE_RECIPES_20261029_R10.zip'
OLD_SERVICE = 'GENOS_DATAIKU_COMPUTE_20261028_R9'
OLD_CODE = 'aa73eedbbee5f9f4e842c87e7f0fca2278c2dc56b936390871fbf268efea7c73'
R7 = '1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
R8 = 'f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def edit(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def writezip(path, files):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, raw)


def main():
    assert not (HERE / 'VALIDATION.json').exists(), 'Do not overwrite qualified delivery'
    with zipfile.ZipFile(BASE / (OLD_SERVICE + '.zip')) as archive:
        old = {n.split('/', 1)[1]: archive.read(n) for n in archive.namelist()}
    assert sha(old['CODE_PINS.json']) == OLD_CODE
    pins = json.loads(old['CODE_PINS.json'])
    assert set(old) == set(pins['files']) | {'CODE_PINS.json'}
    assert all(sha(old[n]) == h for n, h in pins['files'].items())
    payload = dict(old)
    payload['worker.py'] = edit(old['worker.py'].decode(), "'--fulltext-workers', '4'", "'--fulltext-workers', '1'").encode()
    payload['CODE_PINS.json'] = (json.dumps({**pins, 'files': {n: sha(b) for n, b in payload.items() if n != 'CODE_PINS.json'}}, sort_keys=True, indent=2) + '\n').encode()
    code = sha(payload['CODE_PINS.json'])
    writezip(HERE / (SERVICE + '.zip'), {SERVICE + '/' + n: b for n, b in payload.items()})
    (HERE / 'worker.py').write_bytes(payload['worker.py'])
    with zipfile.ZipFile(BASE / 'DATAIKU_COMPUTE_RECIPES_20261028_R9.zip') as archive:
        client = {n: archive.read(n) for n in archive.namelist()}
    client['COMPUTE_CODE_SHA256.txt'] = (code + '\n').encode()
    upgrade = client['checkpoint_upgrade.py'].decode()
    upgrade = edit(upgrade, 'PREVIOUS_CODES = {', "PREVIOUS_CODES = {'" + OLD_CODE + "', ")
    upgrade = edit(upgrade, f"if previous_code in {{'{R7}', '{R8}'}}:", f"if previous_code in {{'{R7}', '{R8}', '{OLD_CODE}'}}:")
    upgrade = upgrade.replace('SEALED_R7_R8_FIXED_SKIP_NO_MODEL_PATH', 'SEALED_R7_R8_R9_FIXED_SKIP_NO_MODEL_PATH')
    upgrade = upgrade.replace('BOUNDED_FOUR_WORKER_UNIT_INDEX', 'SINGLE_CPU_WORKER_CONFIGURATION')
    client['checkpoint_upgrade.py'] = upgrade.encode()
    client['updater.py'] = client['updater.py'].replace(b'speed-r9-before.json', b'single-cpu-r10-before.json')
    reference = json.loads(client['REFERENCE.json'])
    reference['prior_compute_bootstraps'].append((BASE / 'bootstrap.txt').read_text())
    client['REFERENCE.json'] = (json.dumps(reference) + '\n').encode()
    client['PACKAGE_FILES.json'] = (json.dumps({n: sha(b) for n, b in client.items() if n != 'PACKAGE_FILES.json'}, sort_keys=True, indent=2) + '\n').encode()
    writezip(HERE / PACKAGE, client)
    old_boot = (BASE / 'bootstrap.txt').read_text()
    boot = old_boot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R9.zip', PACKAGE).replace(sha((BASE / 'DATAIKU_COMPUTE_RECIPES_20261028_R9.zip').read_bytes()), sha((HERE / PACKAGE).read_bytes()))
    boot = re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = ' + str((HERE / PACKAGE).stat().st_size), boot)
    (HERE / 'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL', 'CONTROL'):
        text = (BASE / f'DATAIKU_R9_{kind}.txt').read_text().replace(old_boot, boot).replace(repr(old_boot), repr(boot))
        text = text.replace('pipeline_speed_r9_updater', 'pipeline_single_cpu_r10_updater').replace('SPEED_R9_FLOW_READY', 'SINGLE_CPU_R10_FLOW_READY').replace('GENOS R9 적용', 'GENOS R10 적용')
        (HERE / f'DATAIKU_R10_{kind}.txt').write_text(text)
        ast.parse(text)
    original_installer = (BASE / 'install_compute.py').read_text()
    old_archive_sha = sha((BASE / (OLD_SERVICE + '.zip')).read_bytes())
    archive_sha = sha((HERE / (SERVICE + '.zip')).read_bytes())
    installer = original_installer.replace(OLD_SERVICE, SERVICE).replace(old_archive_sha, archive_sha).replace(OLD_CODE, code)
    installer = installer.replace('install-r9', 'install-r10').replace('PIPELINE_R9', 'PIPELINE_R10').replace('sealed pipeline R9', 'sealed pipeline R10')
    installer = edit(installer, ', CODE_SHA):', ", '" + OLD_CODE + "', CODE_SHA):")
    (HERE / 'install_compute.py').write_text(installer)
    old_embed = original_installer.split("if __name__ == '__main__':")[0]
    embed = installer.split("if __name__ == '__main__':")[0]
    for filename in ('GENOS_R9_INSTALL.txt', 'ROLLBACK_GENOS.txt'):
        text = (BASE / filename).read_text().replace(old_embed, embed).replace(OLD_SERVICE, SERVICE).replace(old_archive_sha, archive_sha)
        text = text.replace('R9', 'R10').replace('speed_r9', 'single_cpu_r10').replace('Fix lossless binary export and remove redundant return work', 'Match pipeline indexing to one CPU; preserve R9 export fixes')
        (HERE / filename.replace('R9', 'R10')).write_text(text)
    (HERE / 'DATAIKU_02_시간진단.txt').write_bytes((BASE / 'DATAIKU_02_시간진단.txt').read_bytes())
    for n, b in list(payload.items()) + list(client.items()):
        if n.endswith('.py'):
            compile(b, n, 'exec')
    save('CODE_MANIFEST.json', {'code_sha256': code, **json.loads(payload['CODE_PINS.json'])})
    save('BUILD.json', {'baseline_code_sha256': OLD_CODE, 'code_sha256': code, 'service_files': len(payload),
        'unchanged_baseline_files': sum(payload[n] == b for n, b in old.items()),
        'changed_files': [n for n in payload if payload[n] != old[n]], 'fulltext_workers': 1,
        'files': {n: {'sha256': sha((HERE / n).read_bytes()), 'bytes': (HERE / n).stat().st_size} for n in (SERVICE + '.zip', PACKAGE)}})
    print('PREPARED_NOT_QUALIFIED', code, len(payload))


if __name__ == '__main__':
    main()
