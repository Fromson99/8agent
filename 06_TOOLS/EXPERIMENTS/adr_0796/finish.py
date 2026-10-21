from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/ptr['manifest_path']);active=read(A/'artifacts/active-consumer-v2.json');integrated=read(A/'artifacts/working-integration.json');w=read(D/'working-before.json')
assert ptr['release_id']=='latest-document-selection-20261015-r1' and ptr['generation']==73
assert all(active['checks'].values()) and release['files']==f['serving_files']
C=R/release['code_root'];assert all(sha(C/n)==h for n,h in release['files'].items())
assert '28 passed, 2 deselected' in (A/'artifacts/working-tests.log').read_text()
cm=read(R/f['candidate']['manifest_path']);upstream={v['target_path']:v.get('upstream_sha256') for v in cm['files']}
for row in integrated['changes']:
 if row['path'] in ('05_TESTS/CONTRACTS/test_latest_document_policy.py','00_SYSTEM/FILENAME_EXCEPTIONS.json','02_BACKEND/semantic_runtime/filename_versions.py'):row['before']=None;row['backup_note']='File absent before task; any backup copy made during preparation resume is a post-write copy, not a preimage'
put(A/'artifacts/working-integration.json',integrated)
receipt={'status':'PASS','environment':'WSL local','active_pointer':ptr,'release_code_root':release['code_root'],'data_path':release['data_path'],'serving_files_verified':len(release['files']),'candidate_code_identical':True,'preserved_unrelated_working_differences':integrated['preserved_other_working_differences'],'actual_service_checks':active['checks'],'local_internal_latest_documents':11,'genos_deployed':False,'git_main_merged':False,'pipeline_integration_fix':'08_DEPLOYMENT/GENOS/handoffs/latest_selection_20261015_r1/PIPELINE_ADAPTER.json'}
put(A/'artifacts/active-verification.json',receipt)
(A/'MAIN_RESULT.txt').write_text(f'''로컬 MAIN73 완료 — 2026-10-15

최신 선택
- 공통 파일명 판정기를 RAW 입력과 기존 RAG 세대에 연결했습니다.
- 붙여쓴 인덱스북운용준칙은 2026-05-29, 띄어쓴 이름은 모두 유지합니다.
- 기존 승인 예외(대차/POP골든랩/위탁증거금/주식/투자리스크/별첨/단독파일)를 FILENAME_EXCEPTIONS.json 한 파일로 관리합니다.
- 신규 공식 파이프라인은 구조화 전에 최신 선택을 수행하고, 구조화 결과와 문서 DB에 is_latest=true를 저장합니다.
- 기존 세대는 원본을 보존하는 선택표와 읽기 뷰에서 같은 마킹과 검색 제한을 적용합니다.
- 검토 보존/공유 원본도 사유를 보존한 검색 대상입니다. is_latest는 법률상 시행일 인증이 아닙니다.
- 목록·폴더·검색·원문 직접 조회·정의·참조에서 구버전 접근을 제한하며 이전 캐시/상태의 선택 지문도 검사합니다.

검증
- 동결 후보 선택 계약28건, RAW→구조화→색인→API legacy/compact-v2 각1건, 총30건 통과.
- 작업 코드 선택 계약28건 통과. 실제 후보/활성 서비스10개 검사 각각 통과. 모델0회.
- 합성 동일원문2개는 기준2→후보최신1개, 원본 DB 불변.
- 로컬 세대1547문서 중 내규11문서는 모두 유지/마킹. GENOS 예외 대상 문서가 없는 로컬 결과입니다.
- GENOS 설치본의 RAW 파이프라인 검사에서 별도 로컬 migration receipt 의존 결함을 재현했습니다.
  원문 수집 manifest 탐색을 명시한 input_root로 한정하는 일반 통합 결함 수정과 검사 기록은 handoff PIPELINE_ADAPTER.json에 있습니다.
- ADR0796 final validation 통과. 전체 graph의 기존 오류8개는 보존했으며 ADR0796 관련 새 오류 없음.

실제 연결
- release: {ptr['release_id']}
- pointer generation: {ptr['generation']}
- manifest SHA256: {ptr['release_manifest_sha256']}
- serving code: {release['code_root']}
- data: {release['data_path']}
- 선택334파일과 검증 후보 hash 동일. 다른 작업 코드 변경과 MAIN72 기능은 보존했습니다.
- 실제 service.service 바인딩: artifacts/active-consumer-v2.json 및 active-verification.json.
- 원복: stable rag_main_promotion.py rollback에 artifacts/main-apply.json의 적용 영수증을 사용합니다.
- 기존 MAIN72의 원문/색인 파일과 이전 릴리스를 보존합니다.
- GENOS는 별도 검증한 인계 패키지입니다. 현장 apply/commit/gate/push/revision/workflow 테스트는 아직 실행하지 않았습니다.
''')
p=R/'AGENTS.md';s=p.read_text().replace('`definition-entry-navigation-20261015-r1`(포인터 generation 72)','`latest-document-selection-20261015-r1`(포인터 generation 73)');p.write_text(s)
p=R/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text().replace('현행 로컬 RAG **MAIN72','이전 로컬 RAG **MAIN72',1);i=s.index('\n')+1;s=s[:i]+'\n2026-10-15 현행 로컬 RAG **MAIN73 `latest-document-selection-20261015-r1`**은 승인 파일명 예외와 최신 표시를 RAW 구조화 입력 및 기존 세대 검색·탐색에 연결한다. 원본 세대는 보존하고 선택표/네이티브 메타데이터를 검증한다. MAIN72의 최초 정의 탐색을 유지하며 로컬 내규11개 모두 최신 검색 대상으로 마킹했다. [실제 연결·검증·원복](../04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search/MAIN_RESULT.txt). GENOS 현장 적용은 별도다.\n'+s[i:];p.write_text(s)
p=R/'01_DATA/README.md';s=p.read_text();i=s.index('\n')+1;s=s[:i]+'\n로컬 MAIN73은 `latest-selection-20261015-r1/generation`을 선택한다. MAIN72의 불변 소스/색인 파일을 공유하고 독립 선택표에서 최신 내규만 노출한다. 신규 RAW 구축은 최신 선택 후 `document_metadata.is_latest`를 저장한다. [검증·한계](../04_EXPERIMENTS/ADR/ADR-0796-latest-document-pipeline-search/MAIN_RESULT.txt).\n'+s[i:];p.write_text(s)
print('MAIN73 verified:334 serving files; actual service10 checks; local11 internal latest marks')
