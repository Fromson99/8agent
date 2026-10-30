from common import *
import gzip
x=read(ART/'run-001/result.json');b=x['arms']['baseline'];s=x['arms']['semantic'];build=x['build'];old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1121-ontology-semantic-compilation/artifacts/build/result.json')
review={'schema_version':'source-semantic-review-v1','rubric_path':str((ART/'rubric.json').relative_to(ROOT)),'rubric_sha256':sha(ART/'rubric.json'),'reviewer':'Codex source comparison, not independent legal certification','answer_cells':1,'dimensions':[
 {'id':'separate_effects','baseline':'PASS','semantic':'PASS','basis':'Both final texts distinguish gain threshold eligibility and separately conditioned decreased-value refund. Semantic final explicitly says below threshold is excluded.'},
 {'id':'presumption_deeming','baseline':'FAIL_WRONG_MERGE','semantic':'FAIL_OMITTED','basis':'P10 separates mixed-assets presumption and collateral-financed deeming. Baseline combines both as 추정; semantic final omits both.'},
 {'id':'gain_inputs_scope','baseline':'PASS','semantic':'PASS','basis':'Both retain (settlement per-share value - initial per-share value - real enterprise gain per share) times share count and settlement-date rule.'}],
 'dimension_passed':{'baseline':2,'semantic':2},'dimension_total':3,'paired_dimensions':{'candidate_only_pass':0,'baseline_only_pass':0,'both_pass':2,'both_fail':1},
 'all_primary_dimensions_case_pass':{'baseline':{'passed':0,'total':1},'semantic':{'passed':0,'total':1}},'legal_accuracy_certified':False,
 'errors':[
 {'stage':'PROPOSAL','type':'condition_exception','detail':'N18 effect depends only on N10 calculation; generated N14-N17 applicability/threshold conditions lack dependency edges to it. They and four other effect nodes are outside the selected N18/N19 closure. Originals remain fully delivered.'},
 {'stage':'PROPOSAL','type':'unsupported_inference','detail':'N22 repeats historical C3 error: mixed-assets presumption and collateral-financed deeming combined as 추정, with modality OBLIGATION. Its exact P10 quote contains both distinct expressions. Node is not in selected plan.'},
 {'stage':'PROPOSAL','type':'condition_exception','detail':'N19 quotes 환급받을 수 있다 but labels modality OBLIGATION; syntactic/source-quote validation does not validate legal modality.'},
 {'stage':'COMPOSE','type':'numeric_temporal','detail':'Semantic final describes 30 percent basis using initial tax/acquisition values and share count, omitting real enterprise gain. Source P21, node N12 expression (N4 + N5) × N9 × 30/100, and ASSESS condition leaf4 preserve both amounts. Loss occurred in final prose.'},
 {'stage':'BASELINE_ASSESS_AND_COMPOSE','type':'condition_exception','detail':'Baseline repeats collateral acquisition as presumption; source P10 says deemed.'},
 {'stage':'SEMANTIC_ASSESS_AND_COMPOSE','type':'required_issue_omission','detail':'Presumption/deeming and other application extensions absent from final answer; 8 generated nodes omitted from compiled goal closure. No claim that this single-pair association establishes causality.'},
 {'stage':'HARNESS_PREFIX','type':'other','detail':'Semantic binding changed request-local judgment handles; old raw compact aliases required one native repair. Same canonical READ and exact120 source options verified afterward. Causal timing or call-saving comparison invalid.'}],
 'decision':'Implementation and actual data-to-ASSESS integration verified; no semantic quality improvement. Do not promote or prune originals using this proposal.'}
