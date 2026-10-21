"""Post-promotion receipt; does not alter frozen qualification artifacts."""
from pathlib import Path
import hashlib
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0846-source-return-boundary'
D = R / '09_ARTIFACTS/AUDITS/20261016-risk-comparison-source-return'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def ref(p):
    return {'path': str(p.relative_to(R)), 'sha256': sha(p)}

pointer = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['generation'] == 81
assert pointer['release_id'] == 'source-return-comparison-20261016-r1'
release_path = R / pointer['manifest_path']
release = read(release_path)
assert sha(release_path) == pointer['release_manifest_sha256']
frozen = read(A / 'artifacts/design/verification-binding.json')
active = read(A / 'artifacts/active-consumer-v2.json')
working = read(A / 'artifacts/working-consumer-v2.json')
integration = read(A / 'artifacts/working-integration.json')
result = read(A / 'artifacts/run-001/result.json')
assert release['files'] == frozen['serving_files']
assert len(release['files']) == 344
assert all(sha(R / release['code_root'] / n) == h for n, h in release['files'].items())
assert active['status'] == 'PASS' and len(active['checks']) == 13
assert all(active['checks'].values()) and not active['entry']['app_injected']
assert working['status'] == 'PASS' and working['qualified_component_hashes_match']
assert all(sha(R / c['path']) == c['after'] for c in integration['changes'])
assert result['strict_success'] is True
for name in ('candidate-api.log', 'working-api.log'):
    assert '76 passed, 1 deselected' in (A / 'artifacts' / name).read_text()
