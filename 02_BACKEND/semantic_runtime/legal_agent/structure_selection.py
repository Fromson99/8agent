"""Execute model-proposed structural sets, never interpret natural language.

The model supplies parent paths, unions, intervals and exclusions. Stored nodes
determine membership and order. No question regex, invented intermediate node,
body scan, model call or persistent corpus cache belongs here.
"""
from copy import deepcopy
from jsonschema import validate, ValidationError

from lawrag.core.legal_coordinate import LegalCoordinate, MOK_LETTERS
from ..contracts import digest
from .errors import ContractError

CONTRACT = 'model-structure-selection-v1'
MAX_NODES = 4096
UNITS = ['편', '장', '절', '관', '조', '항', '호', '목', '세목', '세세목']


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


NUMBER = obj({'n': {'anyOf': [{'type': 'integer', 'minimum': 1},
    {'type': 'string', 'enum': list(MOK_LETTERS)}]},
    'sub': {'type': ['integer', 'null'], 'minimum': 1},
    'dash': {'type': ['integer', 'null'], 'minimum': 1}}, ['n'])
PART = obj({'unit': {'enum': UNITS}, **deepcopy(NUMBER['properties'])}, ['unit', 'n'])
CLAUSE = {'anyOf': [obj({'kind': {'const': 'ALL'}}),
    obj({'kind': {'const': 'SINGLE'}, 'value': NUMBER}),
    obj({'kind': {'const': 'BOUND'},
         'operator': {'enum': ['LT', 'LTE', 'GT', 'GTE'],
                      'description': '번호 비교: LT 미만(<), LTE 이하(<=), GT 초과(>), GTE 이상(>=)'},
         'value': NUMBER}),
    obj({'kind': {'const': 'RANGE'},
         'start': {'anyOf': [NUMBER, {'type': 'null'}]},
         'end': {'anyOf': [NUMBER, {'type': 'null'}]},
         'start_inclusive': {'type': 'boolean'}, 'end_inclusive': {'type': 'boolean'}})]}
SCHEMA = obj({'coordinate_scope': {'type': 'string', 'minLength': 1},
    'groups': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': obj({
        'parent_path': {'type': 'array', 'items': PART, 'maxItems': 12},
        'unit': {'enum': UNITS},
        'include': {'type': 'array', 'items': CLAUSE, 'minItems': 1, 'maxItems': 64},
        'exclude': {'type': 'array', 'items': CLAUSE, 'maxItems': 64,
                    'description': '읽기 대상에서 빼 달라는 요청만. 해당하지 않는다는 가정, 예외 적용 사실, 적용 불가능 판단은 원문 제외가 아니므로 [] 유지.'}})}})
FILTER_SCHEMA = {'anyOf': [obj({'coordinate': {'type': 'string'},
    'title': {'type': 'string'}, 'coordinate_scope': {'type': 'string'}}),
    obj({'selection': SCHEMA})]}

