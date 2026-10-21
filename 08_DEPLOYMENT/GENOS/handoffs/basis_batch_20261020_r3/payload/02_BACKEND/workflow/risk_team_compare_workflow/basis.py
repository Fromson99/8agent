from .contracts import BASIS, check_citations, check_sides, evidence_map
from copy import deepcopy


def child_gap_requirements(state):
    """Carry current committed child shortages through the parent boundary.

    A model may interpret originals but cannot erase an unresolved material
    shortage from the child which supplied them. Joins use the host's explicit
    parent issue mapping; positional or label-based guesses are forbidden.
    """
    issue_ids={issue['id'] for issue in state['scope']['issues']}
    concept_children={}
    for issue in state['scope']['issues']:
        parent=issue.get('concept',{}).get('request_issue_id')
        if parent:concept_children.setdefault(parent,set()).add(issue['id'])
    blocked=set();gaps=[];audit=[];unknown=0
    kinds={'UNREAD_SAVED':'PARTIAL_PROVISION','MISSING_SOURCE':'PARTIAL_PROVISION',
        'UNRESOLVED_REFERENCE':'MISSING_REFERENCE','WRONG_SUBJECT':'QUERY_SCOPE',
        'MISSING_FACT':'QUERY_SCOPE','VERSION_AMBIGUOUS':'UNKNOWN_VERSION'}
    research_actions={'VIEW_SAVED_SOURCE','READ_SCOPE','FOLLOW_CONNECTION','RETURN_TO','RESEARCH'}
    for side,result in sorted(state.get('rag_results',{}).items()):
        bundle=result.get('bundle') or {}
        for original in bundle.get('gaps',[]):
            refs=set(original.get('parent_issue_refs',[]))
            mapped=refs & issue_ids
            for ref in refs:mapped.update(concept_children.get(ref,set()))
            unresolved_mapping=bool(original.get('unmapped_child_issue_refs')) or bool(refs-issue_ids-set(concept_children)) or not mapped
            material=original.get('material') is True
            audit.append({'side':side,'run_id':result.get('run_id'),'bundle_hash':bundle.get('bundle_hash'),
                'parent_issue_refs':sorted(mapped),'mapping_complete':not unresolved_mapping,
                'material':material,'original_gap':deepcopy(original)})
            if not material:
                continue  # Optional references remain in audit, not blocking gaps.
            if unresolved_mapping:
                unknown+=1
                continue
            blocked.update(mapped)
            kind=(('INTERNAL_SCOPE' if side=='internal' else 'EXTERNAL_SCOPE')
                  if original['kind']=='MISSING_SCOPE' else kinds.get(original['kind'],'PARTIAL_PROVISION'))
            action=None
            target=original.get('missing_target')
            if (original['kind'] not in ('MISSING_FACT','VERSION_AMBIGUOUS') and
                    original.get('suggested_action') in research_actions and isinstance(target,str) and target.strip()):
                source_ids=set((original.get('target_binding') or {}).get('source_ids',[]))
                context=[]
                for ident,origins in (bundle.get('origin_refs') or {}).items():
                    if ident in bundle.get('evidence_ids',[]) and any(
                            origin.get('receipt',{}).get('source_id') in source_ids for origin in origins):
                        context.append(ident)
                action={'side':side,'question':target,'reason':'자식 조사에 남은 원문 대상을 기존 조사 기록에서 확인합니다.',
                        'context_evidence':sorted(context)}
            for ident in sorted(mapped):
                # Original reasons/targets stay in the bound audit record above;
                # this parent obligation is a state observation, not a finding.
                gap={'issue_id':ident,'kind':kind,
                    'reason':'자식 조사에 해결되지 않은 필수 확인 사항이 남아 있습니다.',
                    'action':deepcopy(action)}
                if gap not in gaps:gaps.append(gap)
    for side,attempt in state.get('rag_attempts',{}).items():
        if attempt.get('status')!='failed':continue
        affected={r['task']['issue_id'] for r in state.get('task_board',{}).get('tasks',{}).values()
            if r['task']['target_side']==side and r['status'] in ('FAILED','RUNNING')} or issue_ids
        blocked.update(affected)
        gaps.extend({'issue_id':i,'kind':'TOOL_FAILURE','reason':'추가 조사가 실패하여 기존 확인 내용만 보존합니다.','action':None} for i in sorted(affected))
    for row in state.get('task_board',{}).get('rows',{}).values():
        item=row['current']
        if item is None or any(item[s]['status']!='CONFIRMED' or not item[s]['scope_sufficient'] for s in ('internal','external')):
            blocked.add(row['issue_id'])
            gap={'issue_id':row['issue_id'],'kind':'PARTIAL_PROVISION','reason':'필수 비교 항목의 원문·조건·예외 또는 상충 검토가 완료되지 않았습니다.','action':None}
            if gap not in gaps:gaps.append(gap)
    if unknown:
        # No reliable join means the affected issue is unknown. Preserve that
        # provenance failure explicitly rather than assigning a guessed issue.
        blocked.update(issue_ids)
        gaps.extend({'issue_id':ident,'kind':'QUERY_SCOPE',
            'reason':'미완료 자식 조사 기록과 부모 쟁점의 연결을 확인하지 못했습니다.','action':None}
            for ident in sorted(issue_ids))
    return {'gaps':gaps,'blocked_issue_ids':sorted(blocked),
            'unmapped_material_gap_count':unknown,'audit':audit}


