"""Scripted guided-mode model for the Oracle scale guard.

Vendored from 05_TESTS/CONTRACTS/test_guided_continue_bounds.py at git HEAD (2026-11-06 10:54 commit)
so concurrent edits of that shared test file cannot change or break the guard.
"""
from copy import deepcopy
import json

from test_bounded_source_main import settings
from test_legal_agent_double_harness import wire
from test_memory_runtime_v2 import command


NAMED = '모의승인규정 제1조제1항의 승인 기준을 알려줘'
BROAD = '긴급 승인 예외 기준을 알려줘'
CONTINUE = '어 계속 찾아줘'
OFFER = {'kind': 'SOURCE', 'uncertainty': '모의승인규정 제1조제2항의 본문은 아직 읽지 않았습니다.',
         'question': '제1조제2항을 이어서 읽어볼까요?'}


def find(node, name):
    if isinstance(node, dict):
        if name in node.get('properties', {}): return node['properties'][name]
        for child in node.values():
            found = find(child, name)
            if found is not None: return found
    if isinstance(node, list):
        for child in node:
            found = find(child, name)
            if found is not None: return found


def fit(value, schema):
    """The scripted full command answered in the shape of the requested resolver step.

    The two-step resolver (2026-11-07) asks method/target/reason first and the chosen
    method's remaining fields second; a full closed schema (one step) returns the command
    unchanged. Same rule as test_memory_runtime_v2.fit, vendored so the guard stays fixed.
    """
    if not isinstance(value, dict) or not isinstance(schema, dict) or 'anyOf' in schema or 'properties' not in schema:
        return value
    defs = schema.get('$defs', {})
    def rule(r):
        while isinstance(r, dict) and '$ref' in r: r = defs[r['$ref'].split('/')[-1]]
        return r if isinstance(r, dict) else {}
    def default(r):
        r = rule(r)
        if 'const' in r: return r['const']
        if r.get('enum'): return r['enum'][0]
        if r.get('type') == 'array': return []
        if r.get('type') == 'object': return {k: default(v) for k, v in r.get('properties', {}).items()}
        if r.get('anyOf'): return default(r['anyOf'][0])
        return None
    return {k: (deepcopy(value[k]) if k in value else default(r)) for k, r in schema['properties'].items()}


def related_all(schema):
    """Scripted related-question step (2026-11-07): every earlier question judged related, i.e. the
    earlier behavior. One yes/no judgment per question q1..qN."""
    return {'reason': '모의 선택', **{k: {'related': 'YES', 'why': '모의: 이전 질문 전체'} for k in schema['properties'] if k != 'reason'}}


def fill(schema):
    if 'const' in schema: return schema['const']
    if 'enum' in schema: return schema['enum'][0]
    if 'anyOf' in schema: return fill(schema['anyOf'][0])
    kind = schema.get('type')
    if isinstance(kind, list): kind = kind[0]
    if kind == 'object': return {k: fill(schema['properties'][k]) for k in schema.get('required', [])}
    if kind == 'array':
        n = max(1, schema.get('minItems', 0)) if schema.get('minItems', 0) or 'enum' in schema.get('items', {}) else 0
        return [fill(schema['items']) for _ in range(n)]
    if kind == 'boolean': return False
    if kind == 'null': return None
    if kind == 'integer': return 1
    return '모의 이유: 다음 본문 확인'


