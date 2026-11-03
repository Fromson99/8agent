"""Collect exact recorded evidence for manual review; no model or product writes."""
from common import *

f = read(DES / 'freeze.json')
C = ROOT / f['code_root']
sys.path.insert(0, str(C / '02_BACKEND'))
from semantic_runtime.legal_agent import scenario_application

P = ART / 'live/review-whatif'
proposals = []
for path in sorted((P / 'canonical').glob('[0-9][0-9][0-9].json.gz')):
    number = path.name.split('.')[0]
    view = read(path)['view']
    if not view.get('source_stage', '').startswith('memory-assess'):
        continue
    output = P / 'canonical' / (number + '-output.json.gz')
    summary = read(P / 'canonical' / (number + '-summary.json'))
    item = {'number': int(number), 'turn': summary['turn'], 'stage': summary['stage'],
            'input': {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)},
            'generation_status': summary['status'],
            'repair_feedback': (view.get('repair_feedback') or {}).get('validation')}
    if output.exists():
        value = read(output)
        item.update(output={'path': str(output.relative_to(ROOT)), 'sha256': sha(output)},
                    claims=value.get('claims', []), gaps=value.get('gaps', []),
                    scenario_review=value.get('scenario_review'))
        if view.get('hypothetical_scenario') and isinstance(value.get('scenario_review'), dict):
            item['current_facts'] = view.get('current_facts')
            item['scenario_issues_from_frozen_validator'] = scenario_application.errors(
                value, view['hypothetical_scenario'], view['current_facts'])
    proposals.append(item)

responses = []
for turn in read(P / 'turns.json'):
    response = read(P / (turn['label'] + '-response.json.gz'))
    body = response.get('body') or {}
    answer = body.get('answer') or {}
    meta = body.get('assembly', {}).get('term_agent', {})
    explanation = meta.get('review_explanation') or {}
    responses.append({'label': turn['label'], 'http_status': response['status'],
        'claims': len(answer.get('claims', [])) if isinstance(answer, dict) else 0,
        'accepted_outcome': meta.get('accepted_outcome'),
        'failed_checks': explanation.get('failed_checks', []),
        'scenario_review': explanation.get('scenario_review'),
        'scenario_application_display': explanation.get('scenario_application_display'),
        'scenario_calculation': explanation.get('scenario_calculation'),
        'source_response': str((P / (turn['label'] + '-response.json.gz')).relative_to(ROOT))})
put(ART / 'record-inspection.json', {'model_calls': 0, 'proposals': proposals, 'responses': responses,
    'limits': 'Recorded content and component diagnostics only; manual source/meaning review is separate. No rejected proposal adopted or repaired.'})
print(json.dumps({'responses': responses, 'repair_calls': [p['number'] for p in proposals if p['repair_feedback']]}, ensure_ascii=False))
