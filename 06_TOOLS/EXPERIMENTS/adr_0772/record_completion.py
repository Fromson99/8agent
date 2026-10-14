from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';H=R/'08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(R/p['manifest_path']);smoke=read(A/'artifacts/main-service-smoke.json');email=read(H/'EMAIL_SENT.json');assert p['generation']==58 and email['status']=='SENT_VERIFIED' and smoke['status']=='PASS'
for n,h in m['files'].items():assert sha(R/m['code_root']/n)==h,n
concurrent=read(A/'artifacts/concurrent-changes-observed.json')
assert sha(R/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')==m['files']['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
(A/'MAIN_RESULT.md').write_text(f'''# MAIN58 기관별 한국어 법령 표시 및 오류 비공개

완료: 로컬 선택 포인터 generation58, `{p['release_id']}`. GENOS 현장 저장/검증은 별도 미확인이다.

- 표시: 외부법률 / 한국거래소·한국금융투자협회·법제처·금융위원회·법제처(법령해석례)·판례. internal은 **내부 규정**.
- 검색 결과 chunk와 연속 원문 확인을 각각 한 카드로 묶고 기관별 번호 목록으로 표시한다. 내부 팀/기술 폴더명은 제거하고 별표/서식 제목은 보존한다.
- 과정의 오류·거절 제안·추적 로그는 비공개 필터로 제외. 진단 journal/request 저장은 유지. 최종 실패는 짧은 안내와 조회 번호를 표시한다.
- 기관 표기는 선택 용어집 ID/해시와 수집기 분류에 결속한 화면용 표기다. `법제처` 자체 표제어는 없어 사용자 지정 출처명으로 명시했다. [근거](artifacts/design/provider-label-evidence.json).
- 선택한 로컬 DB의 출처를 확인했으며 망분리 현장 DB를 읽었다고 주장하지 않는다.

검증: 후보 97계약 및 합성24/24 경계 통과, 작업 코드97계약 통과. 답변은 baseline과24/24 동일. 모델 호출0. 개발 rev001의 HTML 경로 구분자2실패와 수정전 산출물은 보존했다. 수정후 rev002를 동결하고 paired 감사를 최초 실행했다.

선택297파일은 검증 후보와 동일하다. MAIN57 대비 serving 변경은 workflow 한 파일뿐이다.
작업 workflow SHA256 `{m['files']['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']}`.
원문 세대 `{m['data_path']}`, manifest SHA256 `{m['data_manifest_sha256']}` 보존.
프로필/검색 정책 지문과 실제 binding은 [서비스 검사](artifacts/main-service-smoke.json)에 기록했다.
기존 별도 모델 전송 작업과32개 미선택 작업 파일 차이는 설치 시 보존했다. 이후 별도 AD/service 작업의 동시 변경38파일을 발견해 그대로 유지하고 concurrent-changes-observed.json에 기록했다. 이 transport 수정이 MAIN58에 승격됐다는 의미는 아니다.

실제 새 WSL `service.service` 프로세스에서 HEALTH200/RAG_SEARCH200, MAIN58 binding, 선택 표시 모듈 경로, 권한 제외 및 원문12개/카드1개 확인.
현재 실행 중인 GENOS 서버나 기존 상주 프로세스의 재시작 성공을 뜻하지 않는다.
[표준 prepare](artifacts/main-prepare.log) · [apply](artifacts/main-apply.log) · [작업 설치](artifacts/working-install-receipt.json).

ADR0772 최종 validate PASS. 전체 graph의 기존8오류(ADR0305/0444/0541/0622/0638/0542/0158)는 기존 이력을 유지했으며 신규0772 오류는 없다. [검사](artifacts/graph-validation.txt).

삼성메일 `{email['to']}` SENT `{email['message_id']}`: ZIP·전체 교체TXT·안내·검증요약·해시5첨부 이름/크기 재확인.
[인계](../../../08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/GUIDE_UTF8.txt) · [발송](../../../08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/EMAIL_SENT.json).
GENOS는 R1 대신 R2 PASTE_ALL TXT를 기존 워크플로우 Python 편집기에 저장하고 워크플로우 테스트 화면에서 확인한다. backend 코드 ZIP 적용·NFS generation 변경이 아니다. 별도 MODEL_STREAM_FIX R1 인계와 독립적이다.

롤백: 후속 service.py/PIPELINE 동시 변경이 있으므로 현재 파일 백업과 차이 검토 후에만 표준 rollback을 실행한다. 로컬 활성 릴리스는 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 MAIN57을 선택한다. 포인터 generation은 단조 증가한다. 작업 표시 파일은 `06_TOOLS/EXPERIMENTS/adr_0772/rollback_working.py`의 해시 확인 후 `--confirm-working-rollback`으로 복원한다. 현장은 붙여넣기 전 백업한 편집기 내용으로 복원한다. Git main 병합·GENOS 리비전 배포는 수행하지 않았다.
''')
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();s=s.replace('2026-10-13 현재 로컬 RAG MAIN은 `source-cards-20261013-r1`', '2026-10-13 MAIN57 전환 당시 로컬 RAG MAIN은 `source-cards-20261013-r1`',1)
intro='''2026-10-13 현재 로컬 RAG MAIN은 `source-provider-20261013-r2`(포인터 generation **58**)다. MAIN57의 원문·검색·모델·진단 저장을 유지하고 기관별 한국어 법령 번호 목록과 `internal → 내부 규정` 표시를 연결했다. 합성24조합과 후보/작업 각각97계약, 검증후보·선택297파일, 실제 `service.service` HEALTH/RAG_SEARCH200과 표시 소비자를 확인했다. 별도 작업의 모델 전송 수정은 작업 트리에 보존했으나 이번 MAIN58에는 섞지 않았다. GENOS 편집기 R2는 삼성메일로 발송했고 현장 저장/화면 검증은 별도다. [반영·근거·롤백](../04_EXPERIMENTS/ADR/ADR-0772-source-provider-display/MAIN_RESULT.md).

'''
s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);p.write_text(s)
p=R/'AGENTS.md';s=p.read_text().replace('`source-cards-20261013-r1`(포인터 generation 57)', '`source-provider-20261013-r2`(포인터 generation 58)');p.write_text(s)
p=R/'GENOS.md';s=p.read_text();intro='''2026-10-13 사진 후속 수정으로 [기관별 표시 R2](08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/GUIDE_UTF8.txt)를 완성했다. 용어집에서 확인한 한국어 기관명 아래 번호 목록으로 모으고 `internal`은 **내부 규정**으로 표시한다. R1에 남아 있던 전체 오류 표시를 공개 이벤트 필터로 차단하며 진단 원장은 유지한다. 로컬 MAIN58 `source-provider-20261013-r2` 선택과 실제 service.service HEALTH/RAG_SEARCH200·원문12개/카드1개를 확인했다. 후보/작업 각각97계약·24조합 통과, 검증후보/선택297파일 동일. 삼성메일 SENT `1a133d8e5a42035e`의 ZIP/전체 교체TXT/안내/검증요약/해시5첨부를 재확인했다. **현장은 기존 워크플로우 편집기를 R2 TXT 전체로 교체**하며 저장/실제 화면은 미확인이다. 아래 MODEL_STREAM_FIX R1은 backend 전송 수정으로 별도 유지한다. [로컬 반영·롤백](04_EXPERIMENTS/ADR/ADR-0772-source-provider-display/MAIN_RESULT.md) · [발송](08_DEPLOYMENT/GENOS/handoffs/workflow_source_provider_20261013_r2/EMAIL_SENT.json).

''';s=s.replace('# GENOS — 질문과 작업의 진입점\n\n','# GENOS — 질문과 작업의 진입점\n\n'+intro,1);p.write_text(s)
p=R/'04_EXPERIMENTS/ADR/README.md';s=p.read_text()
if 'ADR-0772-source-provider-display' not in s:s+='\n- [ADR-0772 기관별 한국어 법령 표시와 진행 오류 비공개](ADR-0772-source-provider-display/README.md): Accepted, 24/24 표시 감사·97계약, 로컬 MAIN58 선택 및 실제 서비스 확인, GENOS R2 삼성메일 발송.\n'
p.write_text(s)
print('Completion recorded; current pointer MAIN58; scoped workflow matches; unrelated work preserved')
