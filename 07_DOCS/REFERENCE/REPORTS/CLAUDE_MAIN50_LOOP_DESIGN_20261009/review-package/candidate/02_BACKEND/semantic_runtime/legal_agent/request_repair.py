"""Request-local lifecycle and evidence-target contracts; never legal entailment.

Enabled only by the release-bound completion v5 policy. All identities are
computed from the selected immutable source/authorization binding, not model IDs.
"""
from copy import deepcopy
import re
import unicodedata
from ..contracts import digest
from .errors import ContractError, ProposalError

VERSION = 'investigation-completion-v5'


def enabled(profile):
    return profile.get('candidate_navigation', {}).get('completion_policy_version') == VERSION


def text_key(value):
    return re.sub(r'[\s\W_]+', '', unicodedata.normalize('NFKC', value or '')).casefold()


def new_epoch(state, *, reason):
    """Only an explicit new decision boundary retires a repair. Budget survives."""
    state = deepcopy(state)
    previous = state.pop('decision_retry', None)
    if previous:
        state.setdefault('decision_retry_history', []).append({
            **previous, 'closed_reason': reason, 'epoch': state.get('investigation_epoch', 0)})
    if state.get('accepted'):
        raise ContractError('cannot enter a new investigation with an uncommitted accepted action')
    state['investigation_epoch'] = state.get('investigation_epoch', 0) + 1
    state.pop('coverage_warning', None)
    # no_progress, read_state, request_progress, counters and deadline stay intact.
    return state


def decision_identity(state, data, phase):
    return {'epoch': state.get('investigation_epoch', 0), 'phase': phase,
            'presentation_id': data['presentation_id'], 'input_hash': digest(data)}


def deduplicate_decision(value):
    """Remove byte-equivalent semantic items only; opposing choices stay invalid."""
    out = deepcopy(value); changes = []
    if not isinstance(out, dict): return out, changes
    for key in ('law_decisions', 'branch_decisions', 'gap_resolutions'):
        rows = out.get(key)
        if not isinstance(rows, list): continue
        seen = set(); kept = []
        for row in rows:
            fingerprint = digest(row)
            if fingerprint in seen: changes.append({'field': key, 'duplicate_hash': fingerprint})
            else: seen.add(fingerprint); kept.append(row)
        out[key] = kept
    return out, changes


def bind_gap(gap, session):
    """Resolve a stated target using the existing scope-aware structure reader."""
    from . import structure_query as sq, unit_reading as ur, evidence_inventory as inv
    from lawrag.core.legal_coordinate import find_coordinates
    target_text = gap.get('missing_target', '').strip()
    binding = {'generation': session.context.query['generation_id'],
               'scope': sorted(session.scope),
               'index': session.matcher.unit_fulltext.manifest['index_sha256']}
    target = {'status': 'UNLOCATED', 'text': target_text, 'pairs': [], 'source_ids': [],
              'expected': [], 'absence_proven': False}
    if gap['kind'] != 'MISSING_FACT' and target_text:
        resolved = sq.resolve(target_text, session.matcher, session.scope)
        target['lookup'] = deepcopy(resolved)
        if resolved['status'] == 'MATCH':
            expected = []
            for pair in resolved['pairs']:
                blocks = ur.blocks(session, pair['document_id'], pair['unit_id'], 'subtree')
                if not blocks:
                    expected = []; break
                expected.extend({'document_id': pair['document_id'], **span}
                                for span in inv.expected(session, pair['document_id'], blocks))
            if expected:
                target.update(status='EXACT', pairs=resolved['pairs'],
                              source_ids=resolved['source_ids'], expected=expected)
        else:
            code = resolved.get('failure', {}).get('code')
            docs = {d for hit in sq.document_hits(target_text, session.matcher)
                    for d in hit['values'] if d in session.scope}
            coordinates = find_coordinates(target_text)
            indexed_complete=False
            if len(docs)==1 and len(coordinates)==1:
                did=next(iter(docs))
                # A missing index entry is not source absence if the stored tree
                # lacks coordinate bindings. Partial/legacy trees stay unknown.
                nodes=[(key,u) for key,u in session.matcher.units.items() if key[0]==did
                       and (u.get('family')=='kr_article' or bool(coordinates[0].coordinate.chain))]
                indexed_complete=bool(nodes) and all(
                    u.get('coordinate_scope') is not None
                    and session.matcher.stored_coordinates.get(key) is not None
                    and u.get('coordinate_binding',{}).get('mode')!='unresolved' for key,u in nodes)
            if code == 'MISSING_COORDINATE' and len(docs) == 1 and len(coordinates) == 1 and indexed_complete:
                target.update(status='ABSENT_COORDINATE', absence_proven=True,
                    pairs=[{'document_id': next(iter(docs)),
                            'coordinate': coordinates[0].coordinate.canonical_surface()}])
            elif code in ('AMBIGUOUS_DOCUMENT', 'AMBIGUOUS_COORDINATE', 'NON_UNIQUE_ORIGINAL'):
                target['status'] = 'AMBIGUOUS'
    location = sorted((p['document_id'], str(p.get('unit_id', '')), p.get('coordinate', ''))
                      for p in target['pairs'])
    family = 'FACT' if gap['kind'] == 'MISSING_FACT' else 'SOURCE'
    identity = location if location else ['unlocated', text_key(target_text or gap.get('reason'))]
    key = 'K' + digest([binding, gap['issue_id'], family, identity])[:20]
    return {**deepcopy(gap), 'identity_key': key, 'target_binding': target,
            'target_binding_hash': digest(binding)}


