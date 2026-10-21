"""Seal tested GENOS output policy; does not send mail or deploy anything."""
import ast, base64, gzip, hashlib, json, re, subprocess, sys, tempfile, zipfile, zlib
from pathlib import Path
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
NAME = 'GENOS_OUTPUT_UNLIMITED_20261015_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def stats(path, *, allow_failures=False):
    cases = list(ET.parse(path).iter('testcase'))
    value = {'tests': len(cases), 'passed': sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in cases),
        'failures': sum(c.find('failure') is not None for c in cases),
        'errors': sum(c.find('error') is not None for c in cases), 'skipped': sum(c.find('skipped') is not None for c in cases)}
    assert cases and (allow_failures or value['passed'] == len(cases)), (path, value)
    return value


def main():
    archive = OUT/(NAME+'.zip'); assert not archive.exists(), 'Preserve sealed delivery'
    delivery = stats(OUT/'DELIVERY_TESTS.xml')
    installed = {p.stem: stats(p) for p in OUT.glob('INSTALLED_*.xml')}
    assert delivery['tests'] == 10 and len(installed) == 2
    regression = stats(OUT/'REGRESSION.xml', allow_failures=True)
    assert regression['failures'] == 4 and regression['errors'] == 0
    before_gateway = stats(OUT/'PREEXISTING_GATEWAY.xml', allow_failures=True)
    before_service = stats(OUT/'PREEXISTING_FAILURE.xml', allow_failures=True)
    assert before_gateway['failures'] == 4 and before_service['failures'] == 1
    cases = list(ET.parse(OUT/'REGRESSION.xml').iter('testcase'))
    new_cases = [c for c in cases if 'test_genos_output_unlimited' in c.attrib.get('classname','')]
    assert new_cases and all(c.find('failure') is None and c.find('error') is None for c in new_cases)
    source = json.loads((OUT/'SOURCE_BINDING.json').read_bytes())
    spec = json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    parent = json.loads(gzip.decompress((OUT.with_name('length_recovery_20261015_r2')/'PATCH_SPEC.json.gz').read_bytes()))
    assert {r['output_signature'] for r in parent['signatures'].values()} <= set(spec['signatures'])
    for name, digest in source['source_files'].items():
        assert sha((ROOT/name).read_bytes()) == digest
        assert (ROOT/name).read_bytes() == (OUT/'payload'/name).read_bytes()
    run = OUT/(NAME+'_RUN.txt')
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", run.read_text()).group(1)
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    assert bundle['spec'] == spec and base64.b64decode(bundle['code']) == (OUT/'apply_patch.py').read_bytes()
    commands = gates = boots = restores = 0; roots = []
    for path in OUT.glob('TEST_*.json.gz'):
        rows = json.loads(gzip.decompress(path.read_bytes())); commands += len(rows); roots.append(rows[0]['cwd'])
        for row in rows:
            gates += 'GENOS_RELEASE_GATE PASS' in row['stdout']
            boots += 'SERVICE_TLS_BOOTSTRAP PASS' in row['stdout']
            restores += 'CODE_RESTORED;' in row['stdout']
    assert gates == boots == restores == 2
    pointer_path = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    pointer = json.loads(pointer_path.read_bytes()); assert pointer['generation'] == 66
    validation = {'revision': NAME, 'request': '우리 출력길이 제한 풀어버리자',
        'new_working_contracts_passed': len(new_cases), 'working_regression': regression,
        'preexisting_failures': json.loads((OUT/'EXISTING_FAILURES.json').read_bytes()),
        'installer_and_delivery_contracts': delivery, 'installed_contracts': installed,
        'installed_passes': sum(v['passed'] for v in installed.values()),
        'actual_txt_and_checkout_commands': commands, 'same_committed_checkout_generation_gates': gates,
        'service_loopback_tls_boots': boots, 'rollback_verified': restores,
        'known_predecessors': len(spec['signatures']), 'source_files': source['source_files'],
        'output_policy': {'genos_effective_max_output_tokens': None, 'wire_max_tokens_present': False,
            'server_default_output_and_context_limit': 'UNKNOWN', 'retired_env_ignored': 'GENOS_RAG_MAX_OUTPUT_TOKENS',
            'length_stop': 'OUTPUT_INCOMPLETE; no repeated same-limit correction', 'schema_corrections': 'existing bounded owner'},
        'verified_local_code_roots': roots, 'sys_executable': sys.executable, 'python': sys.version,
        'external_model_calls': 0, 'genos_connections': 0, 'local_main_changed': False,
        'local_release': pointer['release_id'], 'local_pointer_generation': pointer['generation'],
        'local_pointer_sha256': sha(pointer_path.read_bytes()),
        'field_git_commit': None, 'field_generation': None, 'field_generation_manifest_sha256': None,
        'field_serving_revision': None, 'field_workflow_success': None,
        'initial_validation_failures': 'failures/initial-inventory-coverage and INITIAL_COLLECTION_FAILURE.xml.gz preserved; only installer coverage/test fixture handling changed'}
    (OUT/'VALIDATION.json').write_bytes(encoded(validation))
    summary = (f'GENOS 출력 토큰 상한 제거 R1 검증\n\n'
        f'GENOS RAG/AD의 실제 요청에서 max_tokens를 생략한다. 단계별 기본값과 과거 환경변수는 상한을 복구하지 않는다.\n'
        f'제품 소스 7파일과 소비 엔진 pin 변경. 모델 서버의 자체 한도는 미확인.\n'
        f'신규 작업 계약 {len(new_cases)}개 통과. 확대 검사 {regression["passed"]}개 통과/기존 4개 실패.\n'
        f'별도 초기 검사 워크플로우 실패 1개도 수정 전 동일 재현. 기존 실패 총 5개는 해결 항목이 아니다.\n'
        f'설치/실패/원복/실제 서비스 및 generation gate 계약 {delivery["tests"]}개 통과.\n'
        f'두 설치 구성 계약/API {validation["installed_passes"]}개 통과.\n'
        f'실제 TXT/checkout 명령 {commands}회, service.service localhost TLS 부팅/동일 committed checkout gate/원복 각각 2회.\n'
        f'알려진 {len(spec["signatures"])} 코드 inventory와 모든 알려진 LENGTH_RECOVERY 최종 코드 구성 결속.\n'
        f'정상·길이 종료·스키마 수정 성공/실패·예산/시간 소진·중복·재개·스트리밍 실패 보존 확인.\n'
        f'근거/권한/버전/코드·데이터 해시·최종 발행 검증과 기존 설정 보존.\n'
        f'외부/GENOS 실제 모델 호출 0회. 로컬 외부 Qwen 정책 및 MAIN66 유지.\n'
        f'GENOS 반입/push/리비전/워크플로우 질의 성공은 미확인.\n')
    (OUT/'VALIDATION_SUMMARY.txt').write_text(summary)
    names = ['apply_patch.py', 'PATCH_SPEC.json.gz', 'SOURCE_BINDING.json', 'VALIDATION.json',
        'VALIDATION_SUMMARY.txt', 'GUIDE_UTF8.txt', run.name, 'CHANGE_CONTRACT.txt', 'SOURCE_CHANGE.diff']
    names += ['payload/'+n for n in source['source_files']]
    manifest = {'schema_version': 'genos-partial-patch-v1', 'revision': NAME,
        'gate_archive': 'apply-generated BACKUP/APPLIED_CODE.zip', 'files': []}
    for name in names:
        raw = (OUT/name).read_bytes()
        if name.endswith('.py'): ast.parse(raw, feature_version=(3,10))
        manifest['files'].append({'path': name, 'sha256': sha(raw), 'bytes': len(raw)})
    (OUT/'CODE_MANIFEST.json').write_bytes(encoded(manifest))
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(names)+['CODE_MANIFEST.json']: z.write(OUT/name, name)
    with tempfile.TemporaryDirectory(prefix='output-unlimited-sealed-') as td:
        unpack = Path(td)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist())); z.extractall(unpack)
        for row in manifest['files']: assert sha((unpack/row['path']).read_bytes()) == row['sha256']
        assert (unpack/run.name).read_bytes() == run.read_bytes()
        subprocess.run(['bash','-n',str(unpack/run.name)],check=True)
    attachments = [archive.name, run.name, 'GUIDE_UTF8.txt', 'VALIDATION_SUMMARY.txt', 'VALIDATION.json']
    (OUT/'SHA256SUMS.txt').write_text(''.join(sha((OUT/n).read_bytes())+'  '+n+'\n' for n in attachments))
    sealed = {'zip_sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size,
        'standalone_txt_identical': True, 'member_hashes_verified': True, 'bash_syntax': 'PASS',
        'source_files_verified': len(source['source_files']), 'known_predecessors': len(spec['signatures'])}
    (OUT/'SEALED_UNPACK_CHECK.json').write_bytes(encoded(sealed))
    for p in OUT.glob('*.xml'): p.with_suffix('.xml.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    print(json.dumps({'sealed': sealed, 'verification': summary}, ensure_ascii=False))


if __name__ == '__main__': main()
