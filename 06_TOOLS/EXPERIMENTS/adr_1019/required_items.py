"""Source-bound review obligations. Structure is enforced; legal truth is not.

Only the explicit research host enables this prototype. Native source verification,
assessment repair budget, request journal and publication own their existing roles.
"""
from copy import deepcopy
import html
import json
from ..contracts import digest
from .errors import ContractError, ProposalError
from .repository import text_hash

VERSION = 'source-required-review-v1'
FIELD = 'required_review'
EVENT = 'REQUIRED_ITEMS_ACCEPTED'

PROMPT = '''
required_review_items는 현재 원문에 연결된 검토 메모이며 법률 결론이나 사용자 사실이 아니다.
현재 질문에 필요한 각 항목의 구체 내용을 claims에 설명하고 required_review에서 그 claim_id를 연결한다.
action은 EXPLAIN(이번 claims로 설명), NOT_APPLICABLE(현재 질문과 무관한 이유), UNKNOWN(구체 미확인), KEEP(이전 검토 유지) 중 하나다.
KEEP은 previous가 있는 항목에서만 사용한다. 이전 검토를 바꾸면 reason에 변경 근거를 적는다.
시스템이 제공한 item_id를 선택하고 그 결과를 required_review 배열에 쓴다. 원문 좌표와 인용은 시스템이 결속한다.
검토 메모를 복사한 것, 조문 위치만 안내한 것, 미확인 표시는 설명 완료가 아니다.
한 항목의 부족 때문에 다른 항목의 설명을 없애지 않는다. 미확인 자체를 추가 조사의 이유로 삼지 않는다.
이 추가 스키마의 required_review 필드는 기존 필드에 더해 작성한다. 같은 설명은 claims에 한 번만 쓰고 여러 항목에서 참조할 수 있다.
'''


def enabled(execution):
    from .knowledge_delivery import enabled as delivery_enabled
    return delivery_enabled(execution) and bool(getattr(
        execution.host.pipeline.term_agent.transport, 'knowledge_required_items', False))


def latest(work, key):
    if not hasattr(work, 'db'):
        return None
    for row in work.db.execute('SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq DESC', (EVENT,)):
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise ContractError('required review journal hash mismatch')
        if payload['context_key'] == key:
            return payload
    return None


def validate_sources(items, store, scope):
    for item in items:
        for ref in item['source_refs']:
            if ref['document_id'] not in scope or ref['version'] != ref['document_id']:
                raise ContractError('required review source permission/version changed')
            raw = store.source(ref['document_id'], ref['locator'])
            if text_hash(raw['text']) != ref['content_hash']:
                raise ContractError('required review source hash changed')


def prepare(execution, selection, sources, question):
    execution.required_review_context = None
    execution.required_review_proposal = None
    if not enabled(execution):
        return None
    plan = execution.host.knowledge_plan
    binding = {k: execution.host.binding.get(k) for k in ('generation', 'store_sha256', 'unit_index_sha256')}
    if plan['plan']['binding']['source_binding'] != binding:
        raise ContractError('required review generation mismatch')
    deliveries = {digest(r['ref']): r for r in selection.get('knowledge_original_delivery', {}).get('items', [])}
    offered = {s['source_id'] for s in sources}
    items = []
    for method in plan['plan']['items']:
        if not method['source_refs']:
            continue
        delivery = deliveries.get(digest(method['ref']), {})
        for step in method['steps']:
            item = {'item_id': 'R' + digest([binding, method['ref'], step['id']])[:20],
                    'method_ref': deepcopy(method['ref']), 'step_id': step['id'],
                    'title': method['title'], 'note': step['label'],
                    'source_refs': deepcopy(method['source_refs']),
                    'source_ids': sorted(set(delivery.get('source_ids', [])) & offered),
                    'original_status': delivery.get('status', 'OMITTED'),
                    'original_reason': delivery.get('reason')}
            items.append(item)
    if not items:
        return None
    if len({i['item_id'] for i in items}) != len(items):
        raise ContractError('duplicate required review identity')
    validate_sources(items, execution.s.sources.store, execution.s.sources.scope)
    # Stable across changed delivery spans/selection rounds: identity comes from
    # question/principal/plan and immutable registered source definitions.
    identity = [{k: i[k] for k in ('item_id', 'method_ref', 'step_id', 'note', 'source_refs')} for i in items]
    key = digest([plan['identity_hash'], question, binding, identity])
    previous = latest(execution.s.work, key)
    context = {'schema_version': VERSION, 'context_key': key, 'binding': binding,
               'items': items, 'previous': previous, 'automatic_legal_approval': False}
    execution.required_review_context = context
    execution.s.work.event('REQUIRED_ITEMS_BOUND', {k: v for k, v in context.items() if k != 'previous'})
    return context


