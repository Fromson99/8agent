from common import *
import re
f=read(DES/'freeze.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
r=read(ROOT/active['manifest_path']);tests=read(ART/'contracts-final/result.json');prepared=read(ART/'prepared-api/result.json')
assert active['generation']==134 and active['release_id']==RELEASE
assert tests['passed']==169 and tests['failed']==0 and prepared['passed']==14 and prepared['failed']==0
assert read(DES/'freeze-rev-004.json')['files']==f['files']
assert all(sha(ROOT/n)==h for n,h in f['files'].items())
for name in ('main-entry','gold-entry','ui-package-check'):assert read(OUT/(name+'.json'))['passed']
for name in ('oracle-create-r2','oracle-read','oracle-withdraw'):assert read(ART/name/'result.json')['status']=='PASS'
assert read(OUT/'oracle-readonly.json')['publications']==3
archives=read(ART/'runtime-archives.json');assert archives['all_restore_hashes_verified']
limits=[
 'ADR1290 real Qwen remains overall NOT_PASSED; this task made no external model call or causal quality claim.',
 'Natural-language historical comparison false positives and unregistered/free-text gap references remain outside this exact-reference repair.',
 'N1 final-effect formula is unregistered/UNKNOWN; no legal meaning inferred or automatically approved.',
 'Field Dataiku/GENOS/NFS and concurrent Oracle host lifetime/deployment are not verified. The package requires the authenticated host factory; local connector fresh-process contract remains.',
 'New application-v4 persisted calculations need a compatible reader; do not read new namespaces with a MAIN133 reader during rollback. Oracle layout4 remains required.',
 'Oracle synthetic trial records are retained, and the successful trial publication was explicitly withdrawn. Existing source and three operating publications are unchanged.'
]
result={'status':'TECHNICAL_PASS_USER_DIRECTED_MAIN','candidate_revision':f['candidate_revision'],'candidate_files':len(f['files']),
 'working_changed':44,'working_product':11,'working_tests':2,'pins':31,
 'selected_main':134,'selected_release':RELEASE,'serving_files':len(r['files']),'main_delta_files':41,
 'contracts_passed':169,'new_checks':17,'updated_existing_checks':4,'prepared_api_passed':14,
 'overlap':'Prepared API includes the same new native ID repair test; earlier rounds overlap final scope. Do not sum as independent samples.',
 'root_checks':16,'gold_binding_checks':9,'ui_package_checks':6,
 'oracle_isolated_authoring_read_withdraw':True,'existing_oracle_publications':3,'existing_oracle_anchors':12,'existing_oracle_paths':9,
 'model_calls':0,'ddl_changes':0,'field_deployed':False,'git_pushed':False,'mail_sent':False,'quality_certified':False,
 'oracle_code_identity_to_final539':True,'limits':limits,
 'evidence':{name:bind(p) for name,p in {
 'contracts':ART/'contracts-final/result.json','prepared':ART/'prepared-api/result.json',
 'oracle_create':ART/'oracle-create-r2/result.json','oracle_read':ART/'oracle-read/result.json','oracle_withdraw':ART/'oracle-withdraw/result.json',
 'main':OUT/'main-entry.json','gold':OUT/'gold-entry.json','oracle_existing':OUT/'oracle-readonly.json',
 'ui_package':OUT/'ui-package.json','ui_check':OUT/'ui-package-check.json','activation':OUT/'activation.json',
 'integration':ART/'working-integration.json','archives':ART/'runtime-archives.json'}.items()}}
put(ART/'run-001/result.json',result)
put(ART/'verification-reconciliation.json',{'retained_initial_failures':{
 'connections-r1':'Three failures: a DomainWorkflow fixture injected into the legacy dashboard, navigation label mismatch, dict-only session-state mock. Use the actual legacy Workflow host, stable navigation key and mapping state write. All retained.',
 'oracle-create':'Synthetic proposal hardcoded S1 but the actual source ID was S1420. Correctly rejected before publication. Four real glossary candidates were restored; new r2 private scope uses supplied source ID and exact original. No validator relaxed.',
 'native-gap-r1':'Fixture text insertion missed its target, so no fault was injected and expected two calls saw one. Explicit injection now produces COMPUTED_GAP_IN_REASON and one successful repair; raw rejected proposal retained.'},
 'intermediate_168':'Previous candidate before historical issue-label separation; final 169 uses rev005 and exact matching prepared code.',
 'results':[bind(p) for p in sorted(ART.glob('*/result.json')) if p.parent.name!='run-001'],
 'no_live_result_overwrite':True,'oracle_trial_publication_withdrawn':True})
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '사용자의 수정계획 진행 지시에 따라 공통 관리 화면·Oracle authoring 포트·가정 표시를 수정하고 로컬 MAIN134/ontology-console-20261103-r1로 선택했다. 서빙515파일·MAIN133대비41차이(제품10+pin31), 별도 관리 화면525파일 ZIP을 검증했다. USER_DIRECTED_CUTOVER/quality_certified=false이며 현장 배포·법률 품질 인증은 아니다.',
 'MAIN133 서빙과 Gold 결속은 정상이었지만 두 관리 앱이 최신 자유 작업공간/도메인 화면으로 연결되지 않았다. 원격 도메인 용어집 포트도 UI에서 공급되지 않았고, 작업에만 남은 ADR1289 서버 계산7파일이 미선택이었다. 과거 compiler 전체 해시·Markdown 출처 기대 검사4건은 최신 계약을 반영하지 못했다. ADR1290의 내부 ID 노출·옛138만원 확인 목적 잔존과 실제 모델 전체 미통과를 별도로 보존했다.',
 '호스트 인증/문서/원문세대/ACL을 유지하며 실제 두 앱에서 저장·왕복하고, 승인된 동일 게시본을 RAG가 읽으며, 가정의 현재 표시를 기준 사건 이력과 구분한다. 원문/권한/상태/소비 검증을 약화하거나, 자동 게시·모델 재시도를 추가하거나, 검증하지 않은 코드를 선택하면 실패다. criteria.json은 수정 전 동결했다.',
 'ontology_console 공통 선택기에서 선택한 패널만 실행한다. actor/설정/코드 root 변경은 미완료 화면 상태를 비우고 저장 정본은 유지한다. configuration의 요청별 ContextVar 호스트가 Workflow와 새 glossary factory를 공급하고 종료 시 복원하며 각 소비자가 reader를 닫는다. mapped_authoring은 기존 mapped Gold reader와 별도 관리자 writer를 결속하고 쓰기 권한으로 RAG 읽기 scope를 넓히지 않는다. 미사용/읽기범위없음/빈 게시/원문대조완료/확인 전/오류를 구분한다. 기존 대시보드는 승인 전용으로 유지한다.',
 'ADR1292 rev005/539파일을 동결했다. Oracle에 사용한 rev004와 제품 전체539파일이 동일하다. 실제 원문과 용어집은 기존 로컬 Oracle을 사용하고 별도 ADR1292 namespace만 합성 작성·승인·게시 후 철회했다. 원문/기존게시/DDL/설정/권한 세대는 바꾸지 않았다. 외부 모델0이며 Qwen3.8 정책과 UNKNOWN 재전송 금지는 유지했다. 합성 제안은 기능 검사이며 법률 정확도 평가가 아니다.',
 '최종 계약169(새17+기존152, 기존4검사 갱신) 통과. 준비 서빙 API14 통과, 새 native ID 보완 검사1은 앞169와 겹친다. 실제 루트16·Gold결속9·별도 UI패키지6 조건 통과. Oracle 새범위 작성/중복쓰기재사용/컴파일/승인/활성화, 새프로세스 동일본문·권한거절, 철회후 저장답변 차단 통과. 기존3게시/12앵커/9경로 재확인. 작업44파일(제품11+검사2+pin31) 반영·539정확일치. MAIN134/Gold/화면 backend 해시를 대조했다.',
 '첫 연결검사3실패는 legacy Workflow 대용 fixture·탐색 버튼 키·dict 상태 mock의 불일치였다. Oracle 최초는 시험 제안S1과 실제S1420 ID가 달라 정당거절됐고 새범위에서 검사 제안만 정확한 ID에 결속했다. native 오류주입 최초는 삽입이 누락되어 정상1호출과 기대2호출이 달랐으며 명시 주입으로 수정했다. 모든 최초 결과/원응답/저장 journal은 보존했다. 실제 모델1290의 실패는 그대로 미통과다.',
 f'외부 모델/비용0. 최종169검사 {tests["seconds"]:.3f}초, 준비14검사 {prepared["seconds"]:.3f}초. 성공 Oracle 작성25.100초/새조회0.568초/철회0.911초, source SQL102/27/32이며 writer SQL을 포함한 전체 횟수 주장이 아니다. 최초 별도 용어집4복원은141.469초 뒤 fixture거절로 전체실패다. 기존게시 읽기검증157SQL. 성능·토큰·인과 개선율은 측정하지 않았다. 완료/실패 runtime{len(archives["rows"])}개를 모든 파일/심볼릭링크 대조 후 무손실 압축했다.',
 '제시된 정확한 computed_gap_ref가 이유문에 들어오면 원제안을 보존하고 기존 한 번의 보완으로 되돌린다. 구조화 선택만 같은 위치에서 전개하고 일반 자유문·원문·600자 사유를 자르지 않는다. 현재 가정 확인 범위는 현재 쟁점으로 표시하며 기준 질문/조사 목적 전체는 별도 이력 필드와 채팅 이력 영역에 보존한다. 수치·미확인은 서버 계산표 그대로 저장/재조회한다. 금액 TRUE만으로 최종 허용을 확정하지 않는다.',
 '\n'.join('- '+s for s in limits),
 '공식 prepare/apply로 MAIN134를 선택하고 Gold engine binding만 정렬했다. 원문 generation/Gold query·매핑·설정·Oracle layout4·상세 NFS 계약은 유지했다. 별도 ontology_console_20261103_r1.zip에는 검증한 backend515파일과 화면/진입/안내를 결속했고 현장 배포는 하지 않았다. MAIN133 포인터와 이전 Gold binding, 작업 변경 전 파일·기존 UI패키지를 보존한다. 새 application-v4 저장 namespace는 구MAIN133으로 읽지 않고 v4 호환 복구 리더를 유지해야 한다. 이력/원문 삭제로 원복하지 않는다.',
 '06_TOOLS/EXPERIMENTS/adr_1292의 prepare→격리편집→freeze→check→oracle(create/read/withdraw)→release_prepare→check_prepared→build_ui/check_package→activate→main_entry/gold_entry/oracle_readonly→archive_runtime→finalize. 원래 namespace에서 create를 재실행하지 않는다. 검사는 새 run 경로를 사용하고, runtime.tar.gz는 해당 run 폴더에 runtime이 없을 때만 풀어 복원한다. 명령별 runner와 입력/후보 hash는 artifacts 및 support-files.json을 따른다.'
]
report=OUT/'수정과_검증_메인반영결과.txt';report.write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
(OUT/'남은문제와_현장적용.txt').write_text('남은 범위\n\n'+'\n\n'.join(limits)+f'\n\n관리 화면 묶음: 08_DEPLOYMENT/DATAIKU/ontology_console_20261103_r1.zip\n실행/인증/호스트 연결/원복: 같은 폴더 GUIDE.txt\n현재 로컬 선택: MAIN134/{RELEASE}\n')
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1292 RAG·온톨로지·관리 화면 통합\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 연결 계약 검증\n\n[판정과 한계](../README.md) · [최종 결과](../artifacts/run-001/result.json) · [초기 실패 보존](../artifacts/verification-reconciliation.json) · [계보](manifest.json)\n')
sections=[('실행 메타','run-001/verified; 기술검사 완료. 실제 모델 품질 검사는 아님.'),('입력과 기준',values[4]),('설계',values[3]),('실제 출력',values[5]),('판정과 오류',values[6]),('재현과 한계',values[9]+'\n\n'+values[11])]
(ADR/'실험/001-console-and-scenario-contracts.md').write_text('# 공통 화면·Oracle 포트·가정 표시 계약\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'main':133,'historical_audit':True},'verified':result},judge_disagreements=0,
 usage={'external_model_calls':0,'ddl_changes':0,'oracle_synthetic_trial_writes':True},latency={'contracts_seconds':tests['seconds'],'prepared_seconds':prepared['seconds']},
 error_taxonomy=[{'type':'INITIAL_CONSOLE_FIXTURE','count':3},{'type':'ORACLE_SYNTHETIC_SOURCE_HANDLE','count':1},{'type':'MOCK_FAULT_NOT_INJECTED','count':1}]);put(ADR/'실험/manifest.json',m)
