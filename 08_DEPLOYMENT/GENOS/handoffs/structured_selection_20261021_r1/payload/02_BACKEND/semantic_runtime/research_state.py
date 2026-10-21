"""Research state owners shared by native RAG and workflow orchestration.

The existing journal/checkpoint dictionaries are the sole persisted records.
These owners mutate them in place; model views are detached projections, never
another mutable state store. Operation completion is not semantic resolution.
Legacy keys and wire contracts are deliberately preserved for saved runs.
"""
from .contracts import digest
from copy import deepcopy
from .legal_agent.errors import ContractError

CONTRACT = 'research-continuity-v1'
TERMINAL = frozenset(('COMPLETE', 'PARTIAL', 'FAILED', 'BLOCKED', 'RESOLVED'))


class KnowledgeReferences:
    """Review bindings live in the same native journal and transaction as other state."""
    def __init__(self, journal):
        self.journal = journal

    def read(self, identity):
        import json
        for row in self.journal.db.execute(
                'SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq', ('LEGAL_KNOWLEDGE_BOUND',)):
            value = json.loads(row[0])
            if digest(value) != row[1] or not value.get('identity_hash'):
                raise ContractError('review knowledge journal binding changed')
            if value['identity_hash'] == identity: return value
        return None

    def bind(self, identity, value):
        before = self.read(identity)
        if before is not None:
            if before != value: raise ContractError('review knowledge request binding changed')
            return
        with self.journal.transaction():
            self.journal.event('LEGAL_KNOWLEDGE_BOUND', value, event_id='knowledge:'+identity)

    def all(self):
        import json
        values = []
        for row in self.journal.db.execute(
                'SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq', ('LEGAL_KNOWLEDGE_BOUND',)):
            value = json.loads(row[0])
            if digest(value) != row[1]: raise ContractError('review knowledge journal binding changed')
            values.append(value)
        return values


def original_progress(state):
    """Monotonic union of acquired original intervals, not cards or judgments."""
    from .legal_agent.request_repair import spans_by_document
    from .legal_agent.evidence_inventory import intervals
    actual = spans_by_document(state, list(state.get('basis_history', {})))
    for record in state.get('selected', {}).values():
        if record.get('document_id'):
            actual.setdefault(record['document_id'], []).extend(
                p for e in record.get('evidence', []) for p in e.get('spans', []))
    saved = state.setdefault('original_progress', {'ranges': {}, 'revision': 0})
    changed = False
    for did, spans in actual.items():
        prior = saved['ranges'].get(did, {})
        old = [{'block_id': bid, 'start_cp': lo, 'end_cp': hi}
               for bid, ranges in prior.items() for lo, hi in ranges]
        merged = {str(bid): [[lo, hi] for lo, hi in ranges]
                  for bid, ranges in intervals(old + spans).items()}
        if merged != prior:
            saved['ranges'][did] = merged
            changed = True
    if changed:
        saved['revision'] += 1
    saved['last_changed'] = changed
    return changed


def progress_view(state):
    saved = state.get('original_progress', {})
    return {'criterion': 'NEW_ORIGINAL_INTERVALS', 'source_revision': saved.get('revision', 0),
            'new_original': saved.get('last_changed', False),
            'discovery_changed': state.get('discovery_changed', False),
            'unchanged_turns': state.get('no_progress', 0),
            'semantic_sufficiency': 'MODEL_JUDGMENT', 'absence_proven': False}


def need_id(issue, field, side):
    return digest([issue, field, side])


def evidence_basis(row):
    # Citation wording/extent within an already verified evidence unit is not
    # newly acquired source material. Evidence IDs bind the original spans/version.
    return digest(sorted({c['evidence'] for c in row.get('citations', []) + row.get('dependencies', [])}))


def acquisition_key(task):
    """Physical operation identity; display labels and issue names do not alter it."""
    loc = task.get('target_locator')
    exact = task['operation'] in ('read_node', 'follow_reference')
    target = {k: loc.get(k) for k in ('document_id', 'unit_id', 'source_id', 'reference_id')} if loc else None
    value = {'binding': task['binding_hash'], 'side': task['target_side'],
             'operation': task['operation'], 'target': target}
    if not exact:
        value['query'] = ' '.join(task['missing_target'].split())
        value['anchors'] = sorted({digest({k: a.get(k) for k in (
            'origin_side', 'generation_id', 'document_id', 'source_id', 'source_artifact_hash', 'spans_hash')})
            for a in task.get('anchor_refs', [])})
    return digest(value)


