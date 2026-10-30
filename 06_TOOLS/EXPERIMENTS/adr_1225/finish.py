from common import *
f=read(DES/'freeze.json');b=read(DES/'baseline.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==122 and active['release_id']==RELEASE and release['files']==f['files']
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
consumers={m:read(ART/f'consumer-active-{m}.json') for m in ('off','on','db')};assert all(v['passed'] for v in consumers.values())
old={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-regex-wire-repair-main121/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
new={x for x in (OUT/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')};assert old==new
nc=sum(len(v['checks']) for v in consumers.values());cc=len(read(ART/'consumer-candidate-off.json')['checks'])
roots=[ROOT/'04_EXPERIMENTS/ADR'/name for name in ['ADR-1220-normalization-accumulation-live','ADR-1222-accumulation-reference-live','ADR-1224-accumulation-source-live']]
audits=[read(p/'artifacts/audit.json') for p in roots];calls=sum(a['calls'] for a in audits);cost=sum(a['reported_cost_usd'] for a in audits);seconds=sum(a['seconds'] for a in audits)
assert calls==9 and all(a['error_null_count']==0 for a in audits)
quality=read(roots[-1]/'artifacts/content-review.json');budget=read(roots[-1]/'artifacts/budget-stop-classification.json')
put(OUT/'completion.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'serving_files':487,'changed_files_from_MAIN121':34,'product_files':3,'pin_files':31,'feature_contracts':106,'regression':read(ART/'regression-comparison.json'),'selected_service_checks':nc,'candidate_service_checks':cc,'selected_service':{k:bind(ART/f'consumer-active-{k}.json') for k in consumers},'all_working_and_selected_files_equal':True,'global_graph_existing_errors':16,'global_graph_new_errors':0,'physical_calls':calls,'reported_cost_usd':cost,'dispatch_seconds_sum':seconds,'error_null':0,'external_unknown':0,'pre_dispatch_budget_stop':budget,'normalization_saved':2,'normalized_raw_segments':10,'exact_locators':35,'accumulation_saved':1,'compiled_previews':1,'compiled_status':'PARTIAL','whole_experiment_passed':False,'content_review':quality,'last_same_diagnostic_real_model_retest':False,'quality_certified':False,'genos_deployed':False,'rollback_release':b['active']['release_id']})
report=f'''정규화·누적 상태/참조 계약 수정 및 MAIN122 — 2026-10-29

결론
수정본을 MAIN122 / {RELEASE}에 반영했다. 구조/서비스 계약106개와 선택 서비스{nc}조건이 통과했다.
실제 실험은 전체 미통과다. 정규화2/2·첫 누적1판본 저장/부분 컴파일·두 번째 누적 미통과다.
총9물리 호출에 도달해 추가 실모델을 호출하지 않았다. 마지막 SAME 오류 진단 보강은 합성/회귀 검사로 확인했으며 실모델 재검증은 하지 않았다.

수정한 내용
1. 정규화의 coverage를 raw.index의 모든 입력 구간을 키로 갖는 닫힌 객체로 요청한다. 누락·추가 키를 허용하지 않는다.
   USED는 관찰 참조가 있어야 하고 NON_JUDGMENT/NEEDS_CONTEXT는 참조가 없어야 한다. 상태를 서버가 추측해 바꾸지 않는다.
2. 모델은 원문 내 pointer·정확한 인용 문구·0부터 세는 출현 순서를 선택한다. 서버는 이 선택으로 hash/start/end를 계산한다.
   유사 문구로 보정하거나 첫 출현으로 임의 대체하지 않는다. 원래 canonical 배열/좌표 형식으로 저장하고 원래 검증기를 다시 통과한다.
   원래 모델 제안과 조립 전후/원문 index 해시, 구간/좌표 수 영수증을 함께 보존한다.
3. 관찰 요소 ID·이전 그래프 ID·이번 그래프 ID·규정 원문 ID를 구분한다.
   comparison은 제안 그래프 노드만, removed는 이전 그래프의 실제 삭제만, unused는 제안 그래프의 미사용 노드만 참조한다.
   관찰 참조와 이전 노드, basis.source를 실제 입력의 허용 ID에 결속한다. UNKNOWN에 근거가 없으면 basis=[]가 허용됨을 명시한다.
4. 누락 노드·잘못된 참조·SAME 상태 충돌을 함께 진단하고 인용 오류는 정확한 필드 경로를 알려준다.
   SUPPORTED는 원문 지지 여부이고 SAME은 이전 그래프 전체와 동일함을 뜻한다. 새 노드가 생기거나 기존 노드가 사라지면 SAME이 아니다.
5. 원래 컴파일러를 기존 한 번의 보완 안에서도 실행한다. 원래 저장 시 컴파일 검증도 그대로 유지한다.
   보완 횟수/기한을 늘리지 않고, 서버가 의미·그래프·ID·상태를 자동 대체하지 않는다.

실제 실험 — 실패를 지우거나 한 번의 성공 실행처럼 합치지 않음
1220: 1219후보로 정규화A→누적A 최초/보완→정규화B, 4물리.
  정규화 두 건 모두 최초 응답으로 저장. A3/B7=입력10구간 및 인용35좌표가 원문과 일치했다.
  첫 누적은 관찰의 요소ID를 제안 그래프ID와 혼동해 실패. 두 번째 누적은 의존성 때문에 실행하지 않았다.
1222: 원래 정규화 두 결과를 읽기 전용 복사해 누적만 이어 실행, 2물리.
  그래프 ID 혼동은 사라졌지만 UNKNOWN인 식별자 관찰의 ID를 규정 원문 ID로 인용해 최초/보완 모두 실패했다.
1224: 원문 ID enum과 오류 경로를 보강한 후보로 다시 이어 누적, 3물리.
  A 최초는 node.text와 statement값 차이로 거절. 기존 보완에서 수정해 첫 판본 저장/컴파일 성공.
  A의 원래 조건형 의견2개는 CONTRADICTED, 식별자 관찰은 UNKNOWN·빈 근거로 보존했다. 새 EFFECT는 취득·보유 의무를 유지한다.
  3노드/2간선/1목적 경로. scope·delegation·exceptions 검토 슬롯3개가 미확인이라 preview는 PARTIAL이다.
  B 최초는 새 n-004~007만 제안하고 기존 n-001~003을 누락했으면서 removed_nodes=[]와 relation=SAME을 썼다.
  서버가 두 번째 저장을 거절해 첫 판본과 원래 관찰은 유지됐다. B 보완은 전송 전에 호출 예산 소진으로 중단됐다.
  그 보완이 실제 공급자로 나간 것은 아니다. 실험 실행기의 일반 예외 분류가 UNKNOWN으로 남았지만 before=after=3이며
  model_call_budget_exhausted가 확인돼 별도 정정 영수증에서 PRE_DISPATCH_BUDGET_EXHAUSTED로 분류했다. 원기록은 보존했다.
1225: 위 SAME/이전노드 누락 충돌을 한꺼번에 알려주는 마지막 진단·지시 보강. 실모델0, 새3계약 및 누적106계약 통과.

아직 남은 내용 문제
정규화는 정확한 원문 구간 연결을 통과했지만 의미 분류의 정답 인증은 아니다.
A에서 구조값 '1'을 reason/purpose로 기재한 관찰이 있어, 미기록 이유/목적 보존이라는 별도 내용 기준은 미통과다.
B의 세 취득 기준은 미채택 제안에 있었으나, 두 번째 누적 판본/컴파일 성공으로 계산하지 않는다.
따라서 정규화와 누적의 전체 의미/상태 기준을 통과했다고 보고하지 않는다. 지식 내용 승인/게시도 수행하지 않았다.

호출·시간·비용
총{calls}회, 모두 Parasail의 stop/비어 있지 않은 JSON. error/null0, 공급자 전환0, 공급자 응답 불명 UNKNOWN0.
세 동결 배치 실행시간 합계 약{seconds:.3f}초, 보고 비용{cost:.8f}달러. 속도 효과를 비교한 실험은 아니다.
원문5구간·저장 판단2개·용어9후보는 승인된 기존 자료 그대로다. 새 검색/007·009 전체 재실행은 없다.
모든 원본 응답/실패 JOB/정규화/원문/실험 저장소를 보존했다. 원래1220 저장소 해시도 후속 전후 동일하다.

입력 크기와 호환
원래 정규화 profile schema159226자와 누적61329자는 그대로 보존했다.
실제 입력별 정규화 전송 schema는 A11654/B11887자였다. 원문 ID 결속 누적 사전 schema는13938자였다.
입력 구간/관찰/이전 노드 수에 따라 달라지므로 고정 크기나 토큰/속도 효과로 일반화하지 않는다.
원래 profile.py/profile_schema.py/assembly_ir.py/assembly_compiler.py 바이트와 승인 프로필 binding, canonical 저장 형식은 동일하다.
용어 후보 본문 자체의 길이는 이번에 줄이지 않았다.

메인 및 검증
MAIN122 / {RELEASE}. MAIN121 대비 제품3+pin31=34변경, 다른453파일 보존.
487파일의 후보·작업·실제 선택 서비스 해시가 같다. 데이터 generation/모델/온톨로지 기본OFF는 그대로다.
최종 후보: 상태3+원문6+그래프16+정규화34+기존도메인47=106검사 통과.
기존47개는 MAIN121 기준과 항목별 동일하며 새 회귀0이다. 기준은1219에 저장한 동일 MAIN121 검증을 재사용했다.
후보 서비스{cc}조건, 선택 서비스 OFF/ON미설정/ON빈DB {nc}조건·HEALTH3·모의HTTP3 통과.
이전1219/1221의 준비 코드 실수(상속pin 집계, JOB 필드명), 문서 준비/lineage 오류는 각 ADR에 실패를 보존하고 정정했다.
마지막1225의59새/누적 계약과47기존 검사는 첫 실행 모두 통과했다.
최종 ADR검사 통과, 전체graph 기존16오류 동일·새0. 법률품질 인증없음.

반영 범위
로컬 MAIN만 선택했다. GENOS 현장 배포·Git·메일은 없다.
MAIN121 / regex-wire-repair-20261029-r1를 롤백으로 보존했다. 데이터/원래 저장 reader/canonical 형식은 동일하다.
장기 실행 중인 기존 프로세스는 새로 시작해야 새 선택 포인터를 읽는다.

근거
04_EXPERIMENTS/ADR/ADR-1219-normalization-coverage-contract
04_EXPERIMENTS/ADR/ADR-1220-normalization-accumulation-live
04_EXPERIMENTS/ADR/ADR-1221-accumulation-reference-contract
04_EXPERIMENTS/ADR/ADR-1222-accumulation-reference-live
04_EXPERIMENTS/ADR/ADR-1223-accumulation-source-contract
04_EXPERIMENTS/ADR/ADR-1224-accumulation-source-live
04_EXPERIMENTS/ADR/ADR-1225-cumulative-authoring-main
09_ARTIFACTS/AUDITS/20261029-cumulative-authoring-main122/completion.json
'''
(OUT/'수정과_실제실험_결과.txt').write_text(report)
note=f'''<!-- AUTHORING_CONTRACT_MAIN122_20261029 -->
**2026-10-29 — 정규화·누적 계약 MAIN122:** [수정·실험 TXT](09_ARTIFACTS/AUDITS/20261029-cumulative-authoring-main122/수정과_실제실험_결과.txt) · [ADR1225](04_EXPERIMENTS/ADR/ADR-1225-cumulative-authoring-main/README.md). 닫힌입력coverage/상태별참조·정확quote+출현순서→좌표조립/원본영수증, 관찰·이전/제안그래프·원문ID구분/enum, 동시참조·SAME오류진단, 원래컴파일을기존보완안에연결. **MAIN122 / {RELEASE}, 487파일·제품3+pin31=34변경·후보/작업/선택동일.106계약통과·기존47동일/새0, 후보{cc}·선택{nc}/HEALTH3/모의HTTP3통과.** 실제1220/1222/1224 **합계9물리/stop9/error-null0·정규화2/2(10구간/35좌표)·누적1/2·PARTIAL컴파일1**, 약{seconds:.3f}초·보고{cost:.8f}달러. A취득의무정정/원래관찰보존, B이전노드누락+SAME로거절·보완전예산중단. raw UNKNOWN1은물리before=after인전송전예산오류이며별도정정·외부UNKNOWN0. **전체실험Rejected**, A구조값1을reason/purpose로분류한별도의미문제남음. 마지막SAME진단보강실모델재시험0. 원래profile/compiler/canonical저장·데이터/모델/기본OFF 유지, 승인/게시/GENOS/Git/메일없음. MAIN121롤백·법률품질인증없음. 준비/fixture/문서실패보존정정·최종후보첫106통과. ADR최종통과·graph기존16/새0.
<!-- /AUTHORING_CONTRACT_MAIN122_20261029 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- AUTHORING_CONTRACT_MAIN122_20261029 -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1225 정규화·누적 계약 누적](ADR-1225-cumulative-authoring-main/README.md) — MAIN122·106계약·새회귀0, 실제9회·정규화2/2·누적1/2·전체미통과.\n');p.write_text(''.join(lines))
print('MAIN122 verified;',nc,'selected checks; whole experiment incomplete retained')
