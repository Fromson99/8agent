from pathlib import Path
import json,hashlib,datetime,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);smoke=read(A/'artifacts/main-smoke.json');assert smoke['status']=='passed' and smoke['pointer']==pointer
assert pointer['generation']==48 and pointer['release_id']=='compact-progress-20261009-r1'
manifest=R/pointer['manifest_path'];release=read(manifest);assert sha(manifest)==pointer['release_manifest_sha256'];rebase=read(A/'artifacts/design/release-rebase.json');assert release['files']==rebase['staged_files']
for name,h in release['files'].items():assert sha(R/name)==sha(R/release['code_root']/name)==h,name
result=read(A/'artifacts/run-001/result.json');assert result['strict_success'];auth=read(A/'artifacts/main-authorization.json')
for ref in auth['qualification'].values():
 if isinstance(ref,dict) and 'path' in ref:assert sha(R/ref['path'])==ref['sha256']
checks=list(E.parse(A/'artifacts/working-required.xml').iter('testcase'));assert len(checks)==233 and all(t.find('failure') is None and t.find('error') is None for t in checks)
apply_path=R/'01_DATA/ACTIVE/local/receipts/semantic-apply-13f566de90a644c48c3ac6b839abb220.json';apply=read(apply_path)
assert apply['action']=='VALIDATED_ADR_PROMOTION' and apply['after']==pointer and apply['before']==read(A/'artifacts/design/baseline.json')['pointer']
record={'status':'local-main-verified','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_pointer':bound(p),'release_manifest':bound(manifest),'pointer':pointer,'qualification':auth['qualification'],'working_install_receipt':bound(A/'artifacts/working-install-receipt.json'),'working_tests':bound(A/'artifacts/working-required.xml'),'working_passed':233,'service_verification':bound(A/'artifacts/main-smoke.json'),'execution_binding':smoke['execution_binding'],'exact_working_validated_release_inventory':True,'serving_file_count':len(release['files']),'apply_receipt':bound(apply_path),'rollback_files':[bound(q) for q in (manifest.parent/'rollback').iterdir() if q.is_file()],'working_rollback_dry_check':'Passed, no rollback executed','git_main_merged':False,'genos_deployed':False,'resident_server_restarted':False,'new_external_model_calls':0,'semantic_quality_certified':False}
(A/'artifacts/main-completion.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
(A/'MAIN_RESULT.md').write_text('''# 진행 표시 압축·호출별 시간 — 로컬 MAIN48 반영

2026-10-09 `compact-progress-20261009-r1`을 로컬 RAG MAIN generation **48**로 선택했다. 전체 MAIN 중 서빙 표시·계측 변경이며, 용어집·구조화·색인·원문 세대와 MAIN47의 구조 우선 검색·판단 정책은 유지한다.

## 화면에서 달라지는 점

진행 카드는 **요청 확인 → 관련 문서 찾기 → 선택한 원문 확인 → 근거 검토·답변 작성 → 답변 준비 완료**로 최대5개만 표시한다. 반복 읽기·검토는 새 턴처럼 카드를 늘리지 않는다. 문서명·목차·조문 구조를 먼저 확인한다는 안내를 사용한다.

최종 답변의 **처리 상세 · 판단 근거와 LLM 호출** 접힘에 다음 정보를 넣었다.

- 실제 모델 전송 시도 횟수
- 각 호출의 작업 구분과 소요 시간
- 모델 호출 시간 합계와 서버 요청 처리 시간

재시도는 각각 포함하고, 문서 열람·내부 연산은 모델 호출로 세지 않는다. 기록이 없는 과거 답변은0회로 추측하지 않으며 시간 미확인은 그대로 표시한다. 서버 처리 시간은 워크플로우 전달·화면 렌더 시간을 포함하지 않는다.

전체 오류·거절·재시도·승인 판단은 기존 로그에 보존한다. 내부 상세 기록 생성은 압축을 적용하지 않는다. 최종 근거 그래프·출처·답변 본문을 유지하며, 최종 실패는 기존의 간단한 안내와 조회 번호만 표시한다.

## 검증과 실제 선택

- 후보와 선별 통합한 작업 코드에서 각각 필수 계약 **233개 전부 통과**.
- 사전 동결한 합성 표시20조합 통과. 기존 최대80카드가 최대5개로 줄었다. 실제 질의의 모델 호출 수나 응답 속도가 개선됐다는 주장은 하지 않는다.
- 재시도·실패·권한 거절·동시 요청·0회/미확인 시간·SSE·저장 표시·전체 판단 로그 보존을 검사했다.
- 검색·모델 입력·상태 변경·답변 생성 코드는 계측 래퍼를 제외한 구조가 같고, 나머지 비표시 코드는 기존 MAIN47과 바이트가 같다. 신규 외부 모델 요청0회다.
- 변경43파일만 이전 해시를 확인하고 백업 후 통합했다. 작업·검증 후보·선택 릴리스의 서빙 **285파일 전체 해시가 일치**한다.
- 새 WSL 프로세스의 실제 `service.service`에서 HEALTH·RAG_SEARCH, generation48과 새 표시·계측 모듈 선택, 프로필·원문·검색 정책 지문을 확인했다. 별도 상주 서버 재시작은 수행하지 않았다.

기존 모델 복구 fixture9개 실패와 기존1개 제외는 보존했다. 전체 ADR graph의 기존8개 이력 오류도 남아 있으며 이번 ADR의 final 검증은 통과했다. 신규 법률 품질 평가는 수행하지 않았다.

**GENOS 현장 반입·워크플로우 편집기 반영·배포·내부 모델 검증은 별도다. Git main 병합도 수행하지 않았다.**

## 복구와 근거

서빙 복구는 `.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main`으로 직전 MAIN47을 선택한다. 작업 파일은 `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0704/rollback_working.py`로 후속 변경 여부를 검사한 뒤, 필요할 때 `--confirm-working-rollback`을 붙여 복구한다. 백업·해시 사전 검사를 통과했으며 실제 롤백은 하지 않았다.

[전체 검증](README.md) · [완료 영수증](artifacts/main-completion.json) · [실제 선택](artifacts/main-smoke.json) · [선별 통합](artifacts/working-install-receipt.json)
''')
p=R/'AGENTS.md';s=p.read_text().replace('`structured-judgment-20261009-r1`(포인터 generation 47)','`compact-progress-20261009-r1`(포인터 generation 48)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();intro='2026-10-09 현재 로컬 RAG MAIN은 `compact-progress-20261009-r1`(포인터 generation **48**)이다. MAIN47의 구조 우선 검색·판단·원문 세대를 유지하면서 사용자 진행 표시를 최대5단계로 압축하고 최종 접힘에 실제 모델 전송 시도별 시간·횟수와 서버 요청 시간을 연결했다. 전체 내부 로그는 보존한다. 계약233개와 합성 표시20조합, 작업·검증·선택285파일 해시와 실제 서비스 선택을 확인했다. 신규 외부 모델 호출0회이며 GENOS 현장 배포는 별도다. [검증·선택·롤백](../04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics/MAIN_RESULT.md).\n\n';s=s.replace('2026-10-09 현재 로컬 RAG MAIN은 `structured-judgment','2026-10-09 MAIN47 전환 당시 로컬 RAG MAIN은 `structured-judgment',1).replace('현재 MAIN47의 선별 반영 범위','현재 MAIN48의 선별 반영 범위');s=s.replace('# MAIN — 원문과 용어 기반 탐색\n\n','# MAIN — 원문과 용어 기반 탐색\n\n'+intro,1);p.write_text(s)
p=R/'07_DOCS/BACKLOG.md';s=p.read_text();head='## BL-007 · 오류 로그와 사용자 채팅 표시 분리\n\n';assert head in s;s=s.replace(head,head+'- 후속 완료(2026-10-09): MAIN48에서 진행 카드를 최대5단계로 압축하고 최종 접힘에 실제 LLM 전송 시도 횟수·각 소요 시간·합계·서버 요청 시간을 연결했다. 전체 상세 로그 보존, 필수233계약 및 실제 로컬 선택을 확인했다. [실제 반영·롤백](../04_EXPERIMENTS/ADR/ADR-0704-compact-progress-call-metrics/MAIN_RESULT.md)\n',1);p.write_text(s)
print('Local MAIN48 verified; completion report and current entry documents updated')
