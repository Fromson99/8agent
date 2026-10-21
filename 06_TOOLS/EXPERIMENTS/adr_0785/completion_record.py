"""Publish factual implementation records after working-service verification."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
O=R/'09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(A/'artifacts/design/freeze.json')
d=read(A/'artifacts/data-binding.json')
audit=read(A/'artifacts/run-001/result.json')
integration=read(A/'artifacts/working-integration.json')
service=read(O/'verification/working-service.json')
cases=list(ET.parse(O/'verification/working-contracts.xml').iter('testcase'))
assert audit['strict_success'] and integration['all_serving_bytes_equal'] and service['verified']
assert len(cases)==60 and not any(any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases)
assert all(sha(R/n)==h for n,h in f['serving_files'].items())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(A/'artifacts/design/baseline.json')['pointer_sha256']

summary=f'''risk_team_compare_workflow 구현 결과 — 2026-10-15

상태: 작업 코드 통합 및 명시적으로 연결한 로컬 서비스 경로 검증 완료.
활성 로컬 MAIN66(length-recovery-20261015-r1) 포인터는 변경하지 않았다.
GENOS 반입·배포·워크플로우 편집기 반영·내부 모델 실행은 수행하지 않았다.

구현
- 02_BACKEND/workflow 공통 등록·실행·체크포인트·예산·재개·API.
- 별도 risk_team_compare_workflow 패키지의 질문 범위, 양쪽 탐색, 근거 관계,
  사유별 복귀, 항목별 비교, 검증된 근거 기반 리포트.
- service.py 및 RAG API의 대사: 라우팅, WORKFLOW_RUN/RESUME/STATUS.
- 기존 RAG 원문·정의·참조 도구, gateway 및 SQL journal을 통한 상태·사용량 공유.
- 로컬/GENOS 표시 코드의 workflow 출처 및 부분 완료 상태 소비.
- 관계 확인과 준수 판정을 분리하고, 내용 유사성·수치 차이만의 확정 판단을 차단.

데이터
제공 DOCX: deb0727589aad3cc / SHA256 {d['source_sha256']}
새 세대: {d['generation_id']} / 문서 {d['document_count']}개.
기존1546개 원문의 artifact 해시를 보존하고 DOCX1개를 추가했다.
세대 경로: {d['generation_path']}
세대 manifest SHA256: {d['manifest_sha256']}
사진 전사·2018-09-20 판본·현재 유효성 미확인·외부 반출 불가를 보존했다.
원본·이전 세대·활성 포인터는 보존한다. 새 세대는 아직 기본 서빙 대상이 아니다.
최초 색인 실행은 전체255878단위 삽입 후 최적화 단계에서 exit143으로 중단됐다.
송신 주체는 미확인이다. 원래 DB를 무손실 압축 보존하고, canonical 원문 항목을
전수 대조한 뒤 최적화·SQLite/FTS 무결성·해시를 확인해 체크포인트를 복구했다.
정식 reindex 명령이 체크포인트와 세대 전체를 다시 검증했다.
복구 원인·코드·원본/결과 해시: ADR artifacts/data-recovery/proof.json.

실제 검증
- 동결 후보의 관련 계약·회귀500건 통과, 추가 v6 프로필 검사1건 통과.
- 통합 작업 코드의 workflow 및 v6 계약60건 재확인 통과(위 검사와 중복).
- 별도 legacy GENOS 진행 표시14건 실패는 선택 기준과 후보에서 동일하다.
- 실제 DOCX로 POST /v1/rag/ask → workflow → 원문 도구 → 저장·출처 확인.
- 작업 service.service의 LEGAL_AGENT/대사: → v6 → WORKFLOW_STATUS 확인.
- 제15조 및 원본 해시 확인, 수치·산식은 '현재 확보한 내규에서 수치 기준 미확인'.
- 외부·내부 실제 모델 호출0회. 실제 DOCX 확인은 모델 미사용이며,
  정상 관계·상충·복귀·재개 검사는 합성 원문과 모의 모델 응답으로 수행했다.
- 검증 후보와 작업 코드의 서빙 {len(f['serving_files'])}파일 해시 일치.
- 서비스 검사는 작업 코드·새 세대를 명시한 create_app을 service dispatcher에
  연결한 로컬 검사다. 현재 실행 중인 기본 MAIN 서비스 전환의 증명이 아니다.

한계
내부 모델의 실제 법률 판단 정확도·질문별 품질·비용·지연은 미검증이다.
현재 문서에 승인된 판본 유효성 메타데이터가 없어 확정 적용 판정은 보류한다.
GENOS NFS 동시 잠금·배포 리비전·편집기·화면은 현장 검증이 필요하다.
대사 LLM 경로는 trust_zone=internal에서만 허용한다. 로컬 외부 모델 설정에서는
차단 결과를 내며 내부 질문을 전송하지 않는다. use_llm:false는 원문 조회와 미확인 보고다.
임의의 workflow 재귀 호출은 제공하지 않으며 명시 return_to로 호출자에게 복귀한다.

기록·재현·원복
운영 안내: 07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md
감사: {A.relative_to(R)}/README.md
동결: {A.relative_to(R)}/artifacts/design/freeze.json
결과: {A.relative_to(R)}/artifacts/run-001/result.json
데이터: {A.relative_to(R)}/artifacts/data-binding.json
통합 및 변경 전 백업: {A.relative_to(R)}/artifacts/working-integration.json
서비스: {O.relative_to(R)}/verification/working-service.json
일반 회귀: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0785/run_tests.py /home/jin/8-AGENT 05_TESTS/CONTRACTS/test_risk_team_compare_workflow.py 05_TESTS/CONTRACTS/test_risk_team_compare_workflow_v6.py
원복은 통합 receipt의 after 해시가 현재 파일과 같은 경우에만 해당 backup을 복구한다.
새 파일 삭제 또한 현재 after 해시를 확인해야 하며 병행 변경은 덮어쓰지 않는다.
MAIN 승격·데이터 선택은 별도 승인된 plan/confirm 계약을 따른다.
'''
(O/'IMPLEMENTATION_RESULT.txt').write_text(summary)

p=R/'00_SYSTEM/ARCHITECTURE.md';v=p.read_text()
note='''2026-10-15 **작업 코드에 Risk팀 대사 workflow를 통합**했다(ADR-0785). `대사:` → 공통 `workflow` 실행부 → `risk_team_compare_workflow` → 기존 RAG 원문·정의·참조 도구로 연결하며, 관계 확인·내용 비교와 사유별 복귀를 분리한다. 새 DOCX를 포함한1547문서 세대와 같은 코드로 로컬 서비스 경로를 확인했다. 후보500계약·추가 v6검사1건, 통합 후60계약 통과. 활성 MAIN66과 GENOS는 변경하지 않았고 실제 내부 모델 법률 판단은 미검증이다. [운영 계약](../07_DOCS/REFERENCE/OPERATIONS/RISK_TEAM_COMPARE_WORKFLOW.md), [구현·검증·한계](../09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow/IMPLEMENTATION_RESULT.txt).

'''
assert '작업 코드에 Risk팀 대사 workflow를 통합' not in v
first,rest=v.split('\n\n',1);p.write_text(first+'\n\n'+note+rest)
p=R/'01_DATA/README.md';v=p.read_text()
note='''2026-10-15 Risk팀 대사 구현용으로 제공 DOCX를 `risk-compare-input-20261015-r1` SourceSet에 등록하고 `risk-compare-docx-20261015-r1-index` 새 세대1547문서를 구축·검증했다. 기존1546문서 원문 해시와 활성 MAIN66은 보존했다. 사진 전사/2018판본의 현재 유효성은 미확인이며 외부 반출 불가다. 이 세대는 기본 선택 전환 전 상태다. [데이터·코드 연결과 검증](../09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow/IMPLEMENTATION_RESULT.txt).

'''
assert 'Risk팀 대사 구현용으로 제공 DOCX' not in v
first,rest=v.split('\n\n',1);p.write_text(first+'\n\n'+note+rest)
print('Working implementation result and architecture/data entrypoints recorded')