def bind_gaps(value, session, rounds):
    out = deepcopy(value)
    known = {g['gap_key']: g for r in rounds for g in r['gaps']}
    for n, raw in enumerate(out['gaps']):
        previous = raw.pop('previous_gap_key', None)
        gap = bind_gap(raw, session)
        if previous is not None:
            prior = known.get(previous)
            if prior is None or prior['issue_id'] != gap['issue_id']:
                raise ProposalError('unknown or different-issue previous gap')
            old_target = prior.get('target_binding', {})
            if gap['target_binding']['status'] == 'UNLOCATED' and not raw.get('missing_target'):
                gap.update(identity_key=previous, target_binding=deepcopy(old_target))
                gap['missing_target'] = prior.get('missing_target', '')
            elif gap['identity_key'] != previous:
                raise ProposalError('previous gap refers to a different document, scope or version')
        out['gaps'][n] = gap
    return out


def spans_by_document(state, basis_refs):
    result = {}
    for ref in basis_refs:
        basis = state.get('basis_history', {}).get(ref)
        if not basis or not basis.get('accepted'): continue
        group = state['groups'].get(basis.get('branch_id'))
        if not group: continue
        did = group['hit']['document_id']
        result.setdefault(did, []).extend(basis.get('spans', []))
    return result


def covers_target(target, state, refs):
    from .evidence_inventory import covers
    if target.get('status') != 'EXACT' or not target.get('expected'): return False
    actual = spans_by_document(state, refs)
    docs = {s['document_id'] for s in target['expected']}
    return all(covers([s for s in target['expected'] if s['document_id'] == did], actual.get(did, []))
               for did in docs)


def target_evidence_signature(gap, state):
    """An unrelated adopted article cannot reopen this exact missing target."""
    from .evidence_inventory import intervals
    target = gap.get('target_binding', {})
    dids = {p['document_id'] for p in target.get('pairs', [])}
    wanted = {(p['document_id'], str(p['block_id'])) for p in target.get('expected', [])}
    refs = [ref for group in state.get('groups', {}).values()
            for issue, d in group.get('issue_decisions', {}).items()
            if issue == gap['issue_id'] and d['status'] in ('ADOPT', 'KEEP')
            for ref in d.get('basis_refs', [])]
    actual = spans_by_document(state, refs)
    return digest({did: intervals([p for p in spans if not wanted or (did, str(p['block_id'])) in wanted])
                   for did, spans in actual.items() if not dids or did in dids})


def may_reopen(gap, state):
    previous = [r for r in state.get('gap_rounds', [])
                if any(g.get('gap_key') == gap['identity_key'] for g in r['gaps'])]
    if not previous: return True
    latest = previous[-1]
    return latest.get('target_evidence_at_close', {}).get(gap['identity_key']) != target_evidence_signature(gap, state)


