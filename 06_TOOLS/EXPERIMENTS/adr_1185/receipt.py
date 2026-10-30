"""Read-only final R9 evidence receipt; never rerun or rewrite product artifacts."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1185-pipeline02-delivery-receipt'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-1183-pipeline02-spawn-safe-delivery'
DELIVERY = ROOT / '08_DEPLOYMENT/DATAIKU/pipeline_speed_20261028_r9'
ART = ADR / 'artifacts'
sys.path[:0] = [str(ROOT / '06_TOOLS/maintenance'), str(ROOT / '06_TOOLS/COMMANDS')]
from experiment_json import write_summary
import adr_structure


def read(path):
    return json.loads(path.read_text())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def relative(path):
    return str(path.relative_to(ROOT))


def main():
    assert not (ART / 'result.json').exists(), 'Preserve completed receipts'
    own_manifest = ADR / '실험/manifest.json'
    manifest = read(own_manifest)
    assert manifest['reservation']['status'] == 'in_progress'
    parent_manifest = PARENT / '실험/manifest.json'
    original_parent_hash = sha(parent_manifest)
    active = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    original_active_hash = sha(active)
    assert read(active)['generation'] == 112
    errors = adr_structure.validate_adr(PARENT, final=True)
    assert len(errors) == 1 and 'runner must stay in 06_TOOLS' in errors[0], errors
    write_summary(ART / 'parent-validation.json', {
        'canonical_manifest': relative(parent_manifest),
        'sha256': original_parent_hash,
        'errors': errors,
        'original_preserved': True,
        'interpretation': 'Parent final metadata validation remains failed; this receipt does not relabel it as passed.'})

    delivery_manifest = DELIVERY / 'DELIVERY_MANIFEST.json'
    assert sha(delivery_manifest) == manifest['dataset']['sha256']
    delivery = read(delivery_manifest)
    sealed_hashes = {name: row['sha256'] for name, row in delivery['delivery_files'].items()}
    for name, row in delivery['delivery_files'].items():
        path = DELIVERY / name
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes'], name
    # Also retain bindings of test reports, builder, finalizer and the closed result.
    for row in read(PARENT / 'artifacts/manifest.json')['files']:
        path = ROOT / row['path']
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes'], path

    outer = DELIVERY / 'DATAIKU_SPEED_20261028_R9.zip'
    with zipfile.ZipFile(outer) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(sealed_hashes) - {outer.name}
        assert all(digest(archive.read(n)) == sealed_hashes[n] for n in archive.namelist())
    with zipfile.ZipFile(DELIVERY / 'GENOS_DATAIKU_COMPUTE_20261028_R9.zip') as archive:
        payload = {name.split('/', 1)[1]: archive.read(name) for name in archive.namelist()}
    pins = json.loads(payload['CODE_PINS.json'])['files']
    code_hash = digest(payload['CODE_PINS.json'])
    assert code_hash == delivery['code_sha256']
    assert len(payload) == 1282 and set(payload) == set(pins) | {'CODE_PINS.json'}
    assert all(digest(payload[name]) == wanted for name, wanted in pins.items())
    with zipfile.ZipFile(DELIVERY / 'DATAIKU_COMPUTE_RECIPES_20261028_R9.zip') as archive:
        client = {name: archive.read(name) for name in archive.namelist()}
    client_pins = json.loads(client['PACKAGE_FILES.json'])
    assert set(client) == set(client_pins) | {'PACKAGE_FILES.json'}
    assert all(digest(client[name]) == wanted for name, wanted in client_pins.items())
    assert client['COMPUTE_CODE_SHA256.txt'].decode().strip() == code_hash

    binding = read(DELIVERY / 'RELEASE_BINDING.json')
    assert binding['code_pins_sha256'] == code_hash
    for item in binding['frozen_candidates']:
        path = ROOT / item['path']
        assert sha(path) == item['sha256']
        revision = next(r for r in read(path)['revisions'] if r['revision_id'] == item['revision'])
        assert revision['revision_sha256'] == item['revision_sha256']
        assert all(sha(ROOT / r['frozen_path']) == r['snapshot_sha256'] for r in revision['files'])
    frozen1181 = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1181/balanced4/revisions/rev-001/snapshot'
    frozen1183 = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1183/repaired/revisions/rev-001/snapshot'
    assert payload['worker.py'] == (frozen1181 / '08_DEPLOYMENT/DATAIKU/pipeline_export_20261028_r8/worker.py').read_bytes()
    def build_ast(raw):
        return ast.dump(next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'build'))
    assert build_ast(payload['02_BACKEND/semantic_runtime/unit_fulltext.py']) == build_ast((frozen1181 / '02_BACKEND/semantic_runtime/unit_fulltext.py').read_bytes())
    assert ast.dump(ast.parse(payload['06_TOOLS/pipeline.py']).body[-1]) == ast.dump(ast.parse((frozen1183 / '06_TOOLS/pipeline.py').read_bytes()).body[-1])

    cases = {}
    for name, expected in [('TEST.xml', 103), ('NATIVE_TEST.xml', 4), ('SPAWN_TEST.xml', 3)]:
        tests = ET.parse(DELIVERY / name).getroot().findall('.//testcase')
        assert len(tests) == expected
        assert all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in tests)
        cases[name] = {'passed': len(tests), 'sha256': sha(DELIVERY / name)}
    checkouts = binding['local_installer_checkouts']
    assert len(checkouts) == 7
    for row in checkouts:
        committed = subprocess.check_output(['git', 'show', row['commit'] + ':CODE_PINS.json'], cwd=row['path'])
        assert digest(committed) == row['committed_pins_sha256'] == code_hash
    native = binding['native_generations']
    assert len(native) == 2
    for row in native:
        archive_path = Path(row['archive'])
        assert sha(archive_path) == row['sha256']
        with zipfile.ZipFile(archive_path) as archive:
            release = json.loads(archive.read('audit/release.json'))
        assert release['settings']['fulltext_workers'] == 4 and release['offline_e2e'] == 'PASS'
    validation = read(DELIVERY / 'VALIDATION.json')
    assert validation['tests_passed'] == 110 and validation['performance']['mismatches'] == 0
    assert validation['performance']['local_logical_cpus'] == 16
    assert validation['performance']['field_cpu'] == 4 and validation['performance']['field_ram_gib'] == 16
    assert validation['onsite_total_seconds'] is None
    assert not any(validation[key] for key in ['goal_1hour_achieved', 'onsite_deployed', 'main_changed', 'intermediate_failed_added_resume'])
    assert validation['raw_01_reusable'] and validation['requires_02_recompute']
    assert sha(parent_manifest) == original_parent_hash and sha(active) == original_active_hash
    assert all(sha(DELIVERY / name) == wanted for name, wanted in sealed_hashes.items())

    result = {
        'status': 'complete', 'checks_passed': 5,
        'parent_validation_errors_preserved': errors, 'parent_manifest_unchanged': True,
        'server_files': len(payload), 'client_files': len(client),
        'code_pins_sha256': code_hash, 'outer_zip_sha256': sha(outer),
        'frozen_functions_match': True, 'recorded_tests_passed': 110, 'test_reports': cases,
        'installer_commit_bindings': 7, 'native_result_bindings': 2,
        'main112_unchanged': True, 'active_pointer_sha256': original_active_hash,
        'new_product_tests': 0, 'new_model_calls': 0, 'new_performance_runs': 0,
        'performance_reference': validation['performance'],
        'onsite_deployed': False, 'whole02_1hour_verified': False,
        'raw_01_reusable': True, 'failed_added_resume': False, 'requires_02_recompute': True}
    write_summary(ART / 'result.json', result)
    manifest['runs'][0].update(status='complete', sha256=sha(ART / 'result.json'), success_criteria_met=True)
    manifest['results'].update(status='complete', by_arm={'receipt': result}, comparisons=[], judge_disagreements=[],
        usage={'new_model_calls': 0}, latency={'not_measured_reason': 'Read-only audit; inherited token-component timing only'},
        error_taxonomy=['Closed1183 runner location metadata error preserved; all delivered product evidence matches'])
    own_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    heads = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
    texts = [
        'R9 전달 파일과 기존 110개 검사 결과의 결속을 읽기 전용으로 확인했다. 새 제품·모델·성능 실행은 없다.',
        '완료된 ADR1183의 실행기가 08_DEPLOYMENT 아래에 기록되어 허용된 실행기 경로 규칙에 걸렸다. 원본 manifest와 오류를 보존한다.',
        '[사전 기준](artifacts/criteria.json): 알려진 메타데이터 오류 1건만 존재하고, 코드·결과·성능 해석이 모두 고정되어야 한다.',
        '부모1183/repaired의 감사 후속이다. 모든 ZIP·해시·동결 함수·기존 XML과 실제 테스트용 Git 커밋을 대조한다. 부모 실행기의 경로를 사후 변경하지 않는다.',
        '동일 R9 전달본, 동결1181/1183, 기존 로컬 검사 증거를 사용했다. 원문·모델 호출·법률 채점은 없다.',
        '[결과](artifacts/result.json): 5개 감사 조건 통과. 서버1282파일, 기존110검사, 설치7커밋과 native 반환2개가 일치한다.',
        '[부모 최종 메타데이터 오류](artifacts/parent-validation.json)는 그대로 실패 기록이다. 이 영수증은 그 검사를 통과로 바꾸지 않는다. 초기 native 2실패와 제한 환경 대기 기록도 유지한다.',
        '새 모델0·제품검사 재실행0·성능 재측정0. 기존12,288단위 토큰 생성265.485→106.823초는 로컬16논리CPU 환경 측정이다.',
        '실제로 검사한 R9와 전달하는 R9가 같음을 확인했다. 토큰 생성의 약2.49배 개선을 전체02 개선율로 확대하지 않는다.',
        '현장 CPU4/메모리16GB의 전체02 시간은 미측정이다. 5시간→1시간 달성은 미확인이다. 현장 저장 로그의 구간별 시간이 필요하다.',
        'MAIN112·GENOS 리비전은 바꾸지 않았다. 기존01은 동일 입력에서 재사용하고, 실패한 added 위치부터 이어갈 수 없어02는 재계산한다. R9 안내에 설치·원복 절차가 있다.',
        '06_TOOLS/EXPERIMENTS/adr_1185/receipt.py가 읽기 전용 대조를 수행했다. 완료 결과를 덮어쓰지 않으며 재감사는 새 ADR에서 수행한다. [산출물](artifacts/manifest.json).']
    readme = ADR / 'README.md'
    front = readme.read_text().split('---', 2)[1]
    readme.write_text('---' + front + '---\n\n# R9 전달 증거 확인\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{t}' for i, (h, t) in enumerate(zip(heads, texts), 1)) + '\n')
    (ADR / '실험/README.md').write_text('# 감사 실행\n\n질문·모델 실행 없음. [결과](../artifacts/result.json), [원본 오류](../artifacts/parent-validation.json), [manifest](manifest.json).\n')
    paths = [ART / 'criteria.json', ART / 'parent-validation.json', ART / 'result.json', Path(__file__), delivery_manifest]
    artifact_manifest = {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-1185', 'files': [
        {'path': relative(p), 'sha256': sha(p), 'bytes': p.stat().st_size,
         'description': 'Read-only final R9 evidence receipt', 'contains_raw_prompts_and_outputs': False} for p in paths]}
    (ART / 'manifest.json').write_text(json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + '\n')
    print('R9 receipt: 5 checks passed; 110 prior test results bound; parent metadata error preserved')


if __name__ == '__main__':
    main()
