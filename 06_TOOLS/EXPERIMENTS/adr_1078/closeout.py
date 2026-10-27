"""Complete the isolated ADR only after both frozen runs pass; no MAIN mutation."""
from common import *
from datetime import datetime, timezone
import re

primary = read(ADR/'artifacts/run-001/result.json')
secondary = read(ADR/'artifacts/run-002/result.json')
for result in (primary,secondary):
    assert result['strict_success'] is True and all(v is True for v in result['checks'].values())
freeze = read(DESIGN/'freeze.json')
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
manifest = read(ADR/'실험/manifest.json')
assert manifest['results']['status'] == 'not_run' and manifest['reservation']['status'] == 'in_progress'
for run in manifest['runs']:
    run.update(status='complete',sha256=sha(ROOT/run['artifact_path']),success_criteria_met=True)
manifest['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','new_primary_state_pairs':280,'primary_calls':3208,
        'native_role':'Historical35completedviewwindows only, predeclared; original1076whole-service failure unchanged.'},
    'optimized':{'status':'complete','new_primary_state_pairs':280,'primary_calls':3208,
        'new_native_recorded_responses':38,'native_frames_exact':35,'native_final_answer_exact':True}},
    comparisons=[{'pair':['baseline','optimized'],'new_primary_equivalent':280,'primary_mismatches':0,
        'known_secondary_view_timing':secondary['timing']['view_seconds'],
        'full_request_speed_comparison':False,'legal_accuracy':'NOT_MEASURED'}],
    usage={'new_product_model_calls':0,'new_evaluator_calls':0,'new_input_tokens':0,'new_output_tokens':0,
        'saved_responses_supplied_to_optimized':38},
    latency={'primary_wall_seconds':primary['wall_seconds'],'known_secondary':secondary['timing'],
        'limit':'Only completed35viewwindows compared. Original baseline service failed later and remains failed; no fullrequest/GENOS/p95 claim.'},
    error_taxonomy=[],main_wiring='promotion-candidate',quality_certified=False,
    limitations=primary['limitations']+[secondary['scope']],
    working_integration_status='NOT_APPLIED_IN_THIS_SOURCE; may be combined with a separately qualified follow-up before MAIN activation.')