def validate(value, evidence, issues, as_of):
    sources=evidence_map(evidence);seen=set()
    issue_ids={i['id'] for i in issues}
    for pair in value['pairs']:
        if pair['pair_id'] in seen or pair['issue_id'] not in issue_ids:
            raise ValueError('duplicate pair or unknown issue')
        seen.add(pair['pair_id'])
        check_sides(pair['internal'],'internal',sources)
        check_sides(pair['external'],'external',sources)
        content=pair.get('content_citations',[])
        check_citations(content,sources)
        content_ids={c['evidence'] for c in content}
        if content_ids-set(pair['internal']+pair['external']):raise ValueError('content comparison cites outside its pair')
        if pair.get('content_difference') and (not content_ids.intersection(pair['internal']) or not content_ids.intersection(pair['external'])):
            raise ValueError('content difference needs both original sides')
        app=pair['applicability']
        check_citations(app['citations'],sources)
        if app['as_of'] != as_of: raise ValueError('applicability date differs from request')
        path=pair['basis_path']
        for edge in path:
            if edge['from_evidence'] not in sources or edge['to_evidence'] not in sources:
                raise ValueError('unknown basis path endpoint')
            check_citations([edge['citation']],sources)
            if edge['citation']['evidence'] != edge['from_evidence']:
                raise ValueError('basis witness must belong to its citing source')
        # Relation, applicability and material sufficiency are model judgments.
        # Exact witnesses/endpoints remain checked; no inferred legal approval.
    for gap in value['gaps']:
        if gap['issue_id'] not in issue_ids:raise ValueError('unknown gap issue')
        if gap['action'] is not None:
            check_sides(gap['action'].get('context_evidence',[]),gap['action']['side'],sources)


def assess(ctx, state):
    from ..presentation import packets, checkpoint
    inherited=child_gap_requirements(state)
    blocked=set(inherited['blocked_issue_ids'])
    # Only the latest current child bundles decide the active requirements.
    # Earlier bundles and failures remain in their immutable export journals.
    if state.get('basis_child_gaps')!=inherited['audit']:
        state['basis_child_gaps']=inherited['audit']
        if state.get('retained_pairs'):
            state['retained_pairs']=[p for p in state['retained_pairs'] if p['issue_id'] not in blocked]
        ctx.repo.save(state)
    if not ctx.request['use_llm']:
        return {'pairs':[],'gaps':[{'issue_id':i['id'],'kind':'UNKNOWN_VERSION',
            'reason':'모델 미사용으로 근거 관계와 적용 범위를 판정하지 않았습니다.','action':None} for i in state['scope']['issues']]+inherited['gaps'],
            'summary':'확보 원문만 제시합니다. 근거 관계·부합·상충은 미확인입니다.'}
    results=[]
    for data,evidence in packets(ctx,state,'BASIS'):
        complete=data['packet']['dependency_closure_complete']
        data['child_gap_constraints']={k:inherited[k] for k in ('blocked_issue_ids','unmapped_material_gap_count')}
        def checked(value):
            validate(value,evidence,state['scope']['issues'],ctx.request['as_of'])
            if {'internal','external'} <= {e['side'] for e in evidence} and not value['pairs'] and not value['gaps'] and not inherited['gaps']:
                raise ValueError('both sides require a content pair or a specific unresolved comparison gap')
        value=ctx.model.decide('BASIS',data,BASIS,
            '내규와 외규의 내용상 대응 짝을 먼저 만들고 근거 관계·적용 범위를 검토하라. '
            'content_difference에 양쪽 원문에서 확인한 내용 차이를 쓰고 content_citations로 양측의 최소한의 결정 근거를 연결하라. 비교할 수 없으면 빈 문자열과 빈 목록을 둔다. 부합·상충 판정은 다음 비교 단계가 담당한다. 직접 인용은 내규→외규 원문 경로, 간접은 연속 경로가 필요하다. '
            '명시 인용 없이 내용이 대응하면 CONTENT_ONLY로 비교할 수 있다. 기준일·판본 미확인은 applicability에 설명한다. '
            '실제 원문 sources만 인용하며 법률 부재를 추정하지 마라. 숫자·산식 부족은 MISSING_NUMERIC이다. '
            '현재 source_complete=false인 인용의 조건·예외·참조 문맥이 더 필요하면 gaps.action.context_evidence에 해당 근거 ID를 넣어라. '
            '이미 읽은 해당 원문을 먼저 확인하며 부족하면 같은 쪽 RAG가 추가 조사한다. 의미가 다른 규정도 필요하면 양측 근거와 차이를 보존하라. '
            '자식의 부족 기록과 원문 범위를 참고해 비교 가능 여부를 직접 판단한다. 부족 기록이 남았다는 이유만으로 모든 내용 비교를 보류하지 않는다. '
            '판본 메타데이터가 없다는 사유만으로 반복 원문 조사를 요청하지 마라.',checked)
        checked(value)
        value=deepcopy(value)
        value['gaps'].extend(deepcopy(g) for g in inherited['gaps'] if g not in value['gaps'])
        checkpoint(ctx,state,'BASIS',data,value)
        if data['packet']['count']>1:
            for p in value['pairs']:p['pair_id']='packet-'+str(data['packet']['index'])+':'+p['pair_id']
            value['gaps'].extend({'issue_id':i['id'],'kind':'PARTIAL_PROVISION',
                'reason':'입력 분할로 전체 조건·예외·상충 관계의 동시 확인이 끝나지 않았습니다.','action':None} for i in state['scope']['issues'])
        results.append(value)
    pairs=[];gaps=[]
    for value in results:
        pairs.extend(value['pairs'])
        for g in value['gaps']:
            if g not in gaps:gaps.append(g)
    return {'pairs':pairs,'gaps':gaps,'summary':'\n'.join(v['summary'] for v in results)}


