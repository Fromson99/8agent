"""Versioned native completion: original spans, typed gaps and closed rendering.

The flag is release-bound. Historical routes retain their original contract.
This checks provenance and structural consistency, not legal entailment.
v2 adds a typed missing target per gap, wording-independent gap identity,
issue-grouped rendering and a conservative normalization instead of a failed
request when the model twice keeps a coverage/materiality conflict.
"""
from copy import deepcopy
from html import escape
import re
import unicodedata
from jsonschema import Draft202012Validator
from ..contracts import digest
from .errors import ContractError, ProposalError

V1 = 'investigation-completion-v1'
V2 = 'investigation-completion-v2'
V3 = 'investigation-completion-v3'
CONTRACT = 'investigation-completion-v4'
V5 = 'investigation-completion-v5'
V6 = 'investigation-completion-v6'
V7 = 'investigation-completion-v7'
V8 = 'investigation-completion-v8'
KNOWN = (V1, V2, V3, CONTRACT, V5, V6, V7, V8)
GAP_REASON_PRESENTATION = 'attributed-gap-reasons-v1'

def version(profile):
    return profile.get('candidate_navigation', {}).get('completion_policy_version', CONTRACT)
GAP_ACTIONS = ['VIEW_SAVED_SOURCE', 'READ_SCOPE', 'FOLLOW_CONNECTION', 'RETURN_TO', 'RESEARCH',
               'SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'BROWSE_STRUCTURE', 'REQUEST_FACT', 'CHOOSE_VERSION']


def enabled(profile):
    return profile.get('candidate_navigation', {}).get('completion_contract', False)


def gap_key(gap):
    """Identity of a gap across assessment rounds, independent of reason wording."""
    if gap.get('identity_key'):return gap['identity_key']
    target = unicodedata.normalize('NFKC', gap.get('missing_target') or '')
    target = re.sub(r'[\s\W_]+', '', target).lower()
    # A missing optional locator is unknown, not a common identity for every
    # missing source in this issue. Retain its stated reason as a fallback.
    identity = target if target else ('unlocated', ' '.join(
        unicodedata.normalize('NFKC', gap.get('reason') or '').split()).casefold())
    return 'K' + digest([gap.get('issue_id'), gap.get('kind'), gap.get('material_id'), identity])[:20]


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def refs(values, minimum=0):
    return {'type': 'array', 'items': {'type': 'string', **({'enum': list(values)} if values else {})},
            'minItems': minimum, **({} if values else {'maxItems': 0})}


def evidence_options(sources):
    """Use delivered, adopted spans; offsets are original Unicode codepoints."""
    rows = []
    for source in sources:
        spans = source.get('adopted_spans') or []
        if not spans:
            raise ContractError('completion requires adopted original spans')
        for span in spans:
            text = span['text']
            if text not in source['text']:
                raise ContractError('adopted span is absent from selected original')
            # Newlines delimit without normalization; long lines remain bounded.
            offset = 0
            for line in text.splitlines(keepends=True):
                for start in range(0, len(line), 1200):
                    piece = line[start:start + 1200]
                    if not piece.strip():
                        continue
                    lo = span['start_cp'] + offset + start
                    identity = {'source_id': source['source_id'], 'document_id': source['document_id'],
                                'block_id': str(span['block_id']), 'start_cp': lo,
                                'end_cp': lo + len(piece), 'evidence_id': span['evidence_id'],
                                'text_hash': digest(piece)}
                    rows.append({'id': 'S' + digest(identity)[:28], **identity, 'text': piece})
                offset += len(line)
    return list({row['id']: row for row in rows}.values())


def assessment_schema(issues, materials, options, *, contract=None, facts=()):
    from .investigation_contracts import GAP_KINDS
    ids = [i['id'] for i in issues]
    schema = obj({
        'claims': {'type': 'array', 'maxItems': 12, 'items': obj({
            'claim_id': {'type': 'string', 'pattern': '^C[1-9][0-9]*$'},
            'issue_refs': refs(ids, 1), 'text': {'type': 'string', 'minLength': 1},
            'evidence_refs': refs([o['id'] for o in options], 1)})},
        'disposition': {'type': 'string', 'enum': ['ANSWER', 'LIMITED_ANSWER', 'NEEDS_INVESTIGATION']},
        'issue_assessments': {'type': 'array', 'items': obj({
            'issue_id': {'type': 'string', 'enum': ids},
            'status': {'type': 'string', 'enum': ['COVERED', 'PARTIAL', 'INSUFFICIENT']},
            'reason': {'type': 'string', 'minLength': 1}})},
        'gaps': {'type': 'array', 'items': obj({
            'issue_id': {'type': 'string', 'enum': ids},
            'kind': {'type': 'string', 'enum': GAP_KINDS},
            'reason': {'type': 'string', 'minLength': 1},
            'material_id': {'anyOf': [{'type': 'string', 'enum': list(materials)}, {'type': 'null'}]} if materials else {'type': 'null'},
            'material': {'type': 'boolean'},
            'missing_target': {'type': 'string'},
            'suggested_action': {'type': 'string', 'enum': GAP_ACTIONS}})}})
    if contract == CONTRACT:
        claim = schema['properties']['claims']['items']
        claim['properties']['rule'] = rule_schema([o['id'] for o in options], facts)
        claim['required'].append('rule')
    # Optional on the wire (like structure_filter): an omitted locator means none stated.
    gap = schema['properties']['gaps']['items']
    gap['required'] = [k for k in gap['required'] if k != 'missing_target']
    return schema


def with_targets(value):
    """missing_target is an optional locator; absence means no stated target."""
    value = deepcopy(value)
    for gap in value.get('gaps', []) if isinstance(value, dict) and isinstance(value.get('gaps'), list) else []:
        if isinstance(gap, dict):
            gap.setdefault('missing_target', '')
    return value


def source_gap_actions(value):
    """Route schema-valid source gaps to investigation, preserving their content.

    A source gap cannot request a user fact. Correct only that contradictory
    action label; fact classification, targets, evidence and materiality remain
    model observations subject to the existing validators and bounded reentry.
    """
    value = with_targets(value)
    changes = []
    for index, gap in enumerate(value['gaps']):
        if gap['kind'] != 'MISSING_FACT' and gap['suggested_action'] == 'REQUEST_FACT':
            gap['suggested_action'] = 'RESEARCH'
            changes.append({'gap_index': index, 'issue_id': gap['issue_id'],
                'kind': gap['kind'], 'from': 'REQUEST_FACT', 'to': 'RESEARCH'})
    return value, changes


def assessment_errors(value, schema, issues, *, model_materiality=False):
    value = with_targets(value)
    errors = [f'{"/".join(map(str, e.path))}: {e.message}'
              for e in Draft202012Validator(schema).iter_errors(value)]
    if errors:
        return errors[:16]
    expected = {i['id'] for i in issues}
    rows = value['issue_assessments']
    if len(rows) != len(expected) or {r['issue_id'] for r in rows} != expected:
        errors.append('Assess every offered issue exactly once; preserve the original request.')
    claims = value['claims']
    if len({c['claim_id'] for c in claims}) != len(claims):
        errors.append('claim_id must be unique')
    for gap in value['gaps']:
        if gap['kind'] == 'MISSING_FACT':
            if gap['suggested_action'] != 'REQUEST_FACT':
                errors.append('Missing user facts require REQUEST_FACT, not source research.')
            if gap['material_id'] is not None:
                errors.append('MISSING_FACT cannot target a saved legal material. If a law/decree/list/scope is missing, select a source gap and source research action; only an unprovided fact needed for a requested case application is a user fact.')
        elif gap['suggested_action'] == 'REQUEST_FACT':
            errors.append('A legal source gap requires source research, not REQUEST_FACT.')
        if not model_materiality and gap['kind'] != 'UNRESOLVED_REFERENCE' and not gap['material']:
            errors.append('A missing requested scope/source/subject/fact is a material gap.')
    blocked = {g['issue_id'] for g in value['gaps'] if g['material']}
    for row in rows:
        if row['status'] == 'COVERED' and row['issue_id'] in blocked:
            errors.append(f'{row["issue_id"]}: COVERED conflicts with a material gap. Preserve the gap and mark PARTIAL/INSUFFICIENT; use NEEDS_INVESTIGATION for missing legal text. Do not mark a missing requested requirement non-material to evade repair.')
        if row['status'] == 'COVERED' and not any(row['issue_id'] in c['issue_refs'] for c in claims):
            errors.append(f'{row["issue_id"]}: COVERED requires a supported claim')
    if value['disposition'] == 'ANSWER' and (blocked or any(r['status'] != 'COVERED' for r in rows)):
        errors.append('ANSWER requires all requested issues covered without material gaps')
    if value['disposition'] == 'NEEDS_INVESTIGATION' and not value['gaps']:
        errors.append('NEEDS_INVESTIGATION requires an explicit gap')
    if value['disposition'] != 'NEEDS_INVESTIGATION' and not claims:
        errors.append('A completed answer requires supported claims')
    for claim in claims:
        if claim.get('rule') is not None:
            errors.extend(rule_errors(claim))
    return errors


def normalize_assessment(value, schema, issues):
    """Conservatively close structural conflicts after the single model repair.

    Never invents a claim or evidence. Every conflict resolves toward a weaker
    answer: hidden gaps become visible limitations and COVERED becomes PARTIAL.
    Returns (normalized, changes) or (None, reason) when no claim survives.
    """
    if not isinstance(value, dict):
        return None, 'assessment is not an object'
    value = with_targets(value)
    changes = []
    if list(Draft202012Validator(schema).iter_errors(value)):
        return None, 'assessment is not schema-valid'
    if not value['claims']:
        return None, 'no supported claims'
    expected = [i['id'] for i in issues]
    seen = {}
    for row in value['issue_assessments']:
        seen.setdefault(row['issue_id'], row)
    if len(seen) != len(value['issue_assessments']):
        changes.append('duplicate_issue_assessment_dropped')
    for ident in expected:
        if ident not in seen:
            seen[ident] = {'issue_id': ident, 'status': 'INSUFFICIENT', 'reason': '판단 기록이 없어 근거 미확인으로 처리'}
            changes.append('missing_issue_marked_insufficient:' + ident)
    value['issue_assessments'] = [seen[i] for i in expected]
    if len({c['claim_id'] for c in value['claims']}) != len(value['claims']):
        for number, claim in enumerate(value['claims'], 1):
            claim['claim_id'] = 'C' + str(number)
        changes.append('claim_ids_renumbered')
    for gap in value['gaps']:
        if gap['kind'] == 'MISSING_FACT':
            if gap['suggested_action'] != 'REQUEST_FACT':
                gap['suggested_action'] = 'REQUEST_FACT'; changes.append('fact_gap_action')
            if gap['material_id'] is not None:
                gap['material_id'] = None; changes.append('fact_gap_material_cleared')
        elif gap['suggested_action'] == 'REQUEST_FACT':
            gap['suggested_action'] = 'RESEARCH'; changes.append('source_gap_action')
        if gap['kind'] != 'UNRESOLVED_REFERENCE' and not gap['material']:
            gap['material'] = True; changes.append('gap_made_visible:' + gap['issue_id'])
    blocked = {g['issue_id'] for g in value['gaps'] if g['material']}
    for row in value['issue_assessments']:
        supported = any(row['issue_id'] in c['issue_refs'] for c in value['claims'])
        if row['status'] == 'COVERED' and not supported:
            row['status'] = 'INSUFFICIENT'; changes.append('unsupported_covered:' + row['issue_id'])
        elif row['status'] == 'COVERED' and row['issue_id'] in blocked:
            row['status'] = 'PARTIAL'; changes.append('covered_with_gap:' + row['issue_id'])
    complete = not blocked and all(r['status'] == 'COVERED' for r in value['issue_assessments'])
    disposition = 'ANSWER' if complete else 'LIMITED_ANSWER'
    if value['disposition'] != disposition:
        changes.append('disposition:' + value['disposition'] + '->' + disposition)
        value['disposition'] = disposition
    if assessment_errors(value, schema, issues):
        return None, 'normalization did not close every structural conflict'
    return value, changes


def bind_rule_evidence(value, options):
    """Canonicalize only refs already explicitly chosen inside this claim's rule.

    These are delivered/adopted options, not newly retrieved sources. Unknown
    refs remain invalid and cannot be made valid by normalization.
    """
    value=deepcopy(value);available={o['id'] for o in options};changes=[]
    for claim in value.get('claims',[]) if isinstance(value,dict) else []:
        if not isinstance(claim,dict) or not isinstance(claim.get('rule'),dict):continue
        chosen=claim.get('evidence_refs')
        if not isinstance(chosen,list) or not all(isinstance(x,str) for x in chosen):continue
        nested=[]
        for kind in ('conditions','exceptions'):
            rows=claim['rule'].get(kind,[])
            if not isinstance(rows,list):continue
            for row in rows:
                if isinstance(row,dict) and isinstance(row.get('evidence_refs'),list):
                    nested.extend(x for x in row['evidence_refs'] if isinstance(x,str))
        if set(nested)-available:continue
        merged=list(dict.fromkeys(chosen+nested))
        if merged!=chosen:
            claim['evidence_refs']=merged;changes.append({'claim_id':claim.get('claim_id'),'explicit_nested_refs':list(dict.fromkeys(nested))})
    return value,changes


def materialize_assessment(value, options, issues):
    """Compile legacy quote/source fields from exact offered spans only."""
    by_id = {o['id']: o for o in options}
    claims = []
    for claim in value['claims']:
        selected = [by_id[i] for i in dict.fromkeys(claim['evidence_refs'])]
        if not selected:
            raise ContractError('claim has no selected original span')
        quotes = [{'source_id': s['source_id'], 'quote': s['text']} for s in selected]
        if claim.get('rule') is not None:
            problems = rule_errors(claim)
            if problems:raise ContractError('; '.join(problems))
            claim = {**claim, 'text': render_rule(claim['rule'])}
        claims.append({**deepcopy(claim), **quotes[0], 'evidence': quotes[1:],
                       'span_receipts': deepcopy(selected)})
    out = {**deepcopy(value), 'claims': claims, 'completion_contract': CONTRACT}
    return refresh_limitations(out, issues)


def verify_span_claim(claim, sources):
    from .completion_v5 import verify_content
    verify_content(claim)
    by_id = {o['id']: o for o in evidence_options(sources)}
    selected = [by_id.get(i) for i in dict.fromkeys(claim.get('evidence_refs', []))]
    if not selected or any(s is None for s in selected) or claim.get('span_receipts') != selected:
        raise ContractError('claim span receipts differ from delivered adopted originals')
    expected = [{'source_id': s['source_id'], 'quote': s['text']} for s in selected]
    actual = [{'source_id': claim['source_id'], 'quote': claim['quote']}, *claim.get('evidence', [])]
    if actual != expected:
        raise ContractError('claim quote differs from source-span compilation')


GAP_WORDS = {'MISSING_FACT': '해당 사안에 적용할 결론을 하나로 확정하려면 추가 사실 정보가 필요합니다',
             'VERSION_AMBIGUOUS': '적용 시점과 판본 확인이 필요합니다',
             'WRONG_SUBJECT': '질문의 주체와 적용 범위를 추가로 확인해야 합니다',
             'UNREAD_SAVED': '확보한 자료의 원문 확인이 남아 있습니다',
             'MISSING_SCOPE': '요청한 범위의 원문 확인이 더 필요합니다',
             'MISSING_SOURCE': '추가 근거 자료 확인이 필요합니다',
             'UNRESOLVED_REFERENCE': '판단에 필요한 참조 원문 확인이 남아 있습니다'}
CLOSED_WORDS = {'NOT_AVAILABLE': '허용된 자료 범위에서 해당 원문을 찾지 못했습니다',
                'NOT_NEEDED': '조사 단계에서 답변에 필요하지 않다고 판단해 추가 열람하지 않았습니다',
                'UNRESOLVED': '추가 조사 중 확보하지 못했습니다'}
STOP_WORDS = {'ASSESSMENT_REENTRY_LIMIT': '추가 조사 횟수 한도에 도달하여 확인한 근거 범위에서 답변합니다.',
              'REPEATED_ASSESSMENT_GAP': '같은 원문 부족이 반복되어 추가 조사를 멈추고 확인한 근거 범위에서 답변합니다.',
              'INVESTIGATION_BUDGET': '조사 호출 한도에 도달하여 확인한 근거 범위에서 답변합니다.',
              'FINALIZATION_TIME_RESERVE': '응답 시간 한도에 도달하여 확인한 근거 범위에서 답변합니다.',
              'NO_PROGRESS': '추가 조사에서 새 원문이 확보되지 않아 확인한 근거 범위에서 답변합니다.',
              'MODEL_DECISION_UNRESOLVED': '근거 선택 결정을 확정하지 못해 확인한 근거 범위에서 답변합니다.',
              'MODEL_PENDING': '조사 단계가 보류를 선택해 확인한 근거 범위에서 답변합니다.'}
NOTE_WORDS = {'ADOPTION_FALLBACK': '조사 단계의 근거 채택이 확정되지 않아, 실제로 열람한 원문을 기준으로 판단했습니다.',
              'ASSESSMENT_NORMALIZED': '판단의 충족 표시를 기록된 원문 부족에 맞춰 부분 충족으로 조정했습니다.'}


def refresh_limitations(value, issues, stop_reason=None, *, closed=None, notes=()):
    """Deterministic limitation text. Free-form model reasons are never rendered;
    the bounded missing_target locator says what was not confirmed."""
    labels = {i['id']: i.get('question', i['id']) for i in issues}
    closed = closed or {}
    items = []
    for gap in value['gaps']:
        if not gap.get('material', True):
            continue
        target = (gap.get('missing_target') or '').strip()
        key = gap_key(gap)
        ident = 'L' + digest([gap['issue_id'], gap['kind'], gap.get('material_id'), target])[:20]
        words = CLOSED_WORDS.get(closed.get(key)) if gap['kind'] != 'MISSING_FACT' else None
        text = labels[gap['issue_id']] + ' — ' + (target + ': ' if target else '') + (words or GAP_WORDS[gap['kind']]) + '.'
        items.append({'id': ident, 'kind': gap['kind'], 'issue_id': gap['issue_id'], 'text': text,
                      **({'missing_target': target} if target else {}),
                      **({'navigation_status': closed[key]} if key in closed else {})})
    # Recovery/normalization are operational diagnostics, never user limitations.
    for note in ():
        items.append({'id': 'L-' + note.lower(), 'kind': note, 'issue_id': None, 'text': NOTE_WORDS[note]})
    if stop_reason == 'ASSESSMENT_OUTPUT_LIMIT':
        items.append({'id':'L-review-incomplete', 'kind':'EXECUTION_LIMIT', 'issue_id':None,
            'text':'원문은 확보했으나 답변 검토가 출력 한도에서 끝나 완료하지 못했습니다. 아래 원문은 확정된 법률 판단이 아닙니다.'})
    if stop_reason == 'ASSESSMENT_CONTRACT_UNRESOLVED':
        items.append({'id':'L-review-incomplete', 'kind':'REVIEW_INCOMPLETE', 'issue_id':None,
            'text':'원문은 확보했지만 주장과 근거의 연결을 검증하지 못해 결론을 확정하지 않았습니다. '
                   '확보한 원문을 재사용해 시스템의 연결 검토를 다시 해야 합니다. '
                   '추가 정보 없이 같은 요청을 반복해도 자동으로 다시 호출하지 않습니다.'})
    # An investigation stop is diagnostic history, not evidence of an unread scope.
    # Preserve it below; user limitations require a material gap or incomplete final review.
    value['limitation_items'] = list({r['id']: r for r in items}.values())
    # Detailed gap identities stay separate; identical display text is emitted once.
    value['limitations'] = list(dict.fromkeys(r['text'] for r in value['limitation_items']))
    value['stop_reason'] = stop_reason
    return value


SOURCE_REPLY_CONTRACT = 'verified-source-excerpt-reply-v1'


def source_excerpt_reply(sources):
    """Return exact delivered spans as observations, never as legal claims."""
    options = evidence_options(sources)
    rows = []
    for source in sources:
        spans = [deepcopy(o) for o in options if o['source_id'] == source['source_id']]
        if spans:
            rows.append({'source_id': source['source_id'],
                'document_name': source.get('document_name') or source['document_id'],
                'heading': source.get('heading', ''), 'span_receipts': spans})
    if not rows:
        raise ContractError('source excerpt reply requires verified delivered originals')
    return {'schema_version': SOURCE_REPLY_CONTRACT, 'sources': rows,
            'legal_conclusion_confirmed': False, 'absence_proven': False}


def verify_source_excerpt_reply(assessment, sources):
    from .investigation_contracts import coverage
    if (assessment.get('source_excerpt_reply') != source_excerpt_reply(sources)
            or assessment['claims'] or assessment['disposition'] != 'LIMITED_ANSWER'
            or assessment.get('answer_coverage') != coverage(assessment)
            or assessment.get('answer_coverage') == 'COVERED'
            or any(r['status'] == 'COVERED' for r in assessment['issue_assessments'])):
        raise ContractError('source excerpt reply differs from unresolved assessment or originals')


def render_source_excerpt_reply(assessment):
    from html import escape
    reply = assessment['source_excerpt_reply']
    if (reply.get('schema_version') != SOURCE_REPLY_CONTRACT or assessment['claims']
            or reply.get('legal_conclusion_confirmed') is not False
            or reply.get('absence_proven') is not False or not reply.get('sources')):
        raise ContractError('invalid source excerpt reply')
    blocks = (['원문은 확보했으나 답변 검토를 완료하지 못했습니다. 확인한 원문을 제공합니다.']
              if assessment.get('stop_reason') in ('ASSESSMENT_OUTPUT_LIMIT','ASSESSMENT_CONTRACT_UNRESOLVED') else
              ['확보한 자료만으로 질문의 결론을 확정하기는 어렵습니다. 확인한 원문과 아직 확인하지 못한 범위를 정리합니다.'])
    for row in reply['sources']:
        title = ' · '.join(x for x in (row['document_name'], row['heading']) if x)
        quotes = '\n\n'.join('\n'.join('> ' + escape(line) for line in span['text'].split('\n'))
                             for span in row['span_receipts'])
        blocks.append('**확인한 원문: ' + escape(title) + '**\n\n' + quotes)
    return '\n\n'.join(blocks)


def internal_schema(base, stage):
    schema = deepcopy(base)
    extra = {'completion_contract': {'type': 'string', 'enum': list(KNOWN)},
             'limitation_items': {'type': 'array'}, 'stop_reason': {'type': ['string', 'null']}}
    if stage == 'COMPOSE':
        extra.update(composition_plan={'type': 'object'}, assessment_hash={'type': 'string'})
    schema['properties'].update(assessment_basis={'type':'object'},model_proposal={'type':'object'},
                                read_judgment_review={'type':'object'},requirement_review={'type':'object'},
                                review_explanation={'type':'object'},ontology_explanation={'type':'object'},
                                scenario_calculation={'type':'object'},review_links={'type':'object'},scenario_application_display={'type':'array','items':obj({
                                    'claim_id':{'type':'string'},'text':{'type':'string'}})})
    schema['properties']['source_excerpt_reply'] = obj({
        'schema_version': {'const': SOURCE_REPLY_CONTRACT},
        'sources': {'type': 'array', 'minItems': 1, 'items': obj({
            'source_id': {'type': 'string'}, 'document_name': {'type': 'string'},
            'heading': {'type': 'string'}, 'span_receipts': {'type': 'array', 'minItems': 1}})},
        'legal_conclusion_confirmed': {'const': False}, 'absence_proven': {'const': False}})
    schema['properties'].update(extra)
    schema['required'] += list(extra)
    schema['properties']['limitations']['maxItems'] = 64
    claim = schema['properties']['claims']['items']
    claim['properties'].update(claim_id={'type': 'string'}, issue_refs={'type': 'array'},
                               evidence_refs={'type': 'array'}, span_receipts={'type': 'array'},
                               rule={'type': ['object', 'null']}, answer_content={'type':'object'})
    if stage == 'ASSESS':
        gap = schema['properties']['gaps']['items']['properties']
        gap.update(identity_key={'type':'string'},target_binding={'type':'object'},target_binding_hash={'type':'string'})
        gap['material'] = {'type': 'boolean'}
        gap['missing_target'] = {'type': 'string'}
        gap['suggested_action'] = {'type': 'string', 'enum': GAP_ACTIONS}
    return schema


def composition_schema(assessment):
    return obj({'layout': {'type': 'string', 'enum': ['paragraphs', 'bullets', 'table']},
                'claim_order': refs([c['claim_id'] for c in assessment['claims']], 1)})


def default_plan(assessment, requested_format=None, issues=None):
    layout = 'table' if requested_format == 'table' else 'paragraphs'
    order = [c['claim_id'] for c in assessment['claims']]
    if assessment.get('completion_contract', V1) == V1 or not issues or len(issues) < 2:
        return {'layout': layout, 'claim_order': order}
    # v2: one section per requested issue; a claim sits under its first issue.
    sections = [{'issue_id': i['id'], 'title': i.get('question') or i['id'],
                 'claim_ids': [c['claim_id'] for c in assessment['claims'] if c['issue_refs'][0] == i['id']]}
                for i in issues]
    if assessment.get('completion_contract') in (V3, CONTRACT, V5, V6, V7, V8):
        for section in sections:
            section['shared_claim_ids'] = [c['claim_id'] for c in assessment['claims']
                if section['issue_id'] in c['issue_refs'][1:]]
    return {'layout': layout, 'claim_order': [c for s in sections for c in s['claim_ids']],
            'issue_sections': sections}


def displayed_limitations(assessment, plan):
    """Expose recorded reasons only in final presentation, never model input.

    Old plans retain their exact rendering for saved-publication verification.
    Reasons remain unverified model observations, separate from legal claims.
    """
    presentation = plan.get('gap_reason_presentation')
    if presentation is None:
        return assessment['limitations']
    if presentation != GAP_REASON_PRESENTATION:
        raise ContractError('unknown gap reason presentation')
    by_id = {row['id']: row for row in assessment['limitation_items']}
    replacements = {}
    for gap in assessment.get('gaps', []):
        if not gap.get('material', True) or not (gap.get('reason') or '').strip():
            continue
        target = (gap.get('missing_target') or '').strip()
        ident = 'L' + digest([gap['issue_id'], gap['kind'], gap.get('material_id'), target])[:20]
        item = by_id.get(ident)
        if item is None:
            continue
        # Render as literal text; a diagnostic cannot create links or markup.
        reason = escape(' '.join(gap['reason'].split()), quote=False)
        reason = re.sub(r'([\\`*_\[\]()#!|~])', r'\\\1', reason)
        label = ('당시 미확인 사유' if item.get('navigation_status') else '미확인 사유')
        detail = item['text'] + ' ' + label + '(AI 판단·검증 전): ' + reason
        replacements.setdefault(item['text'], []).append(detail)
    return list(dict.fromkeys(detail for text in assessment['limitations']
                              for detail in replacements.get(text, [text])))


def render(assessment, plan):
    from .narrative_answer import PRESERVED_VERSION, verify_preserved_plan
    if plan.get('presentation') == PRESERVED_VERSION:
        verify_preserved_plan(assessment, plan)
    claims = {c['claim_id']: c for c in assessment['claims']}
    order = plan.get('claim_order', [])
    if len(order) != len(claims) or set(order) != set(claims):
        raise ContractError('composition must preserve every accepted claim exactly once')
    if plan.get('layout') not in ('paragraphs', 'bullets', 'table'):
        raise ContractError('unknown composition layout')
    sections = plan.get('issue_sections') if assessment.get('completion_contract', V1) != V1 else None
    if assessment.get('source_excerpt_reply'):
        text = render_source_excerpt_reply(assessment)
    elif plan.get('presentation') == 'grounded-narrative-v1':
        from .narrative_answer import render as render_narrative
        text = render_narrative(assessment, plan)
    elif sections:
        if [c for s in sections for c in s['claim_ids']] != order:
            raise ContractError('issue sections must follow the accepted claim order')
        if assessment.get('completion_contract') in (V3, CONTRACT, V5, V6, V7, V8):
            for section in sections:
                expected = [c['claim_id'] for c in assessment['claims']
                    if section['issue_id'] in c['issue_refs'][1:]]
                if section.get('shared_claim_ids', []) != expected:
                    raise ContractError('shared issue support differs from accepted claim references')
        text = _render_sections(claims, sections, plan['layout'])
    else:
        text = _render_flat([claims[i]['text'] for i in order], plan['layout'])
    if assessment.get('scenario_calculation'):
        from .scenario_computation import render as render_calculation
        text=render_calculation(assessment['scenario_calculation'])+'\n\n'+text
    applications=assessment.get('scenario_application_display',[])
    if applications:
        text += '\n\n가정의 수치 조건\n\n'+'\n'.join('- '+row['text'] for row in applications)
    limits = displayed_limitations(assessment, plan)
    if limits:
        text += '\n\n확인 범위\n\n' + '\n'.join('- ' + s for s in limits)
    return text


def _escape(value):
    return value.replace('|', '\\|').replace('\n', '<br>')


def _render_flat(texts, layout):
    if layout == 'table':
        return '| 항목 | 판단 |\n|---|---|\n' + '\n'.join(
            '| ' + str(n) + ' | ' + _escape(t) + ' |' for n, t in enumerate(texts, 1))
    if layout == 'bullets':
        return '\n'.join('- ' + t for t in texts)
    return '\n\n'.join(texts)


NO_ISSUE_EVIDENCE = '제공된 원문으로 이 쟁점의 판단 근거를 확인하지 못했습니다.'


def _render_sections(claims, sections, layout):
    owner = {cid: (n, section['title']) for n, section in enumerate(sections, 1)
             for cid in section['claim_ids']}
    def texts_for(section):
        texts = [claims[c]['text'] for c in section['claim_ids']]
        references = list(dict.fromkeys(owner[c] for c in section.get('shared_claim_ids', [])))
        texts += ['이 쟁점의 판단은 ' + str(n) + '. ' + title + '의 공통 판단에 함께 설명했습니다.'
                  for n, title in references]
        return texts or [NO_ISSUE_EVIDENCE]
    if layout == 'table':
        rows = []
        for s in sections:
            texts = texts_for(s)
            rows += ['| ' + _escape(s['title']) + ' | ' + _escape(t) + ' |' for t in texts]
        return '| 쟁점 | 판단 |\n|---|---|\n' + '\n'.join(rows)
    blocks = []
    for number, s in enumerate(sections, 1):
        texts = texts_for(s)
        body = '\n'.join('- ' + t for t in texts) if layout == 'bullets' else '\n\n'.join(texts)
        blocks.append(str(number) + '. ' + s['title'] + '\n\n' + body)
    return '\n\n'.join(blocks)


def compose(assessment, plan):
    plan = deepcopy(plan)
    if assessment.get('completion_contract') == V8:
        plan['gap_reason_presentation'] = GAP_REASON_PRESENTATION
    return {**({'assessment_basis': deepcopy(assessment['assessment_basis'])} if 'assessment_basis' in assessment else {}),
            **({'source_excerpt_reply': deepcopy(assessment['source_excerpt_reply'])} if 'source_excerpt_reply' in assessment else {}),
            **({'read_judgment_review': deepcopy(assessment['read_judgment_review'])} if 'read_judgment_review' in assessment else {}),
            **({'requirement_review': deepcopy(assessment['requirement_review'])} if 'requirement_review' in assessment else {}),
            **({'review_explanation': deepcopy(assessment['review_explanation'])} if 'review_explanation' in assessment else {}),
            'text': render(assessment, plan), 'claims': deepcopy(assessment['claims']),
            'limitations': deepcopy(assessment['limitations']),
            'completion_contract': assessment.get('completion_contract', V1),
            'limitation_items': deepcopy(assessment['limitation_items']),
            'stop_reason': assessment.get('stop_reason'), 'composition_plan': deepcopy(plan),
            'assessment_hash': digest(assessment)}


def verify_composition(assessment, answer):
    contract = assessment.get('completion_contract', V1)
    if (contract not in KNOWN or answer.get('completion_contract') != contract
            or answer.get('assessment_hash') != digest(assessment)
            or answer.get('claims') != assessment['claims']
            or answer.get('source_excerpt_reply') != assessment.get('source_excerpt_reply')
            or answer.get('read_judgment_review') != assessment.get('read_judgment_review')
            or answer.get('requirement_review') != assessment.get('requirement_review')
            or answer.get('review_explanation') != assessment.get('review_explanation')
            or answer.get('limitations') != assessment['limitations']
            or answer.get('limitation_items') != assessment['limitation_items']
            or answer.get('stop_reason') != assessment.get('stop_reason')
            or answer.get('text') != render(assessment, answer['composition_plan'])):
        raise ContractError('published text differs from accepted assessment rendering')


def decision_basis(view, branch, status):
    current = {p['id'] for p in view.get('sources', []) if p['branch_id'] == branch['id']}
    history = {b['id'] for b in view['basis'] if b.get('branch_id') == branch['id']}
    if not view.get('completion_contract'):
        return history
    if status == 'ADOPT':
        return current & history
    if status == 'KEEP':
        return history & (current | set(branch.get('adopted_basis_refs', [])))
    return history


def progress_signature(state):
    return digest({'binding': state['binding'], 'issues': state.get('issues'),
        'delivered': sorted((b['id'], b.get('scope_id')) for b in state['basis_history'].values()),
        'acquired': sorted((k, digest(r['offer'])) for k, r in state['selected'].items()),
        'decisions': sorted((gid, issue, d['status'], tuple(sorted(d.get('basis_refs', []))))
            for gid, g in state['groups'].items() for issue, d in g.get('issue_decisions', {}).items()),
        'queries': state.get('query_history'), 'query_keys': state.get('query_keys'),
        'candidate_pages': [state.get('law_page'), state.get('article_pages'), state.get('hit_pages'),
                            state.get('structure_page'), state.get('structure_location')],
        'structure_queries': state.get('structure_search_history')})



def rule_schema(evidence_ids, facts):
    """Request-local model observation; never a new legal source schema."""
    text = {'type':'string','minLength':1}
    conditions = obj({'id':{'type':'string','pattern':'^T[1-9][0-9]*$'},
        'text':text,'evidence_refs':refs(evidence_ids,1)})
    groups = obj({'id':{'type':'string','pattern':'^G[1-9][0-9]*$'},
        'mode':{'type':'string','enum':['ALL','ANY','UNKNOWN']},
        'members':{'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,
                   'items':{'type':'string','pattern':'^[TG][1-9][0-9]*$'}}})
    fact_ids=[x['id'] for x in facts]
    rule = obj({
        'kind':{'type':'string','enum':['GENERAL_RULE','CASE_APPLICATION']},
        'subject':text,'action':text,'scope':text,'conclusion':text,
        'conditions':{'type':'array','maxItems':16,'items':conditions},
        'groups':{'type':'array','maxItems':16,'items':groups},
        'root':{'type':['string','null']},
        'exceptions':{'type':'array','maxItems':12,'items':obj({'text':text,'evidence_refs':refs(evidence_ids,1)})},
        'exception_status':{'type':'string','enum':['SOURCE_EXCEPTIONS','NOT_ESTABLISHED']},
        'fact_refs':{'type':'array','items':obj({'id':{'type':'string', **({'enum':fact_ids} if fact_ids else {})},'quote':text}), **({} if fact_ids else {'maxItems':0})}
    })
    # Full alternatives bind the redundant state to its evidence list before
    # generation. The model still chooses the exceptions and their sources.
    branches=[]
    for status,bounds in [('SOURCE_EXCEPTIONS',{'minItems':1}),('NOT_ESTABLISHED',{'maxItems':0})]:
        branch=deepcopy(rule)
        branch['properties']['exception_status']={'type':'string','const':status}
        branch['properties']['exceptions'].update(bounds)
        branches.append(branch)
    return {'anyOf':[{'type':'null'},*branches]}


def rule_errors(claim, facts=None):
    rule=claim['rule'];errors=[]
    atoms={x['id']:x for x in rule['conditions']};groups={x['id']:x for x in rule['groups']}
    if len(atoms)!=len(rule['conditions']) or len(groups)!=len(rule['groups']):
        errors.append('condition/group IDs must be unique')
    allowed=set(claim['evidence_refs'])
    if any(not set(x['evidence_refs'])<=allowed for x in [*rule['conditions'],*rule['exceptions']]):
        errors.append('conditions and exceptions require this claim original span references')
    seen=set()
    def visit(key,stack=()):
        if key in stack or len(stack)>4:
            errors.append('condition group cycle or depth exceeds 4');return
        seen.add(key)
        if key in atoms:return
        if key not in groups:errors.append('unknown condition/group reference');return
        for child in groups[key]['members']:visit(child,(*stack,key))
    if rule['root'] is not None:visit(rule['root'])
    if set(atoms)|set(groups)!=seen:errors.append('every condition/group must be reachable from root')
    if bool(rule['exceptions']) != (rule['exception_status']=='SOURCE_EXCEPTIONS'):
        errors.append('exception_status must be SOURCE_EXCEPTIONS when exceptions is nonempty; an empty list requires NOT_ESTABLISHED, never a no-exception assertion')
    if rule['kind']=='GENERAL_RULE' and rule['fact_refs']:
        errors.append('general rule must not assert user facts')
    if rule['kind']=='CASE_APPLICATION' and not rule['fact_refs']:
        errors.append('case application requires actual user fact provenance')
    if facts is not None:
        by_id={x['id']:x['text'] for x in facts}
        for ref in rule['fact_refs']:
            if ref['id'] not in by_id or ref['quote'] not in by_id[ref['id']]:
                errors.append('user fact quote absent from current request/facts')
    return errors


def render_rule(rule):
    atoms={x['id']:x for x in rule['conditions']};groups={x['id']:x for x in rule['groups']}
    def render_node(key):
        if key in atoms:return atoms[key]['text']
        g=groups[key];items=[render_node(k) for k in g['members']]
        prefix={'ALL':'다음 요건을 모두 충족: ','ANY':'다음 요건 중 하나 이상 충족: ','UNKNOWN':'요건 사이의 관계 미확인: '}[g['mode']]
        return '('+prefix+'; '.join(items)+')'
    text=rule['subject']+' · '+rule['action']+' · '+rule['scope']+'\n'+rule['conclusion']
    if rule['root'] is not None:text+='\n적용 조건: '+render_node(rule['root'])
    if rule['exceptions']:text+='\n원문상 예외: '+'; '.join(x['text'] for x in rule['exceptions'])
    else:text+='\n예외 적용 여부는 확인되지 않았습니다.'
    if rule['fact_refs']:text+='\n사용자가 제공한 전제: '+'; '.join(x['quote'] for x in rule['fact_refs'])
    return text
