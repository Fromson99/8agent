"""Preserve the second strict replay failure; do not relax its frozen rules."""
from common import *
from datetime import datetime, timezone
import re

primary = read(ADR/'artifacts/run-001/result.json')
out = ADR/'artifacts/run-002'
native = read(out/'optimized/result.json')
transport = read(out/'optimized/transport-checks.json')
diagnosis = read(out/'optimized/post-failure-difference.json')
freeze = read(DESIGN/'freeze.json')
assert primary['strict_success'] and not native['completed']
assert native['recorded_responses_used'] == 35 and native['view_count'] == 35
assert len(transport) == 36 and all(x['protected_request_exact'] for x in transport[:-1])
assert not transport[-1]['protected_request_exact'] and not transport[-1]['schema_exact']
assert transport[-1]['system_exact'] and transport[-1]['expected_phase'] == transport[-1]['actual_phase']
assert len(diagnosis['different_paths']) == 47
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == read(DESIGN/'baseline.json')['pointer_sha256']
assert not (ROOT/'09_ARTIFACTS/AUDITS/20261027-navigation-view-working-integration/integration.json').exists()
secondary = {'schema_version':'adr1078-native-replay-failed-v1','strict_success':False,
    'checks':{'new280statepairs_pass':True,'candidate35frames_exact':True,
        'all38protectedrequests_exact':False,'native_completed':False,'final_answer_exact':False,
        'frozen_inputs_unchanged':True,'main104_unchanged':True,'working_not_integrated':True},
    'native_result':bound(out/'optimized/result.json'),
    'diagnosis':bound(out/'optimized/post-failure-difference.json'),
    'frozen_secondary_contract':bound(DESIGN/'secondary-replay.json'),
    'recorded_responses_used':35,'completed_navigation_windows':35,
    'stopped_call':36,'phase':'source-law-navigation-35',
    'reason':'Strict view/schema equality rejected a current-view versus preview V1/V2 alias swap; the frozen guard protects aliases and cannot be changed post-run.',
    'new_model_calls':0,'new_tokens':0,'new_cost_usd':0,'main_promotable':False,
    'performance_claim':'NONE: native replay did not meet its original complete38response/answer requirement.'}
put(out/'result.json',secondary)
manifest = read(ADR/'실험/manifest.json')
assert manifest['results']['status'] == 'not_run'
manifest['runs'][0].update(status='complete',sha256=sha(ADR/'artifacts/run-001/result.json'),success_criteria_met=True)
manifest['runs'][1].update(status='failed',sha256=sha(out/'result.json'),success_criteria_met=False)
manifest['decision_eligible'] = False
manifest['results'].update(status='failed',by_arm={
    'baseline':{'status':'failed','primary_state_pairs':280,'primary_calls':3208,
        'primary_mismatches':0,'reason':'Whole paired qualification failed; observed primary results remain valid within their declared scope, not a completed parent arm.'},
    'optimized':{'status':'failed','primary_state_pairs':280,'primary_calls':3208,
        'primary_mismatches':0,'secondary_status':'FAILED_AT_PROTECTED_REQUEST36',
        'secondary_protected_requests_exact':35,'secondary_navigation_frames_exact':35}},
    comparisons=[{'pair':['baseline','optimized'],'new_primary_equivalent':280,
        'primary_mismatches':0,'secondary':'FAILED_BEFORE_FULL_SOURCE_CHOICE_RESPONSE',
        'speed_improvement':None,'legal_accuracy':'NOT_MEASURED'}],
    usage={'new_product_model_calls':0,'new_evaluator_calls':0,'new_input_tokens':0,'new_output_tokens':0,
        'literal_historical_responses_supplied':35},
    latency={'primary_wall_seconds':primary['wall_seconds'],
        'failed_candidate_view_seconds':native['view_seconds'],
        'failed_candidate_request_seconds':native['request_seconds'],'speed_claim':'NONE'},
    error_taxonomy=[{'kind':'HARNESS_PROTECTED_VIEW_PREVIEW_ALIAS_SWAP','run':'run-002','arm':'optimized',
        'call':36,'phase':'source-law-navigation-35','different_paths':47,
        'frozen_rules_changed':False,'response_rewritten':False}],
    main_wiring='unchanged',quality_certified=False,main_promotable=False,
    limitations=primary['limitations']+['The native completion requirement failed at request36; partial exact frames and predeclared primary checks do not convert the whole arm into a completed promotion source.'])
