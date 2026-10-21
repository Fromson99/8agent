from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0896-cm-read-continuity-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency'
read=lambda p:json.loads(p.read_text());pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==87
release=R/pointer['manifest_path'];done=read(release.parent/'IMPLEMENTATION_RESULT.json');prior=read(P/'artifacts/run-001/result.json');qualified=read(A/'artifacts/run-001/result.json')
rows=[]
labels={'cm-001':'10% 한도 구분','cm-003':'제3호/제4호와 독립 제외 조건','cm-008':'의무보유 연장 요건','cm-033':'최초 연결 기준 제출기한','cm-051':'보유비율 계산','cm-011':'사내규정 정비 근거','cm-022':'비상장주식 기본 평가방법','cm-038':'대표자 보고 위임 범위'}
for cid in ('cm-001','cm-003','cm-008','cm-033','cm-051','cm-011','cm-022','cm-038'):
 c=prior['cases'][cid];run=c['run'];rows.append(f"{cid.upper()} | HTTP {run['http_status']} | {run['model_calls']}호출 | {run['elapsed_seconds']:.1f}초 | 핵심 {'충족' if c['manual']['core_pass'] else '미충족'} | {labels[cid]}")
text=f'''MAIN87 로컬 반영 및 실제 서비스 확인 (2026-10-19)

선택: {pointer['release_id']} / generation 87
최근 MAIN86의 데이터, 출력 압축, 재개·예산, Oracle 연결, 근거 원장, 대사 1.10.0, 근거 발견 1.0.0을 보존했다. 검색 색인 선택은 그대로이며 원문 탐색·전달·종료 코드는 아래와 같이 수정했다.

수정 내용
- 읽을 수 있는 본문과 부분 읽기 상태를 선택 메뉴에 유지하고, 정의를 읽은 뒤 원래 조사 위치로 복귀한다.
- 앞선 화면에서 실제 전달한 원문을 다음 판단에 유지한다. 다른 문서·조문·권한·변조된 구간을 합쳐 전체 읽기로 인정하지 않는다.
- 이미 전달한 참조 원문은 중복 선택을 줄인다. 참조 판단 교정이 소진되면 미확인 상태와 읽은 원문을 보존한다. 같은 실패 메뉴 재개가 호출 예산을 초기화하지 않는다.
- 평가 입력의 반복 설명을 검증 후 줄인다. 시스템이 확정할 수 있는 값은 조립하고, 원문·권한·상태 검증은 유지한다.
- 한 조문 안에 의무와 허용이 함께 있는 원문을 단일 표현으로 단정해 거절하던 오류를 수정했다.
- 같은 확인 문구는 저장 전에 중복을 정리하고, 저장된 최종 답변과 공개 응답을 일치시킨다. 개별 부족 사유와 ID는 보존한다.

실제 모델 검사
CM 51문항 등록부의 기존 001·003·008·033·051과 추가 011·022·038을 같은 최종 후보로 한 문항씩 실행했다.
외부 Qwen3.8 / qwen/qwen3.8-27b / Parasail FP8 / reasoning none / fallback 없음.
모두 service.py의 RAG_ASK 경로다. 8회 모두 응답 완료, 핵심 답변 7/8 충족, 실제 모델 총 152호출.
문항별 호출 상한40회·시간1800초·기본 출력6400토큰은 유지했다.

{chr(10).join(rows)}

CM-008은 이번 실행에서 코스닥 본문과 세칙을 읽고 연장 요건을 설명했다. CM-051은 관련 조항의 실제 계산방식과 예외·간접보유를 설명했으며 다른 항의 산정법을 넓혀 적용하지 않았다.
CM-003은 필요한 원문을 읽었지만 제3자배정만으로 제3호에 해당한다고 넓게 설명하고, 독립적인 제외 조건을 충분히 반영하지 못했다. 검색 누락은 개선됐지만 의미 판단은 미해결이다.
모든 문항의 일반적인 확인 문구, 일부 재검색·재검토, 장황한 설명은 후속 과제다. 핵심 충족은 모든 세부 법률 주장이 검증됐다는 뜻이 아니다.

원문·버전 검사
읽은/인용한 원문 구간 {prior['original_evidence_checks']}회 대조, 불일치 {prior['original_mismatches']}회. 반복 검사 수이며 고유 원문 수가 아니다.
CM-022/038 등록 기준의 문서 ID가 선택 세대의 구조화 원문 ID와 다르다. 실제 선택 원문의 버전·해시는 별도 기록했고 기존 회수 점수나 기준 ID를 소급 수정하지 않았다.
CM-022 선택 원문 시행·개정일 2026-02-27, CM-038 법률 2025-04-01. 지문 차이와 의미 답변 판정은 별개다.

기술·연결 확인
같은 최종 코드 605검사 + 새 경계20검사 + 추가 기존44검사 = 669통과.
이전 계약과 맞지 않는 140검사의 제외 및 기존 실패 재현 근거를 보존했다. 전체 저장소 검사가 모두 통과했다는 뜻은 아니다.
후보/작업 코드/실제 선택 서비스 각각10검사 통과. 작업711파일, 선택370파일 지문 일치. 주입 없이 실제 service.service가 MAIN87을 선택했다.
대사·근거 발견의 등록/권한/원문/승인·취소 연결은 기술 검사했다. 이번8문항이 대사 부모 워크플로우 전체를 실제 모델로8회 실행한 결과는 아니다.

RAM·용량
실제8문항 최대 관측 RSS {qualified['peak_known_case_rss_bytes']/1024**3:.2f}GiB. 8GiB RSS/9GiB 주소공간 한도 내 완료.
작업자1개, 상주 데이터 적재 끔, 메모리 반환 설정, 읽기 전용 원본 데이터 공유, 원시 실행 기록 무손실 압축을 사용했다.
제품이나 GENOS의 메모리 상한을 보장하는 수치는 아니다. 이전 실패·중단 기록은 삭제하거나 성공으로 바꾸지 않았다.

반영 상태
14개 제품 파일과31개 의존성 연결 파일만 백업 후 통합했다. 후보 전체를 작업 폴더에 덮어쓰지 않았다.
로컬 MAIN 선택과 새 서비스 인스턴스 확인 완료. Git main 병합·push, 기존 상주 서비스 재시작, GENOS 반입·배포·내부 모델 검사는 미수행.
이번에 새 GENOS ZIP/TXT를 만들거나 발송하지 않았다.

롤백
이 작업공간에서 .venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
이전 MAIN86 read-first-host-contract-20261018-r1 선택본과 데이터는 보존되어 있다. 선택 롤백과 작업 코드 복원은 별개다.
작업 코드 원본 백업과45개 파일 전후 지문: {A.relative_to(R)}/artifacts/working-integration.json

결과 정본: {P.relative_to(R)}/artifacts/run-001/result.json
문항별 검토: {P.relative_to(R)}/artifacts/run-001/manual-review.json
독립 기술 검증: {A.relative_to(R)}/artifacts/run-001/result.json
실제 선택 서비스: {A.relative_to(R)}/artifacts/active-consumer.json
코드·데이터·프로필·탐색 지문: IMPLEMENTATION_RESULT.json
전체 실험 그래프 검사에는 기존9개 이력 오류가 남아 있다. 이번0895·0896 최종 검증은 통과했고 과거 이력을 고치지 않았다.
'''
(release.parent/'IMPLEMENTATION.txt').write_text(text)
p=R/'AGENTS.md';s=p.read_text();old='`read-first-host-contract-20261018-r1`(포인터 generation 86)';assert old in s;s=s.replace(old,'`cm-read-continuity-20261019-r1`(포인터 generation 87)',1);p.write_text(s)
intro='2026-10-19 현재 선택 로컬 RAG는 **MAIN87 `cm-read-continuity-20261019-r1` / 포인터 generation87**, 대사 workflow **1.10.0**이다. MAIN86 데이터·출력 압축·재개·예산·Oracle·근거 원장을 유지하고 원문 탐색/전달 연속성, 참조 판단의 제한 복구, 평가 입력 축약과 저장·공개 응답 일치를 연결했다. 669기술 검사와 후보/작업/활성 서비스 각10검사 통과. 기존CM5+추가011·022·038 실제 RAG는8응답/핵심7충족이며 **CM003 의미 판단, 불필요한 확인 문구·일부 반복 조사는 남는다.** 전체 대사8회 또는 GENOS현장 검증 결과가 아니다. [실제 결과·한계·원복](08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION.txt) · [선택 binding](08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION_RESULT.json).\n\n'
p=R/'GENOS.md';s=p.read_text();s=s.replace('2026-10-18 현재 선택 로컬 RAG는 **MAIN86','2026-10-18 직전 선택 로컬 RAG는 **MAIN86',1);s=s.replace('# GENOS — 질문과 작업의 진입점\n\n','# GENOS — 질문과 작업의 진입점\n\n'+intro,1);p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();s=s.replace('2026-10-18 현재 선택 로컬 RAG는 **MAIN86','2026-10-18 당시 선택 로컬 RAG는 **MAIN86',1);s+='\n\n## MAIN87 원문 전달 연속성과 응답 일치 — 2026-10-19\n\n'+intro.replace('](08_DEPLOYMENT/','](../08_DEPLOYMENT/');p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();s=s.replace('# 백로그\n\n','# 백로그\n\n- 2026-10-19 MAIN87: CM008검색·종료와CM051계산 설명은 최종 실제 검사에서 개선. 기존CM5+추가3은8응답/핵심7충족. **CM003의 제3호·제4호/독립 제외 조건 의미 판단**, 불필요한 확인 문구·장황함·일부 재검색, 기준 문서ID와 선택 구조화 문서ID의 평가 연결은 후속 과제. 최근MAIN변경 유지,669기술 검사 및 실제선택 서비스 확인. [결과와 한계](../08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/IMPLEMENTATION.txt). GENOS내부모델/현장검증과전체대사8회는 미수행.\n\n',1);p.write_text(s)
print('MAIN87 status and remaining semantic issues documented')