PROMPT = '''
구조 위치 선택은 selection으로 구조화한다. 자연어의 범위·열거·제외·생략 표기는 네가 문맥과 함께 판단한다.
selection={coordinate_scope:"body",groups:[{parent_path:[{unit:"조",n:6,dash:3},{unit:"항",n:2}],unit:"호",include:[...],exclude:[...]}] 형태다.
parent_path는 실제 상위 편/장/절/관/조/항/호 경로이며 문서 루트는 []다. 상위 문맥이 불명확하면 추측하지 말고 목차를 확인하거나 NEED_TARGET으로 확인한다.
include/exclude의 원소는 {kind:"SINGLE",value:{n:1}}, {kind:"RANGE",start:{n:1},end:{n:3},start_inclusive:true,end_inclusive:true}, {kind:"ALL"} 중 하나다.
"1호~3호", "1호에서 3호까지", "1호부터 3호까지"는 해당 상위 조·항 아래 unit="호"의 RANGE다. 중간 번호를 검색어로 일일이 열거하지 않는다.
"1~3호와 7호"는 RANGE와 SINGLE의 합집합이다. "5호 빼고 전부"는 기준 조·항 아래 ALL을 include하고 SINGLE 5를 exclude한다.
번호의 이상·초과·이하·미만은 {kind:"BOUND",operator:"GTE"|"GT"|"LTE"|"LT",value:{n:번호}}로 직접 비교 방향을 선택한다. GTE는 번호>=값(이상), GT는 번호>값(초과), LTE는 번호<=값(이하), LT는 번호<값(미만)이다. 이하/미만은 작은 번호 쪽이며 이상/초과는 큰 번호 쪽이다. 시작·끝이 있는 구간은 RANGE다. 기존 열린 RANGE에서는 작은 쪽 제한이 없으면 start=null, 큰 쪽 제한이 없으면 end=null이다. 이후·이전은 문맥으로 경계 포함 여부까지 판단한다. "홀수 호" 등은 실제 확인한 항목을 SINGLE로 여러 개 선택할 수 있다.
"각 항의 1~3호"처럼 부모가 다르면 parent_path별 groups로 나눈다. 다른 문서는 별도 문서 선택이다.
n은 번호, 목의 n은 "가" 같은 목 문자도 가능하다. 제6-3조는 n=6,dash=3, 제6조의2는 n=6,sub=2다. 문서/노드 ID를 생성하지 않는다.
"전부 제외", "아무 항목도 읽지 말라"는 빈 선택 의도다. ALL 포함과 ALL 제외로 보존하거나 읽지 않고 이유를 설명한다. 빈 선택을 문서 전체 읽기로 바꾸지 않는다.
각 그룹의 포함 집합을 합친 뒤 모든 제외 집합을 뺀다. 선택은 실제 저장 노드로 검증되고 조회·읽기 완료와 법적 적용 여부는 별개다.
원문을 어느 범위까지 읽을지와 읽은 조항을 사건에 적용할지는 별개의 판단 축이다. 먼저 원문 요청(단일/범위/전체)을 selection에 보존하고, 적용·해당 여부의 가정은 facts 또는 조사 쟁점에만 기록한다.
exclude에는 사용자가 원문 열람·답변 범위에서 빼라고 지시한 항목만 넣는다. "해당하지 않는다", "적용되지 않는다고 가정", "예외에 해당한다고 가정"이라는 사건 조건 자체는 읽기 제외 지시가 아니다. 이런 조건 때문에 전체 원문 요청을 좁히지 않는다.
두 요청의 결과를 구분하는 예:
A. "제12조 3항의 모든 호 원문을 읽고, 6호에는 해당하지 않는다고 가정해" → facts=[6호 미해당 가정], 해당 항 아래 unit="호", include=[{kind:"ALL"}], exclude=[]. 6호 원문도 읽고 그 적용 여부를 나중에 판단한다.
B. "제12조 3항 원문에서 6호는 빼고 읽어" → facts에 미해당 사실을 만들지 않음, 해당 항 아래 unit="호", include=[{kind:"ALL"}], exclude=[{kind:"SINGLE",value:{n:6}}].
출력 전에 각 exclude가 실제 원문 제외 요청에 근거하는지 검토한다. 적용 가정만 근거로 넣었다면 exclude에서 빼고 facts/쟁점에만 남긴다. 이 검토도 네 구조화 판단에 포함되며 별도 의미 추정 코드는 없다.
구조화 결과가 형식에 맞아도 사용자 의도와 일치하는지는 네가 판단해야 한다. 요청 범위와 미확인 내용을 설명한다.
'''