def progress_facts(state):
    """Content-based progress, independent of presentation/action/branch IDs."""
    from .evidence_inventory import intervals
    facts = set()
    for row in state.get('laws', {}).values(): facts.add('law:' + row['document_id'])
    for group in state.get('groups', {}).values():
        hit = group['hit']; facts.add('candidate:' + digest([hit['document_id'], hit['source_id']]))
    for item in state.get('structure_page', {}).get('items', []):
        facts.add('location:' + digest([item.get('document_id'), item.get('unit_id')]))
    refs = list(state.get('basis_history', {}))
    for did, spans in spans_by_document(state, refs).items():
        for bid, ranges in intervals(spans).items():
            for lo, hi in ranges: facts.add('delivered:' + digest([did, bid, lo, hi]))
    for group in state.get('groups', {}).values():
        for issue, decision in group.get('issue_decisions', {}).items():
            if decision['status'] not in ('ADOPT', 'KEEP', 'EXCLUDE', 'DEFER'): continue
            status = 'ADOPT' if decision['status'] == 'KEEP' else decision['status']
            spans = spans_by_document(state, decision.get('basis_refs', []))
            facts.add('decision:' + digest([issue, group['hit']['source_id'], status,
                {did: intervals(rows) for did, rows in spans.items()}]))
    for round_ in state.get('gap_rounds', []):
        for resolution in round_.get('resolutions', []):
            if resolution['status'] == 'RESOLVED':
                facts.add('resolved:' + resolution['gap_key'])
    return facts


def record_progress(state):
    current = progress_facts(state)
    known = set(state.get('request_progress', []))
    changed = bool(current - known)
    state['request_progress'] = sorted(known | current)
    return changed


def seed_gap_receipts(round_):
    """The deterministic exact-coordinate lookup is an actual scoped lookup."""
    for gap in round_['gaps']:
        target = gap.get('target_binding', {})
        if not target.get('lookup'): continue
        rid = 'lookup:' + digest([gap['gap_key'], target['lookup']])[:24]
        round_['action_receipts'].append({'id': rid, 'gap_ids': [gap['gap_id']],
            'action': 'TARGET_STRUCTURE_LOOKUP', 'targets': target['pairs'],
            'queries': [target['text']], 'status': 'COMPLETED',
            'outcome': {'target_key': gap['gap_key'], 'status': target['status'],
                        'absence_proven': target['absence_proven']}})


def validate_resolutions(investigation, value, data):
    gaps = {g['gap_id']: g for g in data.get('assessment_gaps', [])}
    rows = value.get('gap_resolutions') or []
    if len(rows) != len(gaps) or {r['gap_id'] for r in rows} != set(gaps):
        raise ProposalError('FINISH must address every open gap exactly once')
    current = investigation.current_gap_round() or {}
    receipts = {r['id']: r for r in current.get('action_receipts', []) if r['status'] == 'COMPLETED'}
    state = investigation.p
    for row in rows:
        gap = gaps[row['gap_id']]; status = row['status']
        if not row['reason'].strip(): raise ProposalError('gap resolution needs a reason')
        if status in ('NOT_NEEDED', 'UNRESOLVED'):
            if row.get('basis_refs') or row.get('action_refs'):
                raise ProposalError(status + ' must not claim verified resolution evidence')
            continue
        if status == 'NOT_AVAILABLE':
            refs = set(row.get('action_refs', []))
            eligible = {k for k, r in receipts.items() if row['gap_id'] in r['gap_ids']
                        and (r.get('outcome') or {}).get('target_key') == gap['gap_key']
                        and (r.get('outcome') or {}).get('absence_proven') is True}
            if not refs and len(eligible) == 1: refs = eligible; row['action_refs'] = sorted(refs)
            if row.get('basis_refs') or not refs or not refs <= eligible:
                raise ProposalError('NOT_AVAILABLE requires completed exact-target absence; unrelated reads, empty fulltext or partial lookup are UNRESOLVED')
            continue
        if status != 'RESOLVED': raise ProposalError('unknown gap resolution')
        adopted = {ref for group in state['groups'].values() if group['status'] == 'ACTIVE'
                   for issue, d in group.get('issue_decisions', {}).items()
                   if issue == gap['issue_id'] and d['status'] in ('ADOPT', 'KEEP')
                   for ref in d.get('basis_refs', [])}
        adopted.update(ref for d in value.get('branch_decisions', [])
                       if gap['issue_id'] in d['issue_refs'] and d['status'] in ('ADOPT', 'KEEP')
                       for ref in d['basis_refs'])
        refs = set(row.get('basis_refs', []))
        # The current presentation is validated against the immutable original by
        # the existing page/decision gate; expose it to the coverage check too.
        checked = deepcopy(state)
        from .evidence_inventory import acknowledge
        for page in data.get('sources', []): acknowledge(investigation.s, checked, page, data['presentation_id'])
        if not refs or not refs <= adopted or not covers_target(gap['target_binding'], checked, refs):
            raise ProposalError('RESOLVED requires adopted original spans covering this exact missing target; another article is insufficient')
        actions = set(row.get('action_refs', []))
        if actions and any(a not in receipts or row['gap_id'] not in receipts[a]['gap_ids'] for a in actions):
            raise ProposalError('resolution action receipt is not completed for this gap')