def history(board, issue=None, side=None):
    rows = []
    for task_id, record in board.get('tasks', {}).items():
        task = record['task']
        if issue is not None and task['issue_id'] != issue: continue
        if side is not None and task['target_side'] != side: continue
        target = task.get('target_locator')
        ids = record.get('new_evidence', [])
        feedback = [{'evidence_id': r['evidence_id'], 'disposition': r['disposition'],
                     'reason': r['reason'], 'fields': r.get('fields', [])}
                    for group in board.get('evidence_updates', [])
                    for r in ([group] if 'evidence_id' in group else group.get('updates', []))
                    if r['evidence_id'] in ids and group.get('issue_id') == task['issue_id']]
        rows.append({'task_id': task_id, 'issue_id': task['issue_id'],
            'fields': list(task['requested_fields']), 'side': task['target_side'],
            'question': task['missing_target'], 'operation': task.get('operation', 'UNKNOWN'),
            'status': record['status'], 'reason': record.get('planning_reason', ''),
            'target': {k: target.get(k) for k in ('document_id','unit_id','source_id','document_name','coordinate')} if target else None,
            'need_ids': list(record.get('need_ids', [])), 'new_evidence_ids': list(ids),
            'result_request_id': record.get('result_request_id'),
            'evidence_review': feedback, 'reused': bool(record.get('reused_acquisition'))})
    return rows


def child_context(board, side, binding, current=None):
    rows = history(board, side=side)
    needs = [{'need_id': n['need_id'], 'issue_id': n['issue_id'], 'field': n['field'],
              'side': n['side'], 'status': n['status'], 'missing': n.get('missing', ''),
              'continuation_reason': n.get('continuation_reason', '')}
             for n in board.get('research_needs', {}).values() if n['side'] == side]
    return {'schema_version': CONTRACT, 'side': side, 'binding_hash': binding,
            'current_task_id': current.get('task_id') if current else None,
            'needs': needs, 'attempts': rows[-24:], 'omitted_attempt_count': max(0, len(rows)-24),
            'used_followups': board['round']}


