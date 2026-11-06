from common import *
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');f=read(DES/'candidate-selected.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==152 and release['files']==f['selected_files']
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
live=read(ART/'live-summary.json');tests=read(ART/'final-contracts/result.json');comparison=read(ART/'regression-comparison-final.json');activation=read(ART/'main/activation.json')
assert not comparison['new_failures'] and not live['source_acl_wire_mismatches'] and live['budget_matches']
result={'implementation':'COMPLETE','main_generation':152,'release_id':active['release_id'],'deployment_basis':'USER_DIRECTED_CUTOVER','quality_certified':False,'serving_files':len(release['files']),'changed':activation['changed'],'contracts':{k:tests[k] for k in ('passed','failed')},'existing_failures':comparison['baseline_failures'],'new_failures':comparison['new_failures'],'live':live,'live_candidate':read(DES/'candidate-live-executed.json')['pin'],'main_candidate':f['pin'],'native_SQL':read(DES/'native-equivalence.json'),'activation':activation,'limits':['Actual CM003 first response completed; continuation timed out UNKNOWN. No baseline or CM018 calls after UNKNOWN. No latency improvement percentage or full multi-turn model pass.','Real first explanation includes unsupported exclusivity/overstatement: one of clauses 3 or 4, and only the time/method suffices despite stated exceptions. Semantic correctness is not certified.','Live rev009; local compatibility guard restricting navigation to guided presentation was verified afterward in rev010 without more model sends.','Confirmed experience ontology reuse is contract-tested; automatic shared ontology publication or learning quality is not established.','No Oracle connection, GENOS deployment, production source writes or mail.']}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'executed':False,'reason':'Global UNKNOWN stop','contracts':comparison['baseline']},'guided':result},comparisons=[],judge_disagreements=0,usage={k:live[k] for k in ('physical_calls','normal','unknown','reported_cost_usd')},latency={'first_turn_seconds':38.502987035084516,'followup_seconds':next(c for c in live['cells'] if c['executed'])['native_result']['turns'][1]['seconds'],'comparison_not_available':True},error_taxonomy=[{'type':'other','count':1,'note':'Provider incomplete response; not a completed bad answer'},{'type':'unsupported_inference','count':1,'note':'Human review of exclusivity and only-condition language, no automatic legal score'}])
m['design']['code_isolation'].update(production_paths_modified_before_decision=False,main_wiring_unchanged=False)
m['design']['code_isolation']['live_revision']=result['live_candidate'];m['design']['code_isolation']['post_live_local_compatibility_revision']=f['pin']
for q in m['questions']:
 case=next(c for c in read(DES/'live-cases.json') if c['id']==q['case_id']);cells=[c for c in live['cells'] if c['case_id']==case['id']]
 text=f"# 질문 {q['number']:03d} — {case['id']}\n\n"
 sections=[('실행 메타','2026-11-05 / ADR-1411-experiment-v1 / run-001 / 원본 상태 exact. Qwen3.8/none, Parasail FP8, 출력상한 없음. 실행 및 미실행 arm은 아래 실제 결과로 구분한다. 오프라인 judge 호출0.'),('사용자 질문 원문',case['steps'][0]['question']),('기준답변 — 채점 전용, 제품 입력 비공개','정답키 입력0·자동 정답률 산출0. 저장 원문과 실제 설명의 범위·조건 표현을 사람이 확인했다. 구조/원문 전달 검사를 법률 의미 품질로 계산하지 않는다.'),('제품 입력을 구성한 원값','[동결 질문·합성 후속 조건](../artifacts/design/live-cases.json), [원문/실전달 대조](../artifacts/source-wire-audit.json), [단계별 전체 좌표 원장](../artifacts/retrieval-stage-ledger.json.gz). 후속 조건은 실험용 가정이며 실제 사용자 사실이 아니다. 원장은 실행 여부, 문서+조문 단위, 미확보·미전달 이유를 보존한다. 독립 gold recall은 없다.'),('제품 모델 호출 — run·arm별 실제 원문','실행된 셀은 ../artifacts/public-live/'+case['id']+'-guided/ 아래 raw/call-*/request.json.gz에 system/user/schema/provider, response.json.gz 또는 partial.json.gz에 실제 응답, finished.json에 시간·usage·UNKNOWN을 보존한다. canonical에는 저장 뷰와 구조 응답, turn-*/response.json.gz에는 실제 API 결과가 있다. 미실행 arm은 원응답이 없으며 가짜 결과를 만들지 않았다.'),('중간 LLM 호출 — router/compiler/verifier/repair','같은 셀의 calls.json과 generations.json에 실제 순서·단계를 전부 기록한다. guided 조사 감독/행동 보완0, 최초 대화 공통 검토 유지. 미확정 후 추가 송신0, 응답 재생0. 기존 저장 모델 응답을 새 성공으로 계산하지 않는다.'),('채점 호출과 반복 판정','외부 judge0. 원문 span·권한·wire·예산을 독립 재조회했다. 한 CM 질문의 첫 완성 응답이며 일반 법률 품질·속도 인증이 아니다. 후속 UNKNOWN으로 비교군 및 CM018 미실행.'),('사례 최종 판정',json.dumps(cells,ensure_ascii=False,indent=2))]
 text+='\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n'
 p=ADR/'실험'/q['file'];p.write_text(text);q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