def from_items(ctx,state):
    """Route field-selected originals to comparison, without another approval."""
    from ..presentation import evidence,source_context
    from ..contracts import digest
    ids={c['evidence'] for row in state['task_board']['rows'].values() if row['current']
        for side in ('internal','external')
        for observation in [row['current'][side]]+row['current'][side].get('alternatives',[])
        for c in observation['citations']+observation['dependencies']}
    from . import concepts
    sources=concepts.originals(ctx,state) if concepts.enabled(ctx) else evidence(ctx,state)
    by=evidence_map(sources);pairs=[];gaps=[]
    for issue in state['scope']['issues']:
        selected={'internal':[],'external':[]}
        anchors=issue.get('concept',{}).get('internal_citations',[])
        check_citations(anchors,by)
        check_sides(list(dict.fromkeys(c['evidence'] for c in anchors)),'internal',by)
        selected['internal'].extend(anchors)
        for row in state['task_board']['rows'].values():
            if row['issue_id']!=issue['id'] or not row['current']:continue
            for side in selected:
                value=row['current'][side]
                # Earlier grounded observations survive a later incomplete review.
                for observation in [value]+value.get('alternatives',[]):
                    citations=observation['citations']+observation['dependencies']
                    check_citations(citations,by)
                    check_sides(list(dict.fromkeys(c['evidence'] for c in citations)),side,by)
                    selected[side].extend(c for c in citations if c not in selected[side])
                if value.get('missing'):
                    gaps.append({'issue_id':issue['id'],'kind':'PARTIAL_PROVISION',
                        'reason':side+' / '+row['field']+': '+value['missing'],'action':None})
        if not all(selected.values()):continue
        pairs.append({'pair_id':'items-'+digest(issue['id'])[:24],'issue_id':issue['id'],
            **{side:sorted(source_context(ctx,state,{c['evidence'] for c in selected[side]},issue['id'])) for side in selected},
            'applicability':{'status':'UNKNOWN','reason':'적용 범위와 의미는 비교 단계에서 검토합니다.','citations':[],'as_of':ctx.request['as_of']},
            'basis_relation':'CONTENT_ONLY','basis_path':[],'comparison_eligibility':True,
            'reason':'항목 검토에서 선택한 양측 원문입니다. 실제 대응 관계와 차이는 직접 판단합니다.',
            'content_difference':'','content_citations':selected['internal']+selected['external']})
    inherited=child_gap_requirements(state)
    state['basis_child_gaps']=inherited['audit']
    # Keep child shortages as observations, not a second permission gate.
    for row in inherited['audit']:
        original=row['original_gap']
        for issue in row['parent_issue_refs']:
            gap={'issue_id':issue,'kind':'PARTIAL_PROVISION',
                'reason':row['side']+' 조사 메모: '+str(original.get('reason') or original.get('missing_target') or '미확인 사항'), 'action':None}
            if gap not in gaps:gaps.append(gap)
    result={'pairs':pairs,'gaps':gaps,'summary':'항목별로 선택한 원문을 직접 비교합니다. 미확인 사항은 판단의 한계로 남깁니다.'}
    validate(result,sources,state['scope']['issues'],ctx.request['as_of'])
    ctx.repo.save(state)
    return result
