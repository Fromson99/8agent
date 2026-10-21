"""Reversible generation projection; canonical schemas alone authorize execution.

Only schema-implied literals are supplied by the host. Action alternatives preserve their
required fields and identity pools on the generation wire and after reconstruction. No reason, evidence choice or legal opinion is inferred.
"""
from copy import deepcopy
import json
from jsonschema import Draft202012Validator, ValidationError
from ..contracts import digest
from .errors import ProposalError
from .output_contract import OutputContractError, issue, schema_issue

VERSION = 'minimal-model-output-v2'
INSTRUCTIONS = ('응답 스키마에 요구된 값만 JSON으로 반환한다. 스키마에서 생략된 고정값과 '
    '빈 항목은 다시 쓰지 않는다. 선택적 필드는 이번 판단에 필요한 것만 출력한다. '
    '중간 판단의 이유는 해당 필드에 핵심 근거를 짧게 한 번 적고 같은 설명을 반복하지 않는다. '
    '최종 답변에 요청된 내용, 의견의 근거·미확인 사항, 정확한 인용은 생략하거나 바꾸지 않는다.')
_MISSING = object()


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _schemas(node):
    if not isinstance(node, dict):
        return
    yield node
    for key in ('properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'):
        for child in node.get(key, {}).values():
            yield from _schemas(child)
    for key in ('items', 'additionalProperties', 'not', 'if', 'then', 'else', 'contains'):
        child = node.get(key)
        for item in child if isinstance(child, list) else [child]:
            yield from _schemas(item)
    for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
        for child in node.get(key, []):
            yield from _schemas(child)


def _fixed(schema):
    if not isinstance(schema, dict):
        return _MISSING
    value = _MISSING
    if 'const' in schema:
        value = schema['const']
    elif len(schema.get('enum', [])) == 1:
        value = schema['enum'][0]
    elif schema.get('type') == 'array' and schema.get('maxItems') == 0:
        value = []
    elif schema.get('type') == 'object' and schema.get('additionalProperties') is False and not schema.get('properties') and not schema.get('patternProperties'):
        value = {}
    if value is not _MISSING and Draft202012Validator(schema).is_valid(value):
        return deepcopy(value)
    return _MISSING


