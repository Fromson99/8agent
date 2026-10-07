"""Focused descriptive findings from saved responses; does not alter evaluator scores."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0503-gemma-obligations-bound-paired-probe'
def read(p):return json.loads(p.read_text())
def main():
 d=read(A/'artifacts/trace-diagnostics.json');metrics=read(A/'artifacts/metrics.json');n=d['candidate_cases_with_plan'];bad=d['candidate_cases_all_requirements_one_character'];b=metrics['by_arm']['baseline'];o=metrics['by_arm']['obligations'];pairs=metrics['paired_outcomes'];comparable=7-pairs.get('unresolved',0)
 onechar=[]
 for r in d['by_case']:
  if r['arm']=='obligations':
   requirements=[x['requirement'] for c in r['calls'] if c.get('plan') for x in c['plan']['demands']]
   onechar.append('|'+r['case_id']+'|'+', '.join(dict.fromkeys(requirements))+'|')
 text=f'''# Gemma agent 판단 보강 검증: 직접 관측한 내용

**현재 보강판의 성능 향상은 확인하지 못했다.** 요구 추적용 계획이 정상적인 요구 문장으로 생성되지 않았고, 일부 검토에서 요구 ID를 잘못 사용했다. 이번 결과로 Gemma 자체의 추론 능력 저하를 주장하지 않는다.

7문항을 같은 Gemma FP8로 수정 전후 각 1회 실행했다. 양쪽 모두 최종 판정이 가능한 비교는 {comparable}/7쌍이었다. 나머지는 실행 미완료 또는 평가 불일치로 구분하며 정답·오답 변화로 계산하지 않는다. 최종 답이 없어도 전송된 모델 초안에서 관측한 내용은 별도 기록한다. 아래 직접 관측은 사후 설명이며 사전 고정한 자동 점수를 바꾸지 않는다. 현행 법률의 독립 인증이나 사람 확정 채점이 아니다.

| 구분 | 관측 | 근거와 해석 |
|---|---|---|
| 원문 조건 설명: 긍정 | 수정 전 CM009가 제외 대상·3년·재량 표현을 유지 | “적용하지 않을 수 있습니다”를 보존. 원문 설명 능력의 긍정 신호 |
| 비슷한 개념 구분: 부분 긍정·과도한 유보 | 수정 전 CM025가 탐색 중 일반 계산과 별도 차감 규정을 구분했지만 최종 문단은 비움 | 탐색 마지막 reason은 별도 명시 규정을 발견하지 못했다고 설명. 최종 단계는 paragraphs=[]로 유보. 이해한 내용을 적절한 한계와 함께 답으로 전달하는 데 실패 |
| 적용 해석의 한계 표시: 약점 | 수정 전 CM033은 60일 규정을 설명했지만 전환 법인에 관한 문언 해석·공식 확인 필요성을 충분히 구분하지 않음 | “원문 미평가”라는 일반적 한계 문구가 질문에 대한 구체적인 해석상 유보를 대신하지 못함 |
| 확정·유보 배분: 약점 | 수정 전 FSC009는 위탁 해당 여부를 조건부로 남기고 법규상 금지되지 않는다고 표현 | 저장 기준은 위탁 해당은 답하고 위법 여부는 사실 부족으로 유보. 서로 다른 요구에 확신을 배분하는 문제가 재관측됨 |
| 조건·예외 보존: 초안의 긍정 신호 | CM050 보강판의 두 번째 초안이 신성장·원천기술 보유 **또는** 기술등급 상위 50%를 유지 | 공시대상기업집단 제외의 범위도 해당 기업 유형에 묶음. 최종 검토된 답변이나 전후 개선의 입증으로 보지는 않음 |
| 규칙 적용: 보강판에서도 남은 약점 | FSC009 보강판 초안은 단순 참조 구조를 업무위탁보다 정보 구매에 가깝다고 결론 | 저장 기준의 업무위수탁 해당 판단과 반대. 일반 규정만으로 특정 구조의 결론을 확정하는 위험이 남음. 최종 검토 완료 전 초안임을 구분 |
| 요구 계획: 이번 구현의 문제 | 계획이 나온 보강판 {n}문항 중 {bad}문항에서 모든 요구문이 한 글자 | 정상 문장으로 된 질문 요구를 추적하지 못함. 모델/출력 형식 상호작용을 먼저 확인해야 함 |
| 참조 및 자기검토 연결: 이번 구현의 문제 | CM033 검토에서 요구 ID 대신 질문 문장을 사용했고 같은 오류가 2회 반복 | 실제 obligation 값은 “종전 별도기준에서 연결기준으로 처음 전환하는 법인도 60일인가?”. 기대 값은 해당 계획의 O ID. 계약 검사가 부정확한 연결을 거부했지만 실제 검토는 완료되지 않음 |
| 구체적 안내 후 수정: 긍정 신호 | CM009 보강판의 첫 초안은 obligation_refs에 E 근거 ID를 넣었고, 다음 초안에서는 O 요구 ID로 고침 | ID 수정 사례는 존재함. 다만 해당 실행의 최종 검토 성공을 뜻하지 않음 |

## 요구문 관측값

| 문항 | 실제 requirement 값(중복 제거) |
|---|---|
'''+ '\n'.join(onechar)+f'''

[전체 trace 관측](artifacts/trace-diagnostics.json)에 계획·초안·검토·오류를 보존했다. 원래 SHORT schema는 `pattern: \\S`, minLength 1, maxLength 400이다. [로컬 계약 확인](artifacts/local-short-schema-check.json)에서 한 글자와 완전한 한국어 문장 모두 유효했다. [첫 계획의 필드 관측](artifacts/plan-field-observations.json)에서 같은 응답의 일반 reason은 43~124글자였고, 7건 모두 finish_reason=stop이었다. 전체 답변이 토큰 한도로 잘린 형태는 관측되지 않았다. 원격 structured output에서 SHORT 필드만 한 글자로 나오는 원인은 아직 분리 실험으로 입증하지 않았다. 따라서 곧바로 “Gemma가 질문 분해를 못한다”로 결론 내리지 않는다.

## 후속 보강 우선순위

| 순서 | 바꿀 점 | 확인 기준 |
|---|---|---|
| 1 | 원격 출력 스키마와 SHORT 필드의 호환성 확인·수정 | 요구·주어진 사실·부족한 사실·검토 사유가 실제 의미를 가진 문장으로 생성됨 |
| 2 | 요구 ID를 단순화하고 오류 응답에 실제 허용 ID와 잘못된 값을 함께 제공 | E/O ID 혼동 및 질문 문장으로의 ID 대체를 구체적인 피드백 후 수정 |
| 3 | FSC009처럼 요구별 답변 가능 여부를 따로 검토 | 위탁 해당 판단과 위법 판단의 확정/유보가 기준에 맞게 분리됨 |
| 4 | CM025처럼 제한된 범위의 답을 전달하도록 보강 | “별도 조정 규정 미확인”을 근거 범위와 함께 답하고 전체를 비우지 않음 |
| 5 | 같은 7문항의 재비교 후 새로운 문제로 확인 | 기존 성공의 회귀가 없고 요구 누락·범위·조건·유보의 개선이 반복됨 |

자동 평가에서는 최종 answer가 없는 사례도 claims나 source 설명을 답변으로 간주하거나, 생성되지 않은 결론을 있다고 판단한 경우가 있었다(CM025·CM029 등). 기술적 미평가는 점수 집계에서 제외했고, 평가 원문은 그대로 보존했다. 그러므로 직접 확인하지 않은 자동 채점 이유를 능력 사실로 사용하지 않는다.

현재 두 설정의 확인된 기준답 일치는 수정 전 {b['confirmed_correct']}/7, 보강 후 {o['confirmed_correct']}/7이며, 미확정은 각각 {b['unresolved']}, {o['unresolved']}건이다. 이 숫자는 미확정을 오답으로 친 정확도가 아니다. 비교 가능한 쌍이 적으므로 모델 우열·개선 폭을 계산하지 않는다. 비용·호출·평가 상세는 [전체 보고서](README.md)와 [metrics](artifacts/metrics.json)에 있다.

MAIN과 GENOS는 변경하지 않았다. 이 보고서는 SQL·게시 안정성을 개선 과제로 다루지 않는다.
'''
 (A/'JUDGMENT_FINDINGS.md').write_text(text)
 p=A/'README.md';s=p.read_text();s=s.replace('## 1. 결정 요약\n\n','## 1. 결정 요약\n\n[Agent 판단 중심 직접 관측 및 다음 보강](JUDGMENT_FINDINGS.md)\n\n',1);p.write_text(s)
 print('Focused judgment findings saved')
if __name__=='__main__':main()
