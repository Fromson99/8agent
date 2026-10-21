"""Internal originals define comparison units before external investigation."""
from copy import deepcopy
from ..contracts import digest, WorkflowError
from .contracts import obj, text, array, choice, CITATION, ISSUE, check_citations

CONTRACT = 'internal-concept-comparison-v1'


def enabled(ctx):
    return ctx.definition.manifest.get('comparison_anchor_contract') == CONTRACT


def originals(ctx, state):
    from ..presentation import evidence, active_ids
    active=active_ids(state)
    return evidence(ctx,state,active | {i for i,root in state.get('packet_evidence',{}).items() if root in active})


def contract(issues, existing, remaining):
    concept = obj(
        existing_id={'enum': [c['id'] for c in existing] + [None]},
        request_issue_id=choice(*(i['id'] for i in issues)),
        label=text(1000), definition=text(2000), scope_reason=text(2000),
        internal_citations=array(CITATION, 1, 100),
        external_task=text(1000), external_queries=array(text(180), 1, 4),
        numeric={'type': 'boolean'},
        work_type=deepcopy(ISSUE['properties']['work_type']),
        requested_fields=deepcopy(ISSUE['properties']['requested_fields']))
    concept['properties']['requested_fields']['minItems'] = 1
    return obj(concepts=array(concept, 0, max(remaining + len(existing), 1)),
               unresolved=array(text(2000), 0, 24))


def validate(value, sources, issues, existing):
    by = {e['evidence_id']: e for e in sources}
    parents = {i['id'] for i in issues}
    old = {c['id']: c for c in existing}
    targets = []
    for row in value['concepts']:
        check_citations(row['internal_citations'], by)
        if any(by[c['evidence']]['side'] != 'internal' for c in row['internal_citations']):
            raise ValueError('concept must be anchored in internal originals')
        if row['request_issue_id'] not in parents:
            raise ValueError('concept outside user question issues')
        if len(set(row['requested_fields'])) != len(row['requested_fields']):
            raise ValueError('duplicate concept fields')
        ident = row['existing_id']
        if ident is not None:
            if ident not in old or old[ident]['request_issue_id'] != row['request_issue_id']:
                raise ValueError('concept extension changed request issue')
            targets.append(ident)
    if len(targets) != len(set(targets)):
        raise ValueError('duplicate concept extension')
    if len(existing) + sum(c['existing_id'] is None for c in value['concepts']) > 12:
        raise ValueError('concept count exceeds child task contract')