def _intersection(left, right):
    """Exact JSON-schema intersection; unfamiliar constraints stay as allOf.

    Full object alternatives are intersections with their parent, not overlays.
    In particular a closed branch cannot acquire another branch's properties.
    """
    if _key(left) == _key(right):
        return deepcopy(left)
    if left is False or right is False:
        return False
    if left is True or left == {}:
        return deepcopy(right)
    if right is True or right == {}:
        return deepcopy(left)
    def owned(result):
        # readOnly is the generation contract's host-ownership annotation.
        # Logical enum/const reduction must not re-advertise a host-owned field.
        if isinstance(result,dict) and (left.get('readOnly') is True or right.get('readOnly') is True):
            result['readOnly']=True
        return result
    for fixed, other in ((left, right), (right, left)):
        value = _fixed(fixed)
        if value is not _MISSING:
            return owned(deepcopy(fixed)) if Draft202012Validator(other).is_valid(value) else False
        if 'enum' in fixed:
            values = [v for v in fixed['enum'] if Draft202012Validator(fixed).is_valid(v)
                      and Draft202012Validator(other).is_valid(v)]
            return owned({'enum': deepcopy(values)}) if values else False
    complex_keys = {'patternProperties', 'dependentSchemas', 'dependentRequired', 'dependencies',
                    'if', 'then', 'else', 'unevaluatedProperties', 'unevaluatedItems', 'propertyNames',
                    'prefixItems', 'additionalItems', '$ref', '$id', '$defs', 'definitions'}
    if complex_keys & (left.keys() | right.keys()):
        return {'allOf': [deepcopy(left), deepcopy(right)]}
    if 'anyOf' in left or 'anyOf' in right:
        aa, bb = left.get('anyOf', [{}]), right.get('anyOf', [{}])
        # Bound expansion; the unchanged allOf is exact when the menu is large.
        if len(aa) * len(bb) > 64:
            return {'allOf': [deepcopy(left), deepcopy(right)]}
        parent = _intersection({k:v for k,v in left.items() if k != 'anyOf'},
                               {k:v for k,v in right.items() if k != 'anyOf'})
        rows = {}
        for a in aa:
            for b in bb:
                merged = _intersection(parent, _intersection(a, b))
                if merged is not False:
                    rows[_key(merged)] = merged
        if not rows:
            return False
        if len(rows) == 1:
            return next(iter(rows.values()))
        values = list(rows.values())
        result = {'anyOf': values}
        if all(isinstance(v, dict) and v.get('type') == 'object' for v in values):
            result['type'] = 'object'
        return result
    low = {'minLength', 'minItems', 'minProperties', 'minimum', 'exclusiveMinimum'}
    high = {'maxLength', 'maxItems', 'maxProperties', 'maximum', 'exclusiveMaximum'}
    annotations = {'title', 'description', '$comment', 'default', 'examples', 'deprecated', 'writeOnly'}
    out = {}
    for key in sorted(left.keys() | right.keys()):
        if key == 'properties':
            a, b = left.get(key, {}), right.get(key, {})
            names = a.keys() | b.keys()
            if left.get('additionalProperties') is False:
                names &= a.keys()
            if right.get('additionalProperties') is False:
                names &= b.keys()
            out[key] = {name: _intersection(a.get(name, left.get('additionalProperties', True)),
                                           b.get(name, right.get('additionalProperties', True)))
                        for name in sorted(names)}
            continue
        if key not in left or key not in right:
            out[key] = deepcopy(left[key] if key in left else right[key])
            continue
        a, b = left[key], right[key]
        if _key(a) == _key(b):
            out[key] = deepcopy(a)
        elif key == 'required':
            out[key] = list(dict.fromkeys(a + b))
        elif key in low:
            out[key] = max(a, b)
        elif key in high:
            out[key] = min(a, b)
        elif key in ('items', 'additionalProperties'):
            out[key] = _intersection(a, b)
        elif key in ('uniqueItems', 'readOnly'):
            out[key] = a or b
        elif key == 'type':
            aa = {a} if isinstance(a, str) else set(a)
            bb = {b} if isinstance(b, str) else set(b)
            if 'number' in aa: aa.add('integer')
            if 'number' in bb: bb.add('integer')
            common = aa & bb
            if 'number' in common: common.discard('integer')
            if not common: return False
            out[key] = next(iter(common)) if len(common) == 1 else sorted(common)
        elif key in annotations:
            out[key] = deepcopy(b)
        else:
            return {'allOf': [deepcopy(left), deepcopy(right)]}
    if out.get('type') == 'object':
        properties = out.get('properties', {})
        if any(properties.get(name, out.get('additionalProperties', True)) is False
               for name in out.get('required', [])):
            return False
    return out


