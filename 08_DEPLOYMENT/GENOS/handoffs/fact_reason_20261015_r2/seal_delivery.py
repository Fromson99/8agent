"""Seal tested R2, preserve R1, and prepare the replacement email."""
import ast
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIOR = OUT.with_name('fact_reason_20261015_r1')
NAME = 'GENOS_FACT_REASON_20261015_R2'
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + '\n').encode()


def stats(path):
    cases = list(ET.parse(path).iter('testcase'))
    result = {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
              'errors': sum(c.find('error') is not None for c in cases),
              'skipped': sum(c.find('skipped') is not None for c in cases)}
    assert result['tests'] and not any(result[k] for k in ('failures', 'errors', 'skipped')), (path, result)
    return result


def main():
    archive = OUT / (NAME + '.zip')
    assert not archive.exists(), 'Preserve sealed delivery'
    contracts = stats(OUT / 'INSTALLER_TESTS.xml')
    delivery = stats(OUT / 'DELIVERY_TESTS.xml')
    assert contracts['tests'] == 11 and delivery['tests'] == 2
    installed = {p.stem: stats(p) for p in OUT.glob('INSTALLED_*.xml')}
    assert len(installed) == 2
    spec = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    binding = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
    old_spec = json.loads(gzip.decompress((PRIOR / 'PATCH_SPEC.json.gz').read_bytes()))
    assert len(spec['signatures']) == 2310 and binding['added_predecessors'] == 660
    assert spec['blobs'] == old_spec['blobs']
    assert all(spec['signatures'][k] == v for k, v in old_spec['signatures'].items())
    assert all(v['missing_outputs'] == 0 for v in binding['transition_coverage'].values())
    original_checksums = {}
    for line in (PRIOR / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert sha((PRIOR / name).read_bytes()) == digest
        original_checksums[name] = digest
    run = OUT / (NAME + '_RUN.txt')
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", run.read_text()).group(1)
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    assert bundle['spec'] == spec and base64.b64decode(bundle['code']) == (OUT / 'apply_patch.py').read_bytes()
    assert (OUT / 'payload' / SOURCE).read_bytes() == (PRIOR / 'payload' / SOURCE).read_bytes()
    commands = gates = boots = restores = original_rejections = 0
    for path in OUT.glob('TEST_*.json.gz'):
        rows = json.loads(gzip.decompress(path.read_bytes()))
        commands += len(rows)
        for row in rows:
            gates += row['returncode'] == 0 and 'GENOS_RELEASE_GATE PASS' in row['stdout']
            boots += row['returncode'] == 0 and 'SERVICE_TLS_BOOTSTRAP PASS' in row['stdout']
            restores += row['returncode'] == 0 and 'CODE_RESTORED;' in row['stdout']
            original_rejections += row['returncode'] != 0 and 'GENOS_FACT_REASON_20261015_R1_RUN.txt' in ' '.join(row['argv']) and 'Known complete GENOS/CM' in row['stdout']
    assert gates == boots == restores == 2 and original_rejections == 1
    pointer = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    validation = {'revision': NAME, 'installer_contracts': contracts, 'delivery_integrations': delivery,
                  'installed_contracts': installed, 'installed_passes': sum(s['tests'] for s in installed.values()),
                  'actual_commands': commands, 'same_checkout_generation_gates': gates,
                  'localhost_service_boots': boots, 'rollbacks': restores,
                  'r1_failure_reproduced_on_field_fingerprint': original_rejections,
                  'field_inventory_sha256': binding['field_inventory_sha256'],
                  'known_predecessors': 2310, 'added_predecessors': 660,
                  'sealed_transitions_fully_covered': binding['transition_coverage'],
                  'original_1650_entries_unchanged': True, 'product_blob_identical_to_r1': True,
                  'r1_artifacts_preserved': original_checksums, 'local_release': pointer['release_id'],
                  'local_pointer_generation': pointer['generation'], 'local_main_changed': False,
                  'genos_connections': 0, 'external_model_calls': 0,
                  'field_generation_verified': False, 'field_commit_verified': False,
                  'field_serving_revision_verified': False, 'field_workflow_verified': False,
                  'genos_field_status': 'NOT_VERIFIED'}
    (OUT / 'VALIDATION.json').write_bytes(encoded(validation))
    summary = (f'FACT_REASON R2 — 기존 R1 설치 중단 수정 검증\n\n'
               f'사진의 지문 {binding["field_inventory_sha256"]}\n'
               f'동일 코드 지문에서 R1의 설치 차단을 재현하고 R2 적용/재실행/검증/원복을 확인.\n'
               f'누락660구성을 추가해2310구성 지원; 길이 복구990출력 전체 포함.\n'
               f'기존1650입력/출력 및 문구 제품 바이트와 R1 봉인 자료 보존.\n'
               f'설치 계약11개·실제 TXT/서비스/generation gate통합2개 통과.\n'
               f'두 설치본 계약/API {validation["installed_passes"]}개 통과. 실제 명령{commands}회,\n'
               f'동일 committed checkout gate2회·localhost service.service부팅2회·원복2회.\n'
               f'알 수 없는 구성/파일 변경/심볼릭 링크/백업 변조는 계속 차단.\n'
               f'기존 예산·표시 정책·데이터 보존. 로컬 MAIN 미변경.\n'
               f'GENOS 내부 접속/모델 호출0회. 실제 반입·배포·워크플로우 결과는 미확인.\n')
    (OUT / 'VALIDATION_SUMMARY.txt').write_text(summary)
    names = ['apply_patch.py', 'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json',
             'VALIDATION.json', 'VALIDATION_SUMMARY.txt', 'GUIDE_UTF8.txt', run.name, 'payload/' + SOURCE]
    manifest = {'schema_version': 'genos-partial-patch-v1', 'revision': NAME,
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
    with tempfile.TemporaryDirectory(prefix='fact-r2-sealed-') as td:
        base = Path(td)
        transfer = base / 'TRANSFER'
        transfer.mkdir()
        target = transfer / NAME
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
            assert all(Path(n).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
            z.extractall(target)
        for row in manifest['files']:
            raw = (target / row['path']).read_bytes()
            assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
        assert (target / run.name).read_bytes() == run.read_bytes()
        subprocess.run(['bash', '-n', str(target / run.name)], check=True)
        fixture = next(f for f in json.loads((OUT / 'FIXTURES.json').read_bytes()) if f['kind'] == 'field_signature')
        root = base / 'DEV'
        with zipfile.ZipFile(OUT / fixture['path']) as z:
            z.extractall(root)
        before = {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
        # No model call: supply a minimal synthetic identity manifest only for check's reporting.
        generation = base / 'synthetic-generation'
        generation.mkdir()
        (generation / 'manifest.json').write_text('{}\n')
        env = dict(os.environ, GENOS_DEV_ROOT=str(root), GENOS_GENERATION=str(generation),
                   GENOS_PYTHON_DIR=str(ROOT / '.venv/bin'), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run(['bash', str(target / run.name), 'check'], cwd=transfer,
                                env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0 and 'CHECK PASS' in result.stdout, result.stdout + result.stderr
        assert all(sha((root / p).read_bytes()) == digest for p, digest in before.items())
    attachments = [archive.name, run.name, 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt', 'VALIDATION.json']
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha((OUT / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    attachments.append('SHA256SUMS.txt')
    body = '''<p>FACT_REASON R1 설치 오류를 수정한 <b>R2 교체본</b>입니다. 설명에서 멈추지 않고, 사진에 나온 코드 구성으로 수정·검증했습니다.</p>
<p><b>기존 FACT_REASON R1 대신 이 R2를 사용해 주세요.</b> LENGTH_RECOVERY R2를 다시 설치하거나 진단 코드를 다시 실행할 필요는 없습니다. 누락된 검증 구성660개를 추가했고 기존 문구·예산·설정·데이터는 보존합니다.</p>
<p>첨부 ZIP을 실제 업로드한 <b>TRANSFER 폴더에서 아래 두 줄을 실행</b>해 주세요.</p>
<pre>python3 -m zipfile -e ./GENOS_FACT_REASON_20261015_R2.zip ./GENOS_FACT_REASON_20261015_R2
bash ./GENOS_FACT_REASON_20261015_R2/GENOS_FACT_REASON_20261015_R2_RUN.txt install</pre>
<p>install 한 번으로 기존 ~/DEV의 사전 검사·백업·적용·검증을 진행합니다. 별도 첨부 TXT와 ZIP 안의 TXT는 동일합니다. 성공하면 <b>CODE_APPLIED</b>와 <b>FACT_REASON_EXIT=0</b>이 출력되며, BACKUP 및 APPLIED_CODE_ZIP 경로를 보관해 주세요.</p>
<p>적용 후에는 안내서의 같은 DEV commit → generation gate → push → 새 코드서빙 리비전/SSE 재시작 순서로 반영합니다. 원문 재구축·추가 워크플로우 편집기 교체는 없습니다. 최종 확인은 워크플로우 테스트 화면에서 새 요청으로 합니다.</p>
<p>사진과 동일한 코드 지문에서 R1 차단을 재현하고 R2의 설치·재실행·변조 거부·원복, 실제 로컬 service.service와 같은 committed checkout의 generation gate를 검증했습니다. GENOS 현장 적용·배포 성공은 실행 결과로 별도 확인해야 합니다.</p>'''
    (OUT / 'EMAIL_BODY_UTF8.html').write_text(body)
    parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
    attachments_binding = []
    for name in attachments:
        raw = (OUT / name).read_bytes()
        mime = 'application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/plain'
        parts.append({'mime_type': mime, 'content_disposition': 'attachment', 'filename': name,
                      'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
        attachments_binding.append({'name': name, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
    (OUT / 'EMAIL_ATTACHMENT_BINDING.json').write_bytes(encoded(attachments_binding))
    args = {'to': 'hyungjininfocz.son@partner.samsung.com',
            'subject': '[GENOS FACT_REASON R2 교체본] 설치 오류 수정 — R1 대신 실행',
            'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
            'response_fields': ['id', 'thread_id', 'label_ids']}
    (OUT / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=True))
    record = {'zip_sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size,
              'members': len(names) + 1, 'no_javascript': True, 'standalone_txt_identical': True,
              'member_hashes_verified': True, 'sealed_field_fingerprint_check': 'PASS',
              'bash_syntax': 'PASS', 'attachments': attachments_binding}
    (OUT / 'SEALED_UNPACK_CHECK.json').write_bytes(encoded(record))
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