report=f'''로컬 MAIN152 반영 완료 — 조사 중 사용자 질문과 기록을 이어가는 루프

1. 바뀐 흐름
본문검색/지정 범위로 후보 확보 → 다음 행동 하나(본문 읽기 / 연결 따라가기 / 구조·본문 검색 / 사용자 질문 / 답변) → 결과 기록.
명확하지 않거나 선택이 상충하면 내부 보완을 반복하지 않고 질문한다. 질문에는 막힌 이유와 가능한 다음 방향을 제시한다. 이미 확보한 원문은 별도 출처 카드로 열어볼 수 있다. 사용자 답은 같은 goal/revision 체계에서 기록하고 필요한 조사 단계부터 이어간다.
최초 요청의 잘못된 모델 판단은 조사 전 질문으로, 조사 선택/최종 출력 오류는 기술적 중단 설명과 방향 질문으로 반환한다. 원문/권한/hash/상태 위반과 전송 UNKNOWN은 이 경계로 삼키지 않는다.

2. 이전 기록과 온톨로지
같은 사건의 이전 질문·답변 전문을 순서대로 다음 판단에 포함한다. 이미 수행한 조사·원문·사용자 질문 checkpoint도 유지한다. 과거 모델 의견은 법적 근거로 취급하지 않는다. 미확보 원문은 답변이 생략해도 미해결로 남긴다.
미해결 답변의 지식 확정을 거절한다. 해결된 결과를 사용자가 확인하면 기존 경험 온톨로지에 조건·출처·주장 연결을 저장하고 다음 질문에 재사용한다. 철회·판본·사용자 권한 검증을 유지한다. 공유 온톨로지 자동 게시나 모델 학습 성능 개선을 인증한 것은 아니다.

3. 구현 범위
{len(release['files'])}파일 동결, MAIN151 대비 {activation['changed']}변경(제품16 + SQL메타1 + pin31). 기존 SQL640 실행 동일, 같은 사건 답변 이력을 읽는 SELECT1 추가(총641). 기존 명시 accepted-content/특수 workflow는 기존 루프를 유지하도록 호환 경계를 검증했다.
핵심 변경: guided_navigation.py, decision_projection.py, guided_answer.py, corrected_memory.py, memory_rag.py, request_entry.py 및 선택된 감독/본문 검토의 활성 조건. 코드 후보 rev009를 실제 Qwen에 사용했다. 이후 독립 회귀에서 발견한 기존 답변 모드의 호환 조건만 rev010으로 수정했고 새 외부 모델 호출은 하지 않았다.

4. 검증
고유 관련 검사 {tests['passed']}통과 / {tests['failed']}실패. 실패는 동일 MAIN151 검사에서도 발생한 기존 항목이며 신규 실패0. 초기 실패와 중간 호환 실패는 보존했다. 작업본/준비본은 새 루프·기존 탐색 메뉴·온톨로지 native API 부분집합을 재검사했다. 실제 선택 root service {activation['main_checks']}검사 및 Gold 코드 연결 {activation['gold_checks']}검사 통과(Oracle 연결0).
주요 확인: 원문 전/후 질문, 추가 모델 없이 즉시 반환, 동일 요청 추가호출0, 같은 goal 재개, 후속 입력의 이전 질문·답변, 상충 명령의 상태변경0/보완0, 미해결 지식확정 거절, 해결·확인 후 재사용, ACL/원문 hash 차단.

5. 실제 Qwen 결과 — 전체 멀티턴 미완료
financial cm-003 첫 턴 38.503초/5물리 호출, 본문 READ→ANSWER→설명3개와 추가 질문. 미확보 범위 표시, 동일 요청 재조회 추가호출0. 후속 memory-resolve 입력에 이전 질문·답변2행/1106자와 현재 질문이 포함되었다.
후속 행동 선택은 HTTP200 헤더 뒤 공백60조각660bytes,179.951초 UNKNOWN으로 API504. 후속 전체 시간은 {next(c for c in live['cells'] if c['executed'])['native_result']['turns'][1]['seconds']:.3f}초. 총8물리/정상7/UNKNOWN1, 보고비용 ${live['reported_cost_usd']:.8f}. 이후 baseline·CM018·지식확정·다음질문 재사용은 실제 모델로 미실행. 원격 완료/취소 및 미보고 비용은 미확인이다.
원문28/실전달20검사, 원문·권한·wire 불일치0, 예산8일치. 비교군 미실행이므로 속도 개선율을 계산하지 않는다. 첫 설명에도 제3호·제4호 중 하나라는 배타 표현, 예외를 언급하면서 시간/취득방식만 충족하면 된다는 과한 표현이 남았다. 사용자 확인 루프가 의미 오류를 모두 찾아내는 것은 아니다.

6. 반영과 원복
release {active['release_id']}, USER_DIRECTED_CUTOVER, quality_certified=false. 실제 root service와 Gold가 같은532파일을 선택한다. 원문 generation/매핑/온톨로지 설정은 유지했다. 이전 MAIN151 포인터 및 Gold binding 원복 바이트는 릴리스 rollback과 artifacts/main/gold-binding-before-exact.json에 보존했다. GENOS 현장 배포·운영 원문 변경·메일0.

증빙: artifacts/run-001/result.json, source-wire-audit.json, regression-comparison-final.json, main/activation.json. 실제 답변은 artifacts/public-live/cm-003-guided/turn-1/answer.txt. 실행 스크립트는 06_TOOLS/EXPERIMENTS/adr_1411.
'''
(ART/'구현과_실험_메인반영_결과.txt').write_text(report)
front=(ADR/'README.md').read_text().split('---',2)[1].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=['로컬 MAIN152 사용자 지시 반영 완료. 구현 계약 통과, 실제 멀티턴 미완료/법률 품질 미인증. [전체 결과](artifacts/구현과_실험_메인반영_결과.txt).','MAIN151은 최종 질문만 지원했고 탐색 중 중단/모순·후속 기록 연결이 부족했다. 조사 감독과 보완 선택을 반복했다.',json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'MAIN151 기반 격리 후보. 5종 행동/원문 경계/대화 기록/온톨로지 확정과 재사용. 실제 평가 rev009, 후속 로컬 호환수정 rev010은 별도 증빙이며 모델 재시험0.','등록 financial CM003/018, 공개 문서 실제 팀 권한 교집합. SQLite 원문·격리 runtime. Qwen3.8 Parasail FP8/none, output cap없음. 질문/기준 사전 동결, 정답키 입력0. UNKNOWN 후 송신0.',f"관련 {tests['passed']}통과/기존{tests['failed']}실패/신규0. 실제 root {activation['main_checks']}/Gold{activation['gold_checks']} 통과. CM003 첫 턴38.503초/5회; 후속 UNKNOWN. 2번째 질문 및 baseline 미실행.",'초기 wire 자료형·재표시 오류·신규 플래그 허용 누락·테스트 번호 참조 오류 보존 후 수정. 기존 accepted-content 호환 회귀는 로컬 수정으로 해결. 실제 첫 답변의 배타 적용·조건 단정 표현은 의미 위험으로 남겼다. 제공자 응답 미완료 원인은 단정하지 않는다.',json.dumps({k:v for k,v in live.items() if k!='cells'},ensure_ascii=False),'사용자가 조사 방향을 조정하고 같은 원문/기록에서 재개하는 계약을 확인했다. 단순 행동 선택이 모델의 모든 모순을 검출하는 것은 아니다.','인샘플 첫 답변1, 멀티턴 실제 미완료. 지식 저장/재사용은 모의 모델 계약, 공유 게시·실모델 일반화 미검증. SQL641 생성 대조는 Oracle 실제 연결 검사와 구분한다.','USER_DIRECTED_CUTOVER/quality_certified=false. 이전151 및 Gold 바이트 보존. 원문/설정 유지. GENOS/메일 없음.','prepare→격리 구현→freeze→check→prepare_live/live→UNKNOWN 중단→audit/ledger→로컬 호환 수정 및 재검사→integrate→작업본 검사→prepare_main→준비본 검사→activate→finalize. 외부 live 재실행은 하지 않는다.']
(ADR/'README.md').write_text('---'+front+'---\n\n# 사용자와 이어가는 조사 루프\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headings,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 결과\n\n- [cm-003](질문-001-cm-003.md)\n- [cm-018 — 미실행](질문-002-cm-018.md)\n- [전체 결과](../artifacts/구현과_실험_메인반영_결과.txt)\n')
report_dir=ROOT/'09_ARTIFACTS/AUDITS/20261105-guided-navigation-main152';report_dir.mkdir(exist_ok=True);(report_dir/'구현과_실험_메인반영_결과.txt').write_text(report);put(report_dir/'result.json',result)
p=ROOT/'AGENTS.md';marker='<!-- GUIDED_NAVIGATION_MAIN152_1411_20261105 -->'
assert marker not in p.read_text()
note=f'''{marker}
**2026-11-05 로컬 MAIN152 — 사용자와 이어가는 조사 루프.** [결과](09_ARTIFACTS/AUDITS/20261105-guided-navigation-main152/구현과_실험_메인반영_결과.txt) · [ADR1411](04_EXPERIMENTS/ADR/ADR-1411-guided-navigation-continuity/README.md). `guided-navigation-20261105-r1`·532파일·151대비48변경(제품16/SQL메타1/pin31), 기존SQL640 동일+대화이력SELECT1. READ/FOLLOW/SEARCH/ASK_USER/ANSWER, 질문 즉시 반환·일반 탐색 감독/보완 생략, 같은 goal의 이전 질문·답변과 조사 재개, 미확보 원문·확정 전 지식저장 차단/확인 후 재사용. **관련{tests['passed']}통과·기존{tests['failed']}실패/신규0, 실제 root{activation['main_checks']}/Gold{activation['gold_checks']}통과.** 실제CM003 첫38.503초/5회 설명+질문, 후속 기존 대화1106자 전달 뒤 memory-resolve179.951초 UNKNOWN→504. 총8물리/정상7/UNKNOWN1·보고$0.01061308·원문28/전달20·원문/ACL/wire0·예산8일치·이후송신0. baseline/CM018/실모델 확정·재사용 미실행, 의미 과잉 표현 보존·품질 인증 아님. 실모델rev009 후 기존 답변모드 호환guard만rev010으로 로컬 수정/검증; 새 모델0. USER_DIRECTED_CUTOVER·quality_certified=false, 이전151/Gold 원복 보존·원문/매핑/온톨로지설정 유지·Oracle/GENOS/메일0.
<!-- /GUIDED_NAVIGATION_MAIN152_1411_20261105 -->

'''
p.write_text(note+p.read_text())
print('MAIN152 report and append-only context prepared')