def prepare(ctx, state):
    from ..presentation import evidence, packets, checkpoint
    originals = [e for e in evidence(ctx, state) if e['side'] == 'internal']
    question_scope = state.setdefault('question_scope', deepcopy(state['scope']))
    binding = digest([question_scope, originals])
    plan = state.setdefault('concept_plan', {
        'schema_version': CONTRACT, 'binding': binding, 'concepts': [],
        'completed_packets': [], 'unresolved': [], 'status': 'RUNNING'})
    if plan['binding'] != binding:
        raise WorkflowError('WORKFLOW_CONCEPT_BINDING', '개념 검토 중 내규 원문 결속이 바뀌었습니다.', 409)
    if plan['status'] != 'RUNNING':
        return bool(plan['concepts'])
    if not originals or not ctx.request['use_llm']:
        plan['status'] = 'NO_INTERNAL_ORIGINALS' if not originals else 'MODEL_DISABLED'
        plan['unresolved'].append('내규 원문 미확보' if not originals else '모델 미사용: 내규 개념 범위 검토 미수행')
    else:
        for data, visible in packets(ctx, state, 'CONCEPTS', ids=[e['evidence_id'] for e in originals]):
            key = digest(data['packet'])
            if key in plan['completed_packets']:
                continue
            data = {k: data[k] for k in ('question', 'as_of', 'sources', 'budget', 'deadline_at', 'packet')}
            data.update(request_issues=question_scope['issues'],
                        existing_concepts=deepcopy(plan['concepts']),
                        remaining_concepts=12-len(plan['concepts']))
            schema = contract(question_scope['issues'], plan['concepts'], data['remaining_concepts'])
            value = ctx.model.decide('CONCEPTS', data, schema,
                '사용자 질문에 답하기 위해 실제 찾은 내규 원문을 개념 단위로 묶는다. '
                '개념의 이름·정의·포함 범위와 그 이유를 직접 판단한다. 장·절·조·항·호·별표 중 '
                '필요한 범위를 선택하되 읽지 않은 상하위 조항 전체를 읽었다고 하지 않는다. '
                '같은 개념에 필요한 정의·조건·예외는 함께 묶고, 다른 의무는 별도 개념으로 나눈다. '
                'internal_citations에는 이 개념의 정확한 내규 원문 범위를 선택한다. 문서명·위치는 시스템이 연결한다. '
                'external_task와 external_queries는 이 내규의 명시 참조·위임·정의·적용 조건에 대응하는 '
                '외규 원문을 찾는 과제다. 질문만 보고 독립된 외규 주제를 만들거나 정답 조문을 추측하지 않는다. '
                '명시 참조가 없으면 내용상 대응 조사임을 설명한다. requested_fields는 이 개념의 대사에 필요한 것만 선택한다. '
                '이전 묶음의 같은 개념이면 existing_id를 선택해 범위를 확장한다. 새로운 개념만 null로 낸다. '
                '이번 원문과 관계없는 질문은 억지로 묶지 말고 unresolved에 남긴다. '
                '범위 판단의 불확실성은 scope_reason과 unresolved에 설명하고 확인한 원문을 보존한다.',
                lambda v: validate(v, visible, question_scope['issues'], plan['concepts']))
            for row in value['concepts']:
                item = deepcopy(row)
                ident = item.pop('existing_id')
                if ident is None:
                    ident = 'concept-' + str(len(plan['concepts']) + 1)
                    plan['concepts'].append({'id': ident, **item})
                else:
                    old = next(c for c in plan['concepts'] if c['id'] == ident)
                    refs = old['internal_citations'] + item['internal_citations']
                    item['internal_citations'] = list({(c['evidence'], c['quote']): c for c in refs}.values())
                    old.update(item)
            plan['unresolved'] = list(dict.fromkeys(plan['unresolved'] + value['unresolved']))
            plan['completed_packets'].append(key)
            checkpoint(ctx, state, 'CONCEPTS', data, value)
        plan['status'] = 'DEFINED' if plan['concepts'] else 'NO_RELEVANT_CONCEPT'
    if plan['concepts']:
        parents = {i['id']: i for i in question_scope['issues']}
        state['scope'] = {**deepcopy(question_scope), 'issues': [
            {**deepcopy(parents[c['request_issue_id']]), 'id': c['id'], 'label': c['label'],
             'numeric': c['numeric'], 'work_type': c['work_type'],
             'requested_fields': c['requested_fields'], 'external_task': c['external_task'],
             'concept': deepcopy(c)} for c in plan['concepts']]}
        # Child contract has four initial search hints; all concept-specific
        # queries remain available in the bound anchor task below.
        state['scope']['external_queries'] = list(dict.fromkeys(
            q for c in plan['concepts'] for q in c['external_queries']))[:4]
        missing = set(parents) - {c['request_issue_id'] for c in plan['concepts']}
        plan['unresolved'].extend(parents[i]['label']+' — 연결할 내규 개념 미확보' for i in sorted(missing))
    state['gaps'].extend(s for s in plan['unresolved'] if s not in state['gaps'])
    ctx.repo.save(state)
    return bool(plan['concepts'])


def anchors(state, sources):
    """Exact parent originals are external search context, never external proof."""
    by = {e['evidence_id']: e for e in sources}
    result = []
    for concept in state.get('concept_plan', {}).get('concepts', []):
        check_citations(concept['internal_citations'], by)
        rows = []
        for citation in concept['internal_citations']:
            e = by[citation['evidence']]
            if e['side'] != 'internal':
                raise WorkflowError('WORKFLOW_CONCEPT_SIDE', '개념의 내규 출처 구분이 다릅니다.', 409)
            rows.append({'evidence_id': e['evidence_id'], 'document_id': e['document_id'],
                         'document_name': e['metadata']['document_name'],
                         'heading': e['metadata'].get('heading', ''), 'quote': citation['quote']})
        result.append({'issue_id': concept['id'], 'definition': concept['definition'],
                       'scope_reason': concept['scope_reason'], 'queries': concept['external_queries'],
                       'sources': rows})
    return result
