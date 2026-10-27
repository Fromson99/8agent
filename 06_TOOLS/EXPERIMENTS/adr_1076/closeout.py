"""Post-execution source report; does not alter frozen inputs or activate MAIN."""
from common import *
from datetime import datetime, timezone
import re

primary = read(ADR/'artifacts/run-001/result.json')
secondary = read(ADR/'artifacts/run-002/result.json')
working = ROOT/'09_ARTIFACTS/AUDITS/20261027-navigation-view-working-integration'
working_result = read(working/'validation.json')
for result in (primary, secondary, working_result):
    assert result['strict_success'] is True and all(v is True for v in result['checks'].values())
freeze = read(DESIGN/'freeze.json')
assert all(sha(ROOT/p) == h for p,h in freeze['files'].items())
manifest = read(ADR/'실험/manifest.json')
assert manifest['results']['status'] == 'not_run'
for run in manifest['runs']:
    result_path = ROOT/run['artifact_path']
    run.update(status='complete', sha256=sha(result_path), success_criteria_met=True)
manifest['results'].update(status='complete',
    by_arm={name: {'status': 'complete', 'mechanical_pairs': 1318,
        'role': 'immutable MAIN104 comparator' if name == 'baseline' else 'MAIN104 plus two-module invocation-local preparation',
        'mechanical_mismatches': 0, 'known_replay_frames_exact': 35,
        'known_replay_responses': 38} for name in ('baseline', 'optimized')},
    comparisons=[{'pair': ['baseline','optimized'], 'mechanical_equivalent': 1318,
        'mechanical_mismatch': 0, 'legal_accuracy': 'not_measured',
        'secondary_known_in_sample': True, 'exact_navigation_frames_per_arm': 35,
        'protected_requests_exact_per_arm': 38, 'final_answer_content_exact': True}],
    usage={'product_model_calls': 0, 'offline_evaluator_calls': 0,
        'historical_raw_provider_responses_per_arm': 38, 'input_tokens': 0, 'output_tokens': 0},
    latency={'primary_audit_wall_seconds': primary['wall_seconds'],
        'secondary_known_in_sample': secondary['timing'],
        'meaning': 'Paired local native reconstruction with recorded responses; excludes live model latency; never GENOS or new live answer speed.'},
    error_taxonomy=[], main_wiring='promotion-candidate', quality_certified=False,
    limitations=primary['limitations'] + [secondary['scope']],
    working_integration={'receipt':bound(working/'integration.json'),
        'validation':bound(working/'validation.json'),
        'role':'Separate working branch integration; preserves newer directory/annex behavior and is not byte-identical to the release candidate.'})
put(ADR/'실험/manifest.json', manifest, replace=True)
meta = (ADR/'README.md').read_text().split('---', 2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),
                  ('decision_eligible','true'),('in_sample','false')]:
    meta = re.sub(r'(?m)^'+key+r':.*$', key+': '+value, meta)
