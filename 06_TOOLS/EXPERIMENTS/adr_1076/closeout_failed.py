"""Close ADR1076 with its original failed secondary criteria intact."""
from common import *
from datetime import datetime, timezone
import re
import sqlite3

primary = read(ADR/'artifacts/run-001/result.json')
out = ADR/'artifacts/run-002'
baseline = read(out/'baseline/result.json')
checks = read(out/'baseline/transport-checks.json')
freeze = read(DESIGN/'freeze.json')
assert primary['strict_success'] is True
assert baseline['completed'] is False and baseline['recorded_responses_used'] == 37
assert len(checks) == 38 and not checks[-1]['protected_request_exact']
assert all(x['protected_request_exact'] for x in checks[:-1])
assert baseline['view_count'] == 35 and not (out/'optimized').exists()
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == read(DESIGN/'baseline.json')['pointer_sha256']
assert not (ROOT/'09_ARTIFACTS/AUDITS/20261027-navigation-view-working-integration/integration.json').exists()

# Read-only diagnosis confirms the exact server-generated identity mechanism.
inventory = read(DESIGN/'secondary-inputs.json')
journals = [ROOT/inventory['original_journal']['path'],
    next((out/'baseline/runtime/legal-agent/runs').glob('*/*/journal.sqlite'))]
