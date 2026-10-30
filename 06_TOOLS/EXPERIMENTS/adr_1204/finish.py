from common import *
import gzip,zipfile
f=read(DES/'freeze.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==118 and active['release_id']==RELEASE and release['files']==f['files']
consumer=read(ART/'consumer-active.json');assert consumer['passed']
old={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-accepted-answer-main117/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
now={x for x in (OUT/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')};assert old==now
H=ROOT/'08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1'
package=read(H/'package/CODE_MANIFEST.json')
assert {r['path']:r['sha256'] for r in package['files']}==release['files']
put(H/'MAIN_VERIFIED.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'selected_service':bind(ART/'consumer-active.json'),'all466_match':True,'source_renderer_sha256':f['files'][PRODUCT],'genos_deployed':False})
(OUT/'consumer-active.log.gz').write_bytes(gzip.compress(Path('/tmp/adr1204-consumer-active.log').read_bytes()))
bundle=H.parent/'GENOS_SOURCE_ACCORDION_MAIN118_20261029_R1.zip'
with zipfile.ZipFile(bundle,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(H.rglob('*')):
  if p.is_file():z.write(p,str(Path(H.name)/p.relative_to(H)))
with zipfile.ZipFile(bundle) as z:
 expected={str(Path(H.name)/p.relative_to(H)):sha(p) for p in H.rglob('*') if p.is_file()}
 assert set(z.namelist())==set(expected) and all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in expected.items())
put(OUT/'completion.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'source_contracts':29,'working_contracts':29,'regression':read(ART/'regression-comparison.json'),'selected_service_checks':len(consumer['checks']),'candidate_service_checks':11,'package_checks':11,'genos_bundle':bind(bundle),'serving_files':466,'changed_files':[PRODUCT],'other_work_preserved':read(OUT/'working-preservation.json')['identical'],'global_graph_existing_errors':len(now),'global_graph_new_errors':0,'external_model_calls':0,'genos_deployed':False,'quality_certified':False,'rollback_release':'accepted-answer-20261029-r1'})
report='''출처 펼치기 — MAIN118 반영 완료

로컬 MAIN118 / source-accordion-20261029-r1을 공식 선택했다.
기존 MAIN117 accepted-answer-20261029-r1은 롤백 대상으로 보존했다.

동작
[출처 · N건] 버튼을 누르면 출처별 네모 상자가 나오고,
상자를 누르면 확보한 원문이 줄바꿈을 유지하며 아래로 펼쳐진다.
다시 누르면 접힌다. 경로만 보이던 일반 출처 표시를 바꿨다.
출처를 클릭할 때 모델/외부 조회를 추가하지 않는다.
답변에 포함된 원문 범위를 표시하며 미확보 문서 전체를 새로 가져오는 기능은 아니다.
기존 comparison-readable-v1 전용 대사표는 유지한다.

반영 범위
MAIN117 서빙466파일 중 GENOS workflow 표시1파일만 변경했다.
새 코드 해시 c059486140f5db8c8d7b356fb5aa4e01d80df80077ad28be2bb8786eaef0c7f3
다른 조사/판단/온톨로지 작업과 pin 변경은 덮어쓰지 않았고 이번 릴리스에 섞지 않았다.
MAIN 선택 전후 작업466파일 해시가 동일함을 확인했다.

검증
후보 출처29/29·작업29/29 통과. JSON/SSE 모의 서비스 결과를 실제 /chat route로 확인했다.
기존23검사: MAIN117과 후보 모두18통과·3실패·2준비오류로 동일하며 새회귀0.
후보 서비스11·실제 선택서비스17 확인 통과. 실제 service HEALTH200,
MAIN118 binding·원문 표시·데이터/프로필·서빙466파일 전부 동일함을 확인했다.
반입11조건(전체ZIP 해시·동일 전체TXT·적용·재실행·원복·변경된 대상 거절) 통과.
이전 로컬 브라우저 데스크톱/모바일 클릭·키보드 확인은 최초 UI 작업 기록에 보존했다.
ADR1204 최종검사 통과, 전역 graph 기존16오류 동일·새오류0.
새 외부모델0·법률 품질/성능 인증없음.

보존한 준비 오류
검사 import shadowing과 pytest 임시폴더 준비오류는 원본을 남기고 검사기만 정정했다.
작업 동시 변경 감지로 보존 assertion이 멈춘 기록을 남겼고 같은 불변 후보로 진행했다.
관련 없는 작업 코드는 보존했다. 기존 실패는 통과로 계산하지 않았다.

GENOS
08_DEPLOYMENT/GENOS/handoffs/GENOS_SOURCE_ACCORDION_MAIN118_20261029_R1.zip
위 ZIP과 source_accordion_main118_20261029_r1/GUIDE.txt를 준비했다.
코드ZIP466파일은 실제 선택 MAIN118과 정확히 같다.
GENOS_WORKFLOW_PASTE_ALL.txt는 편집기 전체 붙여넣기용 동일 코드다.
실제 업로드한 TRANSFER 폴더에서 안내에 따라 ~/DEV를 검사/적용한다.
자동 패치는 MAIN117/118과 다른 checkout을 덮어쓰지 않는다.
현장 commit/generation/코드서빙 리비전/편집기 배포/실제 화면은 미확인이다.
GENOS 반영은 코드서빙 리비전과 워크플로우 편집기를 각각 확인해야 한다.
Git push·메일·현장 접근은 수행하지 않았다.

로컬 롤백
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
이전 MAIN117 릴리스로 복귀한다. 서비스 장기 프로세스는 재시작한다.
롤백 도구가 작업 PIPELINE 백업도 복원하므로 이후 동시 변경을 먼저 확인한다.
GENOS checkout 파일 원복과 배포된 리비전/워크플로우 원복은 GUIDE.txt에서 구분했다.
'''
(OUT/'반영과_검증결과.txt').write_text(report)
note='''<!-- SOURCE_ACCORDION_MAIN118 -->
**2026-10-29 — 출처 원문 펼치기 MAIN118:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261029-source-accordion-main118/반영과_검증결과.txt) · [ADR1204](04_EXPERIMENTS/ADR/ADR-1204-source-accordion-main-integration/README.md) · [GENOS 반입 안내](08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1/GUIDE.txt). 사용자 요청으로 **MAIN118 / source-accordion-20261029-r1**을 선택했다. 출처 버튼→출처별 상자→확보 원문 펼침/접힘을 표시하며 추가모델/조회0. MAIN117의466파일 중 workflow1파일만 변경, 다른 작업/동시 변경 보존. 후보29·작업29검사 통과, 기존23검사18통과/3실패/2준비오류 동일·새회귀0. 후보서비스11·실제선택서비스17·반입11조건 통과, 코드ZIP466파일/워크플로우TXT와 선택 MAIN 일치. 초기 검사기 import/임시폴더·메타 오류 보존. ADR최종검사통과·전역graph기존16오류동일. **GENOS 현장 리비전·편집기 배포·화면·Git·메일 미수행**, 법률품질 인증없음. MAIN117 롤백 보존.
<!-- /SOURCE_ACCORDION_MAIN118 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- SOURCE_ACCORDION_MAIN118 -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md';t=p.read_text();heading='# GENOS 채팅 화면 연결\n\n';p.write_text(t.replace(heading,heading+'2026-10-29 출처 원문 펼치기를 **MAIN118 / source-accordion-20261029-r1**에 반영했다. 출처 버튼 → 개별 상자 → 확보 원문 펼침/접힘으로 동작한다. [GENOS 반입 안내](../../../../08_DEPLOYMENT/GENOS/handoffs/source_accordion_main118_20261029_r1/GUIDE.txt)에 코드서빙·워크플로우 편집기 적용을 구분했다. 로컬 선택서비스 검증을 마쳤으며 현장 배포/화면은 미확인이다.\n\n',1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1204 출처 원문 펼치기](ADR-1204-source-accordion-main-integration/README.md) — MAIN118 반영·466파일 중 표시1변경·후보/작업29·새회귀0·GENOS 반입 준비, 현장 배포 미확인.\n');p.write_text(''.join(lines))
print('MAIN118 verified and documented; GENOS delivery prepared, field deployment pending')