timing = secondary['timing']
view, request = timing['view_seconds'], timing['request_seconds']
body = f'''
# ADR1076 — MAIN104 탐색 화면의 원문 준비 재사용

## 1. 결정 요약

새로 사전 고정한 유한 기계 계약 1,318쌍이 전부 동등하여 Accepted, promotion-candidate다. MAIN104의 420개 서빙 파일 가운데 제품 2개와 필요한 hash pin 31개만 바꾼다. 별도의 알려진 응답 재생에서는 35개 탐색 화면·행동·전달 원문과 38개 보호 요청, 최종 답변 내용이 모두 일치했다. 같은 계측에서 화면 준비 합계가 {view['baseline']:.6f}→{view['optimized']:.6f}초({view['reduction_percent']:.3f}% 감소)였다. 실제 MAIN 선택과 이후 서비스 확인은 별도 activation receipt에 기록한다.

## 2. 문제와 변경 전 구조

ADR1075의 실제 MAIN104 공개 1문항은 38회 모델 호출 후 READY였지만 모델 전송을 제외한 854.473초 중 35회 `Investigation.view`가 702.136초였다. 이미 반영한 정의 조회 SQL은 180회 합계 0.081초였다. 같은 문제를 SQL 실패로 다시 설명하지 않는다.

MAIN104의 `offer_choices`는 표시하는 각 범위를 `preview→catalog`로 구성한다. 이때 범위마다 `acquired_blocks→delivered_blocks`가 누적 확보 원문 전체의 권한·좌표·본문·hash를 반복 확인했다. 범위별 명시 참조와 witness 검사는 필요하지만, 동일 메뉴 구성 중 변하지 않은 확보 원문 전체의 검사를 반복할 필요는 없었다.

## 3. 가설과 사전 판정 기준

[사전 기준](artifacts/design/criteria.json)과 [전수 행렬](artifacts/design/finite-matrix.json)을 후보 실행 전에 고정했다. 1,318쌍에서 정상 반환 또는 오류 유형·문구·상태·권한·원문·메뉴·행동이 전부 같아야 한다. 동일 상태의 원문 조회는 줄어야 하며, source/span/scope/type/order/store/session 변경, 오류, 새 화면에서는 오래된 결과를 재사용하면 안 된다. 420개 파일 가운데 정한 2개 모듈과 핀 이외 변경은 허용하지 않는다.

## 4. 실험 설계

| arm | 코드 | 실행 |
|---|---|---|
| baseline | 불변 선택 MAIN104 | 같은 생성 상태와 같은 알려진 응답 |
| optimized | MAIN104 + 메뉴 한 번의 성공한 읽기 준비 재사용 | 동일 입력·동일 계측 |

주 검증은 static 1,152쌍(원문 6종×결함 24종×control 2×checker 2×반복 2), transition 112쌍(상태 변화 28×control 2×checker 2), 실제 메뉴 경로 54쌍(범위 3×연결 3×오류 6)의 전수다. 검증 범위가 명시된 독립 합성 기계 계약으로만 `in_sample=false`, `decision_eligible=true`를 적용한다. 법률 질문 holdout을 의미하지 않는다.

run002는 이미 본 ADR1075의 원래 provider 응답 38개를 두 arm에 그대로 공급한 별도 in-sample 보조 측정이다. 35개의 NAVIGATION 화면만 비교하고 다른 1개 REFERENCE 화면은 그 수에 섞지 않았다. 제품 모델/평가 호출은 0회다. 과거 성능 probe를 새 holdout으로 바꾸지 않았다.

재생기는 동결된 실제 service.application을 호출하며 선택 해석만 arm의 코드·데이터 경로로 주입했다. 420개 파일과 실제 import/contracts 경로를 따로 검증하되, 원래 요청을 그대로 재현하기 위해 논리 release metadata는 MAIN104 binding을 유지했다. 따라서 optimized 결과를 실제 선택된 MAIN105 실행으로 보고하지 않는다. 새 release hash의 activation·consumer 검사는 별도다.

## 5. 데이터·모델·재현성

후보는 `view-preparation-r1/rev-001`의 동결 snapshot이며 [freeze](artifacts/design/freeze.json), [release rebase](artifacts/design/release-rebase.json)에 모든 파일을 결속했다. 데이터 generation, profile, schema, prompt, 모델/provider, 출력 상한 없음, 검색·메뉴·행동 정책과 호출·도구·시간 예산은 MAIN104와 같다. 주 검증은 tiny 메모리 SQLite뿐이고 보조 재생만 같은 선택 실데이터를 arm별 순차 적재했다.

재사용 객체는 `offer_choices` 지역 변수로 한 번만 만들고 저장하지 않는다. 첫 검사는 기존 순서를 유지하고 성공한 결과만 보관한다. 매 hit의 `check_unchanged`, 정확한 범위·witness·endpoint 검사와 실행 시 재검사는 유지한다. 키는 typed 구조이며 원문 JSON 직렬화나 본문 복사를 하지 않는다. checker가 없거나 비지원·순환 값이면 원래 경로를 사용한다.

## 6. 결과

- 주 검증 1,318/1,318쌍 동등, 불일치 0. 420개 서빙 파일과 9,232개 엔진 dependency pin 확인.
- 반복 3회 최소 사례에서 원문 조회 6→2회, checker 호출 6→4회. 실제 메뉴 4범위×2화면에서는 원문 조회 88→40회였고 두 번째 화면도 다시 검사했다.
- 보조 재생 각 arm의 보호 요청 38/38, NAVIGATION 화면 35/35, 최종 답변 내용이 원래 기록과 같았다. 생성되는 view ID와 답변/run/query ID만 비교 사본에서 구분하며, 답변 ID는 실제 새 journal에 별도로 결속했다.
- 주 검증 strict check {len(primary['checks'])}개와 보조 check {len(secondary['checks'])}개 모두 통과. [주 결과](artifacts/run-001/result.json), [원시 쌍](artifacts/run-001/finite-pairs.jsonl.gz), [보조 결과](artifacts/run-002/result.json).

## 7. 사례별 오류 분석

권한 소실, source/본문/span/hash 변경, bool·float 좌표, checker 예외, 첫 읽기 뒤 실패, 실패 뒤 정상 회복, 반환값 변경, 다른 session/store 및 새 view를 검증했다. 실패 결과는 cache하지 않는다. Timeout/Operational 오류는 기존 preview 복구 담당과 기록을 유지한다. 범위별 `delivered_blocks(s, scoped)`는 계속 실행한다. 이 ADR의 두 실행에서 실패한 arm은 없다. 과거 ADR1073/1075의 원시 기록은 변경하지 않았다.

## 8. 비용·지연·회수 규모

주 합성 감사 {primary['wall_seconds']:.6f}초, peak RSS {primary['peak_rss_kib']:,}KiB. 신규 모델 호출·토큰·비용 0이다.

| 동일 계측의 알려진 응답 재생 | baseline 초 | optimized 초 | 감소 |
|---|---:|---:|---:|
| 35회 화면 준비 합계 | {view['baseline']:.6f} | {view['optimized']:.6f} | {view['reduction_percent']:.3f}% |
| 모델 없는 전체 요청 재구성 | {request['baseline']:.6f} | {request['optimized']:.6f} | {request['reduction_percent']:.3f}% |

초기 application 준비와 offline transport는 [보조 결과](artifacts/run-002/result.json)에 별도 기록했다. 화면 hash·파일 저장 시간은 화면 timer 밖이다. 요청 시간에는 offline harness 비용이 포함된다. 함수별 inclusive 시간은 중첩되므로 합산하지 않는다. 각각 한 경로의 paired replay이며 p95·새 live 전체 응답시간·GENOS 성능이 아니다.

## 9. 해석

같은 화면을 만드는 동안 확보 원문 전체를 여러 번 검증하던 비용을 줄였다. 모델에게 보이는 선택지나 연결 조회 범위를 축소한 효과가 아니며, 권한·본문 검사를 없앤 것도 아니다. SQL 수정 이후 남은 큰 비용이 반복 읽기 준비였다는 메커니즘을 주 계약 검사와 실제 trace 재생이 서로 다른 범위에서 뒷받침한다.

## 10. 한계와 일반화 가능 범위

모든 임의 데이터·동시성·고장 일정을 증명하지 않는다. 메뉴는 동기식이며 `check_unchanged`가 저장소 불변성을 보장한다는 계약을 전제한다. 의도적으로 생략한 중복 I/O의 특정 호출 번호에만 연결한 임의 장애 스케줄은 동일 사건으로 비교할 수 없다. 새 법률 판단·온톨로지 효과·외부 모델 응답시간·GENOS는 측정하지 않았다. 알려진 38응답 재생을 법률 품질 근거로 사용하지 않으며 `quality_certified=false`, `quality_gate_override=false`다.

## 11. 운영 결정·롤백 조건

사용자가 전체 MAIN 반영을 명시했다. 동결 후보는 정확한 MAIN104 기반이고, 작업 코드에는 기존 별표 연결과 선택된 directory 정책이 추가로 있으므로 파일 전체를 덮어쓰지 않고 준비 기능만 적응해 통합했다. [작업 통합 감사](../../../09_ARTIFACTS/AUDITS/20261027-navigation-view-working-integration/integration.json)의 파일 지문과 별도 검사를 함께 남겼다. 두 코드가 바이트 동일하다고 보고하지 않는다.

정확한 source·결과·candidate·rebase를 결속한 stable `rag_main_promotion prepare/apply --confirm-main`으로만 선택을 바꾼다. 원문·권한·hash·상태·서빙 회귀 시 새 receipt로 MAIN104 바이트를 선택한다. 이 완료 ADR을 사후 배포/메일 결과로 고치지 않고 별도 MAIN105 감사와 Samsung 인계 기록을 연결한다. GENOS 반입·배포는 별도다.

## 12. 재현 명령

원래 실행 순서는 `prepare.py→freeze.py→audit.py`, 이후 `native_replay.py baseline`, `native_replay.py optimized`, 결과만 읽는 `native_summary.py`다. 동결 runner와 입력은 [freeze](artifacts/design/freeze.json), 원시 증거는 [artifact manifest](artifacts/manifest.json)에 있다. 완료 실행을 덮어쓰지 않는다. 새 재현·후속 후보는 새 ADR로 선점한다.

최종 구조 검사는 `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse --final`이다. 적용 후 서비스 확인과 현장 인계는 이 실험의 완료 source와 별개다.
'''
(ADR/'README.md').write_text('---'+meta+'---\n'+body)
(ADR/'실험/README.md').write_text('''# 원문 준비 재사용의 두 가지 검증

| 실행 | 역할 | 결과 |
|---|---|---|
| run001 | 신규 사전 고정 유한 기계 계약 | 1,318쌍 전수 동등, 오류·권한·상태 보존 |
| run002 | 알려진 ADR1075의 저장 응답 재생 | 각 arm 38개 보호 요청·35개 화면·답변 내용 exact, 신규 모델 0 |

법률 정답·온톨로지 품질 holdout은 없다. in_sample=false는 명시된 독립 유한 계약에만 해당한다. 재생은 알려진 in-sample 성능 보조이며 원문·모델 응답을 변경하지 않았다. 주 검증과 보조 측정의 원시 결과를 각각 artifacts/run-001, artifacts/run-002에 보존한다.
''')
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1076').glob('*.py'))
put(ADR/'artifacts/manifest.json', {'schema_version':'adr-artifacts-v1', 'adr_id':'ADR-1076',
    'created_at':manifest['reservation']['created_at'], 'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)), 'sha256':sha(p), 'bytes':p.stat().st_size,
        'description':'Frozen independent finite contract or known-response native reconstruction; post-execution reporting scripts separately identified by freeze membership.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]})
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1076 화면 원문 준비 재사용](ADR-1076-navigation-view-preparation-reuse/README.md) — MAIN104+제품2개·31핀, 신규1,318쌍 동등·저장응답38개/화면35개 재생 exact. MAIN 선택과 GENOS는 별도.\n\n'
if 'ADR-1076-navigation-view-preparation-reuse/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n', '# ADR workspace\n\n'+line, 1))
print('Scoped Accepted source drafted; candidate/frozen execution unchanged; MAIN activation remains separate')