class _Node:
    def __init__(self, schema, *, keep=()):
        self.schema = deepcopy(schema)
        self.wire = deepcopy(schema)
        self.children = {}
        self.fixed = {}
        self.item = None
        self.variants = []
        self.discriminator = None
        if not isinstance(schema, dict):
            return
        # Scoped/conditional/pattern objects require a separate contract; leave
        # them intact rather than guessing their dependencies or reference scope.
        if any(k in schema for k in ('$ref', '$id', '$defs', 'definitions', 'allOf', 'oneOf',
                    'if', 'not', 'patternProperties', 'dependentSchemas', 'dependentRequired', 'dependencies', 'prefixItems')):
            return
        branches = schema.get('anyOf')
        if branches:
            if schema.get('type') != 'object' or not all(isinstance(b, dict) and b.get('type') == 'object' for b in branches):
                return
            shared = set.intersection(*(set(b.get('properties', {})) for b in branches))
            candidates = [k for k in sorted(shared) if all(_fixed(b['properties'][k]) is not _MISSING for b in branches)]
            candidates = [k for k in candidates if len({_key(_fixed(b['properties'][k])) for b in branches}) > 1]
            if not candidates:
                return
            key = next((k for k in ('next_action', 'action', 'kind', 'operation', 'type', 'status') if k in candidates), candidates[0])
            self.discriminator = key
            for b in branches:
                parent = {k: deepcopy(v) for k, v in schema.items() if k != 'anyOf'}
                merged = _intersection(parent, b)
                label = _fixed(b['properties'][key])
                siblings = [s for s in branches if _key(_fixed(s['properties'][key])) == _key(label)]
                keep = {key}
                for name in b.get('properties', {}):
                    values = [_fixed(s.get('properties', {}).get(name, {})) for s in siblings]
                    if all(v is not _MISSING for v in values) and len({_key(v) for v in values}) > 1:
                        keep.add(name)  # No single host value is implied by this action.
                self.variants.append((label, _Node(merged, keep=keep)))
            # Do not union properties or intersect requirements across actions.
            # Such a menu accepts values that no selected action can reconstruct.
            # Full alternatives also preserve typed/untyped branches of one action.
            self.wire = {'type': 'object', 'anyOf': [deepcopy(n.wire) for _, n in self.variants]}
            return
        if schema.get('type') == 'object':
            required = schema.get('required', [])
            for name, rule in schema.get('properties', {}).items():
                fixed = _fixed(rule)
                if fixed is not _MISSING and name not in keep and name in required:
                    self.fixed[name] = fixed
                    self.wire['properties'].pop(name)
                else:
                    child = self.children[name] = _Node(rule)
                    self.wire['properties'][name] = child.wire
            self.wire['required'] = [k for k in required if k not in self.fixed]
            # Required literals count toward the canonical object size, but
            # are absent on the generation wire and supplied during expansion.
            for bound in ('minProperties','maxProperties'):
                if bound in self.wire:
                    count=self.wire[bound]-len(self.fixed)
                    if bound=='maxProperties' and count<0:
                        self.wire=False
                        break
                    self.wire[bound]=max(0,count)
        elif schema.get('type') == 'array' and isinstance(schema.get('items'), dict):
            self.item = _Node(schema['items'])
            self.wire['items'] = self.item.wire

    def expand(self, raw):
        if self.variants:
            if not isinstance(raw, dict) or self.discriminator not in raw:
                raise OutputContractError('minimal output missing discriminator: '+str(self.discriminator),
                    [issue('MINIMAL_OUTPUT_DISCRIMINATOR', expected=self.discriminator)])
            matches, errors = {}, []
            for label, child in self.variants:
                if _key(label) != _key(raw[self.discriminator]):
                    continue
                try:
                    value = child.expand(raw)
                    Draft202012Validator(self.schema).validate(value)
                    matches[_key(value)] = value
                except (ValidationError, ProposalError) as exc:
                    errors.append(exc.message if isinstance(exc, ValidationError) else str(exc))
            if len(matches) != 1:
                detail = '; '.join(errors)[:1500] if errors else 'unknown or ambiguous action'
                raise OutputContractError('minimal output branch: '+detail,
                    [issue('MINIMAL_OUTPUT_BRANCH', expected='one unambiguous canonical action')])
            return next(iter(matches.values()))
        value = deepcopy(raw)
        if isinstance(value, dict) and isinstance(self.schema, dict) and self.schema.get('type') == 'object':
            for name, expected in self.fixed.items():
                if name in value and _key(value[name]) != _key(expected):
                    raise OutputContractError('minimal output conflicts with host constant: '+name,
                        [issue('MINIMAL_OUTPUT_CONSTANT', expected={name:expected})])
                if name in value or name in self.schema.get('required', []):
                    value[name] = deepcopy(expected)
            for name, child in self.children.items():
                if name in value:
                    value[name] = child.expand(value[name])
        elif isinstance(value, list) and self.item is not None:
            value = [self.item.expand(v) for v in value]
        Draft202012Validator(self.schema).validate(value)
        return value

    def project(self, value):
        """Testing/retained-response projection; never calls or predicts a model."""
        Draft202012Validator(self.schema).validate(value)
        if self.variants:
            for label, child in self.variants:
                if _key(value.get(self.discriminator)) == _key(label) and Draft202012Validator(child.schema).is_valid(value):
                    return child.project(value)
            raise ProposalError('no canonical action alternative')
        out = deepcopy(value)
        if isinstance(out, dict):
            for name in self.fixed:
                out.pop(name, None)
            for name, child in self.children.items():
                if name in out:
                    if isinstance(child.schema,dict) and child.schema.get('readOnly') is True and name not in self.schema.get('required',[]):
                        out.pop(name)  # Same host-owned omission as genos_wire_schema.
                    else:
                        out[name] = child.project(out[name])
        elif isinstance(out, list) and self.item:
            out = [self.item.project(v) for v in out]
        return out


