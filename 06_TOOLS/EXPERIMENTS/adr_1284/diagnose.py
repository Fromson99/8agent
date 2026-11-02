"""Recorded-proposal inspection only. Does not modify a proposal or dispatch."""
from common import *
from collections import Counter
f = read(DES / 'freeze.json')
C = ROOT / f['code_root']
sys.path.insert(0, str(C / '02_BACKEND'))
from semantic_runtime.legal_agent.scenario_application import errors
P = ART / 'live/review-whatif'
wire = read(ART / 'contract-wire-check.json')

def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)

proposals = []
for n in range(6, 12):
    src = P / 'canonical' / f'{n:03}.json.gz'
    out = P / 'canonical' / f'{n:03}-output.json.gz'
    view = read(src)['view']; value = read(out)
    problems = errors(value, view['hypothetical_scenario'], view['current_facts'])
    proposals.append({'number': n, 'turn': read(P / 'raw' / f'call-{n:03}' / 'started.json')['turn'],
        'input': {'path': str(src.relative_to(ROOT)), 'sha256': sha(src)},
        'output': {'path': str(out.relative_to(ROOT)), 'sha256': sha(out)},
        'scenario_issues_from_frozen_validator': problems,
        'repair_feedback_received': (view.get('repair_feedback') or {}).get('validation'),
        'scenario_review': value.get('scenario_review'),
        'explanations': [{'id': r['claim_id'], 'text': r['explanation']} for r in value.get('claims', []) if r.get('explanation')]})

observations = {
 'low': '최초·보완 모두 C3 긴급 예외 비적용 설명의 가정 연결 누락으로 거절. C2는735000원<=1000000원과 승인 미확인을 기술했으나 보완에서는 개시 미확정 대신 시작할 수 없다고 단정했다. 최종 주장은0이다.',
 'high': '최초는 UNRESOLVED 요구 행의 공유 연결이 C1을 포함하여 복원 후 claim_refs maxItems0 위반. 보완은 C3 승인 설명·C5 긴급 예외 비적용 설명의 가정 연결 누락.1725000원 금액 불충족·승인 미확인은 기술했으나 최종 주장은0이다.',
 'rule': '최초·보완 모두 C4 긴급 예외·C5 승인 설명의 가정 연결 누락. C2는 CURRENT2450000와 HISTORICAL1000000 참조를 함께 달고도 본문에서는 현재1380000원을 이전1000000원 한도로 판정했다. 타입 참조만으로 본문의 현재/과거 역할을 보장하지 못했다. 채택은 별도 연결 누락 검증에서 차단되어 최종 주장은0이다.'}
rows = []
for label in ('low', 'high', 'rule'):
    response = read(P / ('semantic-' + label + '-response.json.gz'))
    answer = response['body'].get('answer', {})
    rows.append({'label': label, 'http_status': response['status'], 'claims': len(answer.get('claims', [])),
        'semantic_and_publication_pass': False, 'observation': observations[label],
        'proposal_numbers': [r['number'] for r in proposals if r['turn'] == 'semantic-' + label]})
semantic = {'method': 'Manual inspection of exact recorded outputs and source clauses plus frozen validator diagnosis; no external judge or new model',
    'passed': 0, 'total': 3, 'all_passed': False, 'rows': rows, 'proposals': proposals,
    'limits': 'Source-only HTTP200 is safe abstention, not semantic success. Recomputed issues are not accepted proposals or a rerun.'}
put(P / 'semantic-review.json', semantic)

history = ROOT / '04_EXPERIMENTS/ADR/ADR-1281-scenario-review-schema-live/artifacts'
question = read(DES / 'cases.json')[0]['request']['json']['question']
source = read(DES / 'source.json')['texts'][0]
count_rows = []
for experiment, folders in (('1281', sorted((history / 'live/review-whatif/raw').glob('call-*'))),
                             ('1284', sorted((P / 'raw').glob('call-*')))):
    for folder in folders:
        started = read(folder / 'started.json')
        if not str(started['turn']).startswith('semantic-'):
            continue
        req = read(folder / 'request.json.gz')
        content = json.loads(next(m['content'] for m in req['messages'] if m['role'] == 'user'))
        all_strings = list(strings(content))
        count_rows.append({'experiment': experiment, 'number': started['number'], 'turn': started['turn'],
            'whole_question_values': sum(s == question for s in all_strings),
            'question_occurrences_including_embedded': sum(s.count(question) for s in all_strings),
            'source_clause_occurrences': sum(s.count(source) for s in all_strings)})
output_repetitions = read(ART / 'wire-schema-audit.json')['rows']
put(ART / 'diagnosis.json', {'model_calls': 0, 'counts_same_method': count_rows,
    'comparison_interpretation': 'Whole question8->1, but embedded question remains once: total9->2. Source6->1. Earlier8 count excluded embedded question; no causal A/B.',
    'repeated_parenthetical_output_detected': [r['number'] for r in output_repetitions if r['output_repetitions']],
    'findings': [
        'Explanation nonempty is treated as scenario application, so ordinary approval/exception explanations also require application_links.',
        'Shared schema removes paired reference constraints from each status branch; restored canonical schema still rejects invalid nonempty UNRESOLVED links.',
        'Historical comparison reference permits old numeric literal; it does not establish whether prose uses that literal as historical comparison or current threshold.',
        'Generic scenario error still says not to use old case values even when precise issue is missing claim links.',
        'Question plus facts embedded in baseline_history remains separate from factored full question; no content slicing was performed.'
    ], 'evidence_code': {n: {'sha256': sha(C / n), 'path': str((C / n).relative_to(ROOT))} for n in (
        '02_BACKEND/semantic_runtime/legal_agent/scenario_application.py',
        '02_BACKEND/semantic_runtime/legal_agent/assessment_links.py',
        '02_BACKEND/semantic_runtime/legal_agent/assessment_input.py')},
    'wire_checks': wire['checks'], 'quality_certified': False})
print(json.dumps({'semantic_passed': 0, 'semantic_total': 3, 'source_and_question_counts': count_rows}, ensure_ascii=False))