def add_target_actions(investigation, actions):
    from . import law_candidates as lc
    result = []
    for gap in investigation.p.get('assessment_gaps', []):
        target = gap.get('target_binding', {})
        offers = []
        for pair in target.get('pairs', []) if target.get('status') == 'EXACT' else []:
            sid = [s for s in target['source_ids']
                   if investigation.s.tools.sources[s]['document_id'] == pair['document_id']
                   and s in investigation.s.matcher._unit_sources(pair['document_id'], pair['unit_id'])]
            if len(sid) != 1: continue
            identity = {'document_id': pair['document_id'], 'source_id': sid[0], 'unit_id': pair['unit_id']}
            ident = lc.token(investigation.s, 'T', ['READ_ARTICLES', identity])
            actions[ident] = {'id': ident, 'action': 'READ_ARTICLES', 'identity': identity,
                             'label': pair['document_name'] + ' ' + pair['coordinate'] + ' 부족 원문 읽기'}
            offers.append(ident)
        result.append({'gap_id': gap['gap_id'], 'missing_target': gap.get('missing_target'),
                       'resolution': target.get('status'), 'read_actions': offers,
                       'absence_lookup_receipt': next((r['id'] for r in investigation.current_gap_round().get('action_receipts', [])
                           if gap['gap_id'] in r['gap_ids'] and (r.get('outcome') or {}).get('absence_proven')), None)})
    return result


def annotate_reused_reads(investigation, data, actions):
    """Do not hide cached bodies: only suppress an already-visible subset read."""
    from . import evidence_inventory as inv, unit_reading as ur
    current = {}
    for page in data.get('sources', []): current.setdefault(page['document_id'], []).extend(page['spans'])
    reused = []
    for ident, action in list(actions.items()):
        if action['action'] not in ('READ_SCOPE', 'READ_PARENT', 'READ_ARTICLES'): continue
        identity = action['identity']; gid = identity.get('branch_id')
        if identity.get('continuation'): continue
        if gid:
            group = investigation.p['groups'][gid]; did = group['hit']['document_id']
            offer = group['offer'] if action['action'] == 'READ_PARENT' else next(
                (o for o in ur.offers(investigation.s, group['hit']) if o['id'] == identity.get('scope')), None)
            if offer is None: continue
            block_ids = offer['block_ids']
        else:
            did = identity.get('document_id'); uid = identity.get('unit_id')
            if not did or uid is None: continue
            block_ids = ur.blocks(investigation.s, did, uid, 'subtree')
        if not block_ids or did not in current: continue
        wanted = inv.expected(investigation.s, did, block_ids)
        if not inv.covers(wanted, current[did]): continue
        refs = [p['id'] for p in data['sources'] if p['document_id'] == did]
        reused.append({'action_id': ident, 'basis_refs': refs, 'reason': '현재 제시한 원문이 선택 범위를 이미 포함합니다',
                       'new_evidence': False, 'next': 'DECIDE or FINISH using offered branch decisions'})
        # Preserve navigation facts but exclude the redundant read from the
        # executable menu, so selecting it cannot spend a model turn repeatedly.
        del actions[ident]
    if reused:
        data['already_presented_reads'] = reused
        forbidden = {x['action_id'] for x in reused}
        def clean(value):
            if isinstance(value, dict):
                for key, val in list(value.items()):
                    if isinstance(val, str) and val in forbidden and key.endswith('action'):value[key] = None
                    elif key == 'read_actions' and isinstance(val, list):value[key] = [x for x in val if x not in forbidden]
                    elif isinstance(val, (dict, list)):clean(val)
            elif isinstance(value, list):
                for val in value:clean(val)
        clean(data)
    return reused