put(ART/'review.json',review)
cost_build=sum(u.get('cost_usd',0) or 0 for u in build['usage']);cost_old=sum(u.get('cost_usd',0) or 0 for u in old['usage']);cost_answers=b['usage']['cost_usd']+s['usage']['cost_usd']
summary='MVP 문서·660파일 격리 구현·111검사와 실제 생성/답변 비교 완료. 25개 의미노드·23의존을 생성해17노드 계획을 ASSESS에 전달했으나, 사전3항목은 양쪽2/3으로 품질 개선을 확인하지 못했다.'
report=f'''온톨로지 의미 조립 MVP 실제 결과 — 2026-10-27

결론
{summary}
현재 선택 MAIN107(genos-mode-20261027-r1)을 기반으로 온톨로지만 붙인 후보를 사용했다. MAIN·GENOS·운영지식·Git commit/push는 변경하지 않았다.

구현과 실제 실행
1. 에이전트 판단3개 + 실제 전달된 원문28조각에서 측정 대상·입출력 단위·산정 표현·범위/시점·조건·효과·예외 대상을 생성했다.
2. 서버가 원문 해시·정확한 인용·실제 판단 ID·의존 대상·순환을 검사한다. 계산 결과나 사건 사실을 만들어 넣지 않는다.
3. 순수 데이터 컴파일러가 목표의 의존관계와 해당 예외를 조립한다. 이번에는25노드·23의존·예외대상1개 중17노드가 선택됐다. 미확인4개. 컴파일 자체의 모델 호출0회.
4. 실제 MAIN107 기반 native HTTP에서 원문과 계획을 ASSESS→COMPOSE로 전달했다. 알려진 CM023 1문항이며 구조 생성 입력에는 기준답변·사후 평가를 넣지 않았다.

실패도 보존
1121: 합성/API110검사는 통과했으나 실제 생성2회 모두 효과→예외 역방향 필드 오류로 거절. 534.738초. 답변 비교 미실행.
1124: 예외 방향을 스키마 안내에 명시하고 오류에 노드·역할·대상을 포함. 합성/API111검사 통과. 첫 새제안은 목표를 ID 대신 문장으로 써서 거절, 보완1회 후 통과. 생성2회 {build['seconds']:.3f}초, 비용${cost_build:.8f}.
운영 승인이 아니라 EXPERIMENT_PROPOSAL_NOT_APPROVED 상태다. 자동 반전·수작업 정답 그래프로 대체하지 않았다.

비교
기존 A1: 새모델{b['new_model_calls']}회 + 재생2회, {b['seconds']:.3f}초, PARTIAL/LIMITED_ANSWER, 사전3항목2/3.
의미 A1: 새모델{s['new_model_calls']}회 + 재생2회, {s['seconds']:.3f}초, PARTIAL/LIMITED_ANSWER, 사전3항목2/3.
둘 다 제외/환급 구분과 이익 산정식·정산시점을 보존했다. 기준은 추정/간주를 합쳤고 의미조건은 그 내용을 누락했다.
모든 사전항목을 만족한 질문은 양쪽0/1. 이는 이 probe의 제한된 점검 기준이며 일반 법률 정답률이 아니다.

왜 아직 정답 품질이 좋아지지 않았나
A. 생성 판단의 의미 오류: N22는 원문 P10의 '추정한다'와 '본다'가 둘 다 인용돼 있어도 이전 판단의 오류를 복제해 하나의 추정으로 썼다. N19의 '환급받을 수 있다'도 OBLIGATION으로 분류했다. 인용 일치만으로 의미가 맞지는 않는다.
B. 의존 누락: N18 효과가 이익 계산 N10만 입력으로 연결했고, 이미 생성한 N14~N17 성립 조건을 연결하지 않았다. 목표N18/N19로 컴파일하니 핵심조건4개를 포함한8개가 계획에서 빠졌다. 원문28개는 유지했으므로 실제 원문 누락은 아니다. 이 상태에서 원문을 계획대로 잘라 제공하면 위험하다.
C. 최종 서술 변형: N12와 ASSESS에는 기준금액의30% 대상에 최초가액과 기업가치 실질증가분이 모두 있었다. COMPOSE가 '증여세 과세가액 또는 취득가액 합계액'으로 바꾸면서 기업가치 증가분을 빠뜨렸다. 이는 원문 전달 실패가 아니라 생성된 최종 문장의 오류다.

비교 장치의 한계
첫 질문해석/READ를 같은 저장응답으로 재생했다. 의미조건에서는 profile binding에 따라 임시 판단번호가 바뀌어 보완1회가 추가됐다. 보완후 같은 canonical READ를 선택했고, ASSESS 원문120옵션의 문서·block·범위·본문은 완전히 같음을 사후 확인했다. 두 조건의 전체 시간·호출 차이를 순수 온톨로지 인과 효과로 쓰지 않는다. 다음 비교에서는 저장된 짧은 번호를 그대로 재생하지 말고 현재 참조에 결속해야 한다.

원문·전송 검증
각208원문단위, 합416검사: 원문 불일치0·권한위반0. 실제 ASSESS 원문120/120 동일, 실제전송 원문 불일치0·모르는 온톨로지 근거번호0·의미 인용문 전달오류0. 양쪽 최종 원문2개 인용. 출력상한 필드0.111검사의 import유출0·동결파일변경0.

시간·비용
1124 생성2회+답변5회=새모델7회, 평가모델0. 답변비용${cost_answers:.8f}, 생성비용${cost_build:.8f}; 1124합${cost_answers+cost_build:.8f}.
1121실패생성2회를 포함한 이번 작업 누적새모델9회, 비용${cost_answers+cost_build+cost_old:.8f}. 의미구조 생성은 질문 처리와 분리한 선행 작업이며 아직 생산성/재사용 편익을 입증하지 못했다.

다음 수정 근거
- 원문의 법적 표현과 생성 노드의 역할·효과를 독립 검토할 필요가 있다. 과거 에이전트 판단을 정답으로 복제하지 않는다.
- 생성한 조건이 어떤 효과의 필수 입력인지 빠짐없이 결속하고, 미연결 핵심 조건을 보여주는 검사가 필요하다.
- ASSESS의 산정 입력·예외·법적 표현이 COMPOSE에서 삭제/결합되는 것을 확인해야 한다.
- 이런 의미 검증 전에 전체 원문을 컴파일 계획만으로 가지치기하지 않는다.

정본
freeze.json, build/result.json, build/binding.json, build/compiled.json, 의미구조_실제생성본.txt,
post-selection-input-check.json, review.json, retrieval-ledger.json, run-001/result.json.
각조건/cm-023의 raw·canonical·wire·answer.txt·audit.json·wire-audit.json은 원본을 보존한다.
'''
put(ART/'report-content.json',{'summary':summary,'report':report,'results':f'양쪽 HTTP200, PARTIAL/LIMITED_ANSWER, 사전3항목2/3. 생성25노드/23의존, 실제계획17노드. 111합성/API검사, 실제416원문검사 불일치0. [상세 결과](artifacts/실험결과.txt).','cost':f'새모델7회(생성2+답변5), 평가0. 생성{build["seconds"]:.3f}초. 답변 baseline{b["seconds"]:.3f}초/semantic{s["seconds"]:.3f}초. 의미조건 재생번호 보완1회로 인과적 속도비교 불가. 비용${cost_answers+cost_build:.8f};1121실패까지9회/${cost_answers+cost_build+cost_old:.8f}.'})
print(summary);print('total calls 9 cost',cost_answers+cost_build+cost_old)
