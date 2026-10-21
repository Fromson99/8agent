from pathlib import Path
import hashlib, json, re, shutil, sys
from xml.etree import ElementTree as ET

R = Path(__file__).resolve().parents[3]
A = R / (sys.argv[1] if len(sys.argv) > 1 else '04_EXPERIMENTS/ADR/ADR-0901-read-choice-information-preservation')
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

m = read(A / '실험/manifest.json')
f = read(A / 'artifacts/design/freeze.json')
resource = read(A / 'artifacts/resource.json')
suite = ET.parse(A / 'artifacts/contracts.xml').getroot().find('testsuite')
counts = {k: int(suite.get(k, 0)) for k in ('tests', 'failures', 'errors', 'skipped')}
ok = counts['failures'] == counts['errors'] == 0 and resource['stop_reason'] is None and resource['returncode'] == 0
failures = [{'test': row.get('name'), 'message': node.get('message')} for row in suite.findall('testcase') for node in row.findall('failure')]
criteria = read(A / 'artifacts/design/criteria.json')
result = {'status': 'complete', 'strict_success': ok, 'counts': counts, 'failures': failures,
          'product_model_calls': 0, 'legal_quality_certified': False, 'latency_evaluated': False,
          'peak_rss_bytes': resource['peak_group_rss_bytes'], 'resource_stop': resource['stop_reason'],
          'candidate': f['candidate'], 'active_MAIN_changed': False, 'genos_executed': False,
          'scope': criteria['evaluation'], 'remaining': ['Actual LLM latency/call-count impact and GENOS internal execution unmeasured.']}
if not ok:
    result['diagnosis'] = 'Three synthetic inputs omitted required law IDs; candidate packaging omitted pre-existing session_identity.py imported by current memory_identity.py. Product projection was unchanged after these results; no acceptance or working integration.'
    if m['adr_id'] == 'ADR-0902':
        result['diagnosis'] = 'All 89 non-API contracts pass. Existing legacy API fixture supplies team_id=t, rejected by current exact *_team selector before any model call. The unchanged product needs a current-contract fixture.'
    source = R / ('06_TOOLS/EXPERIMENTS/adr_0902/test_input.py' if m['adr_id'] == 'ADR-0902' else '05_TESTS/CONTRACTS/test_read_choice_input_preservation.py')
    shutil.copyfile(source, A / 'artifacts/failed-test-source.py')
put(A / 'artifacts/run-001/result.json', result)
m['runs'][0].update(status='complete', sha256=sha(A / 'artifacts/run-001/result.json'))
arm = m['design']['arms'][0]['id']
m['results'].update(status='complete', by_arm={arm: {'status': 'complete', 'strict_success': ok, 'counts': counts}},
                    usage={'product_model_calls': 0, 'offline_evaluator_calls': 0},
                    error_taxonomy=[] if ok else [{'type': 'other', 'count': counts['failures'], 'basis': result['diagnosis']}])
m['decision_eligible'] = ok
put(A / '실험/manifest.json', m)
meta = (A / 'README.md').read_text().split('---', 2)[1]
meta = re.sub(r'(?m)^status:.*$', 'status: ' + ('Accepted' if ok else 'Proposed'), meta)
meta = re.sub(r'(?m)^decision_eligible:.*$', 'decision_eligible: ' + str(ok).lower(), meta)
heads = ['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts = [('입력 정보 보존의 유한 기술 계약 통과.' if ok else '검사 하네스/포장 오류로 승인하지 않음. 실패 기록 보존.'),
    '읽기 후보의 저장 제목이 누락되고 중복 경로가 미리보기를 덮어썼다. 이어읽기/복귀 도구의 범위와 설명도 축약 과정에서 사라졌다.',
    '실행 전에 artifacts/design/criteria.json과 freeze.json에 동결. 입력 보존·문서 구분·원문·출력 스키마·복구 예산·실제 API 연결을 확인한다.',
    criteria['evaluation'], '격리 candidate의 코드와 해시 pin을 사용. 실제 모델 호출 없음. 작은 모의 원문과 scripted transport로 API 계약 검사.',
    'artifacts/run-001/result.json 및 contracts.xml 참조. ' + str(counts),
    result.get('diagnosis', '새 제목/미리보기/도구 대상 검사와 기존 원문·문법·복구·API 검사가 통과했다.'),
    f"모델0회. 검사 최고 RSS {result['peak_rss_bytes']/1024**2:.1f} MiB. 자원 중단 {resource['stop_reason']}. 제품 응답 시간 측정은 아님.",
    '확인 가능한 저장 정보만 전달하며 새 법률 근거/대상을 생성하거나 의미 판단을 대체하지 않는다.',
    '유한 기술 검사는 법률 정답률 또는 GENOS 성능 검증이 아니다. 실제 모델 호출 수·지연 개선은 후속 관측이 필요하다.',
    '활성 MAIN87 포인터와 GENOS는 변경하지 않는다. 승인된 코드만 현재 작업 코드와 해당 해시 pin에 통합하며 기존 변경을 보존한다.' if ok else '작업 코드 통합 없음. 다음 ADR에서 모의 입력 필수 ID 및 누락된 기존 의존 파일만 보완한다.',
    'artifacts/design/execution-plan.json의 검사 목록. resource_guard.py 아래 동결 runner 실행. 완료 결과 덮어쓰기 및 무기록 모델 재실행 금지.']
(A / 'README.md').write_text('---' + meta + '---\n\n# 읽기 선택 입력 보존 검증\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{p}' for i, (h, p) in enumerate(zip(heads, parts), 1)) + '\n')
(A / '실험/README.md').write_text('# 검증 범위\n\n공개 법률 질문 채점 없음. 유한 소프트웨어 계약 검사 결과는 ../artifacts/run-001/result.json에 보존한다.\n')
put(A / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': m['adr_id'], 'files': [
    {'path': str(p.relative_to(R)), 'sha256': sha(p), 'bytes': p.stat().st_size, 'description': 'Finite technical verification record', 'contains_raw_prompts_and_outputs': False}
    for p in (A / 'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json']})
print(json.dumps(result, ensure_ascii=False))
