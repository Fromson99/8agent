"""Complete only a successful pre-frozen SQL and native contract source."""
from common import *
from datetime import datetime, timezone
import re
import subprocess

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
view = secondary['timing']['view_seconds']
manifest['results'].update(status='complete',by_arm={
    'baseline':{'status':'complete','new_sql_fixture_pairs':1582,'sql_observations':404062,
        'code_role':'Observed failed1078 candidate used unchanged as SQL comparator; not a completed lineage parent.',
        'native_role':'Historical1076completed35viewwindows only; original whole-service failure unchanged.'},
    'optimized':{'status':'complete','new_sql_fixture_pairs':1582,'sql_observations':404062,
        'new_native_recorded_responses':38,'native_frames_exact':35,'native_final_answer_exact':True}},
    comparisons=[{'pair':['baseline','optimized'],'primary_equivalent_fixture_pairs':1582,
        'primary_mismatches':0,'known_secondary_view_timing':view,
        'full_request_speed_comparison':False,'legal_accuracy':'NOT_MEASURED'}],
    usage={'new_product_model_calls':0,'new_evaluator_calls':0,'new_input_tokens':0,'new_output_tokens':0,
        'saved_responses_supplied_to_optimized':38},
    latency={'primary_wall_seconds':primary['wall_seconds'],'known_secondary':secondary['timing'],
        'limit':'Only35completeviewwindows compared. Historical baseline service failed later; no fullrequest/GENOS/p95 claim.'},
    error_taxonomy=[],main_wiring='promotion-candidate',quality_certified=False,
    limitations=[primary['scope'],primary['limitations'],secondary['scope'],
        'Cache primary1318+280 pairs are already-observed support; only1582SQLpairs are new prospective contracts.'],
    working_integration_status='NOT_APPLIED_IN_THIS_SOURCE; exact hunk integration and activation are separate audit records.')
