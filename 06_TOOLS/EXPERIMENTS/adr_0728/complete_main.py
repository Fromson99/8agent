"""Write completion evidence only after actual selected-service verification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0728-navigation-input-public-qualification'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
f = read(A / 'artifacts/design/freeze.json')
p = read(R / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
m = read(R / p['manifest_path'])
smoke = read(A / 'artifacts/main-smoke.json')
result = read(A / 'artifacts/run-001/result.json')
working = read(A / 'artifacts/working-verification.json')
assert result['strict_success'] and smoke['status'] == 'passed'
assert smoke['pointer'] == p
assert m['files'] == f['serving_files']
for name, h in f['serving_files'].items():
    assert sha(R/name) == sha(R/f['code_root']/name) == sha(R/m['code_root']/name) == h
base = read(A / 'artifacts/design/baseline.json')
assert m['data_path'] == base['manifest']['data_path']
assert p['generation'] == base['pointer']['generation'] + 1
completion = {
    'completed_at': datetime.now(timezone.utc).isoformat(),
    'status': 'local MAIN selected and actual service verified',
    'source': 'ADR-0728-experiment-v1/integrated', 'run': 'run-001',
    'pointer': p, 'pointer_sha256': sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'working_root': str(R), 'verified_code_root': f['code_root'], 'selected_code_root': m['code_root'],
    'all_serving_files_identical': len(f['serving_files']),
    'file_catalogue_sha256': hashlib.sha256(json.dumps(f['serving_files'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
    'profile_sha256': smoke['execution_binding']['profile_sha256'],
    'data_manifest_sha256': m['data_manifest_sha256'],
    'navigation_policy': smoke['actual_navigation_policy'],
    'policy_code_sha256': {name: sha(R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent'/name)
                           for name in ('law_navigation.py','gateway.py','wire_schema.py','structure_query.py','local_gemma.py')},
    'actual_execution_binding': smoke['execution_binding'], 'working_tests': working,
    'genos_deployed': False, 'git_main_merged': False, 'resident_server_restarted': False,
    'previous_release_preserved': base['pointer'],
}
(A/'artifacts/main-completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
text=f'''# 구조 검색과 탐색 입력 최적화 MAIN 반영

2026-10-12 로컬 MAIN을 `{p['release_id']}`(포인터 generation **{p['generation']}**)로 전환했다. 새 기본 `service.service`의 HEALTH와 RAG_SEARCH가 이 릴리스를 선택함을 확인했다. [실제 연결](artifacts/main-smoke.json), [코드·프로필·데이터 결속](artifacts/main-completion.json).

## 반영한 변경

- 질문에 직접 필요한 조문부터 읽고 필요한 정의·위임·예외로 확장하도록 안내한다. 구조와 본문 검색은 계속 모델이 선택한다.
- 구조 검색의 필터는 문서 대상으로 제한하고 일반 검색식과 섞이지 않게 한다. 기존의 복구 가능한 오류 분류는 유지한다.
- 외부 전송 스키마의 반복 구조를 정확한 참조로 공유한다. 모델 입력의 중복 원문과 불필요한 무결성 해시를 줄이고 판단 단계에도 연결한다. 원문·선택 ID·좌표·서버 감사 기록과 검증은 유지한다.
- MAIN51의 정확한 부족 대상, 동일 실패 반복 차단, 일시적 도구 실패 대체 선택, 부분 읽기 재개, 요청 경계와 판단 내용 보존을 유지한다.

## 검증과 실제 반영

핵심59검사가 통과했다. 후보와 작업 코드의 전체330검사는315통과·기존15실패·신규회귀0이다. 필요한 변경만 선별 통합했고 작업·검증 후보·선택 릴리스의 서빙290파일 해시가 모두 같다. 원문 세대와 공개65문서 범위를 유지했다.

| 공개 질문 | MAIN51 결과 / 호출 / 초 | 반영 후보 결과 / 호출 / 초 |
|---|---:|---:|
| H01 환매금지형 만기 | 정상 / 4 / 112.0 | 정상 / 4 / 89.4 |
| H02 상호계산 결산 | 422 실패 / 5 / 51.7 | 정상 / 7 / 148.6 |
| H03 이행보증금 반환·준용 | 504 실패 / 7 / 530.2 | 정상 / 4 / 326.5 |

새 공개3문항의 원문 근거 응답은1/3→3/3, 전체 입력167632→143062(-14.7%), 호출16→15, 시간693.9→564.5초였다. **전체 비용에는 기존 실패2건이 포함된다. 양쪽 정상 완료한 H01만의 입력 절감은0.43%여서 일반적인 토큰 절감 효과로 주장하지 않는다.** 원문 근거 응답은 독립 법률 정답률이 아니다. 동결한 전체3문항 gate는 통과했다. [검증 설계·결과](README.md), [의미 대조](SEMANTIC_REVIEW.md), [원시 기록 복원](artifacts/run-001/raw-archive.json).

## 추가 압축 후보는 미반영

별도729에서 분기 선택지 문법 축소와 잘못된 ‘문서 없음’ 진단 수정을 구현하고68핵심검사·전체339검사의 신규회귀0을 확인했다. 그러나 새2문항730의 후보 H02는 Parasail의 공유 호출 제한429로503 종료했고, 양쪽 정상 완료한 H01의 입력도30306→29861(-1.47%)로 사전10% 목표에 미달했다. 이 후보는 승격하지 않았다. 검증 결과에 맞춰 완료된727/728의 동일 코드만 반영했으며, 기준을 완화하거나 후보를 섞지 않았다. [미반영 후보 결과](../ADR-0730-compact-choice-public-qualification/README.md).

이번 작업은 공개5질문을 기준·후보에 각1회씩, 총10요청으로 한정했다. 재실행·다른 provider fallback은 없다. Qwen3.8/Parasail FP8/reasoning none 정책을 유지했다. 초기726의 배선 회귀와 모든 실패 기록도 보존했다.

## 남은 과제와 적용 범위

정상 완료 질문의 실질적인 토큰 절감, 불필요한 추가 조문 선택, 조건과 의무의 표현 중복, 제목 부재 진단 후속 후보, 콜드 자원 준비 약23초, 전체 CM51 재평가가 남았다. 기존15검사 실패와 전역 실험 그래프8개 과거 오류를 통과 처리하지 않았고 새 그래프 오류는 없다. 작은 표본으로 통계적인 속도나 법률 정답률을 인증하지 않는다.

로컬 MAIN의 선택 포인터와 새 서비스 프로세스까지 확인했다. GENOS 현장 배포·Git main 병합·상주 로컬 서버 재시작은 수행하지 않았다. 전송 스키마 참조 공유는 외부 adapter에만 적용하고 GENOS adapter는 기존 형식을 유지한다.

## 원복

직전 MAIN51의 코드·원문·포인터와 이번 변경 파일 백업을 보존했다. 후속 변경이 없는지 검사한 뒤 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0728/rollback_working.py --confirm-working-rollback`으로 이번 작업 파일만 복원하고 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 선택을 복원한다. 후속 변경이 있으면 백업으로 덮어쓰지 않고 검토한다. 원복은 이번 작업에서 실행하지 않았다.
'''
(A/'MAIN_RESULT.md').write_text(text)
agents=R/'AGENTS.md';s=agents.read_text();s=s.replace('`source-recovery-20261012-r1`(포인터 generation 51)',f"`{p['release_id']}`(포인터 generation {p['generation']})");agents.write_text(s)
arch=R/'00_SYSTEM/ARCHITECTURE.md';s=arch.read_text();s=s.replace('2026-10-12 현재 로컬 RAG MAIN은 `source-recovery','2026-10-12 MAIN51 전환 당시 로컬 RAG MAIN은 `source-recovery',1)
intro=f"2026-10-12 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. 직접 원문 우선 안내·유효한 구조 필터 결속·외부 스키마 참조 공유·중복 원문 메타데이터 축소를 MAIN51 위에 통합했다. 공개3문항 근거 응답1→3, 전체 입력14.7% 감소지만 기준 실패2건을 포함하며 정상 완료 쌍의 절감은0.43%다. 핵심59검사·전체330검사 신규회귀0(기존15실패), 작업/검증/선택290파일과 실제 service.service binding을 확인했다. 별도 추가 압축729/730은 기준 미달·외부429로 미반영했다. 원문 세대는 유지하며 GENOS 현장은 별도다. [반영·한계·원복](../04_EXPERIMENTS/ADR/ADR-0728-navigation-input-public-qualification/MAIN_RESULT.md).\n\n"
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);arch.write_text(s)
back=R/'07_DOCS/BACKLOG.md';s=back.read_text();s+='\n## 2026-10-12 · MAIN52 구조 검색·탐색 입력 개선과 보류 후보\n\n- 로컬 MAIN52 반영: 유효한 구조 필터 결속, 직접 원문 우선, 외부 스키마 참조 공유·중복 원문 메타데이터 축소. 새 공개3문항 근거 응답1→3, 핵심59검사·새 회귀0·실제 서빙290파일 일치. 전체 입력−14.7%는 기준 실패2건을 포함하고 정상 완료 쌍 절감은0.43%다. [완료·원복](../04_EXPERIMENTS/ADR/ADR-0728-navigation-input-public-qualification/MAIN_RESULT.md).\n- 별도729의 선택지 문법 축소·제목 부재 진단 수정은 합성68검사를 통과했으나730에서 입력10% 목표 미달·Parasail429로 미승격했다. 새 ADR에서 provider 가용성과 실제 사용자 메시지의 반복 법령/참조 카드 비용을 구분해 확인한다. 스키마 문자 감소를 토큰 감소로 대체하지 않는다.\n- 후속: 정상 완료 비용, 불필요한 추가 읽기·조건/의무 표현 중복, cold 원문 준비 약23초의 세대별 검증 캐시 경로, 전체 CM51, 기존15테스트. 원문 해시·권한·상태 검증은 보존한다. GENOS 현장 검증은 별도다.\n';back.write_text(s)
index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text()
for number, slug, label in [
    (725,'source-recovery-public-qualification','구조 검색·재탐색·도구 복구 MAIN51'),
    (726,'lossless-navigation-input','스키마 참조·원문 입력 축소, 배선 회귀로 Rejected'),
    (727,'navigation-input-binding','배선·오류 호환 수정, 핵심59검사·새 회귀0'),
    (728,'navigation-input-public-qualification','공개3문항 검증·로컬 MAIN52, 근거 응답1→3'),
    (729,'compact-branch-choice-contract','추가 선택지 축소·제목 실패 진단 후보, 핵심68검사·미승격'),
    (730,'compact-choice-public-qualification','추가2문항, 비용 기준 미달·외부429로 Rejected')]:
    directory=f'ADR-{number:04}-{slug}'
    if directory not in s:s+=f'\n- [ADR-{number:04} {label}]({directory}/README.md)\n'
index.write_text(s)
print(json.dumps({'release_id':p['release_id'],'generation':p['generation'],'serving_files':290,'supported_public_responses':'3/3'},ensure_ascii=False))
