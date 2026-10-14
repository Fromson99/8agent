"""Write observed cutover evidence only after the actual default entry passes."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
smoke=read(A/'artifacts/main-smoke.json');assert smoke['status']=='passed'
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p==smoke['pointer']
m=read(R/p['manifest_path']);f=read(A/'artifacts/design/freeze.json');result=read(A/'artifacts/run-001/result.json')
assert result['strict_success'] and m['files']==f['serving_files']
for name,h in m['files'].items():assert sha(R/name)==sha(R/m['code_root']/name)==sha(R/f['code_root']/name)==h
install=read(A/'artifacts/working-install-receipt.json');tests=read(A/'artifacts/working-verification.json')
receipt={'status':'complete','environment':'WSL local MAIN','release_id':p['release_id'],'pointer_generation':p['generation'],
 'working_code':'/home/jin/8-AGENT','verified_candidate':f['code_root'],'selected_release_code':m['code_root'],
 'same_serving_file_count':len(m['files']),'reviewed_installed_files':len(install['files']),
 'execution_binding':smoke['execution_binding'],'native_entrypoint':smoke['entrypoint'],
 'new_contracts_passed':40,'working_tests':tests,'qualification':'ADR-0725-experiment-v1/integrated',
 'genos_deployed':False,'git_main_merged':False,'resident_server_restarted':False,
 'artifacts':{'qualification':'artifacts/run-001/result.json','integration':'artifacts/working-install-receipt.json','actual_service':'artifacts/main-smoke.json','reviewed_failures':'../ADR-0723-source-target-recovery-complete/SEMANTIC_REVIEW.md'}}
put(A/'artifacts/main-completion.json',receipt)
rows='| 질문 | 기존 호출 / 초 | 후보 호출 / 초 | 후보 원문 근거 |\n|---|---:|---:|---|\n'
base={x['case_id']:x for x in result['by_arm']['baseline']['cases']}
for x in result['by_arm']['integrated']['cases']:
 b=base[x['case_id']];rows+=f"| {x['case_id']} | {b['model_calls']} / {b['request_seconds']:.1f} | {x['model_calls']} / {x['request_seconds']:.1f} | {x['supported_response']} |\n"
report=f'''# 구조 검색·재탐색·도구 복구 MAIN 반영

2026-10-12 로컬 MAIN을 `{p['release_id']}`(포인터 generation **{p['generation']}**)로 전환했다. 실제 기본 `service.service`의 HEALTH와 RAG_SEARCH가 이 릴리스를 선택함을 확인했다. [실제 연결 영수증](artifacts/main-smoke.json), [완료 기록](artifacts/main-completion.json).

## 반영 기능

- 정확한 부족 대상은 허용된 문서·조문·원문 범위에 묶고 목록 밖 조문도 읽을 수 있다. 모호한 대상에는 문서 범위의 구조·본문 탐색 선택지를 제공한다.
- 현재 전달한 원문에 포함된 부분 읽기와 재열람을 줄이고, 현재 화면에 없는 저장 원문은 다시 제시할 수 있다. 같은 부족의 무진행 재진입과 동등한 실패 검색 반복을 제한한다.
- 알려진 일시적 도구 실패는 미해결 결과와 선택 가능한 다른 경로로 연결한다. 실패를 원문 부재로 간주하지 않는다. 권한·해시·알 수 없는 코드 오류와 모델 전송 결과 미확인은 자동 재시도하지 않는다.
- 부분 묶음 읽기와 승인 행동을 재개할 때 완료 원문·대상·읽기 예산을 보존한다. 실패 이후 상태 버전을 갱신한다. 새 사용자 요청과 같은 요청의 복귀 이력을 구분한다.
- 이전 후보의 요청 원문 인용 검증, 중첩 조건·예외·의무 보존, 하나의 검증된 판단을 답변과 표시가 함께 사용하는 경로를 통합했다.

## 검증과 코드 연결

신규40계약 모두 통과했다. 후보와 실제 작업 코드의 전체311검사는296통과·기존 동일15실패이며 신규 회귀0이다. 실패를 통과로 계산하지 않았다. {len(install['files'])}개 필요한 파일만 선별 통합하고 무관한 작업 내용을 보존했다. 작업 코드·최종 검증 후보·선택 릴리스의 서빙 **{len(m['files'])}파일 해시가 전부 같다**. 원문 세대·공개65문서 범위는 그대로다. 구조/본문 도구는 모델이 선택한다.

{rows}
공개 신규2문항4요청은 기준과 후보 모두 동일 모델(Qwen3.8/Parasail FP8/reasoning none, fallback 없음), 데이터와 예산을 사용했다. 원문 인용·권한·내용 보존·실제 코드 binding을 검증했다. 원문 근거 응답은 기준1/2·후보2/2였다. 기준 H02는 판단 형식 오류로422 종료했고 후보는 정상 완료했다. 총12회씩 호출했으며 입력 토큰은 기준99,973·후보173,656으로 약73.7% 증가했다. 추가 원문 선택 때문에 입력 비용 최적화는 남아 있다. [동결 설계와 결과](README.md), [의미 검토](SEMANTIC_REVIEW.md), [무손실 원시 기록](artifacts/run-001/raw-archive.json).

## 남은 한계

알려진 CM019·050 비교에서는 법령 선택 실패와 참조 조문의 세부 설명 누락이 남았다. CM051 기존 요청은 경계 결함 발견 후 중단했고 후보는 미실행했다. [실패와 중단 기록](../ADR-0723-source-target-recovery-complete/SEMANTIC_REVIEW.md). 고유 질문5개를 제한적으로 사용했으며 전체 CM51·법률 의미 정답률·통계적인 속도/안정성을 인증하지 않는다. 기존15검사 실패와 전역 실험 그래프8개 과거 오류도 보존했다.

GENOS 현장 배포·Git main 병합·상주 로컬 서버 재시작은 수행하지 않았다. 새 로컬 기본 프로세스가 선택하는 MAIN까지 확인했다.

## 원복

이전 MAIN50의 불변 코드·manifest·포인터와 작업 파일 백업을 보존했다. 후속 변경이 없는지 먼저 검사한 뒤, 작업 코드 복원이 필요하면 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0725/rollback_working.py --confirm-working-rollback`을 실행한다. 이어 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 릴리스 선택을 복원한다. 후속 변경이 있으면 이 작업의 백업으로 덮어쓰지 않고 별도 검토한다. 원복은 이번 작업에서 실행하지 않았다.
'''
(A/'MAIN_RESULT.md').write_text(report)
agents=R/'AGENTS.md';s=agents.read_text();s=s.replace('`compact-input-20261009-r1`(포인터 generation 50)',f"`{p['release_id']}`(포인터 generation {p['generation']})");agents.write_text(s)
arch=R/'00_SYSTEM/ARCHITECTURE.md';s=arch.read_text();line=f"2026-10-12 현재 로컬 RAG MAIN은 `{p['release_id']}`(포인터 generation **{p['generation']}**)이다. 정확한 부족 대상·현재 원문 재사용·일시적 도구 실패 복구·부분 묶음 읽기 재개·요청 경계와 판단 내용 보존을 기존 MAIN50에 통합했다. 신규40계약과 작업/후보311검사 대비 신규 회귀0(기존15실패 유지), 공개 신규2문항 비교와 실제 service.service 선택, 서빙289파일 일치를 확인했다. 구조/fulltext는 선택형이며 원문 세대는 유지한다. 의미적 검색 판단·전체 CM51·GENOS 현장은 별도다. [반영·검증·한계·원복](../04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification/MAIN_RESULT.md).\n\n"
s=s.replace('2026-10-09 현재 로컬 RAG MAIN은','2026-10-09 전환 당시 로컬 RAG MAIN은',1);pos=s.index('\n')+1;s=s[:pos]+'\n'+line+s[pos:].lstrip('\n');arch.write_text(s)
backlog=R/'07_DOCS/BACKLOG.md';s=backlog.read_text();s+='\n\n## 2026-10-12 · 구조 검색·중복·실패 복구 반영과 남은 의미 과제\n\n'+f"- 로컬 MAIN{p['generation']} 반영 완료: 정확한 부족 대상, 현재 원문 재사용, 동일 실패 반복 차단, 일시적 실패 대체 선택, 부분 묶음 읽기와 요청 상태 복구. 신규40계약·공개 신규2문항·실제 선택 코드 검증. [완료와 원복](../04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification/MAIN_RESULT.md).\n"+'- 후속: CM019의 법령 선택, CM050의 참조 조문 상세 조건 설명, 불필요한 추가 조문 선택·입력 토큰 축소, 전체 CM51 재평가, 기존15개 테스트 기대값·모의 흐름 정비. 이전 실패·원시 기록은 보존하고 신규 실험은 별도 ADR에서 동결한다. GENOS 현장 검증은 별도다.\n';backlog.write_text(s)
print('Observed local MAIN completion recorded; source qualification artifacts unchanged')
