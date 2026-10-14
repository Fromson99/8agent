"""Write completion evidence only after actual selected-service verification."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0730-compact-choice-public-qualification'
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
    'source': 'ADR-0730-experiment-v1/integrated', 'run': 'run-001',
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
perf = result['performance_comparison']; totals = perf['totals']
b, c = totals['baseline'], totals['integrated']
reduction = 100*(1-c['input']/b['input'])
table = '| 질문 | MAIN51 호출 / 입력 토큰 / 초 | 후보 호출 / 입력 토큰 / 초 |\n|---|---:|---:|\n'
for cr in result['by_arm']['integrated']['cases']:
    br = next(x for x in result['by_arm']['baseline']['cases'] if x['case_id']==cr['case_id'])
    table += f"| {cr['case_id']} | {br['model_calls']} / {br['usage']['input_tokens']:,} / {br['request_seconds']:.1f} | {cr['model_calls']} / {cr['usage']['input_tokens']:,} / {cr['request_seconds']:.1f} |\n"
text = f'''# 탐색 입력 최적화와 구조 검색 진단 MAIN 반영

2026-10-12 로컬 MAIN을 `{p['release_id']}`(포인터 generation **{p['generation']}**)로 전환했다. 실제 새 기본 `service.service`에서 HEALTH와 RAG_SEARCH가 이 릴리스를 선택했다. [서비스 연결](artifacts/main-smoke.json), [코드·프로필·데이터 결속](artifacts/main-completion.json).

## 반영 기능

- 질문에 직접 필요한 조문부터 읽고 정의·위임·예외가 필요한 경우 확장하도록 안내한다. 구조/본문 검색은 계속 모델이 선택한다.
- 구조 필터는 문서 대상과 빈 검색식에만 결속한다. 문서를 찾았지만 제목이 없는 경우를 ‘문서 없음’으로 잘못 보고하지 않는다.
- 외부 모델의 반복 분기 선택지 문법을 축소하고 공통 스키마를 공유한다. 전송 문법은 보수적 상위집합이며 서버는 원래의 분기·상태·근거 상관 제약으로 검증한다. 원래 검증을 통과하기 전에는 행동이나 채택을 승인하지 않는다.
- 모델 입력의 중복 원문과 불필요한 무결성 해시를 줄이고 원문·좌표·선택 ID·서버 감사 기록은 보존한다. 판단 단계에도 같은 입력 투영을 연결한다.
- MAIN51의 정확한 부족 대상, 중복 탐색 제한, 알려진 일시적 도구 실패 복구, 부분 읽기 재개, 요청 경계 및 판단 내용 보존은 유지했다.

## 검증과 관찰 결과

핵심68검사가 통과했다. 후보와 작업 코드의 전체339검사는324통과·기존15실패·신규회귀0이다. 필요한 변경만 선별 통합했고 작업·검증 후보·선택 릴리스의 서빙290파일 해시가 전부 같다. 원문 세대와 공개65문서 범위는 같다.

{table}

새 공개2문항4요청의 후보 원문 근거 응답은 {result['by_arm']['integrated']['supported']}/2다. 양쪽 정상 완료한 {len(perf['case_ids'])}쌍의 입력은 {b['input']:,}→{c['input']:,}토큰(**{reduction:.1f}% 감소**), 호출은 {b['calls']}→{c['calls']}, 요청시간 합계는 {b['seconds']:.1f}→{c['seconds']:.1f}초다. 사전에 동결한 정상 완료 쌍만의 비용 기준을 통과했다. 실패한 기준 비용은 절감 근거에 합산하지 않았다. 모델은 Qwen3.8/Parasail FP8/reasoning none/fallback 없음이다. 원문 근거 응답은 독립 법률 정답률이 아니다. [의미 검토](SEMANTIC_REVIEW.md), [검증 설계·전체 결과](README.md).

선행728의 별도3문항은 근거 응답1→3, 전체 입력167632→143062였으나 기준 실패2건을 포함한다. 유일한 정상 완료 쌍의 절감은0.43%여서 스키마 참조 공유만으로 토큰이 크게 줄었다고 판단하지 않았다. 729에서 별도 후보를 만들고730의 신규2문항으로 다시 검증했다. 이번 작업의 외부 검증은 합계5개 공개 질문, 반복 실행 없이10요청이다. 최초726의 배선 회귀도 실패 기록으로 보존했다.

## 적용 범위와 남은 과제

두 문항은 속도·정답률의 통계적 인증이 아니다. 질문 범위 판단, 조건과 의무의 중복 표현, 전체 CM51 재평가, 콜드 자원 준비 약23초, 기존15검사·실험 그래프8개 과거 오류는 후속 과제다. 새 그래프 오류는 없다. GENOS의 외부 전송 스키마 최적화 호환성은 검증하지 않았으므로 GENOS 어댑터는 기존 형식을 유지한다.

로컬 MAIN 선택과 실제 새 서비스 프로세스까지 확인했다. GENOS 현장 배포·Git main 병합·상주 로컬 서버 재시작은 수행하지 않았다.

## 원복

직전 MAIN51의 코드·데이터·포인터와 이 작업의 변경 파일 백업을 보존했다. 후속 변경을 확인한 뒤 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0730/rollback_working.py --confirm-working-rollback`으로 이번 작업의 파일만 복원하고, `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 선택을 복원한다. 후속 변경이 있으면 백업으로 덮어쓰지 않고 검토한다. 원복은 이번 작업에서 실행하지 않았다.
'''
(A/'MAIN_RESULT.md').write_text(text)
agents=R/'AGENTS.md';s=agents.read_text();s=s.replace('`source-recovery-20261012-r1`(포인터 generation 51)',f"`{p['release_id']}`(포인터 generation {p['generation']})");agents.write_text(s)
arch=R/'00_SYSTEM/ARCHITECTURE.md';s=arch.read_text();s=s.replace('2026-10-12 현재 로컬 RAG MAIN은 `source-recovery','2026-10-12 MAIN51 전환 당시 로컬 RAG MAIN은 `source-recovery',1)
intro=f"2026-10-12 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. 필요한 원문 우선 안내, 유효한 구조 필터 결속, 제목 부재 진단 수정, 외부 선택지 문법·중복 원문 메타데이터 축소를 MAIN51 위에 통합했다. 신규 공개2문항의 양쪽 정상 완료 쌍 입력 {reduction:.1f}% 감소, 핵심68검사·전체339검사 신규회귀0(기존15실패), 작업/검증/선택290파일과 실제 service.service binding을 확인했다. 원문 세대는 유지하며 GENOS 현장 배포는 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0730-compact-choice-public-qualification/MAIN_RESULT.md).\n\n"
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);arch.write_text(s)
back=R/'07_DOCS/BACKLOG.md';s=back.read_text();s+=f"\n## 2026-10-12 · MAIN52 입력 최적화와 남은 병목\n\n- 로컬 MAIN52 반영: 구조 필터 대상 제약·제목 실패 진단·직접 원문 우선·외부 반복 선택지 문법 및 중복 메타데이터 축소. 공개 새2문항 정상 완료 쌍 입력 {reduction:.1f}% 감소, 핵심68검사·새 회귀0·실제 서빙290파일 일치. [완료·원복](../04_EXPERIMENTS/ADR/ADR-0730-compact-choice-public-qualification/MAIN_RESULT.md).\n- 후속: 조건/의무 표현 중복과 질문 범위 판단, cold 자원 준비 약23초의 세대별 검증 캐시 사용 경로, 전체 CM51 재평가, 기존15테스트 정비. 원문 해시·권한·상태 검증을 건너뛰어 속도를 높이지 않는다. GENOS 전송 문법 호환성과 현장 실행은 별도다.\n";back.write_text(s)
print(json.dumps({'release_id':p['release_id'],'generation':p['generation'],'serving_files':290,'successful_pair_input_reduction_percent':reduction},ensure_ascii=False))