put(ADR/'실험/manifest.json',manifest,replace=True)
meta = (ADR/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true'),('in_sample','false')]:
    meta = re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
view = secondary['timing']['view_seconds']
body = f'''
# ADR1078 — 새 상태경계 계약과 원장에 결속한 native 재생

## 1. 결정 요약

새로 사전 고정한 다단계 상태 280쌍, arm당3,208회 관찰이 모두 동등하고 native 후보 재생도 완료하여 명시한 기계 계약 범위에서 Accepted, promotion-candidate다. 38개 저장 응답에 대응하는 보호 요청,35개 화면·행동·전달 원문, 최종 답변 내용이 원래 완료 ADR1075와 일치했다. 제품은 ADR1076 후보의420파일과 바이트 동일하다. 작업 코드 통합·실제 MAIN 선택·현장 배포는 별도이며 여기서는 MAIN104를 유지했다.

## 2. 문제와 변경 전 구조

MAIN104는 같은 메뉴를 구성하면서 각 연결 범위마다 누적 확보 원문 전체를 반복 검증했다. 기존 후보는 `offer_choices` 호출 한 번이 소유하는 성공한 읽기 준비만 재사용하며 매 hit의 저장소 불변성 검사, 범위 원문·witness·endpoint·실행 검증은 유지한다.

ADR1076은 기존1,318쌍 계약을 통과했으나 native baseline의 마지막 COMPOSE에서 실행마다 달라지는 domain choice ID를 보호 입력으로 비교해 중단됐다. 그 실패·미실행 후보·승격 부적격 상태는 그대로 보존했다. 이 후속은 완료 ADR1075를 부모로 하며 ADR1076을 실패 참고로만 사용한다.

## 3. 가설과 사전 판정 기준

[새 기준](artifacts/design/criteria.json)과 [새 상태 행렬](artifacts/design/state-matrix.json)을 실행 전에 고정했다. 기존 후보가 세션/저장소 교차, 지속 실패와 복구, 중첩 변이 순서, 우회 상태와 새 화면에서도 결과·오류·권한·입력 상태를 보존해야 한다. 선언한 모든 호출을 두 arm에서 실행하고 하나의 불일치도 허용하지 않는다.

원래1,318행렬은 이미 관측한 보조 근거다. 이를 이름만 바꿔 새 독립 계약이나 법률 holdout으로 세지 않는다. 제품의 개발 독립성과 평가 상태의 새 범위를 구분한다. 새280쌍의 유한 기계 계약으로만 out-of-sample과 decision eligibility를 해석한다.

## 4. 실험 설계

| 새 상태 경계 | 쌍 수 | 내용 |
|---|---:|---|
| session/store identity 교차 | 36 | 3topology×4경로×3view경계 |
| 지속 실패·재시도·복구·재실패 | 16 | 결함4×보관위치2×실패위치2 |
| ACL/source/span의 중첩 변이 | 216 | 적용6순열×복구6순열×span결함3×보관위치2 |
| 우회 상태와 view 왕복 | 12 | control/checker/empty3×원문배치2×경계2 |

run001은 baseline/optimized에 각각3,208회, 합계6,416회 획득 호출을 관찰했다. 별도 새 순수 메모리 fixture와 oracle을 사용했고 이전 runner를 import하지 않았다. run002는 사전 설계대로 optimized만 새로 실행했다. baseline의 시간 비교 대상은1076에서 이미 완료·원본일치한35개 화면 구간이며 전체 서비스 성공을 재분류하지 않았다.

## 5. 데이터·모델·재현성

공식 snapshot/register/freeze로 `adr_1078/view-preparation-r1/rev-001`에420파일을 고정했다. 선택 MAIN104 대비 제품2모듈과 pin31개이며 데이터·profile·schema·prompt·모델/provider·출력 상한 없음·검색/메뉴 정책과 호출/도구/시간 예산은 동일하다. [freeze](artifacts/design/freeze.json), [rebase](artifacts/design/release-rebase.json).

native는 동결 service.application을 호출하고 arm의 코드/데이터 경로만 선택 주입한다. 원래 요청을 재현하기 위해 논리 release metadata는 MAIN104를 재사용하므로 실제 선택된 MAIN105 실행이 아니다. 실제420파일과 import/contracts 경로를 별도 결속했다. 보호 입력에서 생성 view UUID와 원장에 결속한 답변 id/query_id만 구분하고, 마지막 COMPOSE choice ID는 각 실제 journal의 run/stage/seq/선택으로 재계산한다. offer_json·choice_json·event 순서는 바이트 동일해야 하며 다른 원문·의미 입력은 전부 exact다.

## 6. 결과

- 새280/280쌍과6,416호출의 결과·오류·입력 상태 동등. 9개 strict checks,420서빙파일,9,232dependency pins 통과.
- fresh876회, eligible reuse948회, 실패1,360회, bypass24회의 arm별 관찰을 전수 비교했다. 새 view 경계316회도 확인했다.
- 후보 native38/38 보호 요청과35/35 NAVIGATION 화면이 원래 완료1075 기록과 일치했고 최종 답변·생성ID 원장 결속까지 통과했다.
- [새 주 결과](artifacts/run-001/result.json), [압축 원시](artifacts/run-001/state-pairs.jsonl.gz), [native 결과](artifacts/run-002/result.json). 신규 모델/평가 호출0.

## 7. 사례별 오류 분석

검증 도중 뒤쪽 원문에서 실패한 뒤 같은 입력으로 재시도하고, 고친 뒤 성공·재실패·복구·새 view를 이어 확인했다. ACL/source-block/span을 각 순서로 겹쳐 바꾸고 서로 다른 순서로 되돌렸을 때 기존 오류 우선순위와 성공 시점도 같았다. 공유 store의 다른 session, 값이 같은 다른 store, 한 session의 store 교대에서도 첫 검증을 다시 했다.

새 native 비교기는 마지막 choice ID가 각 원장의 실제 run·COMPOSE·seq·선택 내용에 결속된 경우만 비교 사본에서 구분한다. 원래1076 실패 기준은 수정하지 않았다. 실제1075/1076 마지막 요청 사전 검사와9개 작은 harness 검사를 제품 실행 전에 수행했다. 이 ADR의 두 실행은 원시 실패 없이 완료됐다.

## 8. 비용·지연·회수 규모

주 감사 {primary['wall_seconds']:.6f}초, peak RSS {primary['peak_rss_kib']:,}KiB다. 실데이터 없는 합성 검사이며 이 시간을 제품 응답속도로 사용하지 않는다.

같은 계측 wrapper의35개 완료 화면 준비 합계는 과거 baseline {view['baseline']:.6f}초 → 새 optimized {view['optimized']:.6f}초로 {view['reduction_percent']:.3f}% 줄었다. 과거 baseline은 그 뒤 COMPOSE에서 실패했고 이 실패는 유지된다. **전체 요청시간 개선율은 계산하지 않는다.** 후보의 모델 없는 전체 재구성 시간·초기 준비·offline transport는 [보조 결과](artifacts/run-002/result.json)에 별도로 기록했다.

새 원장 ID 검사는 모든35view 뒤 call38에서 수행해 view timer에 포함되지 않는다. 화면 hash/파일 저장도 timer 밖이다. 실행 시각과 파일 캐시의 온도가 다르고 각1회 측정이므로 엄밀한 반복 분포·p95·GENOS·새 live 답변 지연으로 일반화하지 않는다. 함수별 inclusive 시간은 중첩되므로 합산하지 않는다.

## 9. 해석

새 상태 경계 검사는 성공한 준비 결과가 권한·identity·실패·view 경계를 넘어 살아남지 않음을 선언한 범위에서 뒷받침한다. known trace 재생은 원문·메뉴·행동과 답변을 유지한 채 화면 준비가 줄었음을 보인다. 두 근거의 역할은 다르며 native의 알려진 질문을 독립 품질 표본으로 바꾸지 않는다. 다른 조회·상태 저장 비용이 남을 수 있고 이 후보만으로 모든 비모델 비용을 최적화했다고 하지 않는다.

## 10. 한계와 일반화 가능 범위

유한 순차 상태의 기계 계약이다. 동시 원문 변경이나 임의 adapter·생략한 중복 I/O의 특정 호출에만 붙은 고장 일정을 동등하다고 증명하지 않는다. 저장소의 immutable `check_unchanged`와 동기 메뉴 수명을 전제한다. 원문·판단의 법률 정답률, 온톨로지 효과, 모델 응답속도, GENOS 성능은 측정하지 않았다. `quality_certified=false`, 새 qualification에 이전 품질 우회를 사용하지 않는다.

## 11. 운영 결정·롤백 조건

이 완료 source는 검증 후보와 원시 결과를 고정하며 MAIN 포인터를 바꾸지 않는다. 다음 SQL 병목 후보가 별도로 검증되면 이 완료 arm을 부모로 이어갈 수 있다. 최종 작업 통합은 기존 별표/선택 directory 기능을 보존한 hunk로, 실제 MAIN 선택은 stable hash-bound prepare/apply로 별도 수행한다. 원문·권한·hash·상태·서빙 회귀 시 불변 MAIN104로 새 rollback receipt를 남긴다.

완료 ADR에 사후 MAIN·메일 상태를 덮어쓰지 않는다. 실제 활성 binding·consumer 확인·삼성 인계와 GENOS 현장 적용은 각각 별도 기록이다.

## 12. 재현 명령

`prepare.py→freeze.py→audit.py` 뒤 `native_replay.py optimized`, `native_summary.py`를 실행했다. 후보·입력·runner는 freeze에, raw·보고서는 [artifact manifest](artifacts/manifest.json)에 결속했다. 완료 결과를 덮어쓰지 않으며 후속은 새 ADR에서 선점한다.

`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1078-navigation-bound-replay --final`로 최종 구조를 확인한다. 전역 graph의 과거 오류는 이 source의 새 검증과 구분한다.
'''
(ADR/'README.md').write_text('---'+meta+'---\n'+body)
(ADR/'실험/README.md').write_text('''# 신규 상태 계약과 알려진 native 재생

| 실행 | 역할 | 결과 |
|---|---|---|
| run001 | 새280개 다단계 상태쌍·arm당3,208호출 | 전수동등 |
| run002 | 후보에 원래1075응답38개 재생 | 35화면·최종답변exact, 원장ID결속 |

이전1,318계약과1076완료35view구간은 기존 관측 근거이며 새 독립 표본으로 세지 않는다. 이전 baseline 전체서비스 실패는 그대로다. 비교는 화면 구간에만 해당하며 whole-request 성능·법률품질·GENOS를 인증하지 않는다. MAIN104 유지, working 통합과 실제 승격은 별도다.
''')
assert read(ADR/'artifacts/manifest.json')['files'][0]['path'] == 'TODO'
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1078').glob('*.py'))
paths.append(ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state-matrix.json')
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1078',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'New frozen state contracts or known native reconstruction with journal-bound IDs; previous failed whole-service result remains failed.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]},replace=True)
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1078 원문 준비 상태경계와 원장결속 재생](ADR-1078-navigation-bound-replay/README.md) — 새280쌍/6,416호출 동등·원래응답38개/화면35개/답변exact. 기존실패보존, MAIN선택은별도.\n\n'
if 'ADR-1078-navigation-bound-replay/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Scoped Accepted isolated source drafted; MAIN and working activation remain separate')
