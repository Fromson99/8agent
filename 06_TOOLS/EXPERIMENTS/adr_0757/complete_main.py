"""Write completion evidence only after actual selected-service verification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0757-dependency-recovery-qualification'
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
    'source': 'ADR-0757-experiment-v1/integrated', 'run': 'run-001',
    'pointer': p, 'pointer_sha256': sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'working_root': str(R), 'verified_code_root': f['code_root'], 'selected_code_root': m['code_root'],
    'all_serving_files_identical': len(f['serving_files']),
    'file_catalogue_sha256': hashlib.sha256(json.dumps(f['serving_files'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
    'profile_sha256': smoke['execution_binding']['profile_sha256'],
    'data_manifest_sha256': m['data_manifest_sha256'],
    'navigation_policy': smoke['actual_navigation_policy'],
    'policy_code_sha256': {name: sha(R/m['code_root']/'02_BACKEND/semantic_runtime/legal_agent'/name)
                           for name in ('request_entry.py','law_navigation.py','gateway.py','navigation_input.py','completion_v6.py','completion_v7.py','completion_v8.py','investigation_scope.py','structure_query.py')},
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
    br = next((x for x in result['by_arm']['baseline']['cases'] if x['case_id']==cr['case_id']),None)
    if br is None:
        table += f"| {cr['case_id']} | 미실행(후보 전용 기존 실패 회귀) | {cr['model_calls']} / {cr['usage']['input_tokens']:,} / {cr['request_seconds']:.1f} |\n"
        continue
    table += f"| {cr['case_id']} | {br['model_calls']} / {br['usage']['input_tokens']:,} / {br['request_seconds']:.1f} | {cr['model_calls']} / {cr['usage']['input_tokens']:,} / {cr['request_seconds']:.1f} |\n"
text = f"""# 요청1~4 로컬 MAIN 반영

2026-10-13 `{p['release_id']}`(generation **{p['generation']}**)를 선택하고 실제 새 `service.service`의 HEALTH/RAG_SEARCH 연결을 확인했다. [실행 결속](artifacts/main-completion.json), [서비스 확인](artifacts/main-smoke.json).

## 반영한 변경

1. 실제 탐색 입력의 긴 ID를 호출별 가역 문자열로 바꾸고 반복 카드 필드·감사용 해시를 모델 입력에서 줄였다. 원문과 전체 선택지는 복원 검증하며 서버에는 원래 ID·해시를 보존한다.
2. 추가 탐색의 모든 선택 대상에 원래 사용자 요구 인용과 아직 부족한 내용을 연결했다. 직접 읽기에서 쓰이지 않는 인용 메모가 읽기를 막지 않으며, 그 메모를 답변 근거나 확장 권한으로 인정하지 않는다. 의존 탐색은 실제 전달된 원문 ID를 선택할 수 있으며, 원문 없는 ID나 미열람 ID는 거절한다. 과거의 정확한 인용 방식도 유지한다. 처음 검색할 때 제외된 조문번호보다 실제 요청 제목을 우선하도록 안내한다. 새 검색이 완료됐을 때 실제 신규 문서·원문 등 내용이 추가된 경우에만 진전 없음 횟수를 갱신한다. 같은 검색 결과·검색식 변경만으로는 초기화하지 않는다. 사용자가 제외한 세부 내용의 미조사를 부족한 자료로 만들지 않도록 지침을 명시하며 실제 요청의 필요한 자료 부족은 계속 검증한다. 기존 도구 복구·부분 읽기 재개와 예산을 보존한다. 근거·쟁점·대상 목록은 제시된 서로 다른 ID 수 안에서만 선택하고 중복을 거부해 반복 ID 출력으로 예산을 소진하는 경로를 제한했다.
3. 문서가 결속됐으나 제목만 없는 경우를 UNRESOLVED_HEADING으로 보고하고 문서 부재·권한 밖을 구분한다.
4. completion-v8는 모델이 읽은 원문 ID를 선택하면 서버가 원문을 그대로 붙여 인용 재작성 오류를 없앤다. 원문의 명시 양태와 다른 표지만 의무·허용·금지에 맞춰 교정하고 원래 판단을 기록한다. 설명 자체가 명시 원문을 뒤집으면 거절한다. 끝말이 불명확한 경우의 맥락 판단은 모델 판단이며 정답 인증이 아니다. 구조화 규정 답변은 결론·세부 설명·규정의 세 벌 작성을 없애고 한 내용으로 작성·표시한다. 같은 원문·양태·효과·적용 맥락을 그대로 반복하면 병합하도록 요청한다. 서로 다른 효과나 조건은 허용하며, 자료 부족 재탐색을 형식 선호로 차단하지 않는다. 조건 논리와 양태를 보존하며 불필요한 ALL/ANY 단일·동종 중첩 표시는 논리적 의미를 보존해 줄이며, 원래 조건·근거는 보존한다. 기존 v5/v6와 이전 v7 표시도 계속 검증한다.

## 검증

핵심153검사 통과. 후보와 작업 코드 전체424검사 중409통과·기존15실패·신규회귀0. 작업 코드·검증 후보·선택 릴리스의 서빙295파일 해시가 일치한다. 원문 세대와 공개65문서 범위는 같다.

{table}

새 공개1질문은 양쪽 비교, 기존 실패1질문은 후보 회귀로 총3요청을 실행했다. 후보 원문 근거 응답은 {result['by_arm']['integrated']['supported']}/2. 양쪽 정상 완료한 {len(perf['case_ids'])}쌍의 입력 토큰은 {b['input']:,}→{c['input']:,}(**{reduction:.1f}% 감소**), 호출 {b['calls']}→{c['calls']}, 요청시간 합계 {b['seconds']:.1f}→{c['seconds']:.1f}초. 실패한 기준 비용은 효율 기준에 합산하지 않는다. Qwen3.8/Parasail FP8/reasoning none/fallback 없음. [의미 검토](SEMANTIC_REVIEW.md), [설계와 결과](README.md).