class Transport:
    binding = settings()['model_binding']

    def __init__(self, question, scope, plan):
        self.question = question; self.scope = scope; self.plan = plan
        self.turn = 1; self.target = None; self.task = None; self.log = []; self.reads = {}

    def validate_model(self): return {'verified': True, 'synthetic': True}

    def send_once(self, *, body, ticket):
        from api_fixture_integrated import decode
        view = decode(json.loads(body['messages'][1]['content'])['view'])
        phase = view.get('source_stage') or view['phase']
        schema = body['response_format']['json_schema']['schema']
        self.log.append({'turn': self.turn, 'phase': phase, 'view': deepcopy(view), 'schema': schema})
        if phase == 'request-entry':
            decision = ({'mode': 'NAMED_SCOPE', 'targets': [{'document': '모의승인규정', 'structure': '제1조제1항',
                         'selection': None}], 'user_quote': self.question, 'reason': '명시된 항'} if self.scope == 'named'
                        else {'mode': 'AUTHORIZED_SCOPE', 'targets': [], 'user_quote': '', 'reason': '범위 미지정'})
            return wire({'routing': {'mode': 'CASE', 'answer': '', 'reason': '모의 조사'},
                'command': {'method_id': 'CASE_START', 'source_category': 'ALL', 'facts': [], 'queries': ['승인'],
                            'format': 'prose', 'reason': '모의'},
                'intent': {'purpose': self.question, 'concepts': ['승인'], 'issues': [{'id': 'Q1', 'question': self.question,
                    'subject': '승인', 'kind': 'OTHER', 'request_quote': self.question}]}, 'context_quotes': [],
                # asks_definition only exists in request-entry schemas from the definition-priority change on;
                # older code rejects the extra field, so it is sent only when the schema asks for it.
                'search': {**({'asks_definition': True} if 'asks_definition' in json.dumps(schema) else {}),
                           'mode': 'FULLTEXT', 'scope_decision': decision, 'reason': '범위 조회'}})
        if phase == 'memory-reason-decision-review':
            raise AssertionError('guided conversation must not spend a separate reason review')
        if phase == 'source-request-route': return wire({'mode': 'CASE', 'answer': '', 'reason': '기존 조사 후속'})
        if phase in ('memory-resolve-related', 'memory-resolve-related-repair'):
            return wire(related_all(schema))
        if phase in ('memory-resolve', 'memory-resolve-fields'):
            method, stage = self.plan['resolve']
            return wire(fit(command(method, target=self.target, stage=stage), schema))
        if phase == 'memory-command-check':
            return wire({'valid': True, 'reason': '모의 대조', 'request_relation': self.plan['relation'],
                         'requested_task': self.task})
        if phase == 'source-law-initial-rerank':  # hybrid_rerank (2026-11-09): reverse the last two candidates to the top
            ids = schema['properties']['candidate_ids']['items']['enum']
            return wire({'reason': '모의 재정렬', 'candidate_ids': ids[-2:][::-1]})
        if phase == 'memory-present-focus':  # ANSWER_PRESENT part choice (2026-11-08): the whole answer
            return wire({'reason': '모의: 전체 다시 보기', 'scope': 'WHOLE', 'claim_ids': []})
        if 'open_questions' in schema.get('properties', {}):
            issue = find(schema, 'issue_refs')['items']['enum'][:1]
            evidence = find(schema, 'evidence_refs')['items'].get('enum', [])[:1]
            points = [{'issue_refs': issue, 'evidence_refs': evidence, 'text': '제1조제1항은 각 호의 승인 기준을 적용합니다.'}] if evidence else []
            return wire({'open_questions': [{'issue_refs': issue, **OFFER}], 'answer_points': points})
        if phase == 'investigate':
            options = {}
            for branch in schema.get('anyOf', []):
                options.setdefault(branch['properties']['choice'].get('const'), []).append(branch)
            if self.plan.get('ask') and self.turn == 1:
                return wire({'choice': 'ASK_USER', 'questions': [{'issue_refs': find(schema, 'issue_refs')['items']['enum'][:1], **OFFER}]})
            used = self.reads.get(self.turn, 0)
            if 'READ' in options and view.get('read_candidates') and used < self.plan.get('reads', 1):
                self.reads[self.turn] = used + 1
                return wire(fill(options['READ'][0]))
            if view.get('sources') and not self.plan.get('followed', {}).get(self.turn):
                self.plan.setdefault('menus_after_read', []).append(sorted(k for k in options if k))
            if 'ANSWER' in options: return wire(fill(options['ANSWER'][0]))
            if 'FOLLOW' in options and not self.plan.setdefault('followed', {}).get(self.turn):
                self.plan['followed'][self.turn] = True
                return wire(fill(options['FOLLOW'][0]))
            return wire({'choice': 'ASK_USER', 'questions': [{'issue_refs': find(schema, 'issue_refs')['items']['enum'][:1], **OFFER}]})
        raise AssertionError(phase)


