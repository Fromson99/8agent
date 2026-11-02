"""Finalize the single completed live run; never dispatch or alter product code."""
from common import *
import re
P = ART / 'live/review-whatif'
a = read(P / 'audit.json'); r = read(P / 'result.json'); f = read(DES / 'freeze.json')
s = read(P / 'semantic-review.json'); w = read(ART / 'contract-wire-check.json')
def condition(label):
    return next((x['after']['status'] for x in a['responses'][label]['comparison']['comparisons'] if x['node_id'] == 'N2'), None)
checks = {
    'first_baseline_claims': a['responses']['initial']['claims'] > 0,
    'predeclared_followup_baseline_claims': a['responses']['rereview']['claims'] > 0,
    'numeric_conditions': condition('low') == 'TRUE' and condition('high') == 'FALSE' and condition('rule') == 'TRUE',
    'numeric_no_calls': all(t['physical_calls'] == 0 for t in a['turns'] if t['label'] in ('high', 'low', 'rule')),
    'three_accepted_scenario_answers': s['all_passed'],
    'baseline_preserved': r['baseline_preserved'],
    'duplicate_no_calls': all(t['duplicate']['extra_model_calls'] == 0 for t in a['turns']),
    'input_source_integrity': not any(a[k] for k in ('source_mismatches', 'acl_violations', 'wire_mismatches', 'changed_release_files', 'changed_inputs', 'output_cap_fields')),
    'physical_budget_matches': a['physical_budget_matches'],
    'unknown_zero': a['unknown'] == 0,
    'resource_safe': not a['resources']['resource_stop'],
    'main_unchanged': a['active_pointer_unchanged'],
    'cleanup': a['cleanup_completed'],
    **w['checks'],
}
working_changes = [n for n, h in f['files'].items() if sha(ROOT / n) != h]
script_changes = [n for n, h in f['scripts'].items() if sha(ROOT / n) != h]
assert not working_changes and not script_changes
result = {'status': 'NOT_PASSED', 'checks': checks, 'semantic_passed': 0, 'semantic_total': 3,
    'physical_calls': a['physical_calls'], 'reported_cost_usd': a['reported_cost_usd'],
    'seconds': r['seconds'], 'model_seconds': a['model_seconds'], 'turn_calls': a['turn_calls'],
    'unknown': a['unknown'], 'post_unknown_calls': a['post_unknown_calls'], 'missing_usage_calls': a['missing_usage_calls'],
    'source_checks': a['source_checks'], 'delivered_checks': a['delivered_checks'],
    'source_mismatches': len(a['source_mismatches']), 'acl_violations': len(a['acl_violations']), 'wire_mismatches': len(a['wire_mismatches']),
    'candidate_revision': f['candidate_revision'], 'candidate_files': len(f['files']),
    'working_changed_files': working_changes, 'frozen_script_changed_files': script_changes,
    'baseline_first_claims': a['responses']['initial']['claims'], 'baseline_followup_claims': a['responses']['rereview']['claims'],
    'shared_link_definitions_per_scenario_response': [x['shared_link_definitions_returned'] for x in w['rows']],
    'link_reference_counts': [x['link_references_returned'] for x in w['rows']],
    'resources': a['resources'], 'quality_certified': False, 'main_changed': False, 'oracle_calls': 0,
    'limits': 'Same synthetic in-sample scenario, one fresh baseline plus predeclared one followup, three independent branches. Historical1/3 versus new0/3 is not causal evidence of regression; source-only HTTP200 is not accepted answer.'}
put(RUN / 'result.json', result)
m = read(ADR / '실험/manifest.json')
m['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'))
m['results'].update(status='complete', by_arm={'baseline': {'historical_only': True}, 'verified': result}, judge_disagreements=0,
    usage={'physical_model_calls': a['physical_calls'], 'reported_cost_usd': a['reported_cost_usd'], 'input_tokens': a['reported_input_tokens'], 'output_tokens': a['reported_output_tokens']},
    latency={'elapsed_seconds': r['seconds'], 'model_seconds': a['model_seconds']},
    error_taxonomy=[{'type': 'FAILED_CHECK', 'checks': [k for k, v in checks.items() if not v]}])
put(ADR / '실험/manifest.json', m)