## 적용 범위

5번 캐시는 사용자 지시로 수정하지 않았다. 모델이 조건과 효과를 섞거나 별도 요약으로 의미를 반복하는 오류를 포함해, 의미 판단·중복·전체CM 품질은 완전 해결 또는 인증한 것으로 보지 않는다. 과거15개 테스트 실패와 실험 그래프8개 오류를 별도 보존한다. 로컬 MAIN 반영과 새 서비스 진입점 확인까지 완료했으며 GENOS 배포·Git main 병합·상주 로컬 서버 재시작은 수행하지 않았다.

## 원복

직전 MAIN52의 포인터·코드·원문 세대와 이번 변경 파일별 백업을 보존했다. 후속 변경을 확인하고 `06_TOOLS/EXPERIMENTS/adr_0757/rollback_working.py --confirm-working-rollback`으로 작업 코드 변경만 원복한 다음 `06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 릴리스를 선택한다. WSL에서는 저장소 `.venv/bin/python`으로 실행한다. 원복 시 새v8 세션을 구v5 코드로 강제 재개하지 않는다. 새 요청은 선택된 프로필의 실행 결속을 따른다. 원복은 실행하지 않았다.
"""
campaign=[]
for number in (737,741,744,747,750,753,755,757):
    previous=next((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04}-*'))
    res=read(previous/'artifacts/run-001/result.json');meta=read(previous/'실험/manifest.json')
    campaign.append({'adr_id':meta['adr_id'],'result':str((previous/'artifacts/run-001/result.json').relative_to(R)),
        'result_sha256':sha(previous/'artifacts/run-001/result.json'),'questions':len(meta['questions']),
        'requests':sum(len(a['cases']) for a in res['by_arm'].values()),
        'physical_model_calls':sum(a['calls'] for a in res['by_arm'].values()),
        'reported_input_tokens':sum(a['input_tokens'] for a in res['by_arm'].values()),
        'reported_cost_usd':sum(u.get('cost_usd',0) or 0 for u in meta['results']['usage'].values()),
        'qualified':res['strict_success']})
(A/'artifacts/campaign-accounting.json').write_text(json.dumps({'runs':campaign,'failed_runs_preserved':True,
    'missing_usage_not_imputed':True},ensure_ascii=False,indent=2)+'\n')
text+='\n## 시행착오를 포함한 전체 기록\n\n이번 수정 과정의 공개 실험은 총 '+str(sum(x['questions'] for x in campaign))+'질문사례(17개 고유 질문, 기존 실패 회귀1회 포함)·'+str(sum(x['requests'] for x in campaign))+'요청이다. 이전737·741·744·747·750·753·755의 실패를 보존하고, 최종757의 통과 결과만 해당 검증 코드의 승격 근거로 사용했다. 전체 물리 모델 호출 '+str(sum(x['physical_model_calls'] for x in campaign))+'회, 제공자가 보고한 비용 합계 $'+format(sum(x['reported_cost_usd'] for x in campaign),'.4f')+'다. 미보고 사용량은 추정해 채우지 않았다. [집계와 원본 위치](artifacts/campaign-accounting.json).\n'
(A/'MAIN_RESULT.md').write_text(text)
agents=R/'AGENTS.md';s=agents.read_text();s=s.replace('`compact-navigation-20261012-r1`(포인터 generation 52)',f"`{p['release_id']}`(포인터 generation {p['generation']})");agents.write_text(s)
arch=R/'00_SYSTEM/ARCHITECTURE.md';s=arch.read_text();s=s.replace('2026-10-12 현재 로컬 RAG MAIN은 `compact-navigation','2026-10-12 MAIN52 전환 당시 로컬 RAG MAIN은 `compact-navigation',1)
intro=f"2026-10-13 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. 실제 입력의 가역 ID·카드 압축, 사용자 요구에 연결된 추가 탐색, 제목 부재 진단, 완료된 검색의 실제 진전 반영·원문 양태와 단일 규정 출력을 MAIN52 위에 통합했다. 새 공개1문항 정상 완료 쌍 입력 {reduction:.1f}% 감소, 핵심153검사·전체424검사 신규회귀0(기존15실패), 작업/검증/선택295파일과 실제 service.service 결속을 확인했다. 원문 세대와 캐시는 유지하며 GENOS 현장 배포는 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0757-dependency-recovery-qualification/MAIN_RESULT.md).\n\n"
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);arch.write_text(s)
back=R/'07_DOCS/BACKLOG.md';s=back.read_text();s+=f"\n## 2026-10-13 · 요청1~4 MAIN{p['generation']} 반영\n\n- 실제 입력 축소·요구에 연결된 추가 탐색·제목 부재 진단·원문 양태 및 단일 규정 출력과 검색 재개 교정. 핵심153검사와 새 회귀0, 서빙295파일 일치. [완료·한계·원복](../04_EXPERIMENTS/ADR/ADR-0757-dependency-recovery-qualification/MAIN_RESULT.md).\n- 캐시는 사용자 지시로 이번 작업에서 제외했다. 남은 평가 범위는 모델 의미 판단·의역 중복·전체CM 및 GENOS 현장 검증이며, 기존15개 테스트와 그래프8개 과거 오류는 별도다.\n";back.write_text(s)
print(json.dumps({'release_id':p['release_id'],'generation':p['generation'],'serving_files':len(f['serving_files']),'successful_pair_input_reduction_percent':reduction},ensure_ascii=False))
