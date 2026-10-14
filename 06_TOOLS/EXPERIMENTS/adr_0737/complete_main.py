"""Write completion evidence only after actual selected-service verification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0737-focused-modality-public-qualification'
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
    'source': 'ADR-0737-experiment-v1/integrated', 'run': 'run-001',
    'pointer': p, 'pointer_sha256': sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'working_root': str(R), 'verified_code_root': f['code_root'], 'selected_code_root': m['code_root'],
    'all_serving_files_identical': len(f['serving_files']),
    'file_catalogue_sha256': hashlib.sha256(json.dumps(f['serving_files'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
    'profile_sha256': smoke['execution_binding']['profile_sha256'],
    'data_manifest_sha256': m['data_manifest_sha256'],
    'navigation_policy': smoke['actual_navigation_policy'],
    'policy_code_sha256': {name: sha(R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent'/name)
                           for name in ('law_navigation.py','gateway.py','navigation_input.py','completion_v6.py','investigation_scope.py','structure_query.py')},
    'actual_execution_binding': smoke['execution_binding'], 'working_tests': working,
    'genos_deployed': False, 'git_main_merged': False, 'resident_server_restarted': False,
    'previous_release_preserved': base['pointer'],
}
(A/'artifacts/main-completion.json').write_text(json.dumps(completion,ensure_ascii=False,indent=2)+'\n')
perf = result['performance_comparison']; totals = perf['totals']
b, c = totals['baseline'], totals['integrated']
reduction = 100*(1-c['input']/b['input'])
table = '| 질문 | MAIN52 호출 / 입력 토큰 / 초 | 후보 호출 / 입력 토큰 / 초 |\n|---|---:|---:|\n'
for cr in result['by_arm']['integrated']['cases']:
    br = next(x for x in result['by_arm']['baseline']['cases'] if x['case_id']==cr['case_id'])
    table += f"| {cr['case_id']} | {br['model_calls']} / {br['usage']['input_tokens']:,} / {br['request_seconds']:.1f} | {cr['model_calls']} / {cr['usage']['input_tokens']:,} / {cr['request_seconds']:.1f} |\n"
text = f"""# 요청1~4 로컬 MAIN 반영

2026-10-12 `{p['release_id']}`(generation **{p['generation']}**)를 선택하고 실제 새 `service.service`의 HEALTH/RAG_SEARCH 연결을 확인했다. [실행 결속](artifacts/main-completion.json), [서비스 확인](artifacts/main-smoke.json).

## 반영한 변경

1. 실제 탐색 입력의 긴 ID를 호출별 가역 문자열로 바꾸고 반복 카드 필드·감사용 해시를 모델 입력에서 줄였다. 원문과 전체 선택지는 복원 검증하며 서버에는 원래 ID·해시를 보존한다.
2. 추가 탐색의 모든 선택 대상에 원래 사용자 요구 인용과 아직 부족한 내용을 연결했다. 의존 탐색은 실제 전달된 원문의 인용을 요구한다. 기존 중복 탐색 차단·일시적 도구 실패 복구·부분 읽기 재개를 유지한다.
3. 문서가 결속됐으나 제목만 없는 경우를 UNRESOLVED_HEADING으로 보고하고 문서 부재·권한 밖을 구분한다.
4. completion-v6는 정확한 근거 인용을 바탕으로 의무·허용·금지를 구분하고 명시 양태의 뒤바뀜을 거부한다. 불확실한 의미는 확정하지 않는다. 동일 문구는 중복 출력하지 않으며 조건 논리와 양태 표시를 보존한다. 기존 v5 저장 내용은 기존 방식으로 검증한다.

## 검증

핵심85검사 통과. 후보와 작업 코드 전체356검사 중341통과·기존15실패·신규회귀0. 작업 코드·검증 후보·선택 릴리스의 서빙293파일 해시가 일치한다. 원문 세대와 공개65문서 범위는 같다.

{table}

