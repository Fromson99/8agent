"""Record the applied pointer, exact installed package, and actual local service selection."""
from pathlib import Path
import json,hashlib,datetime,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);smoke=read(A/'artifacts/main-smoke.json');base=read(A/'artifacts/design/baseline.json')
assert pointer['generation']==base['pointer']['generation']+1 and pointer['release_id']=='grounded-entry-20261009-r1'
assert smoke['status']=='passed' and smoke['pointer']==pointer
manifest=R/pointer['manifest_path'];release=read(manifest);rebase=read(A/'artifacts/design/release-rebase.json');assert release['files']==rebase['staged_files']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
auth=read(A/'artifacts/main-authorization.json')
for ref in auth['qualification'].values():
 if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
tests=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(tests)==271 and all(t.find('failure') is None and t.find('error') is None for t in tests)
receipts=[]
for candidate in (R/'01_DATA/ACTIVE/local/receipts').glob('*.json'):
 v=read(candidate)
 if v.get('action')=='VALIDATED_ADR_PROMOTION' and v.get('after')==pointer:receipts.append((candidate,v))
assert len(receipts)==1 and receipts[0][1]['before']==base['pointer']
result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,'qualification':auth['qualification'],'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),'working_tests':bound(A/'artifacts/working-required.xml'),'working_passed':len(tests),'service_verification':bound(A/'artifacts/main-smoke.json'),'execution_binding':smoke['execution_binding'],'exact_working_validated_release_inventory':True,'serving_file_count':len(release['files']),'apply_receipt':bound(receipts[0][0]),'rollback_files':[bound(q) for q in (manifest.parent/'rollback').iterdir() if q.is_file()],'git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,'new_external_model_calls':sum(v['calls'] for v in result['by_arm'].values()),'semantic_quality_certified':False}
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
table='| 질문 | MAIN48 호출 / 시간 | MAIN49 후보 호출 / 시간 |\n|---|---:|---:|\n'
for b,c in zip(result['by_arm']['baseline']['cases'],result['by_arm']['integrated']['cases']):
 assert b['case_id']==c['case_id']
 table+=f"| {b['case_id']} | {b['physical_model_attempts']}회 / {b['request_seconds']:.1f}초 | {c['physical_model_attempts']}회 / {c['request_seconds']:.1f}초 |\n"
