"""Durable pages over a bound metadata menu.

First visits may load bounded excerpts through the existing search projection;
revisits reuse checkpointed details. Candidate availability precedes pagination.
"""
from copy import deepcopy
from .schema_preparation import validate
from ..contracts import digest
from .errors import BudgetExhausted, ContractError
from . import output_contract

VERSION = 'read-candidate-pages-v2'
NEXT = 'NEXT_READ_CANDIDATES'
PREVIOUS = 'PREV_READ_CANDIDATES'


def enabled(inv):
    return inv.policy.get('minimal_input', False)


def page_view(data, schema, page, page_size):
    rows = data.get('read_candidates', [])
    count = max(1, (len(rows) + page_size - 1) // page_size)
    if type(page) is not int or not 0 <= page < count:
        raise ContractError('read candidate page is outside the bound menu')
    view = {**data, 'read_candidates': rows[page * page_size:(page + 1) * page_size],
            'read_candidate_page': {'page': page + 1, 'pages': count, 'total': len(rows),
                                    'shown': min(page_size, max(0, len(rows) - page * page_size)),
                                    'more_available': page + 1 < count}}
    wire = deepcopy(schema)
    visible = [row['target'] for row in view['read_candidates']]
    for branch in wire['anyOf']:
        if branch['properties']['choice'].get('const') == 'READ':
            branch['properties']['selections']['items']['properties']['target']['enum'] = visible
    moves = []
    if page + 1 < count:
        moves.append(NEXT)
    if page:
        moves.append(PREVIOUS)
    for kind in moves:
        wire['anyOf'].append({'type': 'object', 'properties': {'choice': {'const': kind}},
                             'required': ['choice'], 'additionalProperties': False})
    view['read_candidate_page']['actions'] = moves
    return view, wire


def choose(inv, data, schema, invoke, expand, *, key, correction_scope=None, prepare_page=None, recover=None):
    page_size = inv.policy.get('read_candidate_page_size', 20)
    signature = digest([VERSION, key, data['read_candidates'], schema, page_size])
    state = inv.p.get('read_candidate_pager')
    if state is None or state.get('binding') != signature:
        state = {'binding': signature, 'page': 0, 'sequence': 0}
        inv.p['read_candidate_pager'] = state
        inv.save()
    elif (set(state) != {'binding', 'page', 'sequence'} or type(state['sequence']) is not int
          or state['sequence'] < 0):
        raise ContractError('read candidate checkpoint is malformed')
    # The snapshot was prepared once by the investigation owner. All ordinary
    # responses still expand/validate against that original canonical menu.
    while True:
        budget = inv.s.repo.budget()
        if budget['model_limit'] - budget['finalization_reserve'] - budget['model_reserved'] < 1:
            raise BudgetExhausted('candidate paging reached investigation model reserve')
        if inv.left() <= max(1, inv.s.profile.get('selection_time_reserve_seconds', 30)):
            raise BudgetExhausted('candidate paging reached finalization time reserve')
        page, sequence = state['page'], state['sequence']
        view, wire = page_view(data, schema, page, page_size)
        if prepare_page is not None:
            view = prepare_page(view)

        def check(value):
            validate(value, wire, owner=inv.s)
            if value['choice'] not in (NEXT, PREVIOUS):
                expand(value)

        def call(payload, attempt):
            return invoke(payload, attempt, wire, '-page-' + str(page + 1) + '-' + str(sequence))

        from . import request_repair
        value = output_contract.bounded_decision(inv.s.repo, 'read-choice', view, wire, call, check,
            can_repair=lambda: request_repair.gap_review_capacity(inv) is None,
            identity={'binding': inv.p['binding'], 'presentation': data['presentation_id'],
                      'key': key, 'menu': signature, 'page': page, 'sequence': sequence},
            correction_scope=correction_scope,recover=recover)
        if value['choice'] not in (NEXT, PREVIOUS):
            return value
        # Persist only display state. No tool execution, evidence adoption or
        # semantic judgment is fabricated for a next/previous page operation.
        state = {'binding': signature, 'page': page + (1 if value['choice'] == NEXT else -1),
                 'sequence': sequence + 1}
        inv.p['read_candidate_pager'] = state
        inv.save()
        inv.s.repo.event('READ_CANDIDATE_PAGE_SELECTED', {
            'menu': signature, 'from_page': page + 1, 'to_page': state['page'] + 1,
            'sequence': state['sequence'], 'detail_policy':'first-visit-bounded-revisit-cached',
            'originals_acquired': False, 'judgments_completed': False})