공개3질문6요청을 비교했다. 후보 원문 근거 응답은 {result['by_arm']['integrated']['supported']}/3. 양쪽 정상 완료한 {len(perf['case_ids'])}쌍의 입력 토큰은 {b['input']:,}→{c['input']:,}(**{reduction:.1f}% 감소**), 호출 {b['calls']}→{c['calls']}, 요청시간 합계 {b['seconds']:.1f}→{c['seconds']:.1f}초. 실패한 기준 비용은 효율 기준에 합산하지 않는다. Qwen3.8/Parasail FP8/reasoning none/fallback 없음. [의미 검토](SEMANTIC_REVIEW.md), [설계와 결과](README.md).

## 적용 범위

5번 캐시는 사용자 지시로 수정하지 않았다. 모델의 의미 판단·의역 중복·전체CM 품질은 완전 해결 또는 인증한 것으로 보지 않는다. 과거15개 테스트 실패와 실험 그래프8개 오류를 별도 보존한다. 로컬 MAIN 반영과 새 서비스 진입점 확인까지 완료했으며 GENOS 배포·Git main 병합·상주 로컬 서버 재시작은 수행하지 않았다.

## 원복

직전 MAIN52의 포인터·코드·원문 세대와 이번 변경 파일별 백업을 보존했다. 후속 변경을 확인하고 `06_TOOLS/EXPERIMENTS/adr_0737/rollback_working.py --confirm-working-rollback`으로 작업 코드 변경만 원복한 다음 `06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 릴리스를 선택한다. WSL에서는 저장소 `.venv/bin/python`으로 실행한다. 원복 시 새v6 세션을 구v5 코드로 강제 재개하지 않는다. 새 요청은 선택된 프로필의 실행 결속을 따른다. 원복은 실행하지 않았다.
"""
(A/'MAIN_RESULT.md').write_text(text)
agents=R/'AGENTS.md';s=agents.read_text();s=s.replace('`compact-navigation-20261012-r1`(포인터 generation 52)',f"`{p['release_id']}`(포인터 generation {p['generation']})");agents.write_text(s)
arch=R/'00_SYSTEM/ARCHITECTURE.md';s=arch.read_text();s=s.replace('2026-10-12 현재 로컬 RAG MAIN은 `compact-navigation','2026-10-12 MAIN52 전환 당시 로컬 RAG MAIN은 `compact-navigation',1)
intro=f"2026-10-12 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. 실제 입력의 가역 ID·카드 압축, 사용자 요구에 연결된 추가 탐색, 제목 부재 진단, 원문 기반 의무·허용·금지와 중복 출력 교정을 MAIN52 위에 통합했다. 공개3문항 정상 완료 쌍 입력 {reduction:.1f}% 감소, 핵심85검사·전체356검사 신규회귀0(기존15실패), 작업/검증/선택293파일과 실제 service.service 결속을 확인했다. 원문 세대와 캐시는 유지하며 GENOS 현장 배포는 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0737-focused-modality-public-qualification/MAIN_RESULT.md).\n\n"
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);arch.write_text(s)
back=R/'07_DOCS/BACKLOG.md';s=back.read_text();s+=f"\n## 2026-10-12 · 요청1~4 MAIN{p['generation']} 반영\n\n- 실제 입력 축소·요구에 연결된 추가 탐색·제목 부재 진단·원문 양태 및 완전 동일 문구의 중복 출력 교정. 핵심85검사와 새 회귀0, 서빙293파일 일치. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0737-focused-modality-public-qualification/MAIN_RESULT.md).\n- 캐시는 사용자 지시로 이번 작업에서 제외했다. 남은 평가 범위는 모델 의미 판단·의역 중복·전체CM 및 GENOS 현장 검증이며, 기존15개 테스트와 그래프8개 과거 오류는 별도다.\n";back.write_text(s)
print(json.dumps({'release_id':p['release_id'],'generation':p['generation'],'serving_files':len(f['serving_files']),'successful_pair_input_reduction_percent':reduction},ensure_ascii=False))
