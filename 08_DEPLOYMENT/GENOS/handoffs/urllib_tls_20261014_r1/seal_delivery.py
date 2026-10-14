"""Seal tested transport bytes, installer, reference comparison and compact evidence."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as E
import zipfile

O = Path(__file__).resolve().parent
R = O.parents[3]
N = 'GENOS_URLLIB_TLS_20261014_R1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
enc = lambda value: (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()


def stats(path):
    suite = E.parse(path).getroot().find('testsuite')
    return {k: int(suite.attrib[k]) for k in ('tests', 'failures', 'errors', 'skipped')}


def main():
    assert not (O/(N+'.zip')).exists(), 'Preserve sealed handoff'
    source = json.loads((O/'SOURCE_BINDING.json').read_bytes())
    comparison = json.loads((O/'COMPARISON.json').read_bytes())
    for n, h in source['source_files'].items():
        raw = (R/n).read_bytes()
        assert sha(raw) == h == sha((O/'payload'/n).read_bytes())
        assert set(source['field_variants'][n].values()) == {h}
        assert comparison['same_genos_transport_files'][n]['selected_sha256'] == h
        ast.parse(raw, feature_version=(3, 10))
    delivery = stats(O/'DELIVERY_TESTS.xml')
    assert delivery == {'tests': 4, 'failures': 0, 'errors': 0, 'skipped': 0}, delivery
    installed = {p.name: stats(p) for p in sorted(O.glob('INSTALLED_*.xml'))}
    assert len(installed) == 4
    assert all(v['tests'] > 40 and not any(v[k] for k in ('failures','errors','skipped')) for v in installed.values())
    counts = dict(commands=0, legacy_mock_boots=0, tls_success_boots=0, tls_rejected_boots=0,
                  generation_gates=0, tamper_rejections=0, undo=0)
    roots = []
    for p in sorted(O.glob('TEST_*.json.gz')):
        rows = json.loads(gzip.decompress(p.read_bytes()))
        assert rows[-1]['returncode'] == 0 and rows[-1]['argv'][2] == 'undo'
        counts['commands'] += len(rows)
        for row in rows:
            out = row['stdout']
            counts['legacy_mock_boots'] += out.count('SERVICE_PROFILE_BOOTSTRAP PASS')
            counts['tls_success_boots'] += out.count('SERVICE_TLS_BOOTSTRAP PASS')
            counts['tls_rejected_boots'] += out.count('SERVICE_TLS_UNTRUSTED_REJECTED PASS')
            counts['generation_gates'] += out.count('GENOS_RELEASE_GATE PASS')
            counts['undo'] += out.count('CODE_RESTORED;')
            counts['tamper_rejections'] += bool(row['returncode'] != 0 and row['argv'][0] == 'bash')
            if 'installed_runner.py' in str(row['argv']):
                assert row['returncode'] == 0 and 'INSTALLED_RUNTIME_IMPORTS PASS' in out
                roots.append(row['argv'][2])
    assert all(counts[k] == 4 for k in ('legacy_mock_boots','tls_success_boots','tls_rejected_boots','generation_gates','undo'))
    assert counts['tamper_rejections'] == 8
    active = json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    assert active['release_id'] == comparison['selected_release'] and active['generation'] == 61
    baseline = stats(O/'WORKING_TESTS.xml')
    failures = [x.attrib['name'] for x in E.parse(O/'WORKING_TESTS.xml').iter('testcase') if x.find('failure') is not None]
    assert baseline['failures'] == 4 and baseline['tests'] == 70
    validation = {'revision': N, 'installed_contracts': installed,
        'installed_contract_tests': sum(x['tests'] for x in installed.values()),
        'delivery_tests': delivery, 'checks': counts, 'verified_code_roots': roots,
        'known_inventories': source['known_predecessors'], 'engine_helper_pins': source['engine_helper_pins'],
        'source_files': source['source_files'], 'same_working_selected_field_transport_bytes': True,
        'working_tests_before_product_changes': baseline, 'unchanged_workflow_expectation_failures': failures,
        'working_product_files_changed_this_task': [],
        'active_release_unchanged': active['release_id'], 'active_generation': active['generation'],
        'real_model_calls': 0, 'genos_or_external_network_calls': 0,
        'local_network': 'Actual localhost HTTP/TLS with synthetic CA and model responses',
        'field_commit': None, 'field_generation_path': None, 'field_generation_manifest_sha256': None,
        'field_serving_revision': None, 'field_deployment': 'NOT_VERIFIED',
        'fixture_repairs': ['Authoring glossary fixtures use workspace schema; installed runtime imports remain verified',
            'Synthetic gateway generation prebuilt with working build tools; installed runtime, gateway and commit are verified'],
        'limits': ['Actual GENOS CA/container environment and internal inference require workflow-screen verification',
            'Four pre-existing workflow error-display test expectations remain; no workflow file is modified',
            'No local MAIN pointer change; external Qwen/OpenRouter adapter is separate']}
    (O/'VALIDATION.json').write_bytes(enc(validation))
    total = validation['installed_contract_tests']
    summary = f'''GENOS urllib 전송 R1 — 검증 요약

설치본 전송/스트림/gateway/임베딩 계약 {total}개 통과(4조합 합계).
실제 RUN check/apply/중복 apply/verify/변조 거부/undo/동일 checkout generation gate 4조합 통과.
설치 전 모의 부팅 4회, 설치 후 실제 localhost TLS 부팅 성공 4회·미신뢰 인증서 거부 4회.
정확한 committed checkout의 합성 generation 배포 gate 4회 통과. 명령 {counts['commands']}개 기록.
알려진 선행 inventory {source['known_predecessors']}종, 새 helper의 엔진 pin {source['engine_helper_pins']}개 결속.
3개 전송 파일은 작업 코드·선택 MAIN61·설치본의 SHA-256이 동일.
변경 전 작업 확대 검사 70개 중 66통과/4실패. 4개는 변경하지 않는 워크플로우의 공개 오류 표시 기대 불일치.
검사 준비 중 fixture의 생성용 스키마/모듈 누락을 보완한 기록과 초기 실패는 보존.
실제 모델 추론 및 GENOS/외부망 호출 0회. 실제 통신 검사는 localhost 합성 TLS만 사용.
현장 반입·CA 환경·commit/push·새 리비전·SSE 재시작·워크플로우 성공은 미확인.
로컬 MAIN61 포인터와 외부 Qwen/OpenRouter adapter는 유지.
'''
    (O/'VALIDATION_SUMMARY.txt').write_text(summary)
    # Preserve raw outcomes losslessly, without repeating them in prose.
    for p in list(O.glob('*.xml')) + list((O/'failures').glob('*.xml')):
        p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0))
    files = ['apply_patch.py','PATCH_SPEC.json.gz','SOURCE_BINDING.json','INVENTORY_BINDINGS.json.gz',
             'COMPARISON.json','VALIDATION.json','VALIDATION_SUMMARY.txt','FAILURE_CONTRACT.txt','GUIDE_UTF8.txt',
             N+'_RUN.txt','build_delivery.py','seal_delivery.py','test_delivery.py','installed_runner.py']
    files += [str(p.relative_to(O)) for folder in ('payload','preimage') for p in (O/folder).rglob('*.py')]
    files += [p.name for p in O.glob('*.gz')]
    files += [str(p.relative_to(O)) for p in (O/'failures').glob('*.gz')]
    manifest = {'version': N, 'files': [{'path': n, 'sha256': sha((O/n).read_bytes()),
                                        'bytes': (O/n).stat().st_size} for n in sorted(set(files))]}
    (O/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    archive = O/(N+'.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(set(files+['CODE_MANIFEST.json'])):
            assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
            z.write(O/n, n)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in manifest['files']:
            assert sha(z.read(row['path'])) == row['sha256']
        assert z.read(N+'_RUN.txt') == (O/(N+'_RUN.txt')).read_bytes()
    subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))], check=True)
    attachments = [N+'.zip', N+'_RUN.txt','GUIDE_UTF8.txt','VALIDATION_SUMMARY.txt','VALIDATION.json']
    (O/'SHA256SUMS.txt').write_text(''.join(sha((O/n).read_bytes())+'  '+n+'\n' for n in attachments))
    print(json.dumps({'zip_bytes': archive.stat().st_size, 'zip_sha256': sha(archive.read_bytes()),
                      'installed_contract_tests': total, 'checks': counts}))


if __name__ == '__main__':
    main()
