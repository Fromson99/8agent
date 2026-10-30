"""Bounded, typed conditions. UNKNOWN never authorizes skipping source research."""
from decimal import Decimal, InvalidOperation, Inexact, localcontext
from datetime import date
from ..contracts import require, digest

OPS = {'all', 'any', 'not', 'eq', 'in', 'lt', 'lte', 'gt', 'gte',
       'add', 'subtract', 'multiply', 'divide', 'before', 'after'}


def validate_expression(node, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    require(depth <= 8 and counter[0] <= 64 and isinstance(node, dict),
            'KNOWLEDGE_EXPRESSION', '조건은 깊이 8·항목 64 이하로 작성해 주세요.')
    if set(node) == {'field'}:
        from ..contracts import validate, ID
        validate(node['field'], ID)
        return
    if set(node) == {'literal'}:
        literal = node['literal']
        require(isinstance(literal, dict) and set(literal) == {'type', 'value', 'unit'}
                and literal['type'] in ('boolean', 'decimal', 'money', 'ratio', 'duration', 'text', 'date', 'set')
                and isinstance(literal['unit'], str), 'KNOWLEDGE_EXPRESSION', '조건 값에는 타입·단위가 필요합니다.')
        _literal(literal)  # Strict validation, no code evaluation or coercion.
        return
    require(set(node) == {'op', 'args'} and node['op'] in OPS and isinstance(node['args'], list),
            'KNOWLEDGE_EXPRESSION', '지원하는 조건 연산을 사용해 주세요.')
    size = len(node['args'])
    require((1 <= size <= 16 if node['op'] in ('all', 'any') else size == (1 if node['op'] == 'not' else 2)),
            'KNOWLEDGE_EXPRESSION', '조건 연산의 입력 개수가 다릅니다.')
    for child in node['args']: validate_expression(child, depth + 1, counter)


def _literal(literal):
    kind, value = literal['type'], literal['value']
    if kind in ('decimal', 'money', 'ratio', 'duration'):
        require(isinstance(value, str) and len(value) <= 80,
                'KNOWLEDGE_NUMBER', '수치는 십진 문자열로 입력해 주세요.')
        try:
            number = Decimal(value)
            valid = number.is_finite() and abs(number.adjusted()) <= 100
        except InvalidOperation:
            valid = False
        require(valid, 'KNOWLEDGE_NUMBER', '유한한 십진수 범위를 확인해 주세요.')
    elif kind == 'boolean':
        require(type(value) is bool, 'KNOWLEDGE_TYPE', '참·거짓 값이 필요합니다.')
    elif kind == 'date':
        try:
            require(date.fromisoformat(value).isoformat() == value, 'KNOWLEDGE_DATE', '날짜는 YYYY-MM-DD 형식으로 입력해 주세요.')
        except (TypeError, ValueError): require(False, 'KNOWLEDGE_DATE', '날짜 형식을 확인해 주세요.')
    elif kind == 'set':
        require(isinstance(value, list) and len(value) <= 32 and all(isinstance(x, str) for x in value),
                'KNOWLEDGE_TYPE', '문자열 집합이 필요합니다.')
    else:
        require(isinstance(value, str) and len(value) <= 2000, 'KNOWLEDGE_TYPE', '문자열이 필요합니다.')
    return dict(literal)


def evaluate(expression, facts, *, binding):
    validate_expression(expression)
    missing, conflicts = set(), set()
    def calc(node):
        if 'literal' in node: return node['literal']
        if 'field' in node:
            key = node['field']; fact = facts.get(key)
            if not fact or fact.get('status') not in ('ASSERTED', 'VERIFIED') or not fact.get('origin_ref'):
                missing.add(key)
                if fact and fact.get('status') == 'CONFLICT': conflicts.add(key)
                return None
            return _literal(fact['value'])
        op = node['op']; args = [calc(a) for a in node['args']]
        booleans = [a['value'] if a and a['type'] == 'boolean' else None for a in args]
        def boolean(value): return {'type': 'boolean', 'value': value, 'unit': ''} if value is not None else None
        if op == 'all': return boolean(False if False in booleans else True if all(v is True for v in booleans) else None)
        if op == 'any': return boolean(True if True in booleans else False if all(v is False for v in booleans) else None)
        if op == 'not': return boolean(not booleans[0]) if booleans[0] is not None else None
        if any(a is None for a in args): return None
        a, b = args
        if op == 'in':
            return boolean(a['value'] in b['value']) if a['type'] == 'text' and b['type'] == 'set' and a['unit'] == b['unit'] else None
        if a['type'] != b['type'] or a['unit'] != b['unit']:
            missing.add('TYPE_OR_UNIT_MISMATCH'); return None
        x, y = a['value'], b['value']
        numeric = a['type'] in ('decimal', 'money', 'ratio', 'duration')
        if numeric: x, y = Decimal(x), Decimal(y)
        if op == 'eq': return boolean(x == y)
        if op in ('before', 'after'):
            return boolean(x < y if op == 'before' else x > y) if a['type'] == 'date' else None
        if not numeric:
            missing.add('UNSUPPORTED_TYPED_OPERATION'); return None
        if op in ('lt', 'lte', 'gt', 'gte'):
            return boolean({'lt': x < y, 'lte': x <= y, 'gt': x > y, 'gte': x >= y}[op])
        if op in ('multiply', 'divide') and (a['type'] != 'decimal' or a['unit']):
            missing.add('UNSUPPORTED_DIMENSION'); return None
        if op == 'divide' and y == 0:
            missing.add('DIVISION_BY_ZERO'); return None
        with localcontext() as context:
            context.prec = 50
            result = x+y if op == 'add' else x-y if op == 'subtract' else x*y if op == 'multiply' else x/y
            if context.flags[Inexact]:
                missing.add('ROUNDING_POLICY_REQUIRED'); return None
        return {**a, 'value': str(result)}
    value = calc(expression)
    status = ('CONFLICT' if conflicts else 'UNKNOWN' if value is None else
              'TRUE' if value['type'] == 'boolean' and value['value'] else
              'FALSE' if value['type'] == 'boolean' else 'VALUE')
    return {'status': status, 'value': value, 'missing': sorted(missing), 'conflicts': sorted(conflicts),
            'expression_hash': digest(expression), 'inputs_hash': digest(facts), 'binding': binding}


def scope_status(scope, context):
    unknown = []
    for key, dimension in scope.items():
        if dimension['mode'] == 'ANY_REVIEWED': continue
        if dimension['mode'] == 'UNSPECIFIED' or key not in context:
            unknown.append(key)
        elif context[key] not in dimension['values']:
            return 'NOT_APPLICABLE', [key]
    return ('UNRESOLVED', unknown) if unknown else ('MATCHED', [])