rows = []
for path in journals:
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro') as db:
        run_id = db.execute('SELECT run_id FROM run').fetchone()[0]
        row = db.execute('SELECT id,stage,offer_json,choice_json,created_seq FROM domain_choice ORDER BY created_seq DESC LIMIT 1').fetchone()
        selected = read_value = __import__('json').loads(row[3])
        encoded = __import__('json').dumps([run_id,row[1],row[4],selected],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        expected = 'D'+__import__('hashlib').sha256(encoded.encode()).hexdigest()[:28]
        assert expected == row[0]
        rows.append({'journal':bound(path),'stage':row[1],'created_seq':row[4],
            'choice_id':row[0],'formula_verified':True,'offer_json':row[2],'choice_json':row[3]})
assert rows[0]['stage'] == rows[1]['stage'] == 'COMPOSE'
assert rows[0]['created_seq'] == rows[1]['created_seq'] == 1595
assert rows[0]['offer_json'] == rows[1]['offer_json'] and rows[0]['choice_json'] == rows[1]['choice_json']
for row in rows:
    for key in ('offer_json','choice_json'):
        row[key+'_sha256'] = __import__('hashlib').sha256(row.pop(key).encode()).hexdigest()
put(out/'diagnosis-choice-identity.json', {'diagnosis_only':True,
    'formula':'D + SHA256(canonical JSON [native run_id, stage, next_event_seq, selected])[:28]',
    'code_path':'08_DEPLOYMENT/RELEASES/navigation-sql-20261027-r1/code/02_BACKEND/semantic_runtime/legal_agent/domain_control.py',
    'rows':rows,'same_offer_and_choice_bytes':True,
    'interpretation':'The protected request mismatch is a native run-bound generated identity. This post-failure finding does not revise the frozen exemptions or turn the failed replay into success.'})
secondary = {'schema_version':'adr1076-native-secondary-failed-v1','strict_success':False,
    'checks':{'primary_finite_census_pass':True,'baseline_35_frames_exact':True,
        'baseline_38_protected_requests_exact':False,'baseline_native_completed':False,
        'baseline_final_answer_exact':False,'optimized_executed':False,
        'paired_speed_comparison_complete':False,'frozen_inputs_unchanged':True,
        'main104_unchanged':True,'working_integration_not_applied':True},
    'baseline':bound(out/'baseline/result.json'),'baseline_response_count':37,
    'baseline_view_count':35,'optimized_status':'NOT_RUN_AFTER_BASELINE_BOUNDARY_FAILURE',
    'diagnosis':bound(out/'diagnosis-choice-identity.json'),
    'original_contract':bound(DESIGN/'secondary-replay.json'),
    'known_in_sample':True,'new_model_calls':0,'new_tokens':0,'new_cost_usd':0,
    'performance_comparison_available':False,'main_promotable':False,
    'failure':'The final memory-compose request differs at generated domain_choice.choice_id, which was not exempted by the frozen comparator. Stop preserved; no response substitution, comparator alteration, retry or optimized execution.'}
put(out/'result.json',secondary)

manifest = read(ADR/'실험/manifest.json')
assert manifest['results']['status'] == 'not_run'
manifest['runs'][0].update(status='complete',sha256=sha(ADR/'artifacts/run-001/result.json'),success_criteria_met=True)
manifest['runs'][1].update(status='failed',sha256=sha(out/'result.json'),success_criteria_met=False)
manifest['decision_eligible'] = False
manifest['results'].update(status='failed',by_arm={
    'baseline':{'status':'failed','primary_mechanical_pairs':1318,'primary_mismatches':0,
        'secondary_status':'FAILED_AT_RESPONSE38','secondary_protected_requests_exact':37,
        'secondary_navigation_frames_exact':35},
    'optimized':{'status':'failed','primary_mechanical_pairs':1318,'primary_mismatches':0,
        'secondary_status':'NOT_RUN_AFTER_BASELINE_FAILURE','secondary_protected_requests_exact':0,
        'secondary_navigation_frames_exact':0}},
    comparisons=[{'pair':['baseline','optimized'],'primary_finite_pairs_equivalent':1318,
        'primary_mismatches':0,'secondary_comparison':'NOT_COMPLETED','speed_improvement':None,
        'legal_quality':'NOT_MEASURED'}],
    usage={'product_model_calls':0,'offline_evaluator_calls':0,'recorded_responses_delivered_baseline':37,
        'recorded_responses_delivered_optimized':0,'new_input_tokens':0,'new_output_tokens':0},
    latency={'primary_audit_wall_seconds':primary['wall_seconds'],
        'failed_baseline_view_seconds':baseline['view_seconds'],
        'failed_baseline_request_seconds':baseline['request_seconds'],
        'comparison_available':False,'speed_claim':'NONE'},
    error_taxonomy=[{'kind':'HARNESS_PROTECTED_NATIVE_ID_MISMATCH','run':'run-002','arm':'baseline',
        'call':38,'phase':'memory-compose','path':'/view/domain_choice/choice_id',
        'product_source_changed':False,'frozen_comparator_changed':False}],
    main_wiring='unchanged',quality_certified=False,main_promotable=False,
    limitations=primary['limitations']+['Both original arms remain failed/incomplete as whole arms. No arm was post-hoc split into a completed parent. Known secondary replay failed and cannot establish a speed effect.'])
put(ADR/'실험/manifest.json',manifest,replace=True)
meta = (ADR/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Rejected'),('main_wiring','unchanged'),('decision_eligible','false'),('in_sample','false')]:
    meta = re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
body = f'''
# ADR1076 — 원문 준비 재사용 계약 통과, native 재생 실패

## 1. 결정 요약

**승격 자격 없음, MAIN104 유지.** 신규 사전 고정 합성 계약 1,318쌍은 전부 동등했다. 그러나 원래 요구한 native 재생은 baseline의 마지막 38번째 요청 비교에서 중단됐다. optimized 재생, 최종 답변 비교, 속도 비교는 미실행이다. 후보 제품이 틀렸다고 확정한 결과가 아니라 이 ADR의 전체 검증·승격 주장을 채택할 수 없다는 Rejected다. 작업 코드 통합과 MAIN105 prepare/apply도 하지 않았다.

## 2. 문제와 변경 전 구조

ADR1075 실제 MAIN104의 모델 밖 854.473초 가운데 35회 `Investigation.view`가 702.136초였다. 정의 조회 SQL은 180회 합계 0.081초였으므로 이미 반영한 SQL 최적화와 다른 비용이다. MAIN104의 메뉴는 각 범위의 `preview→catalog`마다 `acquired_blocks→delivered_blocks`로 누적 확보 원문 전체를 다시 확인했다.

후보는 `offer_choices` 호출 하나가 소유한 지역 준비 객체에 성공한 읽기 범위만 보관한다. 첫 권한·본문·hash 검사는 기존 그대로이며, hit마다 immutable-store checker를 호출한다. 범위별 원문·witness·endpoint와 실행 시 검증도 유지한다. 메뉴·선택 정책을 변경하지 않았다.

## 3. 가설과 사전 판정 기준

[주 기준](artifacts/design/criteria.json)과 [보조 재생 기준](artifacts/design/secondary-replay.json)을 실행 전에 동결했다. 주 기준은 명시한 유한 합성 1,318쌍의 정상 결과·오류·권한·상태·메뉴 동등성과 반복 조회 감소다. 보조 기준은 원래 38개 보호 요청·35개 화면·최종 답변의 일치 및 후보 화면 합계 시간 감소다.

보조 비교의 사전 예외는 생성 view UUID와 journal에 따로 결속하는 최종 답변 id/query_id뿐이었다. `domain_choice.choice_id`는 예외가 아니었다. 결과를 본 뒤 예외를 늘리거나 기존 실행을 성공으로 바꾸지 않는다.

## 4. 실험 설계

| arm | 제품 코드 | 원래 실행 범위 | 최종 상태 |
|---|---|---|---|
| baseline | 선택 MAIN104 | 주 전수 계약 + 알려진 native 재생 | 주 통과, 보조38번째에서 실패 |
| optimized | MAIN104 + 제품2모듈·31핀 | 같은 두 검증 | 주 통과, 보조미실행 |

주 검증은 static 1,152쌍, transition 112쌍, 실제 메뉴 경로 54쌍이다. 원래 arm을 결과 후 주/보조 완료 arm으로 분리하지 않는다. `results.by_arm`의 두 arm은 전체 범위에서 failed이며, 다음 실험의 완료 부모로 사용하지 않는다. 별도로 완료한 run001 결과는 범위가 명시된 기존 기계 계약 근거로 남긴다.

## 5. 데이터·모델·재현성

[동결 후보](artifacts/design/freeze.json)는 `view-preparation-r1/rev-001`이다. MAIN104의420개 서빙파일 중 제품2개와 hash pin31개만 다르고, 데이터·profile·schema·prompt·모델/provider·출력 상한 없음·검색/메뉴 정책과 호출/도구/시간 예산은 같다. 주 검증은 tiny SQLite만 사용했다.

보조 재생은 알려진 ADR1075 원래 provider 응답을 그대로 사용하며 신규 모델 호출0이다. 실제 service.application을 호출하고 arm의 동결 코드/데이터 경로만 주입했다. 원래 요청 재현을 위해 논리 release metadata는 MAIN104를 유지하므로 실제 MAIN105 선택 실행이라고 설명하지 않는다. 실제 코드420개·import/contracts 경로는 별도 hash로 결속했다.

## 6. 결과

- run001: 1,318/1,318쌍 동등, 오류·권한·상태 불일치0. 420서빙파일과9,232개 엔진 dependency pin 통과.
- 반복3회 최소 사례 원문 조회6→2회, checker6→4회. 실제4범위×2화면에서는 원문 조회88→40회이며 다음 화면에 다시 검증했다. 이는 합성 메커니즘 근거다.
- run002 baseline: 첫37개 보호 요청과35개 NAVIGATION 화면은 원래 기록과 exact. 마지막38번째 memory-compose는 schema/system/phase가 같았지만 보호 입력hash가 달라 fail-closed했다.
- run002 optimized 미실행, 최종 답변 미검증, paired 속도 비교 없음. 원시 [primary](artifacts/run-001/result.json), [secondary failure](artifacts/run-002/result.json), [baseline failure](artifacts/run-002/baseline/result.json)를 보존한다.

## 7. 사례별 오류 분석

원래 journal과 실패 journal의 마지막 request를 파싱하면 허용된 view UUID 외 차이는 `/view/domain_choice/choice_id` 하나다. 두 journal의 COMPOSE 선택은 created_seq=1595이고 offer_json·choice_json이 바이트 단위로 같다. 해당ID는 `D + digest([native run_id, stage, next_event_seq, selected])[:28]`이며, 각각의 실제 run_id로 두ID를 재계산해 일치함을 확인했다. [진단](artifacts/run-002/diagnosis-choice-identity.json).

다른 accepted claims, 출처, 제한 사항은 같았지만, 이는 사후 진단이며 원래 비교 기준을 통과했다는 뜻이 아니다. 서버 생성ID를 run/seq/선택내용에 결속해 비교하는 새 규칙은 후속 ADR에서 실행 전에 고정해야 한다. 이 실행의 STOP·실패·37개 전달 응답을 보존하며 retry·응답 수정·비교기 수정은 하지 않았다.

## 8. 비용·지연·회수 규모

주 감사 {primary['wall_seconds']:.6f}초, peak RSS {primary['peak_rss_kib']:,}KiB. 실패한 baseline의35개 화면 합계는 {baseline['view_seconds']:.6f}초, 요청은 {baseline['request_seconds']:.6f}초, application 준비는 {baseline['application_prepare_seconds']:.6f}초였다. 실행은 실패했으므로 이 수치로 후보 개선율이나 새 전체 응답시간을 주장하지 않는다.

신규 모델/평가 호출·토큰·비용0. 과거응답37개만 전달했고38번째응답은 전달하지 않았다. 실데이터 작업은 baseline 한 프로세스뿐이었으며 optimized는 시작하지 않았다. peak RSS {baseline['resource_peak_rss_kib']:,}KiB. 함수별 inclusive 시간은 중첩되므로 합산하지 않는다.

## 9. 해석

주 계약에서는 동일 화면 안 반복 원문 준비를 줄여도 검증한 상태·권한·실패 동작이 보존됐다. 실데이터 성능 효과는 아직 검증되지 않았다. 실패는 baseline 자체에서 생성 실행ID를 엄격한 재생 비교에 포함한 측정장치의 경계였고, 후보 최적화나 온톨로지 실패로 단정하지 않는다.

## 10. 한계와 일반화 가능 범위

1,318쌍은 사전 정의한 유한 합성 계약으로 모든 가능한 데이터·동시성·임의 장애 스케줄의 증명이 아니다. `check_unchanged`가 보장하는 저장소 불변성과 동기식 메뉴를 전제한다. 제거한 중복 I/O의 특정 호출 번호에만 매긴 임의 장애는 동일 사건으로 비교할 수 없다.

보조 trace는 알려진 in-sample 자료이며 법률 holdout이 아니다. 새 법률 판단·온톨로지 효과·GENOS·모델 속도는 측정하지 않았다. 사전 독립 주 계약의 범위 때문에 `in_sample=false` 기록은 유지하지만, 전체 결과는 실패이므로 `decision_eligible=false`, `quality_certified=false`, `main_promotable=false`다. 과거 품질 우회는 사용하지 않는다.

## 11. 운영 결정·롤백 조건

선택 MAIN104와 작업 제품 코드를 유지한다. 성공 시 작업 통합·승격용으로 미리 작성했던 `closeout.py`, `promotion_records.py` 및 별도 working audit 준비 스크립트는 실행하지 않았고 실패 결과의 guard를 통과할 수 없다. 완료 arm을 사후 새 의미로 만들어 승격 또는 후속 부모로 사용하지 않는다.

후속은 완료 부모 ADR1075와 이 실패의 informed_by 관계를 사용하고, 원래 주 계약 결과는 기존 근거임을 밝힌다. 새 비교 규칙·후속 범위는 새 ADR에서 사전에 고정한다. 이 완료 ADR의 실패를 후속 성공으로 덮어쓰지 않는다. MAIN105·메일·GENOS 배포는 이 실험의 결과가 아니다.

## 12. 재현 명령

실행 순서는 `prepare.py→freeze.py→audit.py`, 이후 `native_replay.py baseline`이다. optimized와 native_summary 성공 집계는 실행하지 않았다. 완료 실행을 덮어쓰거나 원래 freeze를 수정하지 않는다. [artifact manifest](artifacts/manifest.json)에 원시 실패·동결 코드·행렬·진단을 결속했다.

구조 확인: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse --final`. graph는 모든 과거 ADR의 기존 문제와 신규 source의 상태를 구분해 기록한다.
'''
(ADR/'README.md').write_text('---'+meta+'---\n'+body)
(ADR/'실험/README.md').write_text('''# 실행별 완료와 실패

| 실행 | 결과 | 근거 |
|---|---|---|
| run001 | 주 유한 기계 계약1,318쌍 동등 | ../artifacts/run-001/result.json |
| run002 baseline | 37개 보호 요청·35화면 일치 후 마지막 요청에서 중단 | ../artifacts/run-002/baseline/result.json |
| run002 optimized | baseline 실패 뒤 미실행 | ../artifacts/run-002/result.json |

전체 ADR과 두 원래 arm은 승격에 필요한 실행을 완료하지 못했다. 완료 primary run을 결과 후 별도 완료 부모 arm으로 만들지 않는다. 알려진 native trace의 생성 domain choice ID 차이는 진단일 뿐 원래 기준 통과가 아니다. 신규 모델0, MAIN104·작업 제품 유지.
''')
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1076').glob('*.py'))
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1076',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Frozen finite census, failed native reconstruction or post-failure diagnosis. Success-only closeout/promotion helpers were prepared but not executed.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]})
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1076 원문 준비 재사용 검증](ADR-1076-navigation-view-preparation-reuse/README.md) — 주1,318쌍 동등; native baseline38번째 생성ID 비교 실패·후보재생 미실행. 승격자격 없음·MAIN104 유지.\n\n'
if 'ADR-1076-navigation-view-preparation-reuse/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Failed ADR source drafted; original secondary criteria retained; both whole arms remain failed; MAIN104/working unchanged')
