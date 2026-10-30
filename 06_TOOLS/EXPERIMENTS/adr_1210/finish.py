from common import *
f=read(DES/'freeze.json');b=read(DES/'baseline.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==120 and active['release_id']==RELEASE and release['files']==f['files']
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
consumers={m:read(ART/f'consumer-active-{m}.json') for m in ('off','on','db')};assert all(v['passed'] for v in consumers.values())
old={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-cumulative-main119-input-audit/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
new={x for x in (OUT/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')};assert old==new,(new-old,old-new)
reg=read(ART/'regression-comparison.json');nc=sum(len(v['checks']) for v in consumers.values());cc=len(read(ART/'consumer-candidate-off.json')['checks']);sizes=read(ART/'schema-sizes.json')
put(OUT/'completion.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'serving_files':487,'changed_files':37,'product_config_files':6,'pin_files':31,'feature_contracts':375,'new_contracts':27,'excluded_fixture':1,'regression':reg,'selected_service_checks':nc,'selected_service':{k:bind(ART/f'consumer-active-{k}.json') for k in consumers},'candidate_service_checks':cc,'all_working_and_selected_files_equal':True,'global_graph_existing_errors':len(new),'global_graph_new_errors':0,'external_model_calls':0,'quality_certified':False,'genos_deployed':False,'schema_sizes':sizes,'schema_shortening_implemented':True,'rollback_release':b['active']['release_id'],'rollback_caveat':'MAIN119 has the same journal reader and data schema; new schema_projection receipt is additive. Older MAIN118 compression incompatibility caveat is unchanged.'})
report=f'''스키마 공통화 구현·검증·MAIN120 반영 — 2026-10-29

결과
로컬 MAIN120 / {RELEASE}를 공식 prepare/apply로 선택했다.
후보·작업·실제 선택 service의487파일이 모두 같은 해시다.
MAIN119대비 제품6+pin31=37파일 변경, 다른450파일 보존.
새 실모델0·GENOS 현장 배포0·Git commit/push0·메일0.

스키마 크기
단위: 유니코드 compact JSON 문자, sort_keys=True·ensure_ascii=False.
                  이전      이후       감소
도메인 NORMALIZE   159226     10136      93.63%
도메인 ACCUMULATE   61329     12976      78.84%
두 스키마 모두 모든 $ref를 펼치면 원래 구조와 정확히 같다.
사용자 원문/messages·용어 후보 상세·조사 이력은 같은 내용이며 위 수치는 스키마 부분이다.
스키마 줄이기가 전체 입력93.63% 감소나 토큰/속도 개선을 뜻하지 않는다.
일반RAG의 과거45개 전송은 이미 공통화되어 재적용 변화0. 앞으로 생성되는 정의 이름은 짧아진다.
과거49개 중3도메인+1미채택advisory는 읽기 전용 공통화 진단에서도 동등했다. advisory를 제품에 채택한 것이 아니다.

수정한 경로와 소비자
1. legal_agent/wire_schema.py: 동일 구조를 한 번 정의하고 결정적 짧은 D0… 참조를 쓴다. 기존 참조 scope가 있으면 원본을 유지한다. enum/const/default의 값은 schema로 순회하지 않는다.
2. legal_agent/local_gemma.py: 기존 공급자 호환 변환 뒤 공통 project_request를 사용한다.
3. legal_agent/transport.py: GENOS 일반/stream HTTP 직전에 사본을 공통화하고 성공/실패 receipt에 원래 입력과 실제 wire schema hash/문자 수를 붙인다.
4. ontology_work/authoring_model.py: 도메인 NORMALIZE/ACCUMULATE 실제 요청을 공통화·저장하며 기존 DomainWorkflow가 원래 output_schema로 검증한다.
5. ontology_work/configuration.py: 기존 ontology 생성 경로도 같은 전송 경계를 사용한다.
6. legal_agent/read_judgment_final.py: 동일 제약인 USE/CONDITIONAL 분기를 합친다. 필요한 NOT_USED change_review·ID별 분할·claim 최소개수 등은 동일하다.
서버가 원문을 추가하거나 LLM 판단을 보정하는 기능을 넣지 않았다.
필요ID·claim/gap·복수 판단/복수 원문·범위 선택·권한·원문/판단 이력 보존 계약을 유지한다.

전송 경계
RAG 원래 생성 스키마 → 기존 축약/번호 변환 → 공급자 호환 변환 → 최종 공통참조 전송 → 기존 출력 복원·원래 schema/의미 검증.
중간 minimal_output 변환기에 새로운 $ref 해석 책임을 넣지 않는다.
GENOS transport receipt의 validation_schema_sha256는 기존 호환변환 이후 transport에 들어온 schema를 뜻한다. canonical 생성 스키마는 기존 gateway 기록에 남는다.
도메인 요청은 전송 직전 사본만 공통화하며 원래 profile.output_schema와 원문 검증을 유지한다.
strict=true를 유지했으며 JSON-object 전환은 하지 않았다. 새 재시도나 추가 모델 보완도 없다.

검증
기존 누적기능348통과·준비검사1제외 + 신규27통과 = 고유375계약 통과.
신규 검사: 원본 불변/완전복원/참조 scope/리터럴/검증 결과, GENOS 로컬 HTTP·stream·UNKNOWN, 도메인 정상·보완1회·재거절·UNKNOWN·HTTP429, 최종 판단540조합.
최종 분기는별도24구성(0~3판단/목적없음·첫항목·전체/claim형식여부)에서 합친 분기를 다시 나누면 MAIN119 전체 스키마와 정확히 같다.
저장49개 요청 모두 스키마 동등과 schema 외의 요청 불변 확인. 과거 출력을 새 모델 통과나 법률 품질 근거로 세지 않았다.
동일257회귀: MAIN119/후보 각각231통과·기존26실패, 항목별 동일·새실패0.
후보 서비스{cc}조건, 선택 service OFF/ON미설정/ON빈DB {nc}조건·HEALTH3·모의HTTP3 통과.
선택된 schema 함수·실제 코드/프로필/데이터/예산/공급자·출처표시/저장 reader를 확인했다.
ADR1210 최종검사 통과, 전역 graph 기존{len(new)}오류 동일·새0.

보존한 실패
최초 freeze 준비 코드가 mutable 후보 JSON을 불변 산출물 도구로 덮어쓰려던 오류, freeze 메타가 만들어지기 전 실행기 오류를 보존했다.
첫 신규검사26통과/1실패는 로컬 서버 fixture에 없는 sse 모드 지정이었다. 기존 stream 모드·release 이벤트로 고쳐 해당1개만 통과했다.
제품은 처음 동결한 rev001과 동일하며 통과 기준을 낮추지 않았다. 기존 회귀26실패는 해결로 표시하지 않는다.

미검증과 운영
실공급자/GENOS 현장 grammar의 $ref 처리, 토큰·속도·비용, 007/009 법률 내용 개선은 미검증이다. 긴입력이 과거 UNKNOWN의 원인이라는 결론도 내리지 않았다.
새 프로세스가 선택 포인터를 읽어야 한다. 장기 실행 중인 서비스/GENOS는 별도 재시작·현장 반입이 필요하다.
이전 MAIN119 / cumulative-contracts-20261029-r1를 보존했다. 실패 시 공식 rollback --confirm-main으로 선택을 복귀한다.
MAIN119와 저장 reader·데이터 형식은 같고 schema_projection은 부가 metadata다. MAIN118 이하 reader의 압축기록 제한은 기존대로 유지한다.

근거
04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/README.md
04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/artifacts/design/integration.json
04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/artifacts/run-001/result.json
09_ARTIFACTS/AUDITS/20261029-schema-factor-main120/completion.json
'''
(OUT/'구현과_검증결과.txt').write_text(report)
note=f'''<!-- SCHEMA_FACTOR_MAIN120_20261029 -->
**2026-10-29 — 검증 계약 보존 스키마 공통화 MAIN120:** [구현·검증 TXT](09_ARTIFACTS/AUDITS/20261029-schema-factor-main120/구현과_검증결과.txt) · [ADR1210](04_EXPERIMENTS/ADR/ADR-1210-strict-schema-factor-main/README.md). 사용자 요청으로 **MAIN120 / schema-factor-20261029-r1** 선택. 도메인 authoring·GENOS 일반/stream·기존 local transport의 마지막 전송 사본에 공통화·짧은 정의명 적용, 최종 USE/CONDITIONAL 동등분기 병합. **NORMALIZE159226→10136자(93.63%)·ACCUMULATE61329→12976자(78.84%), 정확복원.487파일·제품6+pin31=37변경, 작업/후보/선택동일.375계약(기존348+신규27)통과·1제외, 동일257회귀231통과/기존26실패·새0.** 원래strict/validator·NOT_USED change_review·필요/claim/gap·복수범위 유지, 중간codec 이후 공통화. 저장49스키마 동등·기존참조45재변환0, 최종540판정조합·24구성구조동등. 후보{cc}·선택{nc}(OFF/ON미설정/ON빈DB)·HEALTH3/모의HTTP3통과. 준비메타·stream fixture1실패 보존/정정, 동결제품불변. **새실모델0·속도/토큰효과/현장GENOS grammar미검증·007/009재시험0·GENOS/Git/메일없음·데이터/모델/온톨로지기본OFF유지.** 용어후보/이력본문은 후속, UNKNOWN원인확정아님. ADR최종통과·graph기존{len(new)}오류/새0. MAIN119롤백보존·동일저장reader, 법률품질인증없음.
<!-- /SCHEMA_FACTOR_MAIN120_20261029 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- SCHEMA_FACTOR_MAIN120_20261029 -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1210 스키마 공통화](ADR-1210-strict-schema-factor-main/README.md) — MAIN120·487파일·375계약·새회귀0·도메인스키마93.63%/78.84%감소·실모델0.\n');p.write_text(''.join(lines))
print('MAIN120 verified;',nc,'selected service checks; report written; no new models')