put(ADR/'실험/manifest.json',manifest,replace=True)
meta = (ADR/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Rejected'),('main_wiring','unchanged'),('decision_eligible','false'),('in_sample','false')]:
    meta = re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
body = f'''
# ADR1078 — 새 상태계약 통과, request-local 별칭 비교 실패

## 1. 결정 요약

**전체 검증·승격은 실패, MAIN104 유지.** 신규 다단계280쌍과 arm당3,208호출은 전수 동등했다. 그러나 native optimized 재생은36번째 요청의 V1/V2 별칭·schema 차이로 중단돼 원래38응답·최종답변 완주조건을 충족하지 못했다. 기존 실패를 성공으로 바꾸거나 보호 기준을 소급 완화하지 않는다. 제품 후보가 틀렸다고 단정한 결과가 아니라 전체 qualification의 Rejected다.

## 2. 문제와 변경 전 구조

MAIN104는 메뉴 범위마다 누적 원문을 반복 확인했다. 후보는 한 `offer_choices` 호출 안에서 성공한 acquired 원문 준비를 재사용하며 권한·원문·hash·저장소·범위·witness·endpoint 검사를 유지한다. 이 ADR의420제품파일은1076후보와 바이트 동일하다.

이전1076 baseline은 마지막 COMPOSE의 run-bound domain choice ID 때문에 실패했다. 그 실패를 보존하고 여기서는 새 상태계약과 원장에 결속한 domain ID 비교 규칙을 사전에 추가했다. 완료 부모는1075이며1076은 실패 참고다.

## 3. 가설과 사전 판정 기준

[기준](artifacts/design/criteria.json), [행렬](artifacts/design/state-matrix.json), [native 기준](artifacts/design/secondary-replay.json)을 실행 전에 동결했다. 새280쌍의 각 typed 출력·오류·입력 상태를 모두 비교하고, native는38보호요청·35화면·최종답변이 원본과 같아야 한다.

사전 예외는 생성 view UUID, 원장결속 답변ID와 COMPOSE domain choice ID뿐이었다. `V1`·`V2` 같은 짧은 별칭과 schema는 exact 보호 대상이었다. 이를 결과 후 예외로 바꾸지 않는다.

## 4. 실험 설계

신규 행렬은 session/store identity 교차36쌍, 지속실패·복구16쌍, ACL/source/span 3중변이의 적용·복구 순열216쌍, 우회상태/view왕복12쌍이다. 이전1,318사례나 fixture를 복사하지 않았고 기존 결과는 이미 관측한 보조 근거로만 결속했다.

run001은 baseline/optimized를 각각3,208회 관찰했다. run002는 optimized만 새로 실행하며 이전1076의 완료35view구간을 시간참고로 사전결속했다. 이전 baseline 전체서비스는 계속 실패다. 이번 두 전체 arm도 후속 완료 부모나 승격 근거로 사용하지 않으며 성공한 primary run의 범위를 그대로 남긴다.

## 5. 데이터·모델·재현성

공식 snapshot/register/freeze의 `adr_1078/view-preparation-r1/rev-001`이다. MAIN104 대비 제품2개·31핀, 총420서빙파일이다. 데이터·profile·schema·prompt·모델/provider·출력 상한 없음·검색/메뉴·호출/도구/시간예산은 같다. 주 검증은 새 순수 메모리 fixture로 네트워크·실제자료·모델0이다.

native는 동결 service.application을 쓰고 코드/데이터 선택만 후보로 주입했다. 논리 release metadata는 원래 MAIN104를 유지해 실제 MAIN105 선택이라고 보고하지 않는다.420파일·import/contracts 지문은 별도 확인했다. 실제35개 모델응답을 새로 생성한 것이 아니라 원래1075응답35개를 그대로 공급했다.

## 6. 결과

- 신규280/280쌍, 총6,416관찰이 전부동등.9개 strict checks·420파일·9,232핀 통과.
- arm별 fresh876·reuse948·실패1,360·bypass24회 관찰과 새view316경계를 확인했다.
- native 첫35개 보호요청과35개 NAVIGATION 화면·행동·원문은 exact였다.
-36번째 `source-law-navigation-35`에서 system/phase는 같지만 schema와 보호view가 달라 중단했다.38응답과 최종답변은 미완주다.
- [주 결과](artifacts/run-001/result.json), [압축 원시](artifacts/run-001/state-pairs.jsonl.gz), [실패 집계](artifacts/run-002/result.json), [native 원시](artifacts/run-002/optimized/result.json).

## 7. 사례별 오류 분석

독립 비교에서47차이는 전부 V1/V2 교환이다. current view ID1곳과 동일 preview ID의2곳, schema basis_refs enum44곳이 바뀌었다. 원래 응답은 이 바뀐 V1/V2를 참조하지 않았지만, 이것만으로 사전 exact 기준을 통과시킬 수 없다. [사후 진단](artifacts/run-002/optimized/post-failure-difference.json).

`NavigationReferences`는 원문 필드 밖의 `[A-Z][hex16..64]` ID를 모두 수집한 뒤 정렬하고 첫 글자별 별칭을 붙인다. `repository.save_view`의 `V+uuid4.hex`와 preview의 `lc.token(...,'V',[hit.key,digest(text)])`가 같은V집합에 들어간다. 랜덤 view UUID와 고정 preview ID의 정렬 순서에 따라 V1/V2가 바뀔 수 있다. 이 두 파일은 MAIN104/후보에서 동일하므로 cache 변경만의 현상이라고 단정하지 않는다.

후속 규칙은 실제 model_view의 canonical mapping과 view/preview 역할을 결속한 일대일 대응, 나머지내용/schema exact, 변경별칭을 기록응답이참조하면중단, 응답rewrite0을 실행전에 고정해야 한다. 여기서는 기존 guard·응답·schema를 고치지 않았다.

## 8. 비용·지연·회수 규모

주 감사 {primary['wall_seconds']:.6f}초, peak RSS {primary['peak_rss_kib']:,}KiB. 실패한 후보의35개 view 합계는 {native['view_seconds']:.6f}초, 요청은 {native['request_seconds']:.6f}초, 초기준비 {native['application_prepare_seconds']:.6f}초다. 실패로 원래 성능 인증 요건을 충족하지 못했으므로 개선율·전체응답속도 주장을 하지 않는다.

신규 모델/평가 호출·토큰·비용0, 기록응답35개만 공급했고36번째응답은 전달하지 않았다. 실제자료 worker는1개였으며 peak RSS {native['resource_peak_rss_kib']:,}KiB다. inclusive 함수 시간은 중첩되므로 더하지 않는다.

## 9. 해석

새 상태계약은 재사용이 identity·실패·view경계를 넘지 않는다는 유한 근거다.35개 원래 화면도 재현됐지만 전체native완주를 대신하지 않는다. 이번 차단은 기존 request-local 별칭의 랜덤UUID 정렬과 literal replay 기준이 만난 경계이며, 법률 답변 또는 온톨로지 실패로 설명하지 않는다.

## 10. 한계와 일반화 가능 범위

새280쌍은 순차 합성 상태의 기계 계약이며 법률holdout·동시성·모든임의adapter의 증명이 아니다. 관측한1,318과known trace를 새독립표본으로 바꾸지 않는다. 모델속도·온톨로지·GENOS·전체답변품질은 측정하지 않았다. 전체결과실패이므로 decision_eligible=false, quality_certified=false, main_promotable=false다.

## 11. 운영 결정·롤백 조건

MAIN104와 작업 제품코드를 유지한다. 후보통합·MAIN105준비/적용·메일은 수행하지 않았다. 준비한 성공closeout 생성기는 실행하지 않았고 성공guard를통과하지못한다. 다음실험은 완료1075부모와 이실패의 informed_by 관계로 시작하며, 관측된후보코드와 주계약을 기존근거로 정확히 밝힌다. 실패source를 완료부모로 포장하지 않는다.

## 12. 재현 명령

실행은 `prepare.py→freeze.py→audit.py→native_replay.py optimized`다. native_summary 성공집계와 성공closeout은 실행하지 않았다. 원시실패·STOP·동결코드는 [artifact manifest](artifacts/manifest.json)에 결속한다. 완료실험을 덮어쓰지 않는다.

최종구조검사: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1078-navigation-bound-replay --final`. 전역graph의과거오류는 이source와구분한다.
'''
(ADR/'README.md').write_text('---'+meta+'---\n'+body)
(ADR/'실험/README.md').write_text('''# 완료된 주계약과 실패한 native 재생

run001은 신규280상태쌍/6,416호출 전수동등이다. run002는35응답·35화면 뒤36번째요청의 V1/V2 역할별칭과schema exact비교에서실패했다. 원래38응답·답변완주요건은실패그대로다. 전체arm을완료부모·승격근거로사용하지않는다. 모델0,MAIN104·working유지.
''')
assert read(ADR/'artifacts/manifest.json')['files'][0]['path'] == 'TODO'
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1078').glob('*.py'))
paths.append(ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state-matrix.json')
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1078',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'New state-contract evidence, frozen failed native replay or post-failure diagnosis; success closeout helper was not executed.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]},replace=True)
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1078 원문 준비 상태계약·재생실패](ADR-1078-navigation-bound-replay/README.md) — 새280쌍 통과,35화면exact뒤36번째V별칭/schema차단. 원래완주조건실패·MAIN104유지.\n\n'
if 'ADR-1078-navigation-bound-replay/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Failed1078source drafted; original criteria preserved; no promotion or working integration')