heads = ['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values = [
    '미통과. 실제 Qwen11회에서 가정3개 모두 주장0/원문 전용 응답이다. MAIN132 유지. [결과](artifacts/run-001/result.json).',
    '완료 ADR1283의 입력 통합·서버 확정값 복원·공유 검토 연결·형식화 금액 적용을 작업 코드와 같은527파일 후보로 검증했다. 역사1281의1/3 통과와 실패 원본을 보존한다.',
    '[호출 전 동결 기준](artifacts/design/criteria.json). 가정의 실제 금액 적용·승인 미확인·기준 사건 보존·원문/전송/권한·중복 요청 모델0·원문 무손실을 분리 확인한다.',
    '기준1380000원 → 기준 검토 미완료 시 사전 선언 후속 검토1회 → 숫자 비교 모델0 → 독립 저액735000/고액1725000/한도2450000 의미 검토. 기존 단계 보완 한도1회, 공급자UNKNOWN 이후 추가호출 금지. 기준답변·응답 주입0.',
    '동결527파일·native FastAPI/SQLite·합성3조문·기존 승인 온톨로지. Qwen3.8-27b/Parasail FP8, reasoning none, 출력 토큰 상한 없음. 실제11개 모두stop/UNKNOWN0. [동결](artifacts/design/freeze.json) 및 [실제 요청](artifacts/live/review-whatif/raw).',
    '기준 최초4호출은 주장0, 사전 선언 후속1호출에서 주장4. 가정 저액/고액/규칙은 각2호출 후 전부 주장0/INCOMPLETE. 숫자 비교3개와 재조회는 모델0, 기준 사건 보존. HTTP200을 의미 통과로 세지 않았다.',
    '\n\n'.join(x['label'] + ': ' + x['observation'] for x in s['rows']) + '\n\n[정확한 제안과 오류](artifacts/live/review-whatif/semantic-review.json) · [진단](artifacts/diagnosis.json).',
    f'{a["physical_calls"]}물리호출=예산차감{a["reserved"]}. {r["seconds"]:.3f}초/보고${a["reported_cost_usd"]:.8f}; 사용량 미보고0. 확보 원문{a["source_checks"]}/최종 입력 span 대조{a["delivered_checks"]}; 원문/ACL/wire 불일치0. RSS 표본최대{a["resources"]["peak_RSS_GiB"]:.3f}GiB/가용최소{a["resources"]["min_available_GiB"]:.3f}GiB/host swap증가최대{a["resources"]["max_swap_growth_MiB"]:.3f}MiB. 순수DB/속도 개선율 아님.',
    '정확히 같은 독립 질문 값8→1, 그러나 질문+사실 문장에 포함된 질문1회가 남아 총 등장9→2. 원문6→1, 실제 가정 입력6개 전부 복원hash 검증. 조건결과 재작성0, 응답당 공유 연결3개를10~15곳에서 참조. 이번 괄호 반복 탐지에서는 과거600자 채우기 반복이 없었다. 검토 성공은 개선되지 않았다. 현재/과거 참조를 붙여도 본문이 이전 한도를 현재로 쓰는 문제는 남는다.',
    '동일 합성 사례 한 번이며 법률품질·Oracle/NFS/GENOS·동시부하 인증이 아니다. 1281과 코드뿐 아니라 자연 생성 경로·주장 수·기준 사건 보완 여부도 다르므로1/3→0/3을 인과적 악화율로 해석하지 않는다. 숫자·참조 검증은 문장 의미 검증을 대신하지 않는다.',
    '이번 제품/MAIN/Gold/DDL/메일/Git 변경0. 작업527파일=후보527파일 유지, 선택MAIN132는 별도. 실패 제안은 채택하지 않고 원문 전용으로 반환했다. 다음 수정은 설명 전체를 가정 적용으로 취급하는 조건, 상태별 공유 연결 제약, 현재/과거 의미와 오류 안내의 결합을 다뤄야 한다. 기존 실패 셀 추가 재실행0.',
    'prepare.py → freeze.py → live.py review-whatif --preflight → live.py review-whatif 단1회 → audit.py/wire_audit.py/contract_wire_check.py/diagnose.py → finalize.py → 표준 hash/status/validate/graph. live 재실행 금지; 과거 요청과 결과는 raw/canonical 무손실gzip으로 보존.'
]
p = ADR / 'README.md'; front = p.read_text().split('---', 2)[1]
front = re.sub(r'(?m)^status:.*$', 'status: Rejected', front)
p.write_text('---' + front + '---\n\n# ADR1284 입력 통합·공유 검토 실제 Qwen 검증\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h, v) in enumerate(zip(heads, values), 1)) + '\n')
q = ADR / '실험/질문-001-review-whatif.md'
question = read(DES / 'cases.json')[0]['request']['json']['question']
sections = [
 ('실행 메타', 'run-001/verified/review-whatif. 동결 후보·정책·입력은 ../artifacts/design/freeze.json. 실제 시각·요청은 ../artifacts/live/review-whatif/raw.'),
 ('사용자 질문 원문', question),
 ('기준답변 — 채점 전용, 제품 입력 비공개', '별도 기준답변·평가모델0. 기술 기대조건은 ../artifacts/design/criteria.json. 제품 입력에는 원문·승인 온톨로지만 포함.'),
 ('제품 입력을 구성한 원값', 'design/source.json/ontology-input.json/cases.json 및 raw/call-*/request.json.gz에 실제 전체 원문·system/user/schema.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 비교 없음. stage_ledger not_applicable; 확보·전달 좌표와 ACL 대조는 audit.json.gz.'),
 ('제품 모델 호출 — run·arm별 실제 원문', '11호출/전부Parasail stop. raw의 request/response/finished 및 canonical 참조. 임의 응답 주입·가공·재전송0.'),
 ('중간 LLM 호출 — router/compiler/verifier/repair', 'calls.json/generations.json/turns.json. 기준 최초4+후속1, 가정 각2회. 새 평가모델0.'),
 ('채점 호출과 반복 판정', '외부 채점0. 기록된 실제 제안·최종 응답의 의미 검토 및 새 프로세스 저장 검증. 중복 요청 재조회 추가모델0.'),
 ('사례 최종 판정', '../artifacts/run-001/result.json: NOT_PASSED/0of3. semantic-review.json은 관측한 실제 제안과 누락 연결·이전값 재사용을 보존.')]
q.write_text('# 실제 Qwen 가정 분기 검증\n\n' + '\n\n'.join(f'## {i}. {h}\n\n{v}' for i, (h, v) in enumerate(sections, 1)) + '\n')
(ADR / '실험/README.md').write_text('# 실제 검증 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
report_dir = ROOT / '09_ARTIFACTS/AUDITS/20261102-shared-scenario-contract-live'
report_dir.mkdir(exist_ok=False)
report = '\n\n'.join(h + '\n' + v for h, v in zip(heads, values))
(report_dir / '실제실험과_남은문제.txt').write_text(report + '\n')
put(ART / 'postprocess-pins.json', {str(p.relative_to(ROOT)): sha(p) for p in Path(__file__).parent.glob('*.py')})
print(json.dumps(result, ensure_ascii=False))
