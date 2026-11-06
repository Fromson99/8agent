"""Durable pages over a bound metadata menu.

First visits may load bounded excerpts through the existing search projection;
revisits reuse checkpointed details. Candidate availability precedes pagination.
"""
from copy import deepcopy
from .schema_preparation import validate
from ..contracts import digest
from .errors import BudgetExhausted, ContractError
from . import output_contract
from .guided_navigation import enabled as guided_enabled

VERSION = 'read-candidate-pages-v3'
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


DOCUMENT_TOOLS = 'SHOW_DOCUMENT_TOOLS'


def tool_menu_view(data, schema, document=None):
    """Focus document-specific tools without removing access to another document.

    This is display only: every hidden operation can be opened by its exact
    authorized document. Source and read-candidate sets are unchanged.
    """
    options=data.get('tool_options',[])
    documents={}
    for row in options:
        did=row.get('scope',{}).get('document_id')
        if did is not None:documents.setdefault(did,[]).append(row)
    if not documents:return data,schema
    if document is not None and document not in documents:
        raise ContractError('tool menu document is outside the bound menu')
    focus={document} if document is not None else {s.get('document_id') for s in data.get('sources',[])}
    for goal in (data.get('source_goal_context') or {}).get('goals',[]):
        if goal.get('status') in ('REQUIRED','BLOCKED'):focus.add(goal.get('document_id'))
    if document is None and not focus.intersection(documents):
        focus={r.get('document_id') for r in data.get('read_candidates',[])}
    focus.intersection_update(documents)
    if not focus:focus=set(documents)
    visible=[r for r in options if r.get('scope',{}).get('document_id') is None or r['scope']['document_id'] in focus]
    allowed={}
    for row in visible:allowed.setdefault(row['choice'],set()).add(row['target'])
    wire=deepcopy(schema);branches=[]
    for branch in wire['anyOf']:
        kind=branch['properties']['choice']['const']
        target=branch['properties'].get('target')
        if target is not None and 'enum' in target:
            targets=[t for t in target['enum'] if t in allowed.get(kind,set())]
            if not targets:continue
            target['enum']=targets
        branches.append(branch)
    hidden=set(documents)-focus
    if hidden:
        branches.append({'type':'object','properties':{'choice':{'const':DOCUMENT_TOOLS},
            'document_ref':{'type':'string','enum':sorted(hidden)}},
            'required':['choice','document_ref'],'additionalProperties':False})
    wire['anyOf']=branches
    names={r.get('document_id'):r.get('name') for r in data.get('document_structures',[])}
    view={**data,'tool_options':visible,
        'tool_documents':[{'document_ref':did,'document_id':did,
            'document_name':names.get(did) or did,'visible':did in focus,
            'available_choices':sorted({r['choice'] for r in rows})} for did,rows in sorted(documents.items())],
        'tool_menu':{'focused_document':document,'shown':len(visible),'total':len(options),
                    'hidden_documents':len(hidden),'action':DOCUMENT_TOOLS if hidden else None,
                    'meaning':'다른 문서의 도구는 SHOW_DOCUMENT_TOOLS로 연다. 표시되지 않은 도구·원문이 없다는 뜻이 아니다.'}}
    return view,wire


def tool_menu_state(inv, binding):
    state=inv.p.get('tool_menu_focus')
    if state is not None:
        if state.get('state_hash')!=digest({k:v for k,v in state.items() if k!='state_hash'}):
            raise ContractError('tool menu focus checkpoint hash mismatch')
        if state['binding']==binding:return deepcopy(state)
    return {'binding':binding,'document':None,'visited':[],'edges':[],'halt':False}


def move_tool_menu(inv,data,document,*,expected_state,focus):
    """A durable display transition shares the existing paging correction owner."""
    if inv.p.get('read_candidate_pager')!=expected_state:
        raise ContractError('tool menu checkpoint changed before selection')
    current=tool_menu_state(inv,expected_state['binding'])
    if {k:v for k,v in current.items() if k!='state_hash'}!={k:v for k,v in focus.items() if k!='state_hash'}:
        raise ContractError('tool menu focus changed before selection')
    shown,_=page_view(data,{'anyOf':[]},expected_state['page'],inv.policy.get('read_candidate_page_size',20))
    _, wire=tool_menu_view(shown, {'anyOf':[]}, current['document'])
    permitted=next((b['properties']['document_ref']['enum'] for b in wire['anyOf']
                    if b['properties']['choice']['const']==DOCUMENT_TOOLS),[])
    if document not in permitted:raise ContractError('tool menu document is not currently offered')
    progress=progress_state(inv,data,expected_state)
    edge=[current['document'],document]
    if current['halt'] or edge in current['edges']:
        current['halt']=True;current['state_hash']=digest({k:v for k,v in current.items() if k!='state_hash'})
        inv.p['tool_menu_focus']=current;inv.save()
        from .answer_progress import ProgressHandoff
        raise ProgressHandoff('TOOL_MENU_NO_PROGRESS')
    if document not in current['visited']:
        current['visited'].append(document);current['edges']=[]
    else:current['edges'].append(edge)
    current['document']=document
    current['state_hash']=digest({k:v for k,v in current.items() if k!='state_hash'})
    after={**expected_state,'sequence':expected_state['sequence']+1}
    inv.p['tool_menu_focus']=current;inv.p['read_candidate_pager']=after
    progress['checkpoint']=after;save_progress(inv,progress)
    inv.s.repo.event('TOOL_MENU_DOCUMENT_SELECTED',{'document_id':document,
        'sequence':after['sequence'],'originals_acquired':False,'judgments_completed':False})
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
        focus=tool_menu_state(inv,signature)
        if focus['halt']:
            from .answer_progress import ProgressHandoff
            raise ProgressHandoff('TOOL_MENU_NO_PROGRESS')
        view,wire=tool_menu_view(view,wire,focus['document'])

        def check(value):
            validate(value, wire, owner=inv.s)
            if value['choice'] not in (NEXT, PREVIOUS, DOCUMENT_TOOLS):
                expand(value)

        def call(payload, attempt):
            return invoke(payload, attempt, wire, '-page-' + str(page + 1) + '-' + str(sequence))

        from . import request_repair
        value = output_contract.bounded_decision(inv.s.repo, 'read-choice', view, wire, call, check,
            can_repair=lambda: not guided_enabled(inv.s.profile) and request_repair.gap_review_capacity(inv) is None,
            identity={'binding': inv.p['binding'], 'presentation': data['presentation_id'],
                      'key': key, 'menu': signature, 'page': page, 'sequence': sequence},
            correction_scope=correction_scope,recover=recover)
        if value['choice']==DOCUMENT_TOOLS:
            state=move_tool_menu(inv,data,value['document_ref'],expected_state=state,focus=focus)
            continue
        if value['choice'] not in (NEXT, PREVIOUS):
            return value
        # Persist only display state. No tool execution, evidence adoption or
        # semantic judgment is fabricated for a next/previous page operation.
        state = move(inv, data, value['choice'], expected_state=state)
