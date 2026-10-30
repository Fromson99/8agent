from common import *
f=read(DES/'freeze.json');b=read(DES/'baseline.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==121 and active['release_id']==RELEASE and release['files']==f['files']
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
consumers={m:read(ART/f'consumer-active-{m}.json') for m in ('off','on','db')};assert all(v['passed'] for v in consumers.values())
old={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-schema-factor-main120/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
new={x for x in (OUT/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')};assert old==new,(new-old,old-new)
reg=read(ART/'regression-comparison.json');nc=sum(len(v['checks']) for v in consumers.values());cc=len(read(ART/'consumer-candidate-off.json')['checks']);sizes=read(ART/'schema-sizes.json')
live=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1218-regex-wire-domain-live/artifacts/audit.json')
put(OUT/'completion.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'serving_files':487,'changed_files':33,'product_files':2,'pin_files':31,'feature_contracts':402,'excluded_fixture':1,'regression':reg,'selected_service_checks':nc,'selected_service':{k:bind(ART/f'consumer-active-{k}.json') for k in consumers},'candidate_service_checks':cc,'all_working_and_selected_files_equal':True,'global_graph_existing_errors':len(new),'global_graph_new_errors':0,'diagnostic_physical_calls':22,'actual_authoring_physical_calls':4,'actual_authoring_stop':4,'actual_authoring_error_null':0,'normalization_saved':0,'quality_certified':False,'genos_deployed':False,'schema_sizes':sizes,'rollback_release':b['active']['release_id']})
report=f'''error/null 원인 분리·수정·MAIN121 반영 — 2026-10-29

결론
ID 형식 정규식의 큰 가변 반복 범위 {{0,159}}가 현재 외부 공급자의 구조화 출력 경로에서 error/null을 일으켰다.
동일한 합성 입력에서 정규식만 제거하면 성공했고, 원래 정규식은 아주 작은 스키마에서도 실패했다.
반복 범위를 {{0,32}}로 줄이거나 별표 반복과 별도 길이 제한을 사용하면 성공했다.
공급자 내부 오류 로그와 엔진 버전은 제공되지 않아, 구체적인 내부 결함/설정까지 확인한 것은 아니다.

수정
원래 ID 정규식을 삭제하거나 허용 범위를 넓히지 않았다.
전송 사본에서만 {{0,159}}를 같은 문자 집합의 {{0,32}} 네 개와 {{0,31}} 한 개로 연결했다.
0~32 + 0~32 + 0~32 + 0~32 + 0~31 = 정확히 0~159다. 첫 영문자와 앵커도 그대로다.
원래 profile_schema와 서버 검증, strict=true, 원문/권한/필요ID/claim/gap/복수 범위 계약은 유지했다.
최종 wire_schema 경계를 쓰는 로컬/GENOS 일반·stream/도메인 경로에 적용되며, 해당 패턴 외의 정규식은 변경하지 않는다.
GENOS 현장 실행은 하지 않았다.

함께 고친 오류 처리
authoring이 HTTP200의 finish_reason=error와 JSON처럼 보이는 본문을 성공으로 처리할 수 있던 경로를 차단했다.
비정상 종료·top-level/choice error·refusal은 원본 응답과 영수증을 보존하고 기존 실패 경로로 종료한다.
자동 재시도나 모델 보완 횟수는 늘리지 않았다. UNKNOWN 정책도 그대로다.

실제 모델 결과
합성 원인 분리: ADR1213/1215/1216, 논리20조건·물리22요청(확정429 전환2 포함).
실제 입력: 승인된 공개 규정5구간·저장 판단2개·용어 후보9개, ADR1218.
수정 후 실제4요청 모두 Parasail에서 finish_reason=stop 및 비어 있지 않은 JSON 응답을 받았다.
error/null 0회, UNKNOWN 0회, 공급자 전환0회, 자원 중단0회.
실행 약318.005초, 보고 비용0.059628달러. 합성 진단 보고 비용0.00092884달러는 실패/429 미보고 비용을 제외한 값이다.
실제 요청4개의 schema를 역변환·펼친 결과는 원래 schema와 정확히 일치했고 messages/context도 동일했다.

아직 남은 별도 문제
정상 JSON 응답이 곧 정규화 성공을 뜻하지는 않는다. 정규화0/2·누적/컴파일0·지식 승인/게시0이다.
A 최초/보완: observation ID를 연결해 놓고 coverage 상태를 NON_JUDGMENT로 표시해 원래 상태 일관성 검증에서 거절됐다.
오류 문구 USED coverage needs observation references는 양방향 충돌에 같이 사용되므로, 이번 A를 ID 누락으로 해석하면 틀린다.
B 최종 보완: coverage가 입력 raw index의 모든 구간을 포함하지 않아 거절됐다.
이는 공급자 error/null과 구분되는 후속 내용 연결 검증 문제다. 실패를 성공으로 바꾸거나 검증을 풀지 않았다.
별도실제실험1218은 누적까지의 전체 성공 기준을 충족하지 못해 Rejected로 기록했다.
이번 MAIN 승격은 기술계약과 상태/소비 경로 검증에 근거하며 법률품질 인증이 아니다.

기술 검증과 MAIN
새/보존 전송 계약54 + 기존 기능348 = 402개 통과, 기존 준비 검사1개 제외.
동일257회귀: MAIN120/후보 각각231통과·기존26실패, 항목별 동일·새 실패0.
첫 로컬HTTP 검사3개는 실행 권한 때문에 socket 생성이 거절됐다. 같은 코드/검사를 해당 권한으로 실행해 통과했고 원래 실패 로그를 보존했다.
처음 서비스검사는 제한된 실행에서 대기해 해당 프로세스만 종료·기록했다. 같은 후보/검사에 로컬 통신 권한을 적용한 뒤45조건을 통과했다.
후보 서비스{cc}조건, 선택 서비스 OFF/ON미설정/ON빈DB {nc}조건 및 HEALTH3/모의HTTP3 통과.
MAIN121 / {RELEASE}, 후보·작업·실제 선택 서비스487파일의 해시가 같다.
제품2+pin31=33파일 변경, 다른454파일 보존. 원문/데이터 generation/모델/온톨로지 기본OFF 유지.
ADR1217 최종검사 통과, 전역 graph 기존{len(new)}오류 동일·새0.

스키마 크기
NORMALIZE: 원래159226자, MAIN120 wire10136자, 수정 wire10784자.
ACCUMULATE: 원래61329자, MAIN120 wire12976자, 수정 wire13629자.
동등 정규식 표현 때문에648/653자가 늘지만, 공통화 전보다 여전히 크게 작다.
누적 wire는 사전검사만 했고 실제 누적 모델 호출은 없다. 문자 수를 토큰 수나 속도 효과로 환산하지 않는다.

운영 범위와 롤백
로컬 MAIN121 선택 및 실제 서비스 진입점을 확인했다. GENOS 현장 배포·Git·메일은 수행하지 않았다.
MAIN120 / schema-factor-20261029-r1를 롤백 대상으로 보존했다. 기존 저장 reader와 데이터 형식은 같다.
기존 장기 실행 서비스는 새 프로세스로 선택 포인터를 읽어야 한다.

근거
04_EXPERIMENTS/ADR/ADR-1213-schema-error-cause-isolation/README.md
04_EXPERIMENTS/ADR/ADR-1215-schema-regex-format-isolation/README.md
04_EXPERIMENTS/ADR/ADR-1216-schema-ref-quantifier-isolation/README.md
04_EXPERIMENTS/ADR/ADR-1217-bounded-regex-wire-repair/README.md
04_EXPERIMENTS/ADR/ADR-1218-regex-wire-domain-live/README.md
09_ARTIFACTS/AUDITS/20261029-regex-wire-repair-main121/completion.json
'''
(OUT/'원인과_수정_검증결과.txt').write_text(report)
note=f'''<!-- REGEX_WIRE_MAIN121_20261029 -->
**2026-10-29 — error/null 원인 분리·동등 정규식 수정 MAIN121:** [원인·수정 TXT](09_ARTIFACTS/AUDITS/20261029-regex-wire-repair-main121/원인과_수정_검증결과.txt) · [ADR1217](04_EXPERIMENTS/ADR/ADR-1217-bounded-regex-wire-repair/README.md) · [실제1218](04_EXPERIMENTS/ADR/ADR-1218-regex-wire-domain-live/README.md). 합성20조건/22물리로 REF 정규식의 **{{0,159}} 큰 가변반복 실패**를 분리했다. 작은스키마에서도 원형실패, count32/별표+길이제한 성공. 내부엔진/로그 미확인. 전송사본에서 정확히동등한32+32+32+32+31로변환하고 원래schema/validator/strict유지, error+JSON본문도 미완료거절·원본보존. **MAIN121 / regex-wire-repair-20261029-r1, 487파일·제품2+pin31=33변경·후보/작업/선택동일.402계약통과·1제외, 동일257회귀231통과/기존26실패·새0, 후보{cc}·선택{nc}/HEALTH3/모의HTTP3통과.** 승인된실제입력4요청 **stop/JSON4·error/null0·UNKNOWN0·Parasail4·전환0**, 약318.005초·보고0.059628달러. 그러나A NON_JUDGMENT+참조ID충돌/B coverage입력구간누락으로 **정규화0/2·누적/컴파일0·1218전체Rejected**이며법률품질인증없음. A오류문구를ID누락으로해석하지않는다. wire10784/13629자·원래검증동일·용어본문축약없음. 초기로컬socket권한3실패보존/동일검사통과. **MAIN120롤백·데이터/모델/온톨로지기본OFF 유지·007/009전체재시험/GENOS/Git/메일없음.** ADR최종통과·graph기존{len(new)}오류/새0.
<!-- /REGEX_WIRE_MAIN121_20261029 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- REGEX_WIRE_MAIN121_20261029 -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1217 ID 정규식 동등 전송](ADR-1217-bounded-regex-wire-repair/README.md) — MAIN121·402계약·새회귀0, 실제1218 stop4/error-null0·정규화0/2.\n');p.write_text(''.join(lines))
print('MAIN121 verified;',nc,'selected service checks; report written')
