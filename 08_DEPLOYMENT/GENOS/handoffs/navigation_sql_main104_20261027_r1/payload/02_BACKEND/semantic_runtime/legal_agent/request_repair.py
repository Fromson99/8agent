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
    return profile.get('candidate_navigation', {}).get('completion_policy_version') in (VERSION, 'investigation-completion-v6', 'investigation-completion-v7','investigation-completion-v8')


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


_REVIEW_SPAN_KEYS = ('source_id', 'document_id', 'block_id', 'start_cp', 'end_cp', 'text_hash')


def _review_span(receipt):
    if any(k not in receipt for k in (*_REVIEW_SPAN_KEYS, 'text')):
        raise ContractError('assessment review lacks a verified source span')
    if receipt['text_hash'] != digest(receipt['text']):
        raise ContractError('assessment review source text hash mismatch')
    return {k: receipt[k] for k in _REVIEW_SPAN_KEYS}


def retain_assessment_review(state, assessment, request):
    """Persist source-bound prior opinions, never a new accepted answer.

    Called after native claim verification and before bounded SELECT reentry.
    Original text stays in the source store/journal; only span identities are
    duplicated. Empty later assessments cannot erase this earlier audit trail.
    """
    claims = []
    for claim in assessment.get('claims', []):
        receipts = claim.get('span_receipts')
        if not receipts:
            # Legacy non-span assessments have no safe projection contract.
            continue
        claims.append({'claim_id': claim['claim_id'], 'issue_refs': list(claim['issue_refs']),
            'text': claim['text'], 'spans': [_review_span(r) for r in receipts]})
    if not claims:
        return
    payload = {'request_hash': digest(request), 'claims': claims,
        'issue_assessments': deepcopy(assessment.get('issue_assessments', []))}
    row = {'payload': payload, 'sha256': digest(payload)}
    reviews = state.setdefault('assessment_reviews', [])
    if not any(r['sha256'] == row['sha256'] for r in reviews):
        reviews.append(row)


def assessment_review_context(state, request, options, issues):
    """Expose opinions only when every cited span is present in this model input.

    Rebinding depends on stable source/offset/text identity, not model IDs or
    semantic similarity. An old opinion cannot supply a missing original.
    """
    reviews = state.get('assessment_reviews', [])
    available = {digest(_review_span(o)): o['id'] for o in options} if reviews else {}
    issue_ids = {i['id'] for i in issues}
    rows = []; withheld = 0
    for number, review in enumerate(reviews, 1):
        payload = review['payload']
        if digest(payload) != review['sha256']:
            raise ContractError('assessment review state hash mismatch')
        if payload['request_hash'] != digest(request):
            continue
        for claim in payload['claims']:
            keys = [digest(s) for s in claim['spans']]
            if (not set(claim['issue_refs']) <= issue_ids or not keys
                    or any(k not in available for k in keys)):
                withheld += 1
                continue
            rows.append({'prior_claim': f"{number}:{claim['claim_id']}",
                'issue_refs': claim['issue_refs'], 'text': claim['text'],
                'evidence_refs': list(dict.fromkeys(available[k] for k in keys))})
    return {'status': 'PRIOR_MODEL_OPINIONS_FOR_REVIEW', 'claims': rows,
        'unavailable_claims': withheld,
        'meaning': '앞선 모델 의견이다. 현재 원문과 질문으로 유지·수정·제외를 다시 판단한다. 이전 의견 자체는 법률 근거나 정답이 아니다.'}


def decision_identity(state, data, phase):
    return {'epoch': state.get('investigation_epoch', 0), 'phase': phase,
            'presentation_id': data['presentation_id'], 'input_hash': digest(data)}