def validate_context(value, task, research):
    if value is None: return
    from jsonschema import validate, ValidationError
    def obj(**p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
    text={'type':'string'}; strings={'type':'array','items':text}
    nullable={'type':['string','null']}
    target=obj(**{k:nullable for k in ('document_id','unit_id','source_id','document_name','coordinate')})
    attempt=obj(task_id=text,issue_id=text,fields=strings,side={'const':task['source_category']},
        question=text,operation=text,status=text,reason=text,target={'anyOf':[target,{'type':'null'}]},
        need_ids=strings,new_evidence_ids=strings,result_request_id=nullable,
        evidence_review={'type':'array','items':obj(evidence_id=text,disposition=text,reason=text,fields=strings)},reused={'type':'boolean'})
    schema=obj(schema_version={'const':CONTRACT},side={'const':task['source_category']},binding_hash={'type':'string','minLength':1},
        current_task_id=nullable,needs={'type':'array','items':obj(need_id=text,issue_id=text,field=text,
            side={'const':task['source_category']},status={'enum':['OPEN','RESOLVED']},missing=text,continuation_reason=text)},
        attempts={'type':'array','maxItems':24,'items':attempt},omitted_attempt_count={'type':'integer','minimum':0},used_followups={'type':'integer','minimum':0})
    try:validate(value,schema)
    except ValidationError as exc:raise ContractError('invalid research continuity') from exc
    issues={i['id'] for i in task.get('issues', [])}
    for row in value['needs'] + value['attempts']:
        if row['issue_id'] not in issues: raise ContractError('research continuity issue changed')
    for row in value['needs']:
        if row['need_id'] != need_id(row['issue_id'],row['field'],row['side']):
            raise ContractError('research continuity need identity changed')
    if research and (value['binding_hash'] != research['binding_hash'] or value['current_task_id'] != research['task_id']):
        raise ContractError('research continuity task binding changed')


PRIORITY = {"CORE": 0, "DEPENDENCY": 1, "CONTEXT": 2}


def pending_tasks(board,prioritized):
    rows=[r for r in board['tasks'].values() if r['status'] in ('PENDING','RUNNING')]
    if not prioritized:return rows
    attempted={side:{r['acquisition_key'] for r in board['tasks'].values()
        if r['task'].get('target_side')==side and r.get('acquisition_key')}
        for side in ('internal','external')}
    return sorted(rows,key=lambda r:(0 if r['status']=='RUNNING' else 1,
        1 if PRIORITY.get(r.get('priority'),2)==2 else 0,
        0 if r['task'].get('target_locator') else 1,
        0 if r['task'].get('target_locator') else len(attempted.get(r['task'].get('target_side'),set())),
        PRIORITY.get(r.get('priority'),2),r.get('queue_order',0),r['task']['task_id']))


def register_task(board,task,proposal,general):
    locator=task['target_locator']
    target={k:locator[k] for k in ('document_id','unit_id','source_id')} if locator else None
    parts=[task['issue_id'],*task['requested_fields'],task['target_side'],task['operation'],target,
        sorted((a['document_id'],a['source_id'],a['spans_hash']) for a in task['anchor_refs']),task['binding_hash']]
    if general and task['operation'] not in ('read_node','follow_reference'):
        parts.append(' '.join(task['missing_target'].split()))
    stable=digest(parts);task['task_id']=stable
    record=board['tasks'].setdefault(stable,{'task':task,'status':'PENDING',
        **({'queue_order':len(board['tasks'])} if general else {})})
    if general:
        record.setdefault('planning_reason',proposal.get('reason',''))
        for field in task['requested_fields']:
            ident=need_id(task['issue_id'],field,task['target_side'])
            if ident not in record.setdefault('need_ids',[]):record['need_ids'].append(ident)
    if general and record['status']=='PENDING':
        record.update(priority=proposal['priority'],priority_reason=proposal['priority_reason'])
    return stable


def reconcile_need(board,issue,field,side,row,key,selected,compile_fallback):
    """Retain a model-declared gap; never infer that any law exists/applies."""
    ident=digest([issue['id'],field,side]);needs=board.setdefault('research_needs',{})
    need=needs.get(ident);missing=row['missing'].strip()
    related={i:r for i,r in board['tasks'].items() if r['task']['issue_id']==issue['id']
        and field in r['task']['requested_fields'] and r['task']['target_side']==side}
    if not missing:
        if row.get('need_resolution') == 'RESOLVED':
            if not need or not row['citations'] or not row['text'].strip():
                raise ValueError('need resolution requires an existing need, cited original and reason')
            event={'input_hash':key,'need_id':ident,'status':'RESOLVED',
                   'missing':need.get('missing',''),'reason':row['text'],'citations':deepcopy(row['citations'])}
            if not need['history'] or need['history'][-1]!=event:need['history'].append(event)
            need.update(status='RESOLVED',resolution=event)
            for task_id,record in related.items():
                if (task_id not in selected and ident in record.get('need_ids',[]) and record['status']=='PENDING'
                        and all(needs.get(i,{}).get('status')=='RESOLVED' for i in record['need_ids'])):
                    record.update(status='RESOLVED',resolved_by=key,reason='원문을 인용한 새 판단에서 해당 미확보 내용을 해소함')
        elif need and row.get('need_resolution') == 'OPEN':
            event={'input_hash':key,'need_id':ident,'status':'OPEN','reason':row['text']}
            if not need['history'] or need['history'][-1]!=event:need['history'].append(event)
            need['status']='OPEN';need.pop('resolution',None)
        # An omitted disposition or empty explanation is never a resolution.
        return
    if row.get('need_resolution') == 'RESOLVED':
        raise ValueError('resolved need still declares missing originals')
    if need is None:
        need=needs[ident]={'need_id':ident,'issue_id':issue['id'],'field':field,'side':side,
            'origin':'MODEL_DECLARED_MISSING','history':[],'task_ids':[]}
    event={'input_hash':key,'status':'OPEN','missing':row['missing']}
    if not need['history'] or need['history'][-1]!=event:need['history'].append(event)
    need.update(status='OPEN',missing=row['missing'],basis_hash=evidence_basis(row));need.pop('resolution',None)
    for task_id,record in related.items():
        if task_id not in need['task_ids']:need['task_ids'].append(task_id)
        if ident not in record.setdefault('need_ids',[]):record['need_ids'].append(ident)
    # Existing field/side plans survive an omitted or empty next_tasks list.
    active={i:r for i,r in related.items() if r['status'] in ('PENDING','RUNNING')}
    exhausted=[r for r in related.values() if r['status'] in TERMINAL
        and r.get('need_basis',{}).get(ident)==need['basis_hash']]
    if not active and exhausted:
        # Preserve the gap and receipts. Rewording a gap alone must not create
        # a fresh automatic search; explicit alternate tasks remain allowed.
        need['continuation_reason']='SAME_EVIDENCE_ATTEMPT_RECORDED'
        return
    if not active:
        # Missing is a preserved observation, not permission to invent a search.
        # Only explicit, validated next_tasks are executable investigation plans.
        need['continuation_reason']='NO_EXPLICIT_RESEARCH_TASK'
        return
    need['continuation_reason']='EXPLICIT_OR_NEW_SOURCE_PATH'
    for task_id,record in active.items():
        if task_id not in need['task_ids']:need['task_ids'].append(task_id)
        if ident not in record.setdefault('need_ids',[]):record['need_ids'].append(ident)


def research_need_view(board,issue=None,limit=None):
    out=[]
    for need in board.get('research_needs',{}).values():
        if issue is not None and need['issue_id']!=issue:continue
        tasks=[{'task_id':i,'status':board['tasks'][i]['status']} for i in need['task_ids'] if i in board['tasks']]
        remaining=need['status']!='RESOLVED'
        reason=('BUDGET_EXHAUSTED' if remaining and limit is not None and board['round']>=limit else
            'QUEUED' if any(t['status'] in ('PENDING','RUNNING') for t in tasks) else
            'ATTEMPT_RECORDED' if remaining and tasks else 'NO_TASK' if remaining else 'RESOLVED')
        out.append({**deepcopy(need),'tasks':tasks,'execution_state':reason})
    return out


def acquisition_status(latest,task,ok):
    if not ok:return 'FAILED'
    receipt=(latest.get('investigation_return',{}).get('research_tasks',{}) or {}).get(task['task_id'])
    if not receipt or receipt.get('task_hash')!=digest(task):return 'PARTIAL'
    # A readable child return may contain only old sources. Only the exact
    # requested operation's receipt can certify acquisition completion.
    return receipt['status'] if receipt.get('status') in ('COMPLETE','FAILED','PARTIAL') else 'PARTIAL'


class ResearchLedger:
    """The parent owns need, attempt, review and follow-up transitions here.

    Callers still own authorization, IO, transactions and model validation.
    An existing checkpoint is adopted without copying or resetting its budget.
    """

    def __init__(self, board):
        self.board = board

    @property
    def used_followups(self):
        return self.board['round']

    def pending(self, prioritized=True):
        return pending_tasks(self.board, prioritized)

    def available(self, limit):
        return self.used_followups < limit

    def register(self, task, proposal, general):
        return register_task(self.board, task, proposal, general)

    def reconcile(self, issue, field, side, row, key, selected, compile_fallback):
        return reconcile_need(self.board, issue, field, side, row, key, selected, compile_fallback)

    def need_basis(self, record):
        needs = self.board.get('research_needs', {})
        return {ident: needs[ident]['basis_hash'] for ident in record.get('need_ids', [])
                if ident in needs and 'basis_hash' in needs[ident]}

    def reuse(self, record):
        key = acquisition_key(record['task'])
        prior = next((r for r in self.board['tasks'].values() if r is not record
                      and r.get('acquisition_key') == key
                      and r['status'] in ('COMPLETE', 'PARTIAL', 'FAILED')
                      and r.get('result_request_id')), None)
        if prior is None:
            return False
        record.update(status=prior['status'], acquisition_key=key,
                      acquisition_task_id=prior.get('acquisition_task_id', prior['task']['task_id']),
                      result_request_id=prior['result_request_id'], new_evidence=[],
                      reused_acquisition=True, need_basis=self.need_basis(record))
        return True

    def block(self, record, reason):
        record.update(status='BLOCKED', reason=reason)

    def begin(self, record, previous):
        if record['status'] not in ('PENDING', 'RUNNING'):
            raise ContractError('research attempt is not pending or resumable')
        record.setdefault('previous_request_id', previous['request_id'])
        record.setdefault('prior_evidence_ids', sorted(previous.get('evidence_ids', [])))
        record.setdefault('need_basis', self.need_basis(record))
        record['status'] = 'RUNNING'
        return record['previous_request_id']

    def finish(self, record, latest, ok):
        receipt_hash = digest({'request_id': latest['request_id'], 'ok': ok,
                               'evidence_ids': sorted(latest.get('evidence_ids', [])),
                               'task_receipt': latest.get('investigation_return', {}).get('research_tasks', {}).get(record['task']['task_id'])})
        # Reusing the same persisted receipt cannot spend another follow-up.
        if record['status'] in TERMINAL:
            if (record.get('result_request_id') == latest['request_id']
                    and record.get('result_receipt_hash') == receipt_hash):
                return bool(record.get('new_evidence'))
            raise ContractError('completed research attempt has a different receipt')
        if record['status'] != 'RUNNING':
            raise ContractError('research receipt has no running attempt')
        task = record['task']
        key = acquisition_key(task)
        new_ids = sorted(set(latest.get('evidence_ids', [])) - set(record['prior_evidence_ids']))
        record.update(status=acquisition_status(latest, task, ok),
                      result_request_id=latest['request_id'], acquisition_key=key,
                      acquisition_task_id=task['task_id'], new_evidence=new_ids,
                      result_receipt_hash=receipt_hash)
        for sibling in self.board['tasks'].values():
            if sibling is record or sibling['status'] not in ('PENDING', 'RUNNING'):
                continue
            if acquisition_key(sibling['task']) == key:
                sibling.update(status=record['status'], acquisition_key=key,
                               acquisition_task_id=task['task_id'],
                               result_request_id=latest['request_id'], new_evidence=[],
                               reused_acquisition=True, need_basis=self.need_basis(sibling))
        self.board['round'] += 1
        return bool(new_ids)

    def new_review_sources(self, issue_id, visible):
        seen = set(self.board.get('reviewed_sources', {}).get(issue_id, []))
        return [e['evidence_id'] for e in visible if e['evidence_id'] not in seen]

    def review_input(self, issue_id, sources, attempts, leads):
        # Only external observations belong in admission identity. A review's
        # own judgment, evidence disposition or pending plan must not trigger it.
        outcomes = [{'task_id': ident, 'status': r['status'],
                     'result_request_id': r.get('result_request_id'),
                     'receipt_hash': r.get('result_receipt_hash'),
                     'reason': r.get('reason'), 'reused': r.get('reused_acquisition',False)}
                    for ident,r in sorted(self.board['tasks'].items())
                    if r['task']['issue_id']==issue_id and r['status'] in TERMINAL
                    and r['status']!='RESOLVED']
        # Export hashes still verify integrity at their consumers. A new export
        # with identical offered locations is not a new semantic observation.
        observed_leads={k:v for k,v in leads.items() if k!='catalogue_hash'}
        observed_leads['items']=[{k:v for k,v in row.items() if k!='return_ref'}
                                for row in leads.get('items',[])]
        return digest([issue_id, sorted(sources,key=lambda e:e['evidence_id']), attempts, observed_leads, outcomes])

    def review_allowed(self, *, incremental, new_ids, key=None, input_key=None):
        if incremental and not new_ids and input_key is None:
            return False
        return (key is None or key not in self.board['reviewed']) and (
            input_key is None or (input_key not in self.board.get('quarantined_inputs', [])
                                  and input_key not in self.board.get('reviewed_inputs', [])))

    def record_item(self, issue_id, item, key):
        row = self.board['rows'][issue_id + ':' + item['field']]
        row['revisions'].append({'input_hash': key, 'value': deepcopy(item)})
        row['current'] = item

    def commit_review(self, issue_id, visible, key, *, accepted, general, updates, input_key=None):
        if general and accepted:
            seen = set(self.board.get('reviewed_sources', {}).get(issue_id, []))
            self.board.setdefault('reviewed_sources', {})[issue_id] = sorted(
                seen | {e['evidence_id'] for e in visible})
            self.board.setdefault('evidence_updates', []).extend(
                {'issue_id': issue_id, 'input_hash': key, **r} for r in updates)
        self.board['reviewed'].append(key)
        if input_key is not None and input_key not in self.board.setdefault('reviewed_inputs',[]):
            self.board['reviewed_inputs'].append(input_key)

    def quarantine(self, input_key):
        self.board.setdefault('quarantined_inputs', []).append(input_key)

    def needs(self, issue=None, limit=None):
        return research_need_view(self.board, issue, limit)

    def child_context(self, side, binding, current=None):
        return child_context(self.board, side, binding, current)

    def audit(self, child_results, *, limit):
        """Join operational and semantic observations without inventing a judgment.

        Unread leads may be irrelevant. Keep their exact identifiers visible;
        neither clear them on CONFIRMED nor turn all of them into mandatory work.
        This projection is for the existing journal, not extra model input.
        """
        sides = {}
        for side in ('internal', 'external'):
            result = child_results.get(side, {})
            handoff = result.get('investigation_return', {})
            leads = handoff.get('leads', {})
            unacquired = [r['lead_id'] for r in leads.get('items', []) if r['acquisition'] != 'ACQUIRED']
            fields = [{'issue_id': r['issue_id'], 'field': r['field'],
                       'status': r['current'][side]['status'],
                       'has_missing': bool(r['current'][side]['missing'].strip()),
                       'citation_count': len(r['current'][side]['citations'])}
                      for r in self.board.get('rows', {}).values() if r['current']]
            sides[side] = {'request_id': result.get('request_id'), 'status': result.get('status'),
                           'source_progress': deepcopy(handoff.get('research_progress')),
                           'lead_catalogue_hash': leads.get('catalogue_hash'),
                           'unacquired_lead_ids': unacquired, 'fields': fields}
        return {'schema_version': 'research-state-audit-v1', 'used_followups': self.used_followups,
                'needs': self.needs(limit=limit), 'sides': sides,
                'semantic_quality_certified': False, 'absence_proven': False}


class OriginalProgress:
    """One owner for original/discovery progress and unchanged-turn accounting."""

    def __init__(self, state):
        self.state = state

    def observe(self, discovery_facts):
        known = set(self.state.get('request_progress', []))
        self.state['discovery_changed'] = bool(discovery_facts - known)
        self.state['request_progress'] = sorted(known | discovery_facts)
        return original_progress(self.state)

    def advance(self, changed):
        self.state['no_progress'] = 0 if changed else self.state.get('no_progress', 0) + 1
        return {'changed': changed, 'unchanged_turns': self.state['no_progress']}

    def view(self):
        return progress_view(self.state)

    def reset_for_new_request(self):
        for key in ('request_progress', 'original_progress', 'discovery_changed'):
            self.state.pop(key, None)


class NativeResearchTasks:
    """Child acquisition receipts; COMPLETE means execution, never legal sufficiency."""

    def __init__(self, state):
        self.tasks = state.setdefault('comparison_research', {})

    def begin(self, task):
        key = task['task_id']
        seed = self.tasks.get(key)
        if seed and seed['task_hash'] != digest(task):
            raise ContractError('research task identity reused')
        if seed is None:
            seed = {'task_hash': digest(task), 'status': 'STARTED',
                    'completed': [], 'actions': {}, 'lookup': None}
            self.tasks[key] = seed
        return seed

    @staticmethod
    def terminal(seed):
        return seed['status'] in ('COMPLETE', 'FAILED', 'PARTIAL')

    @staticmethod
    def finish(seed, status):
        if status not in ('COMPLETE', 'FAILED', 'PARTIAL'):
            raise ContractError('invalid research acquisition terminal')
        seed['status'] = status
