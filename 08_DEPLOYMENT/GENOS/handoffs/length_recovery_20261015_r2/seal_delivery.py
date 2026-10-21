"""Seal the tested installer without changing the prior release or product blobs."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
PRIOR = OUT.with_name('length_recovery_20261014_r1')
ROOT = OUT.parents[3]
NAME = 'GENOS_LENGTH_RECOVERY_20261015_R2'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def stats(cases):
    return {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
            'errors': sum(c.find('error') is not None for c in cases),
            'skipped': sum(c.find('skipped') is not None for c in cases)}


def main():
    archive = OUT / (NAME + '.zip')
    assert not archive.exists(), 'sealed archive must not be replaced'
    cases = list(ET.parse(OUT / 'DELIVERY_TESTS.xml').iter('testcase'))
    integration = [c for c in cases if c.get('name', '').startswith('test_install_service_api')]
    assert stats(integration) == dict(tests=2, failures=0, errors=0, skipped=0), stats(integration)
    collision = list(ET.parse(OUT / 'SCHEMA_TESTS.xml').iter('testcase'))
    assert stats(collision) == dict(tests=15, failures=0, errors=0, skipped=0), stats(collision)
    installed = {}
    for path in OUT.glob('INSTALLED_*.xml'):
        kind = path.name.removeprefix('INSTALLED_').removesuffix('.xml')
        tests = list(ET.parse(path).iter('testcase'))
        baseline = json.loads((PRIOR / ('LEGACY_DISPLAY_BASELINE_' + kind + '.json')).read_bytes())
        failed = [c for c in tests if c.find('failure') is not None]
        assert len(failed) == 1 and failed[0].get('name') == baseline['test']['name']
        assert failed[0].find('failure').get('message') == baseline['message']
        assert stats(tests) == dict(tests=575, failures=1, errors=0, skipped=0)
        installed[kind] = stats(tests)
    assert len(installed) == 2
    old = json.loads(gzip.decompress((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()))
    new = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    assert all(new[k] == old[k] for k in ('signatures', 'blobs', 'engine_additions', 'budget_policy'))
    run = OUT / (NAME + '_RUN.txt')
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", run.read_text()).group(1)
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    assert base64.b64decode(bundle['code']) == (OUT / 'apply_patch.py').read_bytes()
    assert bundle['spec'] == new
    commands = gates = boots = undo = 0
    roots = []
    for path in OUT.glob('TEST_*.json.gz'):
        rows = json.loads(gzip.decompress(path.read_bytes()))
        assert rows[-1]['returncode'] == 0
        roots.append(rows[0]['cwd'])
        commands += len(rows)
        for row in rows:
            gates += 'GENOS_RELEASE_GATE PASS' in row['stdout']
            boots += 'SERVICE_TLS_BOOTSTRAP PASS' in row['stdout']
            undo += 'CODE_RESTORED;' in row['stdout']
    assert commands == 32 and gates == boots == undo == 2
    collision_commands = 0
    for path in OUT.glob('COLLISION_*.json.gz'):
        rows = json.loads(gzip.decompress(path.read_bytes()))
        assert len(rows) == 4 and all(r['returncode'] == 0 for r in rows)
        collision_commands += len(rows)
    assert collision_commands == 16
    validation = {
        'revision': NAME, 'installer_contracts': stats(collision), 'service_gate_integrations': stats(integration),
        'initial_snapshot_test_failures': 4,
        'initial_failure_resolution': 'Test snapshot excluded Python-generated __pycache__ files; installer unchanged; complete source and modes still compared. Original failing report retained.',
        'installed_contracts': installed, 'installed_passes': 1148,
        'preexisting_display_expectation_failures': 2, 'new_product_regressions': 0,
        'actual_standalone_txt_commands': commands + collision_commands,
        'same_committed_checkout_generation_gates': gates, 'actual_service_loopback_tls_boots': boots,
        'all_1320_predecessor_and_output_signatures_preserved': True, 'all_product_blobs_identical_to_r1': True,
        'known_unrecorded_schema_preimages': new['unrecorded_schema_preimages'],
        'verified_local_code_roots': roots, 'python': sys.version, 'sys_executable': sys.executable,
        'genos_connections': 0, 'model_inference_calls': 0, 'local_main_changed': False,
        'field_schema_hashes': None, 'field_commit': None, 'field_generation': None,
        'field_serving_revision': None, 'field_workflow_success': None, 'field_status': 'NOT_VERIFIED',
    }
    (OUT / 'VALIDATION.json').write_bytes(encoded(validation))
    (OUT / 'VALIDATION_SUMMARY.txt').write_text('''GENOS LENGTH_RECOVERY R2 검증
설치 결함/원복 계약 15개 및 실제 TXT·서비스·generation gate 통합 2개 통과.
스키마 없음/한 파일/두 파일/목표와 동일 파일의 설치·재실행·원복 확인.
미확인 스키마/모듈·심볼릭 링크·디렉터리·목록 내 변조·검사 후 변경 거부 확인.
중단된 부분 적용의 원복 및 변조된 백업 거부 확인. 기존 파일 바이트·권한·목록 누락 상태 복원.
실제 TXT 48명령, 동일 committed checkout generation gate 2회, service.service localhost TLS 부팅 2회.
설치한 두 구성의 계약/API 1148개 통과. 기존 표시정책 기대 차이 각 1건은 R1 기준과 같고 새 회귀 0.
초기 검사 보조 코드가 생성된 __pycache__를 원복 대상으로 잘못 센 4실패를 보존했으며 코드/권한 비교를 유지해 검사 수정 후 통과.
R1의 1320 입력/출력 지문 및 모든 제품 blob/엔진 추가/예산 규칙 동일. 설치기와 설치 기록만 수정.
외부/GENOS 모델 추론·GENOS 접속 0. 로컬 MAIN66·원문 generation 변경 없음.
사진의 실제 기존 스키마 해시는 미확인. 허용된 정확한 바이트가 아니면 로그와 함께 중단.
현장 반입/commit/push/리비전/내부 모델 질의 성공은 미확인.
''')
    binding = {name: sha((OUT / name).read_bytes()) for name in
               ('apply_patch.py', 'build_delivery.py', 'test_delivery.py', 'test_schema_collision.py',
                'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json', NAME + '_RUN.txt')}
    (OUT / 'TESTED_DELIVERY_BINDING.json').write_bytes(encoded(binding))
    for path in OUT.glob('*.xml'):
        path.with_suffix('.xml.gz').write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    names = ['apply_patch.py', 'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json', 'TESTED_DELIVERY_BINDING.json',
             'VALIDATION.json', 'VALIDATION_SUMMARY.txt', 'GUIDE_UTF8.txt', 'FIX_REPORT_UTF8.txt',
             'FIELD_FAILURE_20261015.json', NAME + '_RUN.txt']
    names += [str(p.relative_to(OUT)) for p in sorted((OUT / 'known-preimages').iterdir())]
    manifest = {'schema_version': 'genos-partial-patch-v1', 'revision': NAME,
                'prerequisite': ['GENOS_SCHEMA_RECOVERY_20261014_R1 or supported later pre-length inventory'],
                'gate_archive': 'apply-generated BACKUP/APPLIED_CODE.zip', 'files': []}
    for name in names:
        raw = (OUT / name).read_bytes()
        if name.endswith('.py'):
            ast.parse(raw, feature_version=(3, 10))
        manifest['files'].append({'path': name, 'sha256': sha(raw), 'bytes': len(raw)})
    (OUT / 'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(names) + ['CODE_MANIFEST.json']:
            z.write(OUT / name, name)
    with tempfile.TemporaryDirectory(prefix='genos-length-r2-unpack-') as td:
        target = Path(td)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
            assert all(Path(n).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs') for n in z.namelist())
            z.extractall(target)
        for row in manifest['files']:
            raw = (target / row['path']).read_bytes()
            assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
        assert (target / run.name).read_bytes() == run.read_bytes()
        subprocess.run(['bash', '-n', str(target / run.name)], check=True)
    attachments = [archive.name, run.name, 'GUIDE_UTF8.txt', 'FIX_REPORT_UTF8.txt', 'VALIDATION_SUMMARY.txt', 'VALIDATION.json']
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha((OUT / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    sealed = {'revision': NAME, 'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size,
              'members': len(names) + 1, 'all_member_hashes_verified': True, 'no_javascript': True,
              'standalone_txt_identical': True, 'bash_syntax': 'PASS', 'field_status': 'NOT_VERIFIED'}
    (OUT / 'SEALED_UNPACK_CHECK.json').write_bytes(encoded(sealed))
    print(json.dumps(sealed))


if __name__ == '__main__':
    main()