put(ADR/'실험/manifest.json',manifest,replace=True)
meta = (ADR/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Accepted'),('main_wiring','promotion-candidate'),('decision_eligible','true'),('in_sample','false')]:
    meta = re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
body = f'''
# ADR1080 — 참조 관계의 가시성 단건 조회와 누적 후보 검증

## 1. 결정 요약

사전 동결한 SQL 계약1,582쌍과 알려진 native38응답 재생이 모두 통과하여 기계 계약 범위에서 Accepted, promotion-candidate다. 35개 화면·행동·전달 원문과 최종 답변이 원래 완료1075와 일치했다. 선택 MAIN104 대비 제품3파일과 pin31개다. 실제 작업 코드 통합·MAIN 활성화·GENOS 배포·메일은 별도이며 이 source는 활성 포인터를 바꾸지 않는다.

## 2. 문제와 변경 전 구조

처음211초 문제의 정의 연결 SQL은 MAIN104에 이미 반영됐다. 이후 실제 MAIN104 관찰에서35번 `Investigation.view`가702.136초를 차지했다. 같은 확보 원문의 반복 검증 외에 연결 관계 TEMP VIEW4개가 `reference_id IN (SELECT id FROM temp.reference)`로 전체 가시 참조ID를 반복 열거했다. compact reference VIEW는 payload/body를 결합하므로 단건 관계 조회에도 전체 payload scan이 생겼다.

새 제품 변경은 `search_selection.py`의 공통 술어1줄을 `EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)`로 바꾸는 것이다. 같은 권한 reference VIEW와 숨김 조건을 쓰며 catalog DISTINCT·정렬·cursor·LIMIT은 바꾸지 않는다. 관측된1078의 호출 한 번 소유 읽기 준비2모듈을 함께 검증하며, 선택 후 preview 정책 등 다른 작업 기능은 포함하지 않는다.

## 3. 가설과 사전 판정 기준

[기준](artifacts/design/criteria.json), [행렬](artifacts/design/sql-matrix.json), [보조 재생 계약](artifacts/design/secondary-replay.json)을 실행 전에 동결했다. NULL·orphan·중복·숨김·빈집합·반환 순서·cursor/LIMIT·요청된 오류와 읽기 전용 상태를 보존해야 한다. 모든 선언 쌍이 동등해야 하며 plan에서는 가시 참조 전역 LIST scan이 ID point lookup으로 바뀌어야 한다. 기준 변경·불일치·누락·hash drift를 허용하지 않는다.

## 4. 실험 설계

| 구분 | 쌍 수 | 범위 |
|---|---:|---|
| 참조 가시성 | 1,344 | legacy/compact,7참조상태,16숨김mask,3bind모드,2중복도 |
| 출처 경계 | 192 | 누락/NULL/빈ID/NULL문서,4관계,3모드,2중복도 |
| 입력 순서 | 12 | 정순/역순과 layout·bind모드 |
| 요청 오류 | 18 | 요청한 손상JSON·필수 relation누락 |
| point plan | 16 | 2layout×2활성모드×4관계 |

baseline은1078의 관측된 후보 코드, optimized는 같은 코드에 SQL1줄과 pin만 바꾼 후보다. 각 arm에서 결과/오류404,046조회와16 EXPLAIN, 합계404,062관찰을 했다. 쌍 수와 개별 query 수를 혼용하지 않는다. 독립 fixture-row oracle과 두 arm의 타입·행·오류·metadata를 비교했다.

완료 부모는1075/observed다.1076/1078은 native 비교기 경계에서 실패한 원래 상태로 보존한다. 그들의 성공한1,318/280 캐시 계약은 이미 관측된 보조 근거이며 새 독립 표본이나 완료 부모가 아니다. 이 ADR의 새로운 out-of-sample 범위는 SQL 유한 계약이다.

## 5. 데이터·모델·재현성

공식 snapshot/register/freeze의420서빙파일을 [freeze](artifacts/design/freeze.json)와 [rebase](artifacts/design/release-rebase.json)에 결속했다.3제품모듈 이외 profile·schema·prompt·모델/provider·상한없음·검색/메뉴·예산·데이터는 MAIN104와 동일하다.9,232 dependency pins를 확인했다. 합성 주검사는 실데이터0·네트워크0·모델0이다.

보조 native는 frozen service.application을 실행하되 arm의 실제 코드/데이터 경로만 선택 주입한다. 논리 릴리스 metadata는 원래 MAIN104를 유지하므로 실제 MAIN105 선택 실행이라고 주장하지 않는다. 실제 binding/import·contracts 경로와420파일은 별도로 검증했다. 원래1075 저장응답38개를 한 번씩 그대로 공급하며 새로운 모델이나 평가 호출은 없다.

## 6. 결과

- 주계약1,582/1,582쌍, arm당404,062관찰,9개 strict checks와9,232pins 통과.
- compact/legacy의 전체scan→ID상관조회 전환16plan 통과. queryplan은 시간 측정이 아니다.
- native38/38 보호요청,35/35 화면·행동·원문·위치hash와 최종답변 내용이 일치했고 완료·게시 상태를 확인했다.
- [주 결과](artifacts/run-001/result.json)·[압축 원시](artifacts/run-001/sql-pairs.jsonl.gz)·[보조 결과](artifacts/run-002/result.json).

## 7. 사례별 오류 분석

SQL NULL과 기존 NOT IN의 NULL 영향은 그대로 보존하며 후보가 임의로 고치지 않는다. 제외집합이 비어도 latest-only가TEMP VIEW를 설치하는 실제 경로와 둘 다 비어 조기 반환하는 경로를 따로 검사했다. 조회한 손상JSON/필수relation 누락은 두 arm 모두 같은 오류를 냈다.

이전1076은 call38 원장 실행별ID 비교에서,1078은 call36 view UUID와 preview가 공유Vnamespace에서 정렬되어V1/V2가 바뀌는 비교에서 중단됐다. 원래 실패를 수정하지 않는다. 새 harness는 실제 model_view·NUMBERED_REFERENCES hash와 codec mapping을 재구성하고 canonical 본문·동일previewID·SELECT/COMPOSE 원장 선택을 증명한 경우만 비교 사본의 생성값/역할alias를 구분한다. 실제 요청·원문·응답은 바꾸지 않으며 원응답이 바뀐alias를 사용하면 거부한다. 현재스키마 검증도 필수다. raw wire/schema exact 수치는 보조 결과에 별도로 남긴다.

## 8. 비용·지연·회수 규모

합성 감사 {primary['wall_seconds']:.6f}초, peak RSS {primary['peak_rss_kib']:,}KiB다. 제품 전체 응답시간으로 사용하지 않는다. 같은 wrapper의 완료35view 합계는 과거1076 baseline {view['baseline']:.6f}초 → 후보 {view['optimized']:.6f}초({view['reduction_percent']:.3f}% 감소)다. 모델시간은 포함하지 않는다.

과거baseline은35view 뒤 compose에서 실패했다. 따라서 전체요청 개선율은 계산하지 않는다. 후보 초기준비·offline transport·전체재생은 보조결과에서 구분한다. call36/38 새원장검사는 view timer밖이며 화면hash/쓰기 또한 timer밖이다. 각1회·실행시각/파일cache상태가 달라 p95나일반처리량으로 확대하지 않는다. 중첩 inclusive함수시간은 합산하지 않는다.

## 9. 해석

SQL 전수계약은 선언한 DB 스키마/입력에서 결과를 보존하면서 전체 가시참조 열거를 피함을 뒷받침한다. 기존 캐시계약은 새표본으로 세지 않되 실패/권한/새view 경계의 별도 근거로 유지한다. 알려진 전체native경로는 두 최적화를 합친 화면/행동/원문/답변 보존과 실제view시간을 보조한다. 새로운 법률 정답률이나 온톨로지 효과를 측정한 것은 아니다.

## 10. 한계와 일반화 가능 범위

TEXT ID·기본 BINARY정렬의 게시된 SQLite세대가 범위다. 임의affinity/collation·동시변경·생략한 중복I/O에만 붙은 고장일정은 인증하지 않는다. SQL 캐시는없고 읽기준비수명은한offer_choices다. 매hit불변성검사와새view첫검사, 실제실행의권한·원문·witness·endpoint검증은유지한다.

전체scan만우연히만나던 **조회하지 않은 전역 손상JSON의 오류시점은 동등성 주장밖**이다. 전역유효성은 적재/게시/세대불변검사의 책임으로 유지한다. 요청된 손상오류는 검사했다. `quality_certified=false`; 새법률holdout·모델속도·GENOS Oracle성능·현장배포를주장하지 않는다. 이전품질우회를재사용하지 않는다.

## 11. 운영 결정·롤백 조건

완료source와정확누적후보를승격입력으로준비한다. working은기존selected-directory/별표기능을보존해3hunk만적응하며후보와동일파일이라고하지않는다. 실제MAIN은별도공식prepare/apply와활성포인터·service소비자검증이필요하다. 권한·원문·hash·상태·서빙회귀시불변MAIN104로새rollback영수증을남긴다. 이완료ADR에후속MAIN/메일상태를소급기입하지않는다.

## 12. 재현 명령

`06_TOOLS/EXPERIMENTS/adr_1080/prepare.py → freeze.py → audit.py → native_replay.py optimized → native_summary.py` 순서다. 입력은freeze, 원시와보고서는artifactmanifest로결속한다. 완료산출물덮어쓰기는금지하며후속은새ADR로선점한다. stable runner의 `adr_structure.py validate --final`과graph를확인한다. 전역graph의기존오류와이번source오류를구분한다.
'''
(ADR/'README.md').write_text('---'+meta+'---\n'+body)
(ADR/'실험/README.md').write_text('# SQL 계약과 알려진 native 재생\n\nrun001: 새 SQL1,582쌍 전수동등. run002: 원래38응답·35화면·최종답변 보존. 기존1318/280캐시계약은 관측된 보조 근거이며 새로운 holdout이 아니다. MAIN104 유지, 작업 통합·승격은 별도다.\n')
# This question belongs to native run002; run001 has synthetic SQL fixtures.
question = '''# 질문001 — fsc-hard-005

## 1. 실행 메타

ADR1080 run002 / optimized, known in-sample native replay. 주run001은 별도합성SQL계약이다. 원본 상태exact, 원래38응답그대로재생; 신규모델/평가0. 실행시각·환경은 run002/optimized/reservation.json과result.json에기록한다.

## 2. 사용자 질문 원문

외국금융회사 국내지점의 총자산이 사업연도 말 이전 6개월 중 7천억원을 초과한 사실이 있으나, 이후 총 자산이 7천억원 미만으로 유지되는 경우 준법감시인이 위험관리책임자를 겸직할 수 있는지

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

새법률채점은하지않았다. 완료1075의답변은재생출력동등성참조이며제품입력에주입한정답이아니다. 원래모델응답38개는사전고정된수송응답으로만순차공급한다.

## 4. 제품 입력을 구성한 원값

design/secondary-inputs.json이원래요청·38raw응답·35화면·완료답변의경로/hash를결속한다. run002/optimized/runtime의실제journal은재생된요청과회수좌표전체를보존한다. 집계치를임의재생성하거나원문을보고서에중복복사하지않는다. 새gold회수채점/선택은없어단계별gold recall은해당없다.35화면data/actions/locationhash를원래기록과전수비교했다.

### 회수·탈락 단계 원장 — run·arm별

새gold 회수채점은 해당없다. 실제 회수·행동·전달 원문은 원본1075 및 새 run002 native journal에 전수 보존하며35개 화면 hash를 비교한다. 제품 입력에 기준답변은 들어가지 않았다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

신규외부호출0. 알려진38응답을그대로공급했다. 원래system/user/schema/도구/응답/사용량은secondary-inputs inventory와원래1075journal에, 실제재생요청·검증은run002/optimized/runtime및transport-checks.json에보존한다. 보호요청38개와원문/의미본문이동등하다. call36역할alias와call38원장ID의검증된차이는design/secondary-replay.json에실행전고정했고실제payload/응답rewrite는0이다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

새중간LLM 호출은0이다. 원래38응답에 포함된 단계·원문은 입력 inventory와 실제 journal에 결속되어 있으며 임의 추가 응답·repair·fallback은 허용하지 않았다.

## 7. 채점 호출과 반복 판정

새judge 호출과 법률 채점은0이다. 원래 완료1075의 답변은 알려진 출력동등성 참조다. SQL 행 oracle과 native protected request/frame/answer 비교는 기계 계약이며 법률 판단이나 다수결이 아니다.

## 8. 사례 최종 판정

run002/optimized/response.json 및 native journal에 전체답변·인용·receipt가 있다. 원래 완료1075와 내용이exact이며 생성답변ID/queryID는 각 실제원장에 결속했다. run002/result.json의 모든 strict검사가 통과했다. 이전1076/1078실패는 보존하며 현재결과로 덮지 않는다. known trace의 기계적완주이지 독립법률holdout·온톨로지효과·GENOS성능은 아니다.

신규제품/평가모델0.35개완료view구간비교만 허용하며 초기준비·전체재생·offline수송은 별도 기록한다. 과거baseline은 마지막compose에서 실패했으므로 전체응답개선율은 계산하지 않는다. 모든 원시경로와hash는 artifacts/manifest.json, 실행전동결은 design/freeze.json이다.
'''
(ADR/'실험/질문-001-fsc-hard-005.md').write_text(question)
subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(ADR)],cwd=ROOT,check=True)
paths = [p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
paths += list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1080').glob('*.py'))
paths.append(ROOT/'06_TOOLS/EXPERIMENTS/adr_1080/sql-matrix.json')
assert read(ADR/'artifacts/manifest.json')['files'][0]['path'] == 'TODO'
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1080',
    'created_at':manifest['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
        'description':'Frozen new SQL contract, known native replay, or exact cumulative candidate audit; earlier failures preserved.',
        'contains_raw_prompts_and_outputs':'run-002' in str(p)} for p in sorted(paths)]},replace=True)
index = ROOT/'04_EXPERIMENTS/ADR/README.md'
text = index.read_text()
line = '- [ADR1080 가시참조 단건조회와 누적최적화](ADR-1080-reference-visibility-point-check/README.md) — 새SQL1,582쌍·원래38응답/35화면/답변동등, 기존실패보존. MAIN활성화는별도.\n\n'
if 'ADR-1080-reference-visibility-point-check/README.md' not in text:
    index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
print('Scoped Accepted isolated source drafted, question/hash complete; MAIN unchanged')
