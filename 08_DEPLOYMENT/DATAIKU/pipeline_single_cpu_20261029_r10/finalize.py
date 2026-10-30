"""Bind the single-CPU correction to actual local installer and native checks."""
import ast
import io
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from build import HERE, ROOT, BASE, SERVICE, PACKAGE, OLD_SERVICE, OLD_CODE, sha, save, writezip


def suite(name, expected):
    tests = ET.parse(HERE / name).getroot().findall('.//testcase')
    failed = [t.attrib['name'] for t in tests if any(t.find(k) is not None for k in ('failure', 'error', 'skipped'))]
    assert len(tests) == expected and not failed, (name, len(tests), failed)
    return {'tests': len(tests), 'passed': len(tests), 'failed': failed, 'sha256': sha((HERE / name).read_bytes())}


def main():
    assert not (HERE / 'VALIDATION.json').exists(), 'Do not rewrite qualified delivery'
    suites = {'protocol_install_upgrade': suite('TEST.xml', 116), 'native_pipeline': suite('NATIVE_TEST.xml', 4), 'spawn_import': suite('SPAWN_TEST.xml', 3)}
    build = json.loads((HERE / 'BUILD.json').read_text())
    with zipfile.ZipFile(HERE / (SERVICE + '.zip')) as archive:
        payload = {n.split('/', 1)[1]: archive.read(n) for n in archive.namelist()}
    with zipfile.ZipFile(BASE / (OLD_SERVICE + '.zip')) as archive:
        old = {n.split('/', 1)[1]: archive.read(n) for n in archive.namelist()}
    assert sha(old['CODE_PINS.json']) == OLD_CODE
    changed = [n for n in payload if payload[n] != old[n]]
    assert set(changed) == {'worker.py', 'CODE_PINS.json'}
    assert payload['worker.py'] == old['worker.py'].replace(b"'--fulltext-workers', '4'", b"'--fulltext-workers', '1'")
    pins = json.loads(payload['CODE_PINS.json'])['files']
    assert sha(payload['CODE_PINS.json']) == build['code_sha256']
    assert set(payload) == set(pins) | {'CODE_PINS.json'}
    assert all(sha(payload[n]) == h for n, h in pins.items())
    with zipfile.ZipFile(HERE / PACKAGE) as archive:
        client = {n: archive.read(n) for n in archive.namelist()}
    client_pins = json.loads(client['PACKAGE_FILES.json'])
    assert set(client) == set(client_pins) | {'PACKAGE_FILES.json'}
    assert all(sha(client[n]) == h for n, h in client_pins.items())
    assert client['COMPUTE_CODE_SHA256.txt'].decode().strip() == build['code_sha256']
    for n, row in build['files'].items():
        assert sha((HERE / n).read_bytes()) == row['sha256'] and (HERE / n).stat().st_size == row['bytes']
    for name in ('GENOS_R10_INSTALL.txt', 'ROLLBACK_GENOS.txt'):
        subprocess.run(['bash', '-n', str(HERE / name)], check=True)
    for name in ('DATAIKU_R10_INSTALL.txt', 'DATAIKU_R10_CONTROL.txt', 'DATAIKU_02_시간진단.txt'):
        ast.parse((HERE / name).read_text())
    installer = (HERE / 'install_compute.py').read_text().split("if __name__ == '__main__':")[0]
    install_text = (HERE / 'GENOS_R10_INSTALL.txt').read_text()
    for tag in ('PY_INSTALL', 'PY_STAGE'):
        cell = install_text.split("<<'" + tag + "'\n")[1].split('\n' + tag)[0]
        assert cell.startswith(installer)
        ast.parse(cell)
    checkouts = []
    for dev in sorted((ROOT / '09_ARTIFACTS/TEMP/single-cpu-r10-lifecycle').glob('test_genos_install_same_checko*/DEV')):
        if 'current' in str(dev):
            continue
        raw = subprocess.check_output(['git', 'show', 'HEAD:CODE_PINS.json'], cwd=dev)
        assert sha(raw) == build['code_sha256']
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dev, text=True).strip()
        checkouts.append({'path': str(dev), 'commit': commit, 'committed_pins_sha256': sha(raw), 'then_rolled_back': True})
    assert len(checkouts) == 8
    native = []
    for path in sorted((ROOT / '09_ARTIFACTS/TEMP/single-cpu-r10-native').glob('test_actual_native_flow_with*/compute/result.zip')):
        if 'current' in str(path):
            continue
        with zipfile.ZipFile(path) as archive:
            release = json.loads(archive.read('audit/release.json'))
            assert release['settings']['fulltext_workers'] == 1 and release['offline_e2e'] == 'PASS'
        native.append({'path': str(path), 'sha256': sha(path.read_bytes()), 'fulltext_workers': 1, 'offline_e2e': 'PASS'})
    assert len(native) == 2
    binding = {'baseline_code_pins_sha256': OLD_CODE, 'code_pins_sha256': build['code_sha256'], 'code_zip': build['files'][SERVICE + '.zip'],
        'local_installer_checkouts': checkouts, 'native_returns': native, 'fulltext_workers': 1,
        'field_cpu': 1, 'field_ram_gib': 16, 'field_checkout': '~/DEV legal_pipeline_serving; absolute path unconfirmed',
        'field_commit': None, 'field_revision': None, 'field_generation': None,
        'generation_policy': 'Ephemeral compute; Dataiku owns state, logs and results', 'onsite_deployed': False,
        'active_main_pointer_sha256': sha((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()), 'main_changed': False}
    save('RELEASE_BINDING.json', binding)
    save('VALIDATION.json', {'status': 'LOCAL_SINGLE_CPU_CORRECTION_PASS', 'suites': suites, 'tests_passed': sum(s['passed'] for s in suites.values()),
        'server_files': len(payload), 'unchanged_r9_files': len(payload) - len(changed), 'changed_server_files': changed,
        'cpu_allocation_corrected_from': 4, 'cpu_allocation_corrected_to': 1, 'ram_gib': 16, 'fulltext_workers': 1,
        'model_calls': 0, 'new_performance_run': False, 'whole02_1hour_verified': False, 'r9_2_49x_does_not_apply_to_single_cpu': True,
        'existing_01_reusable': True, 'failed_added_resume': False, 'requires_02_recompute': True, 'main_changed': False,
        'onsite_deployed': False, 'email_sent': False,
        'historical_limits_preserved': 'R8 historical compatibility failure and R9 initial native failures remain in original records.'})
    names = [SERVICE + '.zip', PACKAGE, 'CODE_MANIFEST.json', 'RELEASE_BINDING.json', 'VALIDATION.json', 'GENOS_R10_INSTALL.txt',
        'DATAIKU_R10_INSTALL.txt', 'DATAIKU_R10_CONTROL.txt', 'DATAIKU_02_시간진단.txt', 'ROLLBACK_GENOS.txt', 'install_compute.py', 'GUIDE.txt', 'PATCH_NOTES.txt']
    outer = HERE / 'DATAIKU_SINGLE_CPU_20261029_R10.zip'
    writezip(outer, {n: (HERE / n).read_bytes() for n in names})
    def inspect(raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.testzip() is None
            for name in archive.namelist():
                assert not name.lower().endswith(('.js', '.jsx', '.mjs', '.cjs')), name
                if name.lower().endswith('.zip'):
                    inspect(archive.read(name))
    inspect(outer.read_bytes())
    with zipfile.ZipFile(outer) as archive:
        assert set(archive.namelist()) == set(names)
        assert all(archive.read(n) == (HERE / n).read_bytes() for n in names)
    save('DELIVERY_MANIFEST.json', {**build, 'delivery_files': {n: {'bytes': (HERE / n).stat().st_size, 'sha256': sha((HERE / n).read_bytes())} for n in names + [outer.name]},
        'onsite_deployed': False, 'email_sent': False})
    print('VALIDATED', sum(s['passed'] for s in suites.values()), 'tests', str(outer), outer.stat().st_size)


if __name__ == '__main__':
    main()