assert (A / 'artifacts/final-validation.txt').read_text().startswith('OK:')
live = R / '04_EXPERIMENTS/ADR/ADR-0844-comparison-source-return/artifacts/run-001/committee-duties-01'
model_result = read(live / 'result.json')
assert model_result['model_calls'] == 9 and model_result['status'] == 'partial'
binding = active['health']['body']['release']
assert binding['release_id'] == pointer['release_id'] and binding['generation'] == 81
receipt = {
    'status': 'PASS', 'active_pointer': pointer, 'release': ref(release_path),
    'workflow_version': '1.8.0', 'serving_files': len(release['files']),
    'working_changes': len(integration['changes']),
    'preserved_other_working_differences': len(integration['preserved_other_working_differences']),
    'candidate_contract_tests': 76, 'working_contract_tests': 76,
    'new_boundary_states': 16, 'retained_contracts': 60,
    'excluded_invalid_fixture': result['excluded_invalid_fixture'],
    'working_service_checks': 13, 'active_service_checks': 13,
    'active_service_entry': active['entry'], 'data': active['actual_data'],
    'verified_candidate': ref(A / 'artifacts/design/verification-binding.json'),
    'working_integration': ref(A / 'artifacts/working-integration.json'),
    'working_consumer': ref(A / 'artifacts/working-consumer-v2.json'),
    'active_consumer': ref(A / 'artifacts/active-consumer-v2.json'),
    'qualification': ref(A / 'artifacts/run-001/result.json'),
    'apply_log': ref(A / 'artifacts/main-apply.log'),
    'actual_service_release_binding': binding,
    'search_selection_fingerprint': active['health']['body']['search_selection']['sha256'],
    'retained_model_run': {
        'result': ref(live / 'result.json'), 'answer': ref(live / 'answer.txt'),
        'audit': ref(live / 'audit.json'), 'calls': model_result['model_calls'],
        'seconds': model_result['elapsed_seconds'], 'comparison_rows': 2,
        'final_code_full_model_rerun': False,
        'final_delta': 'Native journal completion and internal SELECT schema; verified by API and actual-data consumers.',
    },
    'quality_certified': False, 'genos_deployed': False,
    'git_commit_or_push_performed': False, 'existing_resident_services_restarted': False,
    'limitations': result['limitations'] + [
        'Global ADR graph retains 9 pre-existing unrelated errors; individual ADR0844–0846 final validation passed.',
        'ADR0844 retrieval-stage ledger was not frozen before its live call; later counts are descriptive only and are not promotion evidence.',
    ],
    'rollback': 'Only while active generation81 matches this receipt: .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main. Verify pointer and fresh service binding before/after; previous release is MAIN80. Working backups: artifacts/working-before. Do not force new-version journals into old schemas.',
}
(A / 'MAIN_RESULT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
report = '''대사 단순화 설계 전체 구현 및 로컬 MAIN81 반영
2026-10-16 / source-return-comparison-20261016-r1 / workflow 1.8.0

완료 범위
작업 코드 통합 → 동일 후보·작업 코드 검사 → 해시 고정 승격 → 활성 포인터 generation81 → 새 프로세스의 실제 service.application/API/저장 조회 확인까지 완료했다.
GENOS 현장 적용·내부 모델 실행, Git commit/push, 기존 로컬 상주 프로세스 재시작은 수행하지 않았다.

설계의 네 가지 변경
1. 질문이 명시한 내규를 공식 이름·등록 별칭으로 우선 지정한다. 짧은 문서는 전체 구조와 본문·부칙을 먼저 읽고, 긴 문서는 목차와 선택 범위를 읽는다. 실제 읽기와 부모 전달 범위를 구분해 기록한다.
2. 원문에서 확인한 명시 참조는 기존 reference_targets 연결을 먼저 사용한다. 연결이 없을 때만 확인된 문서명·별칭·조문 위치로 조회한다. 자동 추적은 한 단계이며 중복·순환·권한 밖 읽기는 제한한다. 로컬에서 못 찾았다는 이유로 GENOS에도 문서가 없다고 결론내리지 않는다.
3. 대사 자식 RAG에 신뢰된 sources 반환 모드를 연결했다. 모델은 조사 대상·검색어·이유만 선택하고 시스템이 도구·위치·근거 ID·상태를 조립한다. 확보 원문을 정상 SOURCE_HANDOFF로 반환하며 자식 ASSESS/COMPOSE를 요구하지 않는다. 원문이 0건이거나 일부만 있어도 조회 기록과 미확보를 반환한다. 일반 RAG의 답변 경로는 유지한다.
4. 최종 비교를 쟁점별 한 표로 표시한다. 비교 의견·이유·인용·미확보를 함께 남기고, 보류 의견도 비교행에 포함한다. 세부 필드 관측과 모델 원래 의견은 구조화 결과에 보존한다.

정상 종료·실패·재개
원문 반환은 법률 판단 완료나 성공 경험 승인과 구분한다. 자식 사건과 실행 원장을 SOURCES_RETURNED 및 COMPLETED/END로 일관되게 저장하며, 추가 조사 때 이전 FINISH를 잘못 재사용하지 않는다. 중단 후 같은 handoff를 재사용하고 deadline·사용량을 초기화하지 않는다. 기존에 확보한 근거는 후속 실패로 덮어쓰지 않는다.
불확실성·미확보·표현 차이는 실행을 막는 조건이 아니다. 실제 선택한 원문의 일치, 내외규 구분, 권한, 코드·데이터·상태 해시와 중복·예산 검사는 유지한다.

실제 모델 대사에서 확인한 결과
질문: 위험관리위원회운영준칙의 위원회 역할과 심의·의결사항을 관련 외규와 대사해서 공통사항과 차이를 설명해 주세요.
ADR0844 실행에서 지정 준칙의 제1~10조 및 부칙, 37블록·1,641자를 읽었다. 자식은 내부16개·외부31개의 근거 단위를 반환했고 실제 원문 span 불일치는 0건이었다. 자식 ASSESS/COMPOSE 호출은 0회였다.
Qwen3.8/Parasail FP8 전체 9호출, 509.98초, HTTP200·partial로 두 비교행을 반환했다. 위원회 역할은 부합 의견을, 심의·의결사항은 참조 규정 미확보에 따른 보류 의견을 냈다. 이는 모델의 검토 의견이며 법률 정답 인증이 아니다. 실제 답변 원본은 ADR0844의 answer.txt를 참조한다.
이후 최종 코드에서는 원장 종료와 내부 SELECT 스키마를 보완했다. 이 최종 코드로 전체 모델 질의를 다시 호출하지 않았으며, 동일 코드의 API·실제 데이터 서비스 검사로 검증했다. 과거 MAIN80의 19호출·809초와는 개발 사례의 관측 비교이며 일반적인 속도 향상률로 보지 않는다.

검증·선택
최종 후보와 선택 릴리스의 서빙344파일 해시가 일치한다. 관련 작업48파일을 통합했고 다른 작업 차이39개를 보존했다. 후보와 작업 코드 각각76개 검사 통과(새 원문 유무·예산·중단 조합16개 + 기존 계약60개). ADR0845의 원문0건 테스트1개는 검색에서 실제 원문이 나오는 잘못된 fixture였으며 실패 이력을 보존하고 제외했다. 새16개는 도구의 빈 반환을 명시적으로 고정해 0건 경계를 검사했다.
실제 데이터의 작업 서비스13개, MAIN81 선택 서비스13개 검사가 통과했다. 최종 선택 검사는 앱 주입 없이 service.application을 시작하여 실제 선택 릴리스의 코드·프로필·데이터·검색 정책 지문, 팀별 문서 조회·권한, 대사 진입·자식 범위·저장 조회를 확인했다. 이 소비자 검사는 모델0회다.
원문 데이터 세대는 latest-selection-20261015-r1/generation을 유지했다. 전체 MAIN 데이터 파이프라인을 재구축한 것은 아니다.

남은 한계
GENOS의 기존 참조 연결을 우선 쓰도록 구현했지만 현장 연결과 배포는 이 세션에서 확인하지 않았다. 로컬의 참조 미확보는 현장 문서 부재의 증거가 아니다.
법률 정확도·검색 재현율·전체 업무 일반화 성능은 별도 검증 대상이다. 의미 판단 미스를 자동 차단 조건으로 추가하지 않았다.
ADR0844의 검색 단계 계수 원장은 실제 호출 전에 동결하지 못했다. 후속 집계는 설명용이며 검색 개선이나 승격 근거로 사용하지 않았다. 승격 근거는 최종 동일 코드의 새 기술 경계16상태와 계약·소비자 검사다.
ADR0844~0846 개별 final 검사는 통과했다. 전역 ADR graph에는 이번 변경과 무관한 기존 오류9개가 남아 있다.

실제 연결
service.py → semantic_runtime.app → workflow.api → risk_team_compare_workflow → workflow_rag → 기존 Pipeline/Investigation/SourceSession → SOURCE_HANDOFF → 항목 검토·추가 조사·COMPARE → 단일 표·저장 조회.
주요 변경: semantic_runtime/legal_agent/source_investigation.py, source_handoff.py, corrected_memory.py, workflow_execution.py, case_repository.py; semantic_runtime/workflow_rag.py, workflow_evidence.py; workflow/risk_team_compare_workflow/retrieval.py, task_board.py, report.py 및 manifest/PIPELINE/엔진 pin.
새 재구축·별도 조사 실행기 없이 기존 경로에 연결했다. 일반 내규:/외규: RAG와 과거 읽기 결과 호환 경로는 보존한다.

원복
활성 generation81과 MAIN_RESULT.json이 일치할 때 저장소 루트에서:
  .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
이전 MAIN80으로 복귀하며 전후 활성 포인터와 새 프로세스의 service binding을 확인한다. 새 버전 저널을 옛 스키마로 강제 열지 않는다. 작업 변경 백업은 ADR0846 artifacts/working-before이며 다른 작업은 보존한다.

기록
정본 영수증: 04_EXPERIMENTS/ADR/ADR-0846-source-return-boundary/MAIN_RESULT.json
실제 모델 답변: 04_EXPERIMENTS/ADR/ADR-0844-comparison-source-return/artifacts/run-001/committee-duties-01/answer.txt
최종 API 결과: ADR0846 artifacts/candidate-api.log, working-api.log
실제 활성 서비스: ADR0846 artifacts/active-consumer-v2.json
승격·검증: ADR0846 artifacts/main-apply.log, final-validation.txt, graph-final.txt
'''
(A / 'MAIN_RESULT.txt').write_text(report)
D.mkdir(parents=True, exist_ok=True)
(D / 'RESULT.txt').write_text(report)

p = R / 'AGENTS.md'
s = p.read_text()
old = '`direct-comparison-20261016-r1`(포인터 generation 80)'
new = '`source-return-comparison-20261016-r1`(포인터 generation 81)'
assert old in s or new in s
p.write_text(s.replace(old, new, 1))

intro = '2026-10-16 현행 로컬 RAG 서빙은 **MAIN81 `source-return-comparison-20261016-r1` / workflow 1.8.0**다. 지정한 짧은 내규 전문 읽기, 기존 명시 참조 연결 우선 조회, 대사 자식의 정상 원문 반환, 쟁점별 단일 비교표를 구현했다. 불확실성은 의견·미확보로 표시하고 원문·권한·해시·상태 검사는 유지한다. 검증 후보와 선택344파일 동일, 후보/작업 각각76검사와 활성 서비스13검사 통과. 개발 후보의 실제 Qwen 대사는9호출·510초·2비교행을 반환했다. 이후 원장 종료·SELECT 스키마 보완본은 API·실제 데이터 소비자로 검증했으며 전체 모델 질의를 다시 호출하지 않았다. 법률 정답 인증·GENOS 배포는 별도다.'
for name, link in [
    ('00_SYSTEM/ARCHITECTURE.md', '../09_ARTIFACTS/AUDITS/20261016-risk-comparison-source-return/RESULT.txt'),
    ('07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md', '../../../09_ARTIFACTS/AUDITS/20261016-risk-comparison-source-return/RESULT.txt'),
]:
    p = R / name
    s = p.read_text()
    if '**MAIN81 ' not in s:
        s = s.replace('2026-10-16 현행 로컬 RAG 서빙은 **MAIN80', '2026-10-16 이전 로컬 RAG 서빙 **MAIN80', 1)
        first, rest = s.split('\n', 1)
        s = first + '\n\n' + intro + ' [구현·검증·한계·원복](' + link + ').\n' + rest
        p.write_text(s)

p = R / '07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md'
s = p.read_text()
heading = '## 1.8.0 원문 반환과 비교\n\n'
if heading not in s:
    section = heading + '''대사 부모가 기존 RAG에 신뢰된 `return_mode="sources"`를 설정한다. 외부 사용자 body가 이 모드를 직접 켤 수 없다. 짧은 지정 내규의 전문 및 기존 명시 참조를 기존 acquire/Investigation 경로에서 읽고, 모델은 제공된 target_id·query·reason으로 조사 행동을 선택한다. 자료가 부족해도 원문·조회 기록·미확보를 `SOURCE_HANDOFF`로 반환하며 자식의 ASSESS/COMPOSE를 거치지 않는다. 일반 내규·외규 질문의 판단·답변 경로는 유지한다.

`source-investigation-v1`, workflow result v3, source bundle v2를 사용한다. 기존 `comparison-research-v1` 조사 과제와 이전 읽기 결과 호환 경로는 유지한다. 자식 사건의 `SOURCES_RETURNED`와 실행 원장의 `COMPLETED/END`를 함께 확정하며 후속 조사에서는 이전 종료 선택을 재사용하지 않는다. 원문 반환을 성공 답변·법률 결론·경험 승인으로 저장하지 않는다.

부모의 항목 검토·추가 조사·비교는 유지하고 최종 표는 쟁점 이름·내규·외규·의견·이유/미확보를 함께 표시한다. 보류도 비교행으로 계산한다. 실제 선택 인용·내외규 구분·권한·해시·재개·예산은 검사하고, 충분성·적용성·차이는 모델의 의견으로 제시한다. GENOS의 기존 참조 연결을 우선 쓰며 로컬 조회 실패를 현장 문서 부재로 간주하지 않는다.

'''
    s = s.replace('## 1.7.0 실행과 판단의 분리', section + '## 1.7.0에서 이어받은 실행과 판단의 분리', 1)
    s = s.replace('"workflow_version": "1.5.2"', '"workflow_version": "1.8.0"', 1)
    p.write_text(s)

p = R / '04_EXPERIMENTS/ADR/README.md'
s = p.read_text()
for folder, title in [
    ('ADR-0844-comparison-source-return', '대사 단순화 구현·실제 모델 2비교행·개발 관측'),
    ('ADR-0845-source-terminal-qualification', '원문 반환 원장 종료 보완·실패 fixture 이력'),
    ('ADR-0846-source-return-boundary', '원문 유무·예산·재개 경계 검증·로컬 MAIN81 반영'),
]:
    if folder not in s:
        s += '\n- [' + folder + ' — ' + title + '](' + folder + '/README.md)\n'
p.write_text(s)
print('MAIN81 receipt and current documentation saved; frozen ADR artifacts unchanged.')
