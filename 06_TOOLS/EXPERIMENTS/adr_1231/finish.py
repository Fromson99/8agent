from common import *
b=read(DES/'baseline.json');f=read(DES/'freeze.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==123 and active['release_id']==RELEASE
assert release['files']==f['files'] and all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
assert sha(ROOT/release['data_path']/'manifest.json')==b['manifest']['data_manifest_sha256']
services=[read(ART/f'consumer-active-{mode}.json') for mode in ('off','on','db')]
assert all(v['passed'] for v in services)
old={v for v in (ROOT/'09_ARTIFACTS/AUDITS/20261029-main122-authoring-revalidation/adr-graph.log').read_text().splitlines() if v.startswith('ERROR:')}
new={v for v in (OUT/'adr-graph.log').read_text().splitlines() if v.startswith('ERROR:')}
assert len(old)==16 and new==old,(len(old),len(new),new-old)
a=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1228-source-first-authoring-live/artifacts/audit.json');z=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1230-source-meaning-evidence-live/artifacts/audit.json')
total=a['calls']+z['calls'];assert total==9
cost=a['reported_cost_usd']+z['reported_cost_usd'];seconds=a['seconds']+z['seconds']
report=f'''잘못된 판단 지지·없는 이유/목적 수정과 실제 실험
2026-10-30 / MAIN123 / {RELEASE}

결론
기존 판단을 보지 않는 원문 독립 분석, 원래 이유/목적의 부재 보존, 해석과 인용의 분리, 최초 누적의 불가능한 SAME 상태 제외를 구현하고 MAIN123에 반영했다.
특정 법률·조문·사례·기대 정답을 제품 코드에 넣지 않았다. 이유/목적 단어 whitelist도 없다.
의미 해석/역할 분류는 모델이 담당하고 서버는 선택된 원문·인용·상태·그래프 연결을 검증한다.
실제9호출에서 기록에 없는 이유/목적은2개기록 모두 보존했고, 잘못된 판단에 대한 지지는 실제 누적 제안에서 SUPPORTED→PARTIAL로 바뀌며 의무/행위 불일치를 지적했다.
하지만 첫 누적의 식별자 관찰에 SAME이 남아 저장은0건이다. 두번째 누적도 실행하지 못했다. 마지막 SAME 요청 제한은 오프라인84계약으로 검증했으며 새실모델로 재확인하지 않았다.
전체 정규화→누적 성공 또는 법률 의미 정확성 인증으로 보고하지 않는다.

실험의 범위
CM007에서 저장했던 판단2조각을 공개원문5구간/용어후보9개와 대조하는 도메인 작성 경로다.
CM007/009 질문 전체 RAG 실행이 아니다. 본문 내용은 정답으로 고쳐 정규화하지 않고 원래 오답 그대로 보존한다.
원래 판단의 기록 보존과, 그 판단을 지식으로 지지하는 판정은 별개다.

확인한 문제
1. 기존 누적 요청은 잘못된 관찰을 본 상태에서 원문 해석·지지 판정·규칙 그래프를 함께 생성했다. 원래 판단을 정당화하는 설명을 막을 독립 원문 분석과 의미 연결 검사가 없었다.
2. 정규화 statement/reason/purpose가 같은 PRESENT 구조였고, 정확 인용 존재만 검사했다. 본문이나 식별자를 이유/목적 칸에 복사해도 통과했다.
3. 보완 지시가 기존 의미 보존을 요구해, 원래 기록 보존과 잘못된 해석 수정의 경계가 불명확했다.
4. 새 원문 분석에서도 해석문과 정확 인용을 같은 문자열로 요구해 실패했고, 첫 오류만 알려 나머지 잘못된 인용이 보완에 남았다.
5. 이전 묶음이 없는데도 요청 스키마가 SAME을 허용했다. 서버는 이를 거절하지만 모델이 선택하고 나서야 보완이 시작됐다.
이 구조와 실제 출력은 확인했지만, 단일 알려진 사례 실행이므로 독립 분석만의 인과효과·일반 개선율을 증명한 것은 아니다.

수정
- SOURCE_ANALYSIS: originals/profile_hash만 입력한다. 과거 관찰·기존 그래프·용어후보·평가정답을 전달하지 않는다.
- 원문 분석 각 부분은 해석 text와 정확 quote를 나눈다. 모든 잘못된 인용 경로를 함께 보완에 전달한다.
- 누적 모델은 source_analysis의 규범/조건을 선택하고 서버는 선택된 행위 전체·양태·조건을 canonical 그래프에 조립한다. 모순된 SUPPORTED/의미불일치를 거절한다.
- recorded_reason/recorded_purpose는 없으면 null, 실제 원기록 역할 증거가 있을 때만 작성한다. 저장은 기존 NOT_RECORDED/PRESENT로 유지한다.
- 실제 필드명과 인용 위치만 검증한다. 문장의 이유/목적 의미는 모델이 분류하며 고정 단어 목록으로 판정하지 않는다.
- 최초 누적의 relation 선택지에서 SAME을 제외했다. 이전 묶음이 있으면 SAME을 제공하되 원래 서버의 전체 그래프 동일성 검사를 유지한다.
- 원문 분석/누적 보완은 잘못된 해석 연결을 수정할 수 있고 원래 관찰은 고쳐 쓰지 않는다.

실제 실행
ADR1228: 실제5호출. 새정규화A최초/B보완으로2개 저장, 입력3+7=10구간/정확좌표25개 확인.
관찰3개의 reason/purpose 총6필드를 모두 NOT_RECORDED로 저장했다. 이전1226의6개 PRESENT 복사 오류는 이번에 재현되지 않았다.
독립 원문 분석이 취득/보유를 OBLIGATION으로 읽었으나 해석문을 인용으로 제출해 최초·보완 거절. 누적0.
ADR1230: 동일 정규화2개를 그대로 검증·복사해 재사용, 새정규화0/실제4호출.
독립 분석의 최초 생략기호 인용2개는 정확 인용 검사로 거절했고 보완에서 수정됐다.
누적 최초 제안은 오답을 PARTIAL로 판단하고 양태/행위 MISMATCH를 기록했다. 규범연결에 DEFINITION을 섞어 거절, 보완은 이를 고쳤지만 식별자 관찰의 SAME을 유지해 최종 거절됐다.
원문분석과 제안 그래프에는 취득·보유 두 행위가 유지됐다. 그러나 정식저장·컴파일을 통과한 모델 결과는 아니다.
두번째 누적은 첫 판본이 없어 미실행이다. 지식승인·게시0.
총{total}물리, 정상JSON9/error-null0/UNKNOWN0, Parasail9/공급자전환0, {seconds:.3f}초·보고비용${cost:.8f}.
두 실행 모두 자원중단0/호스트swap증가0. 원래 실패와 요청/응답·저장 관찰을 무손실 보존했다.

오프라인 검증과 반영
최종 ADR1231 후보489파일. 새37+기존47=84계약 통과, 기존 범위 새실패0.
후보서비스56, 실제 선택서비스 OFF/ON미설정/ON빈DB 각63=189조건, HEALTH3/모의HTTP3 통과.
제품4(기존workflow/accumulation2+새모듈2)+pin31=35변경. 나머지454파일 보존. 작업/후보/선택489바이트 동일.
profile.py/profile_schema.py/assembly_ir.py/assembly_compiler.py는 이전과 동일해 승인프로필/기존저장 형식을 유지한다.
저장된 실제 응답의 별도 사본에서 SAME만NEW로 바꾼 진단은 나머지 검증·컴파일을 통과했다. 이는 모델 결과 재판정이나 실제 저장 성공이 아니며 DB/원래응답 변경0이다.
해당 진단 최초 준비는 메모리상 공유schema와 실제 저장profile 차이로 실패했고, 실제 저장profile을 읽은 정정 검사를 별도 보존했다.
1227의 초기문법/runner준비/fixture기대값 실패 및 모든 실제 실패도 보존했다. 마지막 후보84검사는 첫 실행 통과다.
ADR1227/1228/1229/1230/1231 최종검사 통과. 전역graph 기존16오류 동일·새0.

남은 한계
마지막 최초상태 요청수정본의 실제 저장과 두번째 누적은 재검증이 필요하다. 승인한9호출을 넘어 추가하지 않았다.
독립 원문 분석 자체의 의미 오류까지 서버가 보장하지 않는다. 예를 들어 원문의 위임문을 DEEMING으로 분류한 부분도 검토 대상으로 남는다.
이유/목적의 역할 증거가 실제로 존재해도 그 의미 분류는 모델 책임이다. 임의의 문구·법률별 정답 분기를 추가해 숨기지 않았다.
원문 독립 분석은 누적당 최소1호출을 추가한다. 동일 완료 작업은 재사용하지만 전체 지연/입력/비용이 줄었다고 주장하지 않는다.
MAIN123은 기술 계약 검증에 따른 반영이다. 실제 전 과정 성공/법률품질 인증이 아니다.
MAIN122 롤백 보존. 데이터/모델/온톨로지기본OFF 유지. GENOS 현장 배포·Git·메일 없음.

주요 근거
04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main/README.md
04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main/artifacts/checks-first.json
04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main/artifacts/saved-response-diagnostic-stored-profile.json
04_EXPERIMENTS/ADR/ADR-1228-source-first-authoring-live/artifacts/audit.json
04_EXPERIMENTS/ADR/ADR-1230-source-meaning-evidence-live/artifacts/content-review.json
08_DEPLOYMENT/RELEASES/{RELEASE}/release.json
'''
(OUT/'수정과_실제실험_결과.txt').write_text(report)
put(OUT/'completion.json',{'main':active,'files':489,'changed':35,'technical_checks':84,'candidate_service_checks':56,'active_service_checks':sum(len(v['checks']) for v in services),'actual_calls':9,'normalized_saved':2,'actual_drafts_saved':0,'second_accumulation_tested':False,'generated_wrong_support_corrected':True,'reported_cost_usd':cost,'actual_final_state_fix_retested':False,'working_candidate_selected_exact':True,'new_graph_errors':0,'quality_certified':False})
note=f'''<!-- SOURCE_SEMANTICS_MAIN123_20261030 -->
**2026-10-30 — 원문 독립분석·원기록 이유/목적 MAIN123:** [수정·실제실험 TXT](09_ARTIFACTS/AUDITS/20261030-source-semantics-main123/수정과_실제실험_결과.txt) · [ADR1231](04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main/README.md). **MAIN123 / {RELEASE}**, 원문만분석→관찰대조·해석text/정확quote분리·선택행위/양태/조건조립·원기록reason/purpose nullable/역할증거·base없음SAME요청금지. 법률/조문/정답/역할단어whitelist없음. **489파일·제품4+pin31=35변경·84계약/후보56/선택189(3설정)/HEALTH3/모의HTTP3통과**, 작업/후보/선택동일·기존47새실패0·canonical프로필4파일불변. **실제1228 5+1230 4=9회: 새정규화2(10구간25좌표)·부재reason/purpose6필드보존, 후속오답SUPPORTED→PARTIAL/양태행위MISMATCH는실제제안에서확인. 하지만식별자관찰SAME/base없음거절→저장0·두번째누적미실행.** 첫원문분석인용혼동/후속생략인용·비EFFECT연결/모든실패보존. 마지막SAME생성제한은오프라인검증만·새실모델0. 진단사본의상태만정정후검증/컴파일통과는실제성공아님. 정상JSON9/error-null0/UNKNOWN0/전환0, {seconds:.3f}초/${cost:.8f}·스왑증가0. 독립분석자체오류/추가호출비용남음·법률품질인증없음. MAIN122롤백/데이터/기본OFF유지·전체007/009/GENOS/Git/메일없음. ADR5개최종통과·graph기존16/새0.
<!-- /SOURCE_SEMANTICS_MAIN123_20261030 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;s=p.read_text();assert heading in s and '<!-- SOURCE_SEMANTICS_MAIN123_20261030 -->' not in s;p.write_text(s.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1231 원문 독립분석·원기록 역할 MAIN123](ADR-1231-source-semantics-state-main/README.md) — 기술84/선택189, 실제9회·부재역할보존/오답지지변경 확인·저장0/두번째누적미검증. 선행1227·1228·1229·1230 실패/후보 보존.\n');p.write_text(''.join(lines))
print('MAIN123 verified; report saved; actual9 with draft0 explicitly preserved')