def navigation_assessment_context(state, request, pages, issues):
    """Rebind prior opinions to exact spans in the current navigation pages.

    A page can be larger than an assessment line. Coordinates and the hash of
    that exact substring must agree; matching titles or text elsewhere cannot
    authorize an opinion. No original text or new semantic decision is stored.
    """
    options = []
    seen = set()
    for review in state.get('assessment_reviews', []):
        payload = review['payload']
        if digest(payload) != review['sha256']:
            raise ContractError('assessment review state hash mismatch')
        if payload['request_hash'] != digest(request):
            continue
        for claim in payload['claims']:
            for wanted in claim['spans']:
                for page in pages:
                    if any(page.get(k) != wanted[k] for k in ('source_id', 'document_id')):
                        continue
                    for span in page.get('spans', []):
                        if str(span['block_id']) != str(wanted['block_id']):
                            continue
                        lo, hi = wanted['start_cp'], wanted['end_cp']
                        if not span['start_cp'] <= lo < hi <= span['end_cp']:
                            continue
                        text = span['text'][lo-span['start_cp']:hi-span['start_cp']]
                        if (len(text) != hi-lo or text not in page.get('text', '')
                                or digest(text) != wanted['text_hash']):
                            continue
                        key = digest([wanted, page['id']])
                        if key not in seen:
                            seen.add(key)
                            options.append({**wanted, 'id': page['id'], 'text': text})
    return assessment_review_context(state, request, options, issues)


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
              'expected': [], 'absence_proven': False,
              'document_candidates': sorted({d for h in sq.document_hits(target_text, session.matcher)
                                             for d in h['values'] if d in session.scope})}
    if gap['kind'] != 'MISSING_FACT' and target_text:
        resolved = sq.resolve(target_text, session.matcher, session.scope)
        target['lookup'] = deepcopy(resolved)
        if resolved['status'] == 'MATCH':
            expected = []
            for pair in resolved['pairs']:
                if pair.get('source_partition') is not None:
                    from . import tool_availability
                    plan, unavailable = tool_availability.article_plan(session, sq.read_identity(pair))
                    blocks = [] if unavailable else plan[1]['block_ids']
                else:
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
            if (len(docs)==1 and len(coordinates)==1
                    and coordinates[0].coordinate.unit=='조'
                    and '부칙' not in target_text):
                did=next(iter(docs))
                # A missing index entry is not source absence if the stored tree
                # lacks coordinate bindings. Partial/legacy trees stay unknown.
                nodes=[(key,u) for key,u in (session.matcher.units.for_document(did) if hasattr(session.matcher.units,'for_document') else session.matcher.units.items()) if key[0]==did
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
            if prior.get('target_binding_hash') != gap['target_binding_hash']:
                raise ContractError('previous gap source authorization or generation changed')
            if gap['target_binding']['status'] == 'UNLOCATED' and not raw.get('missing_target'):
                gap.update(identity_key=previous, target_binding=deepcopy(old_target))
                gap['missing_target'] = prior.get('missing_target', '')
            elif gap['identity_key'] != previous:
                # This is a continuation of the same issue, not an assertion
                # that two source coordinates are identical. Keep the newly
                # resolved target, but retain the investigation allowance.
                # Raw proposals and prior targets remain in the decision journal.
                gap['identity_key'] = previous
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
    facts = {'definition:'+ident for ident in state.get('definition_visible_ids',[])}
    for row in state.get('laws', {}).values(): facts.add('law:' + row['document_id'])
    for did, page in state.get('document_term_exploration', {}).get('documents', {}).items():
        if page.get('status') == 'READY':
            facts.add('term-page:' + digest([did, page['binding'], page.get('cursor')]))
            facts.update('term-candidate:' + digest([did, r['source_id']]) for r in page.get('items', []))
    for group in state.get('groups', {}).values():
        hit = group['hit']; facts.add('candidate:' + digest([hit['document_id'], hit['source_id']]))
    for item in state.get('structure_page', {}).get('items', []):
        facts.add('location:' + digest([item.get('document_id'), item.get('unit_id')]))
    refs = list(state.get('basis_history', {}))
    acquired = spans_by_document(state, refs)
    # Native read receipts are content progress before the next model delivery.
    # Keep presentation/adoption flags unchanged; previews have no receipts here.
    for record in state.get('selected', {}).values():
        did = record.get('document_id')
        if did:
            acquired.setdefault(did, []).extend(p for e in record.get('evidence', [])
                                                for p in e.get('spans', []))
    for did, spans in acquired.items():
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
    from ..research_state import OriginalProgress
    return OriginalProgress(state).observe(progress_facts(state))


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
    ids=[r['gap_id'] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)-set(gaps):
        raise ProposalError('gap resolutions must name unique known gaps')
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
        refs = set(row.get('basis_refs', []))
        # The current presentation is validated against the immutable original by
        # the existing page/decision gate; expose it to the coverage check too.
        checked = deepcopy(state)
        from .evidence_inventory import acknowledge
        for page in data.get('sources', []): acknowledge(investigation.s, checked, page, data['presentation_id'])
        delivered={ref for ref,page in checked.get('basis_history',{}).items() if page.get('accepted') and page.get('spans')}
        if not refs or not refs <= delivered:
            raise ProposalError('RESOLVED requires actual delivered original references; target sufficiency is the model judgment')
        actions = set(row.get('action_refs', []))
        if actions and any(a not in receipts or (receipts[a]['gap_ids'] and row['gap_id'] not in receipts[a]['gap_ids']) for a in actions):
            raise ProposalError('resolution action receipt is not completed for this gap')


UNATTEMPTED_GAP = 'UNATTEMPTED_ASSESSMENT_GAP'


def gap_review_capacity(investigation):
    """One correction plus subsequent assessment, within the existing reserve."""
    budget = investigation.s.repo.budget()
    if budget['model_limit'] - budget['finalization_reserve'] - budget['model_reserved'] < 2:
        return 'INVESTIGATION_BUDGET'
    if investigation.left() <= max(1, investigation.s.profile['selection_time_reserve_seconds']):
        return 'FINALIZATION_TIME_RESERVE'
    return None


def is_unattempted_gap(error):
    from .output_contract import diagnostics
    return any(row['code'] == UNATTEMPTED_GAP for row in diagnostics(error)['issues'])


def validate_unattempted_gap_finish(investigation, value, data, actions):
    """Check an omitted executable investigation, never legal sufficiency.

    Read receipts and delivered spans count without adoption. A failed attempt
    also counts as an attempt, but never as resolution or proof of absence.
    This validator is pure; the existing decision owner records and repairs it.
    """
    if not investigation.modern or value['next_action'] != 'FINISH': return
    current = investigation.current_gap_round()
    if not current: return
    from . import evidence_inventory as inventory, tool_availability as available
    from . import output_contract as output
    presented = spans_by_document(investigation.p, list(investigation.p.get('basis_history', {})))
    for page in data.get('sources', []):
        presented.setdefault(page['document_id'], []).extend(page.get('spans', []))
    for record in investigation.p.get('selected', {}).values():
        if record.get('document_id'):
            presented.setdefault(record['document_id'], []).extend(
                span for evidence in record.get('evidence', []) for span in evidence.get('spans', []))
    resolutions = {r['gap_id']: r['status'] for r in value.get('gap_resolutions', [])}
    menus = {r['gap_id']: r for r in data.get('gap_targets', [])}
    missing = []
    for gap in data.get('assessment_gaps', []):
        gid = gap['gap_id']
        if not gap.get('material') or gap['kind'] == 'MISSING_FACT': continue
        # The preceding resolution validator owns receipts; NOT_NEEDED is an
        # explicit model reassessment whose reason is preserved, not host proof.
        if resolutions.get(gid) in ('NOT_NEEDED', 'RESOLVED', 'NOT_AVAILABLE'): continue
        target = gap.get('target_binding', {})
        expected = target.get('expected', [])
        if expected and all(inventory.covers([s for s in expected if s['document_id'] == did],
                presented.get(did, [])) for did in {s['document_id'] for s in expected}): continue
        menu = menus.get(gid, {})
        handles = [h for h in menu.get('read_actions', []) + menu.get('navigation_actions', []) if h in actions]
        # Do not turn a filtered/forbidden/over-budget tool into a repair demand.
        handles = [h for h in handles if available.navigation_reason(investigation, actions[h], data) is None]
        if not handles: continue
        identities = [actions[h]['identity'] for h in handles]
        documents = {i['document_id'] for i in identities if i.get('document_id')}
        sources = set(target.get('source_ids', []))
        attempted = False
        for receipt in current.get('action_receipts', []):
            if receipt['action'] == 'TARGET_STRUCTURE_LOOKUP':
                outcome = receipt.get('outcome') or {}
                if (receipt['status'] == 'COMPLETED' and gid in receipt.get('gap_ids', [])
                        and outcome.get('target_key') == gap['gap_key'] and outcome.get('absence_proven') is True):
                    attempted = True
                continue
            if receipt['status'] not in ('COMPLETED', 'FAILED'): continue
            for chosen in receipt.get('targets', []):
                ident = chosen.get('identity', {})
                if (chosen.get('id') in handles or
                        (sources and ident.get('source_id') in sources) or
                        (receipt['action'] in ('SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'SEARCH_BODY')
                         and ident.get('document_id') in documents)):
                    attempted = True
            if receipt['action'] == 'RESEARCH' and gid in receipt.get('gap_ids', []): attempted = True
        if attempted: continue
        missing.append({'gap_id': gid, 'missing_target': gap.get('missing_target'), 'available_actions': handles})
    if missing:
        raise output.OutputContractError(
            'FINISH leaves an executable assessment target uninvestigated. Choose an offered investigation '
            'action, or explicitly reassess that gap as NOT_NEEDED with a reason. Preserve unresolved gaps; '
            'do not invent evidence or mark an unread target resolved.',
            [output.issue(UNATTEMPTED_GAP, '/next_action', related=['/gap_resolutions'],
                expected={'unattempted_gaps': missing, 'max_corrections': 1, 'same_evidence_scope': True})],
            category='DECISION_CONFLICT')


def add_target_actions(investigation, actions):
    from . import law_candidates as lc
    result = []
    for gap in investigation.p.get('assessment_gaps', []):
        target = gap.get('target_binding', {})
        offers = []
        documents = set(target.get('document_candidates', []))
        documents.update(pair['document_id'] for pair in target.get('pairs', []))
        # Gap resolution can locate a document outside the paged catalogue.
        # Register its scoped identity before offering an executable read.
        investigation.add_laws([{'document_id': did, 'article_count': None, 'unit_count': None}
                                for did in sorted(documents)
                                if lc.token(investigation.s, 'L', did) not in investigation.p['laws']])
        if not documents <= set(investigation.s.scope):
            raise ContractError('gap target escaped request scope')
        for pair in target.get('pairs', []) if target.get('status') == 'EXACT' else []:
            sid = [s for s in target['source_ids']
                   if investigation.s.tools.sources[s]['document_id'] == pair['document_id']
                   and (pair.get('source_id') is None or pair['source_id']==s)
                   and (s in investigation.s.matcher._unit_sources(pair['document_id'], pair['unit_id'])
                        if pair['unit_id'] is not None else pair.get('source_partition')=={'scope_unit_id':None}
                        and investigation.s.tools.sources[s]['unit_id'] is None)]
            if len(sid) != 1: continue
            identity = {'document_id': pair['document_id'], 'source_id': sid[0], 'unit_id': pair['unit_id']}
            if pair.get('source_partition') is not None:
                identity['source_partition']=deepcopy(pair['source_partition'])
            ident = lc.token(investigation.s, 'T', ['READ_ARTICLES', identity])
            actions[ident] = {'id': ident, 'action': 'READ_ARTICLES', 'identity': identity,
                             'label': pair['document_name'] + ' ' + pair['coordinate'] + ' 부족 원문 읽기'}
            offers.append(ident)
        navigation = []
        # A known document can still have an unresolved coordinate or title.
        # Offer scoped tools without changing the model's requested target.
        for did in target.get('document_candidates', []):
            for kind in ('SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'SEARCH_BODY'):
                identity = {'document_id': did}
                if kind == 'SEARCH_BODY': identity['unit_id'] = None
                ident = lc.token(investigation.s, 'T', [kind, identity])
                actions.setdefault(ident, {'id': ident, 'action': kind, 'identity': identity,
                    'label': investigation.s.matcher.documents[did] + ' 부족 대상 확인: ' + kind})
                navigation.append(ident)
        result.append({'navigation_actions': navigation, 'gap_id': gap['gap_id'], 'missing_target': gap.get('missing_target'),
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
        if action['action'] not in ('READ_SCOPE', 'READ_PARENT', 'READ_ARTICLES', 'VIEW_SAVED_SOURCE'): continue
        identity = action['identity']; gid = identity.get('branch_id')
        if identity.get('continuation'): continue
        if gid:
            group = investigation.p['groups'][gid]; did = group['hit']['document_id']
            offer = group['offer'] if action['action'] in ('READ_PARENT', 'VIEW_SAVED_SOURCE') else next(
                (o for o in ur.offers(investigation.s, group['hit']) if o['id'] == identity.get('scope')), None)
            if offer is None: continue
            if action['action']=='VIEW_SAVED_SOURCE':
                selected=investigation.p['selected'].get(gid)
                if selected is None:continue
                offer=selected['offer']
            block_ids = offer['block_ids']
        else:
            did = identity.get('document_id'); uid = identity.get('unit_id')
            if not did or uid is None: continue
            block_ids = ur.blocks(investigation.s, did, uid, 'subtree')
        if not block_ids or did not in current: continue
        wanted = inv.expected(investigation.s, did, block_ids)
        if not inv.covers(wanted, current[did]): continue
        refs = [p['id'] for p in data['sources'] if p['document_id'] == did
                and any(str(s['block_id']) == str(w['block_id']) and s['start_cp'] < w['end_cp'] and w['start_cp'] < s['end_cp']
                        for s in p['spans'] for w in wanted)]
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



def operation_key(decision, actions):
    return digest({'kind': decision['next_action'],
                   'targets': [actions[t]['identity'] for t in decision['targets']],
                   'queries': sorted({text_key(q) if decision['next_action'] == 'SEARCH_STRUCTURE'
                                      else re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', q)).strip().casefold()
                                      for q in decision.get('queries', [])}),
                   'structure_filter': decision.get('structure_filter')})


def recoverable_tool_failure(error):
    """Only known rejected actions and transient reads can choose another route.

    Hash/ACL/schema errors and unknown model transmission outcomes remain fatal.
    Inspect wrapped causes because relation tools preserve their original error.
    """
    from .tool_outcome import classify_exception
    kind,_ = classify_exception(error)
    return {'PROPOSAL':'ACTION_REJECTED','TRANSIENT':'SOURCE_TEMPORARILY_UNAVAILABLE'}.get(kind)


def record_tool_failure(investigation, decision, actions, step, error):
    code = recoverable_tool_failure(error)
    if code is None: return False
    from . import tool_policy as tp
    from .tool_outcome import exception_outcome
    import time
    from .tool_availability import navigation_reason
    kind=decision['next_action']
    spec=tp.require_registered('ending' if kind in ('DECIDE','FINISH','PENDING') else 'navigation',kind)
    outcome=exception_outcome(error,action={'tool':kind,'args':{'operation_key':operation_key(decision,actions)}},
        binding_hash=investigation.p['binding'],surface=spec.surface)
    failed_key=operation_key(decision,actions)
    distinct=any(operation_key({'next_action':a['action'],'targets':[target],
        'queries':decision.get('queries',[]) if a['action']==kind else [],
        'structure_filter':decision.get('structure_filter') if a['action']==kind else None},actions)!=failed_key
        and navigation_reason(investigation,a) is None for target,a in actions.items())
    budget=investigation.s.repo.budget()
    choice=tp.choose_recovery(spec,outcome,tp.RecoveryState(distinct_alternative=distinct,
        pre_execution_rejection=code=='ACTION_REJECTED'),tp.RecoveryBudget(
        deadline_expired=time.monotonic()>=investigation.s.context.deadline,
        investigation_available=budget['tool_used']<budget['tool_limit']))
    if choice.action=='STOP':return False
    row = {'operation_key': operation_key(decision, actions), 'code': code,
           'action': decision['next_action'], 'targets': deepcopy([actions[t]['identity'] for t in decision['targets']]),
           'queries': list(decision.get('queries', [])), 'step_id': step['id'],
           'status': 'UNRESOLVED', 'absence_proven': False,
           'recovery_policy':{'version':tp.VERSION,'action':choice.action,'owner':choice.owner},
           'tool_outcome':outcome.to_dict()}
    investigation.p.setdefault('tool_failures', []).append(row)
    if kind=='FOLLOW_CONNECTION' and investigation.p.get('selected_connection_scope'):
        investigation.p['selected_connection_scope']['status']='FAILED'
        investigation.p['selected_connection_scope']['failure']={k:row[k] for k in ('code','status','absence_proven')}
    changed = record_progress(investigation.p)
    from ..research_state import OriginalProgress
    progress = OriginalProgress(investigation.p).advance(changed)
    step.update(status='FAILED', outcome={'failure_code': code, 'absence_proven': False, 'changed': changed},
                progress=progress)
    if investigation.control: investigation.p['state_version'] += 1
    investigation.s.repo.event('INVESTIGATION_CHAIN_STEP', step)
    # Raw exceptions stay in the server journal; the model sees typed outcomes.
    investigation.s.repo.event('LAW_TOOL_RECOVERY', {**row, 'error_type': type(error).__name__, 'error': str(error)})
    return True


def recovery_menu(investigation, data, actions):
    failures = investigation.p.get('tool_failures', [])
    blocked = set()
    for ident, action in list(actions.items()):
        if action['action'] in ('SEARCH_BODY', 'SEARCH_STRUCTURE', 'RESEARCH'): continue
        if any(f['action'] == action['action'] and f['targets'] == [action['identity']] for f in failures):
            blocked.add(ident); del actions[ident]
    # Search handles stay usable with a changed expression; validate the exact
    # operation separately. Read/cursor handles cannot immediately repeat a failure.
    if failures:
        data['tool_recovery'] = [{k: f[k] for k in ('code', 'action', 'targets', 'queries', 'status', 'absence_proven')}
                                 for f in failures[-3:]]
        data['tool_recovery_rule'] = ('실패한 동일 요청은 반복하지 않는다. 허용된 다른 구조·범위 조회를 선택하거나 '
            '확인한 원문으로 판단하고 부족은 UNRESOLVED로 남긴다. 실패는 원문 부재 증명이 아니다.')
    lookup = data.get('structure', {})
    if not isinstance(lookup, dict): lookup = {}
    failure = lookup.get('failure') or investigation.p.get('structure_page', {}).get('failure')
    if failure:
        suggested = failure['suggested_action']
        equivalents = {'CHOOSE_VERSION': ('OPEN_STRUCTURE', 'SEARCH_STRUCTURE'),
                      'OPEN_STRUCTURE': ('OPEN_STRUCTURE', 'BROWSE_STRUCTURE'),
                      'SEARCH_STRUCTURE': ('SEARCH_STRUCTURE',), 'BROWSE_STRUCTURE': ('BROWSE_STRUCTURE',)}
        data['lookup_recovery'] = {'failure_code': failure['code'], 'absence_proven': False,
            'action_ids': [k for k, a in actions.items() if a['action'] in equivalents.get(suggested, ())],
            'automatic_fulltext_fallback': False}
    if blocked:
        def clean(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, str) and v in blocked and k.endswith('action'): value[k] = None
                    elif isinstance(v, list) and k.endswith('actions'): value[k] = [x for x in v if not isinstance(x, str) or x not in blocked]
                    elif isinstance(v, (dict, list)): clean(v)
            elif isinstance(value, list):
                for v in value: clean(v)
        clean(data)
    data['actions'] = [a for a in data['actions'] if a['id'] in actions]


def validate_failed_operation(investigation, decision, actions):
    if not decision.get('targets'): return
    key = operation_key(decision, actions)
    if any(f['operation_key'] == key for f in investigation.p.get('tool_failures', [])):
        raise ProposalError('same failed operation in this request; select a different offered target/query or leave UNRESOLVED')


def no_progress_recovery(inv):
    """Bounded discovery-to-read chain; no new budget or source progress."""
    if not inv.modern:return None
    saved = inv.p.get('no_progress_recovery')
    if saved:
        if saved['status'] not in ('RESERVED','COMPLETED'):raise ContractError('unknown no-progress recovery status')
        if (saved['binding'] != digest(inv.p['binding']) or
                saved['snapshot_hash'] != digest(saved['snapshot'])):
            raise ContractError('no-progress recovery snapshot changed')
        if saved['epoch'] != inv.p.get('investigation_epoch',0):
            if saved['status']=='COMPLETED':return None
            raise ContractError('no-progress recovery snapshot epoch changed')
        if saved['status']=='RESERVED':
            if saved['state_version'] != inv.p['state_version']:
                raise ContractError('no-progress recovery snapshot state version changed')
            return deepcopy(saved['snapshot'])
        # A completed tool legitimately advances the state version. Only its
        # immediately committed state may extend this bounded recovery chain.
        completed = saved.get('completed_state_version')
        if completed is None:return None  # Legacy receipts cannot gain new allowance.
        if completed < saved['state_version'] or inv.p['state_version'] < completed:
            raise ContractError('no-progress recovery completion state version changed')
        if inv.p['state_version'] > completed:return None
        if saved.get('selection_count',1)>=3:return None
    data, actions = inv.view()
    useful = {'READ_ARTICLES','READ_SCOPE','READ_PARENT','SEARCH_BODY','SEARCH_STRUCTURE','RETRY_LAW_STRUCTURE',
              'RESEARCH','FOLLOW_CONNECTION','OPEN_LAW','OPEN_STRUCTURE','BROWSE_STRUCTURE',
              'NEXT_ARTICLES','NEXT_LAWS','NEXT_STRUCTURE','NEXT_HITS'}
    if not any(a['action'] in useful for a in actions.values()):return None
    def targets(menu):
        return {digest([a['action'],a.get('identity')]) for a in menu.values() if a['action'] in useful}
    offered=targets(actions)
    seen=set(saved.get('offered_targets',targets(saved['snapshot'][1]))) if saved else set()
    if saved and not offered-seen:return None
    phase = 'source-law-navigation-'+str(inv.p['turn']+1)
    snapshot = [deepcopy(data),deepcopy(actions),phase]
    history=deepcopy(saved.get('history',[])) if saved else []
    if saved:history.append({k:saved[k] for k in ('phase','snapshot_hash','status','unchanged_turns')})
    inv.p['no_progress_recovery'] = {'status':'RESERVED','binding':digest(inv.p['binding']),
        'state_version':inv.p['state_version'],'epoch':inv.p.get('investigation_epoch',0),'snapshot':snapshot,'snapshot_hash':digest(snapshot),
        'unchanged_turns':inv.p['no_progress'],'phase':phase,
        'selection_count':saved.get('selection_count',1)+1 if saved else 1,
        'offered_targets':sorted(seen|offered),'history':history}
    inv.s.repo.event('INVESTIGATION_NO_PROGRESS_RECOVERY',{
        'snapshot_hash':digest(snapshot),'unchanged_turns':inv.p['no_progress'],
        'max_selections':3,'selection_count':inv.p['no_progress_recovery']['selection_count'],
        'counter_reset':False,'budget':inv.s.repo.budget()})
    inv.save()
    return deepcopy(snapshot)


def finish_no_progress_recovery(state, phase):
    saved = state.get('no_progress_recovery')
    if saved and saved['status']=='RESERVED' and saved['phase']==phase:
        saved['status']='COMPLETED'
        saved['completed_state_version']=state['state_version']