class SelectionError(ValueError):
    """Recoverable target ambiguity/miss; never legal absence or permission."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def number(value, unit):
    n = value['n']
    if isinstance(n, str):
        if unit != '목':
            raise SelectionError('INVALID_SELECTION', '문자 번호는 목에만 지정할 수 있습니다.')
        n = MOK_LETTERS.index(n) + 1
    if value.get('dash') is not None and unit != '조':
        raise SelectionError('INVALID_SELECTION', '붙임 조 번호는 조 단위에만 지정할 수 있습니다.')
    return n, value.get('sub'), value.get('dash')


def local_part(coordinate):
    if coordinate is None:
        return None
    if coordinate.chain:
        unit, n = coordinate.chain[-1]
        subs = coordinate.chain_subs or (None,) * len(coordinate.chain)
        return unit, (n, subs[-1], None)
    return coordinate.unit, (coordinate.n, coordinate.sub, coordinate.dash)


class Nodes:
    """Bounded request-local metadata traversal; Oracle uses parent lookups."""

    def __init__(self, matcher, did, branch):
        self.m, self.did, self.branch = matcher, did, branch
        self.seen = {}
        self.gaps = []
        self.context_parent = None

    def node(self, uid):
        uid = str(uid)
        unit = self.m.units[(self.did, uid)]
        coordinate = self.m.stored_coordinates.get((self.did, uid))
        self.seen[uid] = [unit, coordinate.as_dict() if coordinate else None]
        if len(self.seen) > MAX_NODES:
            raise SelectionError('SELECTION_LIMIT', '선택할 구조가 너무 많습니다. 기준 목차 범위를 나누어 주세요.')
        return unit, coordinate

    def children(self, parent):
        values = self.m.units
        if hasattr(values, 'children_for'):
            rows = values.children_for(self.did, parent)
        else:
            rows = values.for_document(self.did) if hasattr(values, 'for_document') else (
                (key, v) for key, v in values.items() if key[0] == self.did)
        out = []
        for (_, uid), unit in rows:
            p = unit.get('parent')
            if (str(p) if p is not None else None) == parent:
                self.node(uid)
                out.append(str(uid))
        return sorted(out, key=self.order)

    def order(self, uid):
        unit, _ = self.node(uid)
        return tuple(unit.get('span', [0, 0])), uid

    def descendants(self, parent, level):
        stack = list(reversed(self.children(parent)))
        visited = set(); out = []
        while stack:
            uid = stack.pop()
            if uid in visited or uid == parent:
                raise ContractError('cyclic or duplicated selection structure')
            visited.add(uid)
            node, coordinate = self.node(uid)
            if node.get('coordinate_scope', 'body') != self.branch:
                continue
            part = local_part(coordinate)
            if part and part[0] == level:
                if node.get('coordinate_binding', {}).get('mode') == 'unresolved':
                    raise SelectionError('UNRESOLVED_COORDINATE_BINDING', '선택 범위에 구조 연결이 미해결인 항목이 있습니다.')
                out.append(uid)
            else:
                stack.extend(reversed(self.children(uid)))
        return sorted(out, key=self.order)

    def parent(self, path):
        # A typed article path goes directly to the published coordinate lookup.
        # No free-text coordinate parsing is performed here.
        if path and path[0]['unit'] == '조' and self.branch == 'body':
            n, sub, dash = number(path[0], '조')
            coordinate = LegalCoordinate('조', n, sub=sub, dash=dash)
            for part in path[1:]:
                pn, ps, pd = number(part, part['unit'])
                if part['unit'] not in ('항', '호', '목', '세목', '세세목'):
                    raise SelectionError('INVALID_SELECTION', '조문 아래 경로는 항·호·목 순서로 지정해야 합니다.')
                coordinate = coordinate.append_part(LegalCoordinate(part['unit'], pn, sub=ps))
            from .structure_query import coordinate_index
            choices = coordinate_index(self.m).get((self.did, coordinate.canonical_surface()), [])
            if len(choices) != 1:
                raise SelectionError('AMBIGUOUS_PARENT' if choices else 'MISSING_PARENT', '선택의 상위 조항을 하나로 확인하지 못했습니다.')
            self.node(choices[0])
            return str(choices[0])
        parent = None
        for part in path:
            wanted = number(part, part['unit'])
            choices = [uid for uid in self.descendants(parent, part['unit'])
                       if local_part(self.node(uid)[1]) == (part['unit'], wanted)]
            if len(choices) != 1:
                raise SelectionError('AMBIGUOUS_PARENT' if choices else 'MISSING_PARENT', '선택의 상위 목차를 하나로 확인하지 못했습니다.')
            parent = choices[0]
        return parent

    def clause(self, clause, candidates, unit):
        if clause['kind'] == 'ALL':
            return set(candidates)
        def endpoint(value):
            wanted = number(value, unit)
            ids = [uid for uid in candidates if local_part(self.node(uid)[1]) == (unit, wanted)]
            if len(ids) != 1:
                raise SelectionError('AMBIGUOUS_ENDPOINT' if ids else 'MISSING_ENDPOINT',
                    '범위의 번호를 하나로 확인하지 못했습니다. 상위 조·항과 저장 목차를 확인해야 합니다.')
            return candidates.index(ids[0])
        if clause['kind'] == 'SINGLE':
            return {candidates[endpoint(clause['value'])]}
        if clause['kind'] == 'BOUND':
            # Execute the model's explicit comparison; never infer its direction.
            pivot = endpoint(clause['value'])
            operation = clause['operator']
            if operation == 'LT': return set(candidates[:pivot])
            if operation == 'LTE': return set(candidates[:pivot + 1])
            if operation == 'GT': return set(candidates[pivot + 1:])
            return set(candidates[pivot:])
        start = endpoint(clause['start']) if clause['start'] is not None else 0
        end = endpoint(clause['end']) if clause['end'] is not None else len(candidates) - 1
        if start > end:
            raise SelectionError('REVERSED_RANGE', '범위의 시작이 끝보다 뒤에 있습니다.')
        if clause['start'] is not None and not clause['start_inclusive']: start += 1
        if clause['end'] is not None and not clause['end_inclusive']: end -= 1
        chosen = set(candidates[start:end + 1]) if start <= end else set()
        left, right = clause['start'], clause['end']
        if left is not None and right is not None:
            lo, ls, ld = number(left, unit); hi, hs, hd = number(right, unit)
            if ls is None and ld is None and hs is None and hd is None and hi >= lo:
                first = lo + (not clause['start_inclusive']); last = hi - (not clause['end_inclusive'])
                if last - first > MAX_NODES:
                    raise SelectionError('SELECTION_LIMIT', '요청 범위의 번호 간격이 너무 큽니다. 범위를 나누어 주세요.')
                have = {local_part(self.node(uid)[1])[1][0] for uid in chosen
                        if local_part(self.node(uid)[1])[1][1:] == (None, None)}
                for n in range(first, last + 1):
                    if n not in have:
                        self.gaps.append({'parent_unit_id': self.context_parent, 'unit': unit, 'n': n,
                                          'reason': 'NO_STORED_MEMBER_IN_INTERVAL'})
        return chosen


def resolve(selection, matcher, did, authorized):
    validate(selection, SCHEMA)
    if did not in authorized:
        raise ContractError('structure selection outside authorization')
    nodes = Nodes(matcher, did, selection['coordinate_scope'])
    included = set(); excluded = set()
    for group in selection['groups']:
        parent = nodes.parent(group['parent_path'])
        nodes.context_parent = parent
        candidates = nodes.descendants(parent, group['unit'])
        if not candidates:
            raise SelectionError('MISSING_SELECTION_LEVEL', '기준 범위에서 요청한 구조 단위를 찾지 못했습니다.')
        for clause in group['include']: included.update(nodes.clause(clause, candidates, group['unit']))
        for clause in group['exclude']: excluded.update(nodes.clause(clause, candidates, group['unit']))
    selected = included - excluded
    # An ancestor must never put an excluded subtree back into the result.
    def ancestors(uid):
        seen = set()
        while uid is not None:
            if uid in seen: raise ContractError('cyclic selection parent')
            seen.add(uid)
            node, _ = nodes.node(uid)
            uid = str(node['parent']) if node.get('parent') is not None else None
        return seen
    for uid in excluded:
        if (ancestors(uid) - {uid}) & selected:
            raise SelectionError('EXCLUSION_REQUIRES_FINER_SCOPE',
                '선택한 상위 원문에 제외 항목이 포함됩니다. 하위 항·호·목 단위로 포함 범위를 지정해야 합니다.')
    selected = {uid for uid in selected if not (ancestors(uid) - {uid}) & (selected | excluded)}
    if not selected:
        raise SelectionError('EMPTY_SELECTION', '제외 조건을 적용한 뒤 선택된 항목이 없습니다.')
    from .structure_query import coordinate_index
    for uid in selected:
        coordinate = nodes.node(uid)[1]
        if coordinate and coordinate.unit == '조' and nodes.branch == 'body':
            if coordinate_index(matcher).get((did, coordinate.canonical_surface())) != [uid]:
                raise SelectionError('AMBIGUOUS_COORDINATE', '선택 범위에 중복되거나 미해결인 좌표가 있습니다.')
    record = {'contract': CONTRACT, 'document_id': did, 'selection': deepcopy(selection),
        'unit_ids': sorted(selected, key=nodes.order), 'excluded_unit_ids': sorted(excluded, key=nodes.order),
        'metadata_hash': digest(nodes.seen), 'content_read': False,
        'membership_gaps': list({digest(gap):gap for gap in nodes.gaps}.values())}
    return {**record, 'hash': digest(record)}


def verify(record, matcher, authorized):
    if record.get('contract') != CONTRACT or record.get('hash') != digest({k:v for k,v in record.items() if k != 'hash'}):
        raise ContractError('structure selection hash mismatch')
    try:
        current = resolve(record['selection'], matcher, record['document_id'], authorized)
    except (SelectionError, ValidationError) as exc:
        raise ContractError('structure selection metadata changed') from exc
    if current != record:
        raise ContractError('structure selection metadata changed')


def route(records, matcher, authorized):
    pairs = []; sources = []
    for record in records:
        verify(record, matcher, authorized)
        did = record['document_id']
        for uid in record['unit_ids']:
            coordinate = matcher.stored_coordinates[(did, uid)]
            pairs.append({'document_id': did, 'unit_id': uid, 'document_name': matcher.documents[did],
                          'coordinate': coordinate.canonical_surface()})
            sources.extend(matcher._unit_sources(did, uid))
    return {'status': 'MATCH', 'pairs': pairs, 'source_ids': list(dict.fromkeys(sources)),
            'reason': 'MODEL_STRUCTURE_SET'}


def catalogue(matcher, scope, did, selection, offset, limit, row_filter=None):
    from . import structure_query as sq
    try:
        record = resolve(selection, matcher, did, scope)
    except SelectionError as exc:
        failure = {'code': exc.code, 'message': str(exc), 'suggested_action': 'BROWSE_STRUCTURE',
                   'automatic_fulltext_fallback': False}
        return {'contract': CONTRACT, 'document_id': did, 'queries': [], 'offset': offset,
            'total': 0, 'items': [], 'next_offset': None, 'lookup_status': 'MISS', 'failure': failure,
            'resolutions': [{'status': 'MISS', 'reason': exc.code, 'failure': failure}],
            'navigation_hint_only': True, 'citation_eligible': False}
    # Build rows only for the requested page; never materialize a remote corpus.
    ids = record['unit_ids']
    if row_filter is not None and any(not row_filter({'document_id': did, 'unit_id': uid}) for uid in ids):
        failure = {'code': 'OUTSIDE_DIRECT_SCOPE', 'message': '선택 범위가 현재 지정한 검색 범위를 벗어납니다.',
                   'suggested_action': 'BROWSE_STRUCTURE', 'automatic_fulltext_fallback': False}
        return {'contract': CONTRACT, 'document_id': did, 'queries': [], 'offset': offset,
            'total': 0, 'items': [], 'next_offset': None, 'lookup_status': 'MISS', 'failure': failure,
            'resolutions': [{'status': 'MISS', 'reason': failure['code'], 'failure': failure}],
            'navigation_hint_only': True, 'citation_eligible': False}
    rows = []
    for uid in ids[offset:offset + limit]:
        node, coordinate = matcher.units[(did, uid)], matcher.stored_coordinates[(did, uid)]
        originals = list(dict.fromkeys(matcher._unit_sources(did, uid)))
        if any(matcher.sources.get(sid, {}).get('document_id') != did for sid in originals):
            raise ContractError('structure selection original outside document')
        readable = bool(coordinate and coordinate.unit == '조' and len(originals) == 1)
        rows.append({'kind': 'structure', 'document_id': did, 'document_name': matcher.documents[did],
            **sq.node_label(matcher, did, uid), 'path': sq.node_path(matcher, did, uid),
            'content_read': False, 'ambiguous': False,
            'source_id': originals[0] if len(originals) == 1 else None,
            'original_count': len(originals), 'source_binding_unique': len(originals) == 1,
            'readable': readable})
    diagnostic = ({'code': 'INCOMPLETE_STRUCTURE_SET',
        'message': '범위 안의 일부 번호를 저장 구조에서 확인하지 못했습니다. 확보한 항목과 미확인 범위를 구분합니다.',
        'suggested_action': 'BROWSE_STRUCTURE', 'automatic_fulltext_fallback': False}
        if record['membership_gaps'] else None)
    return {'contract': CONTRACT, 'document_id': did, 'queries': [], 'offset': offset,
        'total': len(ids), 'items': rows, 'next_offset': offset + limit if offset + limit < len(ids) else None,
        'lookup_status': 'NEEDS_SELECTION' if diagnostic else 'MATCH', 'failure': diagnostic, 'selection_resolution': record,
        'resolutions': [{'status': 'MATCH' if not diagnostic else 'MISS', 'reason': 'MODEL_STRUCTURE_SET',
                         **({'failure': diagnostic} if diagnostic else {})}],
        'navigation_hint_only': True, 'citation_eligible': False}


def progress(inv):
    """Acquisition/delivery of the chosen set, separate from legal sufficiency."""
    from . import evidence_inventory as inventory
    records = inv.p.get('structure_selections', {})
    if not records: return []
    receipts = inventory.inventory(inv.s, inv.p)
    return progress_from_spans(inv.s, records, [r['receipt'] for r in receipts])


def progress_from_spans(session, records, receipts):
    """Cover each requested subtree using actual block spans, not ancestor labels."""
    from . import evidence_inventory as inventory, unit_reading
    out = []
    for ident, record in records.items():
        did = record['document_id']; acquired = []; delivered = []
        matching = [r for r in receipts if r['document_id'] == did]
        have = [p for r in matching for p in r.get('acquired_spans', [])]
        sent = [p for r in matching for p in r.get('delivered_spans', [])]
        for uid in record['unit_ids']:
            want = inventory.expected(session, did, unit_reading.blocks(session, did, uid, 'subtree'))
            if want and inventory.covers(want, have): acquired.append(uid)
            if want and inventory.covers(want, sent): delivered.append(uid)
        out.append({'selection_id': ident, 'document_id': did,
            'selection': deepcopy(record['selection']), 'requested_unit_ids': record['unit_ids'],
            'excluded_unit_ids': record['excluded_unit_ids'], 'acquired_unit_ids': acquired,
            'delivered_unit_ids': delivered,
            'remaining_unit_ids': [uid for uid in record['unit_ids'] if uid not in delivered],
            'membership_gaps': deepcopy(record.get('membership_gaps', [])),
            'acquired_complete': len(acquired) == len(record['unit_ids']) and not record.get('membership_gaps'),
            'delivered_complete': len(delivered) == len(record['unit_ids']) and not record.get('membership_gaps'),
            'semantic_quality_certified': False})
    return out


def limitations(inv, rows):
    return selection_limitations(inv.s.matcher, rows)


def selection_limitations(matcher, rows):
    from .structure_query import node_label
    values = ['요청한 구조 선택 중 아직 원문 전체를 전달하지 못한 항목: ' +
        matcher.documents[row['document_id']] + ' ' + ', '.join(
            node_label(matcher, row['document_id'], uid)['coordinate'] or uid
            for uid in row['remaining_unit_ids']) for row in rows if row['remaining_unit_ids']]
    values.extend('요청 범위의 저장 구조에서 확인되지 않은 번호: ' +
        matcher.documents[row['document_id']] + ' ' + ', '.join(
            str(gap['n']) + gap['unit'] for gap in row['membership_gaps']) +
        '. 원문 부재를 확인한 결과는 아닙니다.' for row in rows if row['membership_gaps'])
    return values
