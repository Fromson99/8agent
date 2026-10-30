"""Dataiku-only, explicit one-attempt recovery; the sealed GENOS R10 is unchanged."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'pipeline_single_cpu_20261029_r10'
PACKAGE = 'DATAIKU_R10_RECOVERY_CLIENT_20261029_R1.zip'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def edit(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def writezip(path, files):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, raw in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 10, 29, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            z.writestr(item, raw)


def main():
    assert not (HERE / 'VALIDATION.json').exists(), 'Do not overwrite validated delivery'
    old_zip = BASE / 'DATAIKU_COMPUTE_RECIPES_20261029_R10.zip'
    assert sha(old_zip.read_bytes()) == '947c62bb1a8796ee6de1ee730d36cf3a93ec9b07417405f2259efb6926d9843c'
    with zipfile.ZipFile(old_zip) as z:
        old = {n: z.read(n) for n in z.namelist()}
    client = dict(old)
    client['one_attempt.py'] = (HERE / 'one_attempt.py').read_bytes()
    upgrade = client['checkpoint_upgrade.py'].decode()
    upgrade = edit(upgrade, "if type(count) is not int or not 1 <= count < 3:\n        raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED')", "if type(count) is not int or count < 1:\n        raise ValueError('COMPUTE_ATTEMPT_BUDGET_EXHAUSTED')\n    grant = None\n    if count >= 3:\n        from one_attempt import read_grant\n        grant = read_grant(folder, name, latest, identity)")
    upgrade = edit(upgrade, "'migration_checked', 'legacy_checkpoint', 'upgrade_history'", "'migration_checked', 'legacy_checkpoint', 'upgrade_history', 'operator_attempt_history'")
    upgrade = edit(upgrade, "'reason': 'SINGLE_CPU_WORKER_CONFIGURATION'", "'reason': ('EXPLICIT_ONE_ADDITIONAL_R10_ATTEMPT' if grant else 'SINGLE_CPU_WORKER_CONFIGURATION')")
    upgrade = edit(upgrade, '    store.value = keep', "    if grant:\n        keep['operator_attempt_history'] = list(keep.get('operator_attempt_history', [])) + [grant]\n    store.value = keep")
    client['checkpoint_upgrade.py'] = upgrade.encode()
    client['updater.py'] = client['updater.py'].replace(b'single-cpu-r10-before.json', b'r10-attempt-recovery-before.json')
    ref = json.loads(client['REFERENCE.json'])
    old_boot = (BASE / 'bootstrap.txt').read_text()
    ref['prior_compute_bootstraps'].append(old_boot)
    client['REFERENCE.json'] = (json.dumps(ref) + '\n').encode()
    client['PACKAGE_FILES.json'] = (json.dumps({n: sha(b) for n, b in client.items() if n != 'PACKAGE_FILES.json'}, sort_keys=True, indent=2) + '\n').encode()
    writezip(HERE / PACKAGE, client)
    boot = old_boot.replace(old_zip.name, PACKAGE).replace(sha(old_zip.read_bytes()), sha((HERE / PACKAGE).read_bytes()))
    boot = re.sub(r'PACKAGE_BYTES = \d+', 'PACKAGE_BYTES = ' + str((HERE / PACKAGE).stat().st_size), boot)
    (HERE / 'bootstrap.txt').write_text(boot)
    install = (BASE / 'DATAIKU_R10_INSTALL.txt').read_text().replace(old_boot, boot).replace(repr(old_boot), repr(boot))
    install = install.replace('pipeline_single_cpu_r10_updater', 'pipeline_r10_attempt_recovery_updater')
    install = install[:install.rfind("print('SINGLE_CPU_R10_FLOW_READY")] + "print('R10_RECOVERY_CLIENT_READY: ONE_ATTEMPT.txt 조회 후 1회 허용 → 00 → 02 → 03')\n"
    (HERE / 'DATAIKU_RECOVERY_INSTALL.txt').write_text(install)
    command = "# LEGAL_RAG 새 Python 노트북. 기본값은 조회만 합니다.\nACTION = 'inspect' # inspect / authorize_one_attempt\nCONFIRMATION = '' # 추가 계산 1회를 허용할 때 AUTHORIZE_ONE_ADDITIONAL_COMPUTE_ATTEMPT\nREASON = 'R10 1코어 및 반환 수정본으로 계산 1회 추가'\n" + boot
    command += "\nwork, root = verified_package()\nsys.path[:0] = [str(root), str(root/'client'), str(root/'client/02_BACKEND')]\nfor name in ('one_attempt','control','controller','checkpoint_upgrade','recipes_runtime','updater','managed_job','upgrade_review','named_inputs'):\n    sys.modules.pop(name, None)\nimport one_attempt\none_attempt.run(ACTION, CONFIRMATION, REASON)\n"
    (HERE / 'DATAIKU_ONE_ATTEMPT.txt').write_text(command)
    for n, raw in client.items():
        if n.endswith('.py'):
            compile(raw, n, 'exec')
    for name in ('DATAIKU_RECOVERY_INSTALL.txt', 'DATAIKU_ONE_ATTEMPT.txt'):
        ast.parse((HERE / name).read_text())
    # Ordinary retry and all server bytes remain untouched.
    assert client['controller.py'] == old['controller.py']
    assert client['control.py'] == old['control.py']
    manifest = {'server_code_sha256': client['COMPUTE_CODE_SHA256.txt'].decode().strip(),
        'server_changed': False, 'baseline_client_sha256': sha(old_zip.read_bytes()),
        'changed_client_files': [n for n in client if old.get(n) != client[n]],
        'unchanged_client_files': sum(b == old.get(n) for n, b in client.items()),
        'client_files': len(client), 'package_sha256': sha((HERE / PACKAGE).read_bytes()),
        'package_bytes': (HERE / PACKAGE).stat().st_size}
    (HERE / 'BUILD.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
