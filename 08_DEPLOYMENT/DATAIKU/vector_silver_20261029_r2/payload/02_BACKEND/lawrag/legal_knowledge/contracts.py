"""Public, engine-independent contracts. No source corpus or model client lives here."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Protocol
from jsonschema import Draft202012Validator

VERSION = 'legal-knowledge-v1'
CAPABILITIES = ('LOCATE_SOURCE', 'READ_SOURCE', 'FOLLOW_EXPLICIT_REFERENCE',
                'ENUMERATE_SCOPE', 'READ_VERSION_CHAIN', 'EVALUATE_TYPED_EXPRESSION')
KINDS = ('FIELD', 'METHOD', 'APPLICATION', 'WIKI_LINK', 'SHORTCUT_LINK')


class KnowledgeError(Exception):
    def __init__(self, code, message, status=422, *, fields=()):
        super().__init__(message)
        self.code, self.status, self.fields = code, status, list(fields)


def require(ok, code, message, status=422):
    if not ok:
        raise KnowledgeError(code, message, status)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def obj(**fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
ID = {'type': 'string', 'pattern': r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$'}
HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
REV = {'type': 'integer', 'minimum': 1}


def array(value, limit=32):
    return {'type': 'array', 'items': value, 'maxItems': limit}


REF = obj(kind={'enum': list(KINDS) + ['WIKI', 'SHORTCUT', 'CONCEPT', 'DEFINITION']},
          id=ID, revision=REV, content_hash=HASH)
SOURCE = obj(document_id=ID, version=ID, locator=TEXT, content_hash=HASH)
DIMENSION = obj(mode={'enum': ['UNSPECIFIED', 'ANY_REVIEWED', 'VALUES']}, values=array(TEXT))
SCOPE = obj(**{name: DIMENSION for name in ('business', 'product', 'role', 'action', 'jurisdiction')})
STEP = obj(id=ID, label=TEXT, capability={'enum': list(CAPABILITIES)}, after=array(ID))
POLICY = obj(effect={'enum': ['DEPRIORITIZE', 'SKIP_CHECK', 'RESTRICT_SUPPORT', 'REOPEN_CHECK']},
             target=ID, condition={'type': 'object'}, reopen_condition={'type': 'object'},
             source_refs=array(SOURCE))
CONTENT = {
    'FIELD': obj(value_type={'enum': ['boolean', 'enum', 'decimal', 'money', 'ratio', 'date', 'duration', 'entity_ref', 'text']},
                 dimension=TEXT, legal_purpose=TEXT, concept_refs=array(REF),
                 allowed_origins=array({'enum': ['USER', 'SOURCE', 'CALCULATION', 'MODEL_PROPOSAL']})),
    'METHOD': obj(purpose=TEXT, requested_outputs=array(TEXT), inputs=array(REF),
                  evidence_needs=array(TEXT), steps=array(STEP), policies=array(POLICY)),
    'APPLICATION': obj(method_refs=array(REF), wiki_refs=array(REF), condition={'type': 'object'},
                       input_refs=array(REF), requested_outputs=array(TEXT)),
    'WIKI_LINK': obj(target=REF, evidence_role=TEXT, reuse_capability={'enum': ['LOCATION', 'PROCEDURE', 'CONDITIONAL_KNOWLEDGE']},
                     application_refs=array(REF)),
    'SHORTCUT_LINK': obj(target=REF, application_refs=array(REF)),
}
DEFINITION = obj(schema_version={'const': VERSION}, kind={'enum': list(KINDS)},
                 title=TEXT, description=TEXT, scope=SCOPE, source_refs=array(SOURCE),
                 dependencies=array(REF), lookup_terms=array({'type': 'string', 'minLength': 2, 'maxLength': 80}, 16),
                 effective_from={'type': ['string', 'null'], 'format': 'date'},
                 effective_to={'type': ['string', 'null'], 'format': 'date'}, content={'type': 'object'})
DEFINITION['allOf'] = [{'if': {'properties': {'kind': {'const': kind}}},
                        'then': {'properties': {'content': value}}} for kind, value in CONTENT.items()]
COMMAND = obj(schema_version={'const': VERSION}, operation={'enum': [
    'save_draft', 'prepare_publication', 'publish', 'retire', 'rollback', 'feedback']},
    operation_id=ID, arguments={'type': 'object'})
PLAN_ITEM = obj(ref=REF, title=TEXT, description=TEXT, kind={'enum': list(KINDS)},
    application_status={'enum': ['MATCHED', 'PARTIAL', 'NOT_APPLICABLE', 'UNRESOLVED']},
    semantic_status={'const': 'UNASSESSED'}, execution_status={'enum': ['READY', 'PARTIAL']},
    missing=array(TEXT, 64), steps=array(STEP), source_refs=array(SOURCE), wiki_refs=array(REF),
    policies=array({'type': 'object'}), decision_receipts=array({'type': 'object'}),
    role={'const': 'REVIEW_GUIDANCE_NOT_EVIDENCE'})
PLAN = obj(schema_version={'const': 'review-plan-v1'}, binding={'type': ['object', 'null']},
    items=array(PLAN_ITEM, 12), unresolved=array(TEXT, 64),
    fallback_owner={'const': 'EXISTING_RESEARCH_EXECUTOR'}, model_calls={'const': 0})
PLAN['properties']['plan_hash'] = HASH


def validate(value, schema):
    from jsonschema import FormatChecker
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise KnowledgeError('KNOWLEDGE_SCHEMA', '입력 형식과 필수 항목을 확인해 주세요.',
                             fields=['.'.join(map(str, e.absolute_path)) for e in errors[:16]])
    return value


def validate_definition(value):
    validate(value, DEFINITION)
    for dimension in value['scope'].values():
        require(bool(dimension['values']) == (dimension['mode'] == 'VALUES'),
                'KNOWLEDGE_SCOPE', '지정 범위에는 값이 필요하며 범용·미확인 범위에는 값을 넣을 수 없습니다.')
    start, end = value['effective_from'], value['effective_to']
    require(not (start and end and start > end), 'KNOWLEDGE_DATE', '효력 시작일과 종료일을 확인해 주세요.')
    c = value['content']
    if value['kind'] == 'METHOD':
        require(bool(c['steps']), 'KNOWLEDGE_STEPS', '검토 항목이 필요합니다.')
        ids = [s['id'] for s in c['steps']]
        require(len(set(ids)) == len(ids), 'KNOWLEDGE_STEPS', '검토 항목 ID가 중복되었습니다.')
        visit_graph({s['id']: s['after'] for s in c['steps']})
        for policy in c['policies']:
            require(policy['target'] in ids and bool(policy['source_refs']),
                    'KNOWLEDGE_POLICY', '제외·재개 정책에는 검토 항목과 근거가 필요합니다.')
            from .ontology import validate_expression
            validate_expression(policy['condition'])
            validate_expression(policy['reopen_condition'])
    if value['kind'] == 'APPLICATION':
        require(bool(c['method_refs']), 'KNOWLEDGE_METHOD', '검토 방법 참조가 필요합니다.')
        require(all(r['kind'] == 'METHOD' for r in c['method_refs']), 'KNOWLEDGE_METHOD', '방법 참조 종류가 다릅니다.')
        from .ontology import validate_expression
        validate_expression(c['condition'])
    if value['kind'] in ('WIKI_LINK', 'SHORTCUT_LINK'):
        require(c['target']['kind'] == value['kind'].removesuffix('_LINK'),
                'KNOWLEDGE_REFERENCE', '기존 지식 참조 종류가 다릅니다.')
    require(len(canonical(value).encode()) <= 64000, 'KNOWLEDGE_SIZE', '항목을 작은 단위로 나누어 주세요.')
    return value


def visit_graph(graph):
    done, stack = set(), set()
    def visit(key):
        require(key in graph, 'KNOWLEDGE_REFERENCE', '선행 항목이 없습니다.')
        require(key not in stack, 'KNOWLEDGE_CYCLE', '순환하는 선행 관계를 수정해 주세요.')
        if key in done:
            return
        stack.add(key)
        for dependency in graph[key]:
            visit(dependency)
        stack.remove(key)
        done.add(key)
    for key in graph:
        visit(key)


def references(definition):
    found = {}
    def walk(value):
        if isinstance(value, dict):
            if set(value) == set(REF['required']):
                found[digest(value)] = value
            else:
                for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(definition)
    return list(found.values())


def principal(value, role='read'):
    require(isinstance(value, dict) and value.get('authenticated') is True,
            'KNOWLEDGE_AUTH', '관리 화면 인증이 필요합니다.', 401)
    for key in ('tenant_id', 'team_id', 'user_id'):
        validate(value.get(key), ID)
    require(isinstance(value.get('document_ids'), list) and all(isinstance(d, str) for d in value['document_ids']),
            'KNOWLEDGE_AUTH', '인증된 문서 범위가 필요합니다.', 403)
    require(role in value.get('knowledge_roles', []), 'KNOWLEDGE_ROLE', '이 작업의 권한이 없습니다.', 403)
    return value


def authorize(record, who):
    require(record['tenant_id'] == who['tenant_id'] and record['team_id'] == who['team_id']
            and set(record['document_ids']) <= set(who['document_ids'])
            and (not record.get('private_owner') or record['private_owner'] == who['user_id']),
            'KNOWLEDGE_NOT_FOUND', '접근 가능한 항목을 찾을 수 없습니다.', 404)


class ReferencePort(Protocol):
    def resolve(self, ref: dict, principal: dict) -> dict:
        """Return verified ref, document_ids and optional read routes; never a copied answer."""
    def verify_source(self, ref: dict, principal: dict, source_binding: dict) -> None: ...


class RepositoryPort(Protocol):
    def transaction(self): ...
    def read(self, namespace: str, key: str, revision: int | None = None): ...
    def append(self, namespace: str, key: str, value: dict, expected_revision: int): ...
