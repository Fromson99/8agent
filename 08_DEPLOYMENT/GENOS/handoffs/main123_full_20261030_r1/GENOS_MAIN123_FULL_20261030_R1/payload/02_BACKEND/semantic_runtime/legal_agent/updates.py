"""Semantic proposal reducer. Issues are revisable hypotheses, never access rules."""
from copy import deepcopy
import uuid
from .errors import ProposalError

PREFIX = {'create_issue': 'I', 'split_issue': 'I', 'merge_issue': 'I', 'supersede_issue': 'I',
          'assess': 'A', 'propose_finding': 'F', 'attach_fact': 'UF'}


def apply_updates(repo, view, updates, seq, *, dry_ids=False, id_map=None):
    if dry_ids:
        result = {}
        for update in updates:
            temps = [update['temp_id']] if 'temp_id' in update else []
            temps += [r['temp_id'] for r in update.get('replacements', [])]
            for temp in temps:
                if not temp.startswith('tmp:') or temp in result:
                    raise ProposalError('unique batch-local tmp IDs required')
                result[temp] = PREFIX[update['op']]+uuid.uuid4().hex
        return result

    def resolve(value):
        if isinstance(value, list):
            return [resolve(v) for v in value]
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, str) and value.startswith('tmp:'):
            if value not in id_map:
                raise ProposalError('unknown batch-local reference')
            return id_map[value]
        return value

    pieces = {p['id']: p for p in repo.context.pieces}

    def issue_payload(issue):
        if not set(issue['question_piece_ids']) <= pieces.keys():
            raise ProposalError('unknown question piece')
        repo.visible(view['view_id'], issue['evidence_ids'])
        if issue['origin'] == 'source_trigger' and not issue['evidence_ids']:
            raise ProposalError('source-triggered issue needs presented source')
        return {**issue, 'state': 'OPEN', 'replacements': [], 'reason': ''}

    def change_targets(update, replacements):
        targets = update.get('targets', [{'issue_id': update.get('issue_id'), 'expected_version': update.get('expected_version')}])
        heads = [repo.head('issue', t['issue_id'], expected=t['expected_version']) for t in targets]
        if len({h['entity_id'] for h in heads}) != len(heads):
            raise ProposalError('duplicate issue targets')
        if any(h['payload']['state'] == 'SUPERSEDED' for h in heads):
            raise ProposalError('issue already superseded')
        required = any(h['payload']['required'] for h in heads)
        old_questions = {q for h in heads for q in h['payload']['question_piece_ids']}
        new_questions = {q for r in replacements for q in r['issue']['question_piece_ids']}
        if not old_questions <= new_questions or (required and any(not r['issue']['required'] for r in replacements)):
            raise ProposalError('issue changes cannot silently drop question coverage or required status')
        return heads

    # Topologically apply batch-local dependencies. References to not-yet-executed
    # reads never enter this map; unresolved/cyclic batches roll back as a whole.
    pending = deepcopy(updates)
    while pending:
        progressed = False
        for original in pending[:]:
            temp_deps = []
            for field in ('issue_id', 'assessment_ids', 'fact_ids', 'finding_ids'):
                v = original.get(field, [])
                temp_deps.extend([v] if isinstance(v, str) else v)
            if any(v.startswith('tmp:') and not repo.db.execute('SELECT 1 FROM entity_head WHERE entity_id=?', (id_map.get(v, ''),)).fetchone() for v in temp_deps):
                continue
            u = resolve(original)
            name = u['op']
            if name == 'create_issue':
                value = issue_payload(u['issue'])
                duplicate = next((h for h in repo.heads('issue', current=True)
                                  if all(h['payload'].get(k) == value[k] for k in ('text', 'question_piece_ids', 'required', 'origin', 'evidence_ids'))
                                  and h['payload']['state'] != 'SUPERSEDED'), None)
                if duplicate:
                    # Keep already reserved IDs stable: duplicate creation is rejected,
                    # rather than silently creating a fake progress event.
                    raise ProposalError('duplicate issue; use revise_issue')
                repo.put('issue', u['temp_id'], value, seq, evidence_ids=value['evidence_ids'])
            elif name in ('revise_issue', 'split_issue', 'merge_issue', 'supersede_issue'):
                replacements = u.get('replacements') or [{'temp_id': u.get('temp_id', u.get('issue_id')), 'issue': u['issue']}]
                heads = change_targets(u, replacements)
                replacement_ids = [r['temp_id'] for r in replacements]
                for h in heads:
                    if name != 'revise_issue':
                        repo.put('issue', h['entity_id'], {**h['payload'], 'state': 'SUPERSEDED',
                                  'replacements': replacement_ids, 'reason': u['reason']}, seq,
                                  evidence_ids=h['payload']['evidence_ids'])
                for r in replacements:
                    value = issue_payload(r['issue'])
                    repo.put('issue', r['temp_id'], {**value, 'reason': u['reason']}, seq, evidence_ids=value['evidence_ids'])
            elif name == 'assess':
                issue = repo.head('issue', u['issue_id'])
                if issue['payload']['state'] == 'SUPERSEDED':
                    raise ProposalError('cannot assess superseded issue')
                repo.visible(view['view_id'], u['evidence_ids'])
                repo.put('assessment', u['temp_id'], {k: u[k] for k in ('issue_id', 'evidence_ids', 'relation', 'reason')}, seq,
                         dependencies=[('issue', u['issue_id'])], evidence_ids=u['evidence_ids'])
            elif name == 'retract_assessment':
                head = repo.head('assessment', u['assessment_id'], current=False, expected=u['expected_version'])
                if head['validity'] == 'RETRACTED':
                    raise ProposalError('assessment already retracted')
                repo.put('assessment', u['assessment_id'], {**head['payload'], 'retraction_reason': u['reason']}, seq,
                         evidence_ids=head['payload']['evidence_ids'], validity='RETRACTED')
            elif name == 'attach_fact':
                repo.head('issue', u['issue_id'])
                if not set(u['question_piece_ids']) <= pieces.keys():
                    raise ProposalError('unknown fact question piece')
                if (u['status'] == 'stated') != bool(u['question_piece_ids']):
                    raise ProposalError('stated facts select server question IDs; unknown facts have no inferred value')
                value = {k: u[k] for k in ('issue_id', 'name', 'status', 'question_piece_ids')}
                value['question_spans'] = [pieces[q] for q in u['question_piece_ids']]
                # Exact selected source text is the fact value; the model does not
                # replace it with a paraphrase and promote an assumption to stated.
                value['value'] = ''.join(pieces[q]['text'] for q in u['question_piece_ids']) if u['status'] == 'stated' else None
                repo.put('fact', u['temp_id'], value, seq, dependencies=[('issue', u['issue_id'])])
            elif name == 'propose_finding':
                assessments = [repo.head('assessment', ident) for ident in u['assessment_ids']]
                facts = [repo.head('fact', ident) for ident in u['fact_ids']]
                if any(h['payload']['issue_id'] != u['issue_id'] for h in assessments+facts):
                    raise ProposalError('finding dependencies belong to another issue')
                if not any(a['payload']['relation'] in ('supports', 'qualifies') for a in assessments):
                    raise ProposalError('finding needs a supporting or qualifying assessment')
                evidence_ids = sorted({e for a in assessments for e in a['payload']['evidence_ids']})
                unknown = any(f['payload']['status'] == 'unknown' for f in facts)
                if unknown and u['applicability'] == 'current':
                    raise ProposalError('missing user facts preclude current applicability')
                if u['applicability'] == 'current' and any(repo.evidence(e)['temporal_status'] != 'verified' for e in evidence_ids):
                    raise ProposalError('unknown source effective date precludes current applicability')
                value = {k: u[k] for k in ('issue_id', 'assessment_ids', 'fact_ids', 'text', 'applicability')}
                value.update(evidence_ids=evidence_ids, fact_unknown=unknown)
                repo.put('finding', u['temp_id'], value, seq,
                         dependencies=[('issue', u['issue_id'])]+[('assessment', a['entity_id']) for a in assessments]+[('fact', f['entity_id']) for f in facts],
                         evidence_ids=evidence_ids)
            elif name == 'mark_unresolved':
                h = repo.head('issue', u['issue_id'], expected=u['expected_version'])
                observations = []
                for ident in u['observation_ids']:
                    row = repo.db.execute('SELECT status FROM observation WHERE observation_id=?', (ident,)).fetchone()
                    if not row:
                        raise ProposalError('unresolved issue needs actual search/read observations')
                    observations.append({'observation_id': ident, 'status': row[0]})
                repo.put('issue', u['issue_id'], {**h['payload'], 'state': 'UNRESOLVED', 'reason': u['reason'],
                         'observations': observations}, seq, evidence_ids=h['payload']['evidence_ids'])
            elif name == 'mark_not_applicable':
                h = repo.head('issue', u['issue_id'], expected=u['expected_version'])
                findings = [repo.head('finding', f) for f in u['finding_ids']]
                if any(f['payload']['issue_id'] != u['issue_id'] for f in findings):
                    raise ProposalError('coverage finding belongs to another issue')
                # Keep issue head stable: mutating it would immediately stale the
                # findings that justify this coverage proposal.
                ids = sorted({e for f in findings for e in f['payload']['evidence_ids']})
                repo.put('claim', 'C'+uuid.uuid4().hex, {'purpose': 'coverage', 'issue_id': u['issue_id'],
                         'text': u['reason'], 'finding_ids': u['finding_ids'], 'evidence_ids': ids}, seq,
                         dependencies=[('finding', f['entity_id']) for f in findings], evidence_ids=ids)
            else:
                raise ProposalError('unsupported update')
            pending.remove(original)
            progressed = True
        if not progressed:
            raise ProposalError('cyclic or unresolved batch-local dependencies')
    return id_map