# Update only current guidance. Historical records remain append-only.
p=ROOT/'03_FRONTEND/README.md';s=p.read_text();old=next(line for line in s.splitlines() if line.startswith('- `APPS/legal-knowledge-streamlit/`'))
s=s.replace(old,'- `APPS/legal-knowledge-streamlit/`: Dataiku 지식 운영 콘솔. 설정된 온톨로지 관리/시뮬레이션은 공통 `ontology_console.py`를 통해 기존 승인 대시보드·자유 작업공간·도메인·시나리오 패널에 연결된다. 나머지 배치/구조화/숏컷/Legal Wiki 화면은 기존 시안 범위다. MAIN134와 결속한 별도 배포 묶음은 `08_DEPLOYMENT/DATAIKU/ontology_console_20261103_r1.zip`; 현장 반영은 별도다.');p.write_text(s)
p=GOLD/'README.txt';s=p.read_text().replace('로컬 MAIN125 Oracle 범위 포트 수정 / 2026-10-30','로컬 MAIN134 온톨로지 관리·가정 표시 연결 / 2026-11-03').replace('oracle-scope-20261030-r1 / MAIN125, 정식 선택 코드489파일.',f'{RELEASE} / MAIN134, 선택 코드515파일.').replace('manifest hash·489파일','manifest hash·515파일');s+='\n2026-11-03: ADR1292 합성 계약169/준비API14·로컬Oracle 격리게시/재조회/철회 검증. 실제 모델 효과/현장 GENOS 품질 미인증. 별도 관리 화면 GUIDE는 ../.. 경로의 DATAIKU/ontology_console_20261103_r1/GUIDE.txt 참조.\n';p.write_text(s)
entry='''<!-- RAG_ONTOLOGY_CONSOLE_MAIN134_1292_20261103 -->
**2026-11-03 현재 로컬 MAIN134 — RAG·온톨로지·관리 화면 연결 수정:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration/수정과_검증_메인반영결과.txt) · [ADR1292](04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/README.md). **ontology-console-20261103-r1·서빙515/MAIN133대비41(제품10+pin31)·작업539정확결속**, 공식 prepare/apply·Gold 같은MAIN. 두 앱 공통 대시보드/자유작업/도메인/시나리오, 인증 호스트의 별도 reader/writer/용어집·scope·상태 분리. 제시된ID의 사유문오용은 기존1회보완·원응답보존, 현재가정 확인범위와 기준질문/조사이력 별도표시. **계약169(새17)/준비API14·root16/Gold9/UI묶음6 통과**(중복범위 합산금지). 실제 로컬Oracle 격리 작성→승인게시→새프로세스 동일조회/ACL거절→철회/답변차단 통과; 기존3게시/12앵커/9경로 보존. 별도 **ontology_console_20261103_r1.zip/525파일** 준비·backend515해시결속. 최초 화면fixture3/Oracle ID불일치1/모의주입누락1 실패·runtime 보존. **USER_DIRECTED_CUTOVER/quality_certified=false·실모델0**, ADR1290 전체미통과·자연문 비교과차단/미등록gap/N1효과UNKNOWN 유지. 현장 Dataiku/GENOS/NFS/원격호스트 동시성 미검증·DDL/Git push/메일0. MAIN133+Gold+기존UI 원복보존; **새application-v4 저장namespace는 호환reader 필요**, Oraclelayout4유지. 아래 MAIN133 유지 설명은 이전 시점이다.
<!-- /RAG_ONTOLOGY_CONSOLE_MAIN134_1292_20261103 -->
'''
p=ROOT/'AGENTS.md';s=p.read_text();assert 'RAG_ONTOLOGY_CONSOLE_MAIN134_1292_20261103' not in s;i=s.index('\n')+1;p.write_text(s[:i]+'\n'+entry+'\n'+s[i:])
p=ROOT/'00_SYSTEM/ARCHITECTURE.md';s=p.read_text();i=s.index('\n')+1
current=f'\n**2026-11-03 현재 로컬 MAIN134:** `{RELEASE}`·서빙515파일·Gold 동일엔진. 공통 관리 화면과 인증 host 포트·서버 가정 계산/현재·이력 표시를 연결했다. 관리 UI는 MAIN 밖의 별도 `ontology_console_20261103_r1.zip`으로 결속했다. 기본 RAG OFF/Gold ON 설정을 유지하며 실제 모델 개선·현장 적용·법률품질은 미인증이다. [검증·한계·원복](../09_ARTIFACTS/AUDITS/20261103-rag-ontology-console-integration/수정과_검증_메인반영결과.txt). 아래 번호는 당시 기록이다.\n'
p.write_text(s[:i]+current+s[i:])
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
p=ART/'manifest.json';am=read(p);am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Frozen code, preserved failures, checked local integration and lossless runtime',contains_raw_prompts_and_outputs=x.name=='runtime.tar.gz') for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/__pycache__/' not in str(x)];put(p,am)
print('Documented MAIN134;169 contracts/14 prepared API;Oracle trial withdrawn;field/model limits retained')
