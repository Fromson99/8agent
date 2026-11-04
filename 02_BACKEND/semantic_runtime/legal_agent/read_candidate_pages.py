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
PROGRESS_VERSION = 'read-candidate-page-progress-v1'
NO_PROGRESS = 'READ_CANDIDATE_PAGE_NO_PROGRESS'


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


def progress_state(inv, data, checkpoint):
    """Bind display history to the same immutable input and durable cursor.

    An old three-field pager starts history at its current page. New originals,
    judgments or candidates belong to a new bound menu; merely restarting the
    same selector does not grant another cycle.
    """
    state = inv.p.get('read_candidate_page_progress')
    if state is not None:
        if (not isinstance(state, dict) or state.get('version') != PROGRESS_VERSION
                or state.get('state_hash') != digest({k:v for k,v in state.items() if k != 'state_hash'})):
            raise ContractError('read candidate progress hash/version mismatch')
        if state['menu'] == checkpoint['binding']:
            if state['input_hash'] != digest(data) or state['checkpoint'] != checkpoint:
                raise ContractError('read candidate progress input/checkpoint mismatch')
            return deepcopy(state)
    state = {'version': PROGRESS_VERSION, 'menu': checkpoint['binding'],
             'input_hash': digest(data), 'checkpoint': deepcopy(checkpoint),
             'visited': [checkpoint['page']], 'edges': [], 'halt': None}
    save_progress(inv, state)
    return state


def save_progress(inv, state):
    state['state_hash'] = digest({k:v for k,v in state.items() if k != 'state_hash'})
    inv.p['read_candidate_page_progress'] = deepcopy(state)
    inv.save()


def require_progress(state):
    if state['halt']:
        # The investigation owner preserves originals and runs its existing
        # bounded-result/final-assessment path. This is not a FINISH proposal
        # or an approval of legal sufficiency.
        from .answer_progress import ProgressHandoff
        raise ProgressHandoff(NO_PROGRESS)


def move(inv, data, choice, *, expected_state, actor=None):
    """Apply one display transition, including an already committed replay."""
    if choice not in (NEXT, PREVIOUS):
        raise ContractError('unknown read candidate page operation')
    before = expected_state
    if (not isinstance(before, dict) or set(before) != {'binding','page','sequence'}
            or type(before['page']) is not int or type(before['sequence']) is not int
            or before['sequence'] < 0):
        raise ContractError('read candidate checkpoint is malformed')
    page_size = inv.policy.get('read_candidate_page_size', 20)
    count = max(1, (len(data.get('read_candidates', [])) + page_size - 1) // page_size)
    target = before['page'] + (1 if choice == NEXT else -1)
    if not 0 <= before['page'] < count or not 0 <= target < count:
        raise ContractError('read candidate page operation is outside the bound menu')
    after = {**before, 'page': target, 'sequence': before['sequence'] + 1}
    current = inv.p.get('read_candidate_pager')
    if current == after:
        require_progress(progress_state(inv, data, after))
        return after
    if current != before:
        raise ContractError('read candidate page checkpoint changed before selection')
    progress = progress_state(inv, data, before)
    require_progress(progress)
    edge = [before['page'], target]
    if edge in progress['edges']:
        progress['halt'] = {'choice': choice, 'from_page': before['page'] + 1,
                            'to_page': target + 1, 'sequence': before['sequence']}
        save_progress(inv, progress)
        inv.s.repo.event('READ_CANDIDATE_PAGE_HANDOFF', {
            'reason': NO_PROGRESS, 'menu': before['binding'], **progress['halt'],
            'visited_pages': [p + 1 for p in progress['visited']],
            'originals_preserved': True, 'legal_sufficiency_approved': False,
            'final_assessment_required': True, 'actor': actor or 'selector'})
        require_progress(progress)
    if target not in progress['visited']:
        progress['visited'] = sorted([*progress['visited'], target])
        progress['edges'] = []
    else:
        progress['edges'].append(edge)
    progress['checkpoint'] = deepcopy(after)
    inv.p['read_candidate_pager'] = after
    # Cursor and history use one checkpoint commit, so a resumed accepted
    # response cannot reset the cycle or apply its page transition twice.
    save_progress(inv, progress)
    receipt = {'menu': before['binding'], 'from_page': before['page'] + 1,
        'to_page': target + 1, 'sequence': after['sequence'],
        'detail_policy':'first-visit-bounded-revisit-cached',
        'originals_acquired':False, 'judgments_completed':False}
    if actor is not None:receipt['actor'] = actor
    inv.s.repo.event('READ_CANDIDATE_PAGE_SELECTED', receipt)
    return after


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
    page_view(data, schema, state['page'], page_size)
    require_progress(progress_state(inv, data, state))
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
        state = move(inv, data, value['choice'], expected_state=state)