def model_input(execution, data, schema, phase):
    context = getattr(execution, 'required_review_context', None)
    if not context or not phase.startswith('memory-assess'):
        return data, schema, ''
    execution.required_review_proposal = None
    previous = {r['item_id']: r for r in (context['previous'] or {}).get('rows', [])}
    items = []
    for item in context['items']:
        view = {k: deepcopy(item[k]) for k in ('item_id', 'title', 'note', 'source_ids', 'original_status', 'original_reason')}
        old = previous.get(item['item_id'])
        view['previous'] = ({k: deepcopy(old[k]) for k in ('status', 'reason', 'claims', 'revision')}
                            if old else None)
        items.append(view)
    row_schema = {'type': 'object', 'additionalProperties': False,
        'properties': {'item_id': {'enum': [i['item_id'] for i in items]},
                       'action': {'enum': ['EXPLAIN', 'NOT_APPLICABLE', 'UNKNOWN', 'KEEP']},
                       'claim_ids': {'type': 'array', 'items': {'type': 'string'}, 'uniqueItems': True, 'maxItems': 32},
                       'reason': {'type': 'string', 'minLength': 1, 'maxLength': 1000}},
        'required': ['item_id', 'action', 'claim_ids', 'reason']}
    schema = deepcopy(schema)
    # Omission itself is recorded as UNKNOWN, not a reason for another LLM loop.
    schema['properties'][FIELD] = {'type': 'array', 'maxItems': len(items), 'items': row_schema}
    return {**data, 'required_review_items': items}, schema, PROMPT


def capture(execution, value, phase):
    if not getattr(execution, 'required_review_context', None) or not phase.startswith('memory-assess'):
        return value
    value = deepcopy(value)
    rows = value.pop(FIELD, [])
    if len({r['item_id'] for r in rows}) != len(rows):
        raise ProposalError('duplicate required review item')
    execution.required_review_proposal = {r['item_id']: {k: v for k, v in r.items() if k != 'item_id'} for r in rows}
    return value


def resolve(context, proposal, claims):
    known = {i['item_id']: i for i in context['items']}
    if not isinstance(proposal, dict) or set(proposal) - set(known):
        raise ProposalError('unknown required review item')
    old = {r['item_id']: r for r in (context.get('previous') or {}).get('rows', [])}
    by_id = {c['claim_id']: c for c in claims}
    rows = []
    for key, item in known.items():
        previous = old.get(key)
        response = proposal.get(key)
        row = {**deepcopy(item), 'status': 'UNKNOWN', 'reason': '이번 판단에서 이 항목을 처리하지 않았습니다.',
               'claims': [], 'revision': (previous or {}).get('revision', 0) + 1,
               'previous_revision': (previous or {}).get('revision'), 'previous_result_hash': digest(previous) if previous else None,
               'model_processed': response is not None, 'semantic_verified': False}
        if response is None:
            if previous:
                row['prior_review'] = {k: deepcopy(previous[k]) for k in ('status', 'reason', 'claims', 'revision')}
            rows.append(row)
            continue
        action, ids, reason = response['action'], response['claim_ids'], response['reason'].strip()
        if not reason or len(ids) != len(set(ids)) or set(ids) - set(by_id):
            raise ProposalError('required review needs a reason and valid claim references')
        if action == 'KEEP':
            if not previous or ids:
                raise ProposalError('KEEP requires a prior result and no new claim IDs')
            row.update(status=previous['status'], claims=deepcopy(previous['claims']), reason=reason)
        elif action in ('EXPLAIN', 'UNKNOWN', 'NOT_APPLICABLE'):
            if action == 'EXPLAIN' and not ids:
                raise ProposalError('EXPLAIN requires a source-validated claim')
            if action == 'NOT_APPLICABLE' and ids:
                raise ProposalError('NOT_APPLICABLE cannot adopt claim references')
            row.update(status='EXPLAINED' if action == 'EXPLAIN' else action,
                       claims=[deepcopy(by_id[i]) for i in ids], reason=reason)
        else:
            raise ProposalError('invalid required review action')
        for claim in row['claims']:
            claim_sources = {claim['source_id']} | {e['source_id'] for e in claim.get('evidence', [])}
            if not claim_sources.intersection(item['source_ids']):
                raise ProposalError('required review claim does not cite its attached original')
        if row['claims'] and item['original_status'] != 'PREPARED':
            raise ProposalError('required review cannot explain an undelivered original')
        rows.append(row)
    return {'schema_version': VERSION, 'context_key': context['context_key'], 'binding': deepcopy(context['binding']),
            'rows': rows, 'registered_item_count': len(rows), 'automatic_legal_approval': False}


