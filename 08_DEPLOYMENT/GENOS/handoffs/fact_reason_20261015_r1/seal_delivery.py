"""Seal verified delivery and prepare MIME arguments; sending is a separate tool call."""
import ast
import base64
import gzip
import hashlib
import html
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
ROOT = OUT.parents[3]
NAME = 'GENOS_FACT_REASON_20261015_R1'
SOURCE = '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def stats(path):
    cases = list(ET.parse(path).iter('testcase'))
    value = {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
             'errors': sum(c.find('error') is not None for c in cases),
             'skipped': sum(c.find('skipped') is not None for c in cases)}
    assert value['tests'] and not any(value[k] for k in ('failures', 'errors', 'skipped')), (path, value)
    return value


def main():
    archive = OUT / (NAME + '.zip')
    assert not archive.exists(), 'Preserve sealed delivery'
    contract = stats(OUT / 'INSTALLER_TESTS.xml')
    delivery = stats(OUT / 'DELIVERY_TESTS.xml')
    working = stats(OUT / 'WORKING_DISPLAY_TEST.xml')
    assert contract['tests'] == 8 and delivery['tests'] == 2 and working['tests'] == 1
    installed = {p.stem: stats(p) for p in OUT.glob('INSTALLED_*.xml')}
    assert len(installed) == 2
    spec = json.loads(gzip.decompress((OUT / 'PATCH_SPEC.json.gz').read_bytes()))
    source = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
    run = OUT / (NAME + '_RUN.txt')
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", run.read_text()).group(1)
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    assert bundle['spec'] == spec and base64.b64decode(bundle['code']) == (OUT / 'apply_patch.py').read_bytes()
    assert sha((ROOT / SOURCE).read_bytes()) == source['source_files'][SOURCE]
    assert (ROOT / SOURCE).read_bytes() == (OUT / 'payload' / SOURCE).read_bytes()
    commands = gates = boots = restores = 0
    code_roots = []
    for path in OUT.glob('TEST_*.json.gz'):
        rows = json.loads(gzip.decompress(path.read_bytes()))
        commands += len(rows)
        code_roots.append(rows[0]['cwd'])
        for row in rows:
            gates += 'GENOS_RELEASE_GATE PASS' in row['stdout']
            boots += 'SERVICE_TLS_BOOTSTRAP PASS' in row['stdout']
            restores += 'CODE_RESTORED;' in row['stdout']
    assert gates == boots == restores == 2
    pointer = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    assert pointer['generation'] == 66
    validation = {'revision': NAME, 'installer_contracts': contract, 'delivery_integrations': delivery,
        'working_fact_display_api': working, 'installed_contracts': installed,
        'installed_passes': sum(v['tests'] for v in installed.values()),
        'actual_txt_and_checkout_commands': commands,
        'same_committed_checkout_generation_gates': gates, 'service_loopback_tls_boots': boots,
        'rollback_verified': restores, 'known_predecessors': len(spec['signatures']),
        'product_source_files': 1, 'product_source_change_lines': 1,
        'wording': '해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다.',
        'preserved': ['claims', 'MISSING_FACT', 'PARTIAL', 'source/data generation',
            'model', 'search/retry limits', 'cache', 'field wiki and logging policy', 'existing budget overrides'],
        'verified_local_code_roots': code_roots, 'python': sys.version, 'sys_executable': sys.executable,
        'external_model_calls': 0, 'genos_connections': 0, 'local_main_changed': False,
        'local_release': pointer['release_id'], 'local_pointer_generation': pointer['generation'],
        'field_git_commit': None, 'field_generation': None, 'field_generation_manifest_sha256': None,
        'field_serving_revision': None, 'field_workflow_success': None, 'field_status': 'NOT_VERIFIED',
        'initial_test_harness_issues': ['Standalone fixture import was missing term_glossary; imported existing fixture.',
            'API assertion used internal answer.limitation_items; corrected to actual assembly metadata and judgment-view consumer. Product code unchanged.']}
    (OUT / 'VALIDATION.json').write_bytes(encoded(validation))
    summary = (f'GENOS 확인 범위 안내 R1 검증\n\n'
        f'제품 코드 변경: completion_contracts.py의 MISSING_FACT 고정 문구 1줄.\n'
        f'알려진 기존 코드 inventory {len(spec["signatures"])}종의 정확한 입력/출력 해시 결속.\n'
        f'설치 실패/원복 계약 {contract["tests"]}개, 실제 TXT·서비스·generation gate 통합 2개 통과.\n'
        f'작업 코드의 실제 모의 API 표시 검사 1개 통과.\n'
        f'두 설치 구성의 계약/API {validation["installed_passes"]}개 통과·실패/skip 0.\n'
        f'실제 TXT 및 checkout 명령 {commands}회, 같은 committed checkout gate 2회,\n'
        f'실제 service.service의 localhost TLS 부팅 2회, 원복 2회 확인.\n'
        f'문구 표시와 기존 PARTIAL·사실 부족·중복 요청 결과 보존을 확인.\n'
        f'기존 원문·검색·모델·예산·위키·로그 설정과 generation 파일 보존.\n'
        f'독립 검사 초기 fixture/import와 API 검증 위치를 수정했으며 제품 코드 변화 없음.\n'
        f'외부/GENOS 모델 호출 및 GENOS 접속 0. 로컬 MAIN66 유지.\n'
        f'GENOS 반입·push·리비전 배포·워크플로우 실제 질의 성공은 미확인.\n')
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
    with tempfile.TemporaryDirectory(prefix='fact-reason-unpack-') as td:
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
    attachments = [archive.name, run.name, 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt', 'VALIDATION.json']
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha((OUT / n).read_bytes()) + '  ' + n + '\n' for n in attachments))
    attachments.append('SHA256SUMS.txt')
    binding = []
    body = '''<p>요청하신 ‘확인 범위’의 추가 사실 안내 수정본을 전달합니다.</p>
<p><b>변경 문구</b><br>해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다.</p>
<p>조건별 설명 뒤에 추가 정보가 필요한 목적을 함께 표시합니다. 답변 본문과 단계별 상세 화면에 공통으로 사용되며, 제품 코드 변경은 한 줄입니다. 기존 사실 부족 상태와 탐색·복구 설정은 유지합니다.</p>
<p><b>실행</b><br>실제로 업로드한 TRANSFER 폴더에서 아래 명령을 순서대로 실행해 주세요. 적용 대상은 기존 ~/DEV입니다.</p>
<pre>python3 -m zipfile -e ./GENOS_FACT_REASON_20261015_R1.zip ./GENOS_FACT_REASON_20261015_R1
bash ./GENOS_FACT_REASON_20261015_R1/GENOS_FACT_REASON_20261015_R1_RUN.txt check
bash ./GENOS_FACT_REASON_20261015_R1/GENOS_FACT_REASON_20261015_R1_RUN.txt apply</pre>
<p>ZIP 안과 별도 첨부 실행 TXT는 같습니다. 백업·지속 로그·재실행 확인·원복·배포 전 gate를 포함했습니다. 상세 절차는 GUIDE_UTF8.txt를 따라 주세요.</p>
<p><b>적용 순서</b><br>앞서 받은 LENGTH_RECOVERY R2 등 복구 패치를 적용할 예정이면 먼저 완료하고, 이번 FACT_REASON R1을 마지막에 적용해 주세요. 이번 ZIP은 문구 수정만 포함합니다.</p>
<p>적용 후 같은 DEV에서 변경 검토·commit·generation gate를 거쳐 push 및 새 코드서빙 리비전 배포가 필요합니다. 분리 SSE 사용 시 재시작합니다. 원문 재구축과 워크플로우 편집기 변경은 필요 없습니다. 워크플로우 테스트 화면에서 새 요청으로 표시를 확인해 주세요.</p>
<p>외부 검증은 모의 데이터·모의 모델 응답으로 수행했으며 GENOS 현장 반입·배포·내부 모델 성공은 별도 확인 사항입니다. 로컬 활성 MAIN66은 유지했습니다.</p>'''
    body += '<pre>' + html.escape(summary) + '</pre>'
    (OUT / 'EMAIL_BODY_UTF8.html').write_text(body)
    parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
    for name in attachments:
        raw = (OUT / name).read_bytes()
        mime = 'application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/plain'
        parts.append({'mime_type': mime, 'content_disposition': 'attachment', 'filename': name,
                      'body': {'base64_url_content': base64.urlsafe_b64encode(raw).decode()}})
        binding.append({'name': name, 'bytes': len(raw), 'sha256': sha(raw), 'mime_type': mime})
    (OUT / 'EMAIL_ATTACHMENT_BINDING.json').write_bytes(encoded(binding))
    args = {'to': 'hyungjininfocz.son@partner.samsung.com',
            'subject': '[GENOS 확인 범위 안내 R1] 추가 사실 정보가 필요한 이유 표시',
            'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
            'response_fields': ['id', 'thread_id', 'label_ids']}
    (OUT / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=True))
    sealed = {'zip_sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size,
        'members': len(names) + 1, 'no_javascript': True, 'standalone_txt_identical': True,
        'member_hashes_verified': True, 'bash_syntax': 'PASS', 'attachments': binding}
    (OUT / 'SEALED_UNPACK_CHECK.json').write_bytes(encoded(sealed))
    for path in OUT.glob('*.xml'):
        path.with_suffix('.xml.gz').write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    print(json.dumps(sealed, ensure_ascii=False))


if __name__ == '__main__':
    main()
