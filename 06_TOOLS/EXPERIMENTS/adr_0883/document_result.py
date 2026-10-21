from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0883-read-first-host-contract-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract'
read=lambda p:json.loads(p.read_text());pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==86
release=R/pointer['manifest_path'];done=read(release.parent/'IMPLEMENTATION_RESULT.json');retry=read(A/'artifacts/run-001/cm-008/result.json');review=read(A/'artifacts/known-retry-review.json');prior=read(P/'artifacts/run-001/result.json')
text=f'''MAIN86 로컬 반영 및 실제 서비스 검증 (2026-10-18)

릴리스: {pointer['release_id']}, 선택 generation86
MAIN85데이터/검색/대사1.10.0/근거 원장/Oracle/출력 압축/재개·예산 변경 유지.
수정: 읽기·완료·추가탐색 선택을 작은 계약으로 분리. 이미 읽고 실제 전달한 본문을 다음 판단에 유지. 평가 disposition/반복 reason/고정 사실필드/질문 원문 인용을 시스템이 조립. 조건문은 leaves+명시ALL/ANY/UNKNOWN관계식에서 기존v8트리로 복원하고 전체 재검증. 오류 제안도 보존해 같은1회수정 담당에게 전달.

실제 CM51중 같은5문항, 외부Qwen3.8/Parasail FP8/reasoning none, fallback없음.
0882:62호출,4답변/1RAM보호중단,핵심답판정2/5,출력{prior['usage']['output_tokens']}토큰,원문{prior['original_evidence_checks']}검사/불일치0.
CM008:최초27호출뒤8GiBRSS보호중단 기록 보존. 같은 코드·데이터·질문으로 메모리 반환 설정을 적용한 별도 재검증 {retry['model_calls']}호출,HTTP{retry.get('http_status')}. {review['summary']}
재실행을 최초 실행의 성공으로 덮어쓰지 않음. 환경이 달라 자원 인과/정답률 A/B로 주장하지 않음.

확인:같은후보341검사+추가63검사=404통과. 후보/통합/실제선택 서비스 각각10검사. 작업711파일·선택370파일 지문 일치. 실제service.py가 주입 없이 선택한local-releasebinding확인. 데이터·검색지문 동일.
변경파일4개와의존성pin31개만 반영,이전작업35파일백업 보존. Gitmain병합/push/상주프로세스재시작/GENOS현장배포는 별도이며 미수행.

남은 문제: CM003조건부설명과불필요한사실요구,CM051시행규칙14실제산식미확보,일부재검색/재조사/확인문구,CM001항호표기 오류. 모두법률정답이라고보고하지않음. 연구실행allocator설정은제품RAM보장아님.

롤백:현재workspace에서 .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --release-id {pointer['release_id']} --confirm-main
롤백 명령 인자는 실행 전 stable runner rollback --help와 release receipt를 확인한다. 이전선택 MAIN85 original-context-20261018-r1 코드와데이터 보존.
검증정본: {A.relative_to(R)}/artifacts/run-001/result.json
작업통합/백업: {A.relative_to(R)}/artifacts/working-integration.json
실제활성서비스: {A.relative_to(R)}/artifacts/active-consumer.json
GENOS새ZIP/TXT와현장검증은이번요청에서수행하지않음.
'''
# Use only the actual stable runner rollback syntax, recorded separately after help.
text=text.replace(f'rollback --release-id {pointer["release_id"]} --confirm-main','rollback --confirm-main')
(release.parent/'IMPLEMENTATION.txt').write_text(text)
p=R/'AGENTS.md';s=p.read_text();old='`original-context-20261018-r1`(포인터 generation 85)';assert old in s;s=s.replace(old,'`read-first-host-contract-20261018-r1`(포인터 generation 86)',1);p.write_text(s)
intro='2026-10-18 현재 선택 로컬 RAG는 **MAIN86 `read-first-host-contract-20261018-r1` / 포인터 generation86**, 대사 workflow **1.10.0**이다. MAIN85의 데이터·검색·Oracle·대사·출력 압축·재개·예산을 유지하고, 본문 읽기 선택과 읽은 원문 유지, 평가 고정값·질문 인용 시스템 조립, 조건 관계식 복원을 연결했다.404기술 검사와 후보/작업/활성 서비스 각10검사를 통과했다. 같은 CM5문항은 최초4답변/1RAM보호중단이며 CM008별도 재검증을 보존했다. **일부 재검색·조기 판단·불필요한 확인 문구와 CM003/051의 답변 완결성 문제는 남고, GENOS현장과새ZIP/TXT는 미수행**이다. [실제 결과·한계·원복](08_DEPLOYMENT/RELEASES/read-first-host-contract-20261018-r1/IMPLEMENTATION.txt) · [선택 binding](08_DEPLOYMENT/RELEASES/read-first-host-contract-20261018-r1/IMPLEMENTATION_RESULT.json).\n\n'
p=R/'GENOS.md';s=p.read_text();s=s.replace('2026-10-18 현재 선택 로컬 RAG는 **MAIN85','2026-10-18 직전 선택 로컬 RAG는 **MAIN85',1);s=s.replace('# GENOS — 질문과 작업의 진입점\n\n','# GENOS — 질문과 작업의 진입점\n\n'+intro,1);p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();s+='\n\n## MAIN86 읽기 선택과 시스템 조립 계약 — 2026-10-18\n\n'+intro.replace('](08_DEPLOYMENT/','](../08_DEPLOYMENT/');p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();s=s.replace('# 백로그\n\n','# 백로그\n\n- 2026-10-18 MAIN86: 읽기 선택·원문 유지·평가 반복 필드와 질문 원문 시스템 조립 반영. [검증과 남은 문제](../08_DEPLOYMENT/RELEASES/read-first-host-contract-20261018-r1/IMPLEMENTATION.txt). CM003참조 예외의 명확한 결론,CM051시행규칙14산식 읽기,이미 읽은 본문 재조사·불필요한 사실요구/확인문구,CM001항호표기,장시간 조사RSS는 후속 대상으로 남는다. 최초CM0088GiB중단과별도재검증을 각각 보존했다. GENOS반입/내부모델검증은 별도.\n\n',1);p.write_text(s)
print('MAIN86 current pointers and accurate limitations documented')