def accept(execution, result, sources):
    context = getattr(execution, 'required_review_context', None)
    if not context:
        return result
    proposal = getattr(execution, 'required_review_proposal', None)
    identity = {'assessment_content_hash': digest({k: v for k, v in result.items() if k != FIELD}),
                'proposal_hash': digest(proposal or {}), 'offered_item_hash': digest(context['items'])}
    previous = latest(execution.s.work, context['context_key'])
    reused = previous is not None and all(previous.get(k) == v for k, v in identity.items())
    receipt = deepcopy(previous) if reused else resolve(context, proposal or {}, result['claims'])
    validate_sources(receipt['rows'], execution.s.sources.store, execution.s.sources.scope)
    for row in receipt['rows']:
        if row['claims']:
            execution.verify_claims(row['claims'], sources)
    receipt.update(identity)
    if not reused:
        execution.s.work.event(EVENT, receipt)
    result[FIELD] = deepcopy(receipt)
    context['previous'] = receipt
    return result


def validate_receipt(receipt):
    if receipt.get('schema_version') != VERSION or receipt.get('automatic_legal_approval') is not False:
        raise ContractError('invalid required review receipt')
    rows = receipt.get('rows', [])
    if len(rows) != receipt.get('registered_item_count') or len({r['item_id'] for r in rows}) != len(rows):
        raise ContractError('required review count/identity changed')
    for row in rows:
        if row['status'] not in ('EXPLAINED', 'UNKNOWN', 'NOT_APPLICABLE') or not row['reason'].strip():
            raise ContractError('required review missing outcome')
        if row['status'] == 'EXPLAINED' and not row['claims']:
            raise ContractError('required review explanation has no claims')
        if row.get('semantic_verified') is not False:
            raise ContractError('required review is not legal certification')


def publication_metadata(work):
    if not hasattr(work, 'db'):
        return {}
    row = work.db.execute('SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq DESC LIMIT 1', (EVENT,)).fetchone()
    if row is None:
        return {}
    payload = json.loads(row[0])
    if digest(payload) != row[1]:
        raise ContractError('required review publication journal changed')
    validate_receipt(payload)
    return {FIELD: payload}


def render(receipt):
    validate_receipt(receipt)
    def esc(text):
        return html.escape(str(text), quote=False).replace('*', '\\*').replace('[', '\\[').replace(']', '\\]')
    labels = {'EXPLAINED': '설명 연결', 'NOT_APPLICABLE': '비적용 의견', 'UNKNOWN': '미확인'}
    blocks = ['원문별 필수 확인 사항', '아래 등록 메모는 원문에 연결한 연구용 검토 후보입니다. 이번 질문의 판단과 구분해 표시합니다.']
    for n, row in enumerate(receipt['rows'], 1):
        text = '**' + str(n) + '. ' + esc(row['title']) + '**\n\n등록 메모: ' + esc(row['note'])
        text += '\n\n이번 판단: ' + labels[row['status']] + ' — ' + esc(row['reason'])
        if row['claims']:
            text += '\n\n' + '\n\n'.join(esc(c['text']) for c in row['claims'])
        if row.get('prior_review'):
            text += '\n\n이전 검토 기록은 보존되어 있으나 이번 판단에서는 갱신되지 않았습니다.'
        if row['original_status'] != 'PREPARED':
            text += '\n\n연결 원문을 이번 판단 입력에 완전히 전달하지 못했습니다.'
        blocks.append(text)
    return '\n\n'.join(blocks)


def verify_publication(receipt, store, scope, sources):
    from .completion_contracts import verify_span_claim
    validate_receipt(receipt)
    if receipt['binding']['generation'] != store.manifest['generation_id'] or receipt['binding']['store_sha256'] != store.manifest['store_sha256']:
        raise ContractError('required review publication generation changed')
    validate_sources(receipt['rows'], store, scope)
    for row in receipt['rows']:
        for claim in row['claims']:
            verify_span_claim(claim, sources)