(A/'MAIN_RESULT.md').write_text('''# 제목 힌트·통합 앞단·선택형 검색 — 로컬 MAIN49

`grounded-entry-20261009-r1`을 로컬 RAG MAIN generation49로 선택했다. 전체 MAIN 중 서빙 변경이며 용어집·구조화·원문 세대는 유지했다. GENOS 현장 반입·배포와 Git main 병합은 별도다.

## 반영 기능

- 새 질문의 요청 분류·세션 해석·명령 확인·질문 이해를 기존 한 호출로 통합한다. 기존 사건·정정·재개는 기존 경로를 유지한다.
- 실제 법령 제목·등록 별칭·부분 일치·약칭 유사 후보를 최대6개까지 원문 일치 위치와 함께 제공한다. 별도 LLM 호출은 없고 권한·근거 채택으로 취급하지 않는다.
- 법령/조문 위치의 단서에는 구조 검색, 세부 문구에는 fulltext를 선택할 수 있다. 구조 검색을 반드시 먼저 거치도록 강제하지 않는다.
- 이전의 중복 검색 검사·승인 판단·묶음 읽기·접힘 호출 시간·최대5단계 진행·로그/표시 분리를 유지한다.
- 기본 PIPELINE의 v6 profile hash를 새 profile과 결속해 직접 설정 주입 없는 기본 기동도 검증했다.

## 실제 검증

'''+table+'''
원문 근거 포함 응답은 양쪽3/3이다. 모델 호출22→12회지만 입력 토큰108,339→144,356, 요청 시간 합계169.544→185.976초로 증가했다. 상세 값은 최종 run-001/result.json을 따른다. 이 수치는 공개3문항을 한 번씩 실행한 관측이며 일반 정확도·일정한 응답 속도를 인증하지 않는다. 실제 전송은 실패/재시도를 포함하고 원문 확보·모델 전달·채택을 구분했다.

후보와 통합 작업 코드 각각271계약 통과. 변경41파일만 현재 해시를 검사하고 백업 후 통합했다. 작업·검증·릴리스287파일 해시가 모두 일치한다. 새 WSL 프로세스의 실제 service.service에서 HEALTH/RAG_SEARCH, generation49, 프로필·데이터·검색 정책 및 request_entry/law_title_hints 모듈의 실제 선택을 확인했다. 별도 상주 서버 재시작은 하지 않았다.

## 남은 문제와 후속 방향

ADR0708에서 정확한 오류를 전달받아도 모델이 원문 읽기 이유를 쓰면서 같은 RESEARCH를 재제안했다. 중복 실행은 두 번 차단됐지만 최종 답변은 실패했다. 이 실패와 reason/action 불일치는 이번 승격으로 해결됐다고 주장하지 않는다.

권장 후속은 추가 판정 LLM 없이 현재 후보·관련 도구를 좁혀 제공하고, 실행 내역을 도구/대상/결과 영수증으로 표시하며, 교정에서는 거절된 행동과 가능한 대체 선택을 짧게 제공하는 것이다. 모델의 자유 설명에서 행동을 추측해 자동 변경하지 않는다. 동일 쿼리 차단과 읽기/채택 분리는 유지한다. 이 정책의 구현·효과 검증은 별도다. 난이도별 예산 정책도 보류했다.

전체 graph 검사에는 기존8개 이력 오류가 남았고0710의 새 오류는 없다. 별도로0709의 final 검사에서 나온 미실행 원장 corpus_total=0 형식 오류는 완료 기록을 소급 수정하지 않고 보존했다.0710 자체 final 검증 결과는 artifacts/final-validation.txt에 있다.0709는 모델0회·승격 거절이며0710의 qualification source가 아니다.

## 복구

서빙 포인터: `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 MAIN48을 새 generation으로 선택한다. 작업 파일은 `06_TOOLS/EXPERIMENTS/adr_0710/rollback_working.py`의 dry check 후 `--confirm-working-rollback`으로 별도 복구한다. 백업·해시·apply receipt와 이전 포인터를 보존했다. 실제 롤백은 수행하지 않았다.

[검증 결과](README.md) · [실제 선택](artifacts/main-smoke.json) · [완료 영수증](artifacts/main-completion.json) · [원시 결과](artifacts/run-001/result.json)
''')
p=R/'AGENTS.md';s=p.read_text().replace('`compact-progress-20261009-r1`(포인터 generation 48)','`grounded-entry-20261009-r1`(포인터 generation 49)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('2026-10-09 현재 로컬 RAG MAIN은 `compact-progress','2026-10-09 MAIN48 전환 당시 로컬 RAG MAIN은 `compact-progress',1)
intro='2026-10-09 현재 로컬 RAG MAIN은 `grounded-entry-20261009-r1`(포인터 generation **49**)이다. MAIN48의 표시·계측·판단·원문 세대 위에 새 질문 앞단 통합, 실제 법령 제목 힌트, 모델이 선택하는 구조/fulltext 검색을 연결했다. 후보·작업271계약과 공개3질문 paired 검증, 작업·검증·선택287파일 및 실제 service.service 선택을 확인했다. 이유/행동 불일치와 난이도별 예산은 후속이며 GENOS 배포는 별도다. [실제 반영·검증·롤백](../04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main/MAIN_RESULT.md).\n\n'
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();start=s.index('- 상태:',s.index('## BL-009'));end=s.index('\n',start)
s=s[:start]+'- 상태: **앞단 통합·실제 제목 힌트·구조/fulltext 선택을 MAIN49에 반영.** 기본 profile hash 연결을 보완하고 후보·작업271계약, 공개3질문 두 방식 E2E와287파일·실제 로컬 선택을 확인했다. [MAIN 결과](../04_EXPERIMENTS/ADR/ADR-0710-grounded-entry-profile-bound-main/MAIN_RESULT.md). 이유/행동 불일치·큰 도구 목록·교정 입력 축소와 난이도별 시간 정책은 후속이다.'+s[end:];p.write_text(s)
print('Local MAIN49 recorded; exact287-file package and actual service selection verified')