class Projection:
    def __init__(self, schema, *, partial_contract=False):
        # Existing local references are intentionally untouched, including
        # references hidden in an item schema. Do not alter reference scope.
        self.schema = deepcopy(schema)
        self.partial_contract = partial_contract
        scoped = any(any(k in n for k in ('$ref', '$id', '$defs', 'definitions')) for n in _schemas(schema))
        self.node = None if scoped or partial_contract else _Node(schema)
        from .model_contract import genos_wire_schema
        self.wire = genos_wire_schema(deepcopy(schema) if self.node is None else self.node.wire)
        self.changed = self.wire != self.schema
        self.receipt = {'version':VERSION, 'canonical_schema_sha256':digest(schema),
            'wire_schema_sha256':digest(self.wire), 'canonical_schema_bytes':len(_key(schema).encode()),
            'wire_schema_bytes':len(_key(self.wire).encode()), 'changed':self.changed,
            'partial_contract':partial_contract}

    def expand(self, value):
        if self.partial_contract:
            # Legacy turn/selection consumers commit valid operations separately
            # and audit rejected siblings. Preserve their original ownership;
            # no schema fields are elided or reconstructed for these contracts.
            return deepcopy(value)
        try:
            result = self.node.expand(value) if self.node else deepcopy(value)
            Draft202012Validator(self.schema).validate(result)
            return result
        except ValidationError as exc:
            path = '/'+ '/'.join(map(str, exc.absolute_path))
            row = schema_issue(exc)
            if exc.validator in ('anyOf', 'oneOf', 'allOf'):
                row['expected_constraint'] = 'one complete permitted action alternative'
            raise OutputContractError('minimal output schema '+path+': '+exc.message, [row]) from exc

    def project(self, value):
        return self.node.project(value) if self.node else deepcopy(value)


def prepare_request(request, canonical_schema=None, *, partial_contract=False):
    schema = request['response_format']['json_schema']['schema']
    original_wire = schema
    if canonical_schema is not None:
        schema = canonical_schema
    projection = Projection(schema, partial_contract=partial_contract)
    result = deepcopy(request)
    result['response_format']['json_schema']['schema'] = projection.wire
    for message in result.get('messages', []):
        if message.get('role') == 'system' and isinstance(message.get('content'), str):
            message['content'] += '\n'+INSTRUCTIONS
            break
    # The same schema is already response_format. Remove only the exact host
    # copy, never similarly named data inside the evidence/view.
    for message in result.get('messages', []):
        if message.get('role') != 'user' or not isinstance(message.get('content'), str):
            continue
        try:
            data = json.loads(message['content'])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and 'view' in data and data.get('output_schema') == original_wire:
            del data['output_schema']
            message['content'] = _key(data)
    return result, projection
