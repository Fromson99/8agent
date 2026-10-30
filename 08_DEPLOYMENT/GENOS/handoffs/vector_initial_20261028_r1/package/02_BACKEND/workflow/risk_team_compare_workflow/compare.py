from .contracts import COMPARE, DIMENSIONS, check_citations, evidence_map


def validate(value, evidence, basis, issues):
    sources=evidence_map(evidence);pairs={p['pair_id']:p for p in basis['pairs']}
    numeric_issues={i['id'] for i in issues if i['numeric']}
    seen=set()
    for row in value['rows']:
        if row['pair_id'] in seen:raise ValueError('duplicate comparison row')
        seen.add(row['pair_id'])
        pair=pairs.get(row['pair_id'])
        if pair is None:raise ValueError('unknown comparison pair')
        check_citations(row['citations'],sources)
        citations={c['evidence'] for c in row['citations']}
        if citations-set(pair['internal']+pair['external']):
            raise ValueError('comparison cites evidence outside its assessed pair')
        if row['verdict']!='DEFERRED' and (
                not citations.intersection(pair['internal']) or not citations.intersection(pair['external'])):
            raise ValueError('substantive judgment needs both original sides')
        for dimension in row['dimensions']:
            check_citations(dimension['citations'],sources)
            if {c['evidence'] for c in dimension['citations']}-set(pair['internal']+pair['external']):
                raise ValueError('dimension cites evidence outside assessed pair')
        # Scope, exceptions, numerical meaning and the verdict are the LLM's
        # review. An incomplete inventory is not a reason to discard that review.


def deferred(pair,issues,reason=None,*,evidence=None,citations=None):
    """Publish literal observations and gate states, never a proposed absence.

    Free-text reasons remain in the model journal/basis audit. A DEFERRED row
    has not established their legal meaning, even when its quotes are exact.
    """
    issue=next(i for i in issues if i['id']==pair['issue_id'])
    if citations is None:
        citations=pair.get('content_citations',[]) or pair['applicability']['citations']
    allowed=set(pair['internal']+pair['external'])
    selected=[];seen=set()
    for citation in citations:
        key=(citation['evidence'],citation['quote'])
        if citation['evidence'] in allowed and key not in seen:
            selected.append(dict(citation));seen.add(key)
    citations=selected
    observations=[]
    for side,label in (('external','외규'),('internal','내규')):
        quoted=list(dict.fromkeys(c['evidence'] for c in citations if c['evidence'] in pair[side]))
        observations.append(label+' 확인 원문: '+(', '.join('['+ident+']' for ident in quoted) if quoted else '이 비교행에 선택된 원문 인용이 없습니다.'))
    reasons=[]
    if not pair['comparison_eligibility']:
        reasons.append('비교에 필요한 조건 확인이 끝나지 않았습니다.')
    if pair['basis_relation'] not in ('DIRECT','INDIRECT'):
        reasons.append('내규와 외규를 연결하는 명시 근거 관계가 확인되지 않았습니다.')
    if pair['applicability']['status']!='MATCH':
        reasons.append('양측 규정의 적용 범위·기준일 확인이 끝나지 않았습니다.')
    if evidence is not None:
        sources=evidence_map(evidence)
        required=allowed|{edge[k] for edge in pair.get('basis_path',[]) for k in ('from_evidence','to_evidence')}
        if any(i not in sources or not sources[i].get('source_complete') for i in required):
            reasons.append('필요한 원문 전체 범위의 확인이 끝나지 않았습니다.')
        if any(i not in sources or not sources[i].get('version_verified') for i in required):
            reasons.append('선택 판본의 기준일 유효성이 확인되지 않았습니다.')
    if reason=='MODEL_REPAIR_EXHAUSTED':
        reasons.append('해당 비교 판단의 수정 한도를 소진했습니다.')
    elif reason=='DEPENDENCY_INCOMPLETE':
        reasons.append('필수 원문과 참조 관계를 함께 확인하지 못했습니다.')
    reasons.append('확인한 원문 문구만 제시하며 부합·상충 판단은 보류합니다.')
    return {'rows':[{'pair_id':pair['pair_id'],'item':issue['label'],'verdict':'DEFERRED',
        'difference':'\n'.join(observations),'reason':' '.join(reasons),'citations':citations,
        'numeric':issue['numeric'],'dimensions':[],'unresolved':reasons}],
        'answer':'확인된 원문과 미완료 상태를 보존했습니다.','unresolved':reasons}


def compare(ctx,state):
    from ..contracts import digest,WorkflowError
    from ..presentation import packets,checkpoint
    basis=state['basis']
    if not ctx.request['use_llm'] or not basis['pairs']:
        return {'rows':[],'answer':'확보한 자료만으로는 내규와 외규의 근거 관계 및 부합 여부를 확정할 수 없습니다.',
                'unresolved':['확인된 양측 원문으로 구성된 비교 항목이 없습니다.']}
    # Rows become durable before the next independent pair starts. A failure
    # cannot discard accepted rows from previous pairs. Replays revalidate them.
    field_reviews=[{'issue_id':r['issue_id'],'field':r['field'],'observation':r['current']}
                   for r in state.get('task_board',{}).get('rows',{}).values() if r.get('current')]
    binding=digest([basis,state['scope'],field_reviews,{s:r.get('bundle_hash') or r.get('bundle',{}).get('bundle_hash')
                                      for s,r in state.get('rag_results',{}).items()}])
    progress=state.setdefault('comparison_progress',{'binding':binding,'completed':{}})
    if progress['binding']!=binding:
        raise WorkflowError('WORKFLOW_STALE_COMPARISON','비교 대상이 바뀐 이전 결과를 재사용할 수 없습니다.',409)
    rows=[];unresolved=[]
    def persist():
        state['comparison']={'rows':list(rows),'answer':'검증된 비교행과 남은 확인 사항을 반환합니다.',
                             'unresolved':list(dict.fromkeys(unresolved))}
        ctx.repo.save(state)
    for pair in basis['pairs']:
        ids=set(pair['internal']+pair['external'])
        ids.update(e[k] for e in pair['basis_path'] for k in ('from_evidence','to_evidence'))
        one={'pairs':[pair],'gaps':[g for g in basis['gaps'] if g['issue_id']==pair['issue_id']], 'summary':pair['reason']}
        focus={'issue':next(i for i in state['scope']['issues'] if i['id']==pair['issue_id']),
               'field_reviews':[r for r in field_reviews if r['issue_id']==pair['issue_id']]}
        for data,evidence in packets(ctx,state,'COMPARE:'+pair['pair_id'],ids=ids,basis=one,extra={'comparison_focus':focus}):
            key=digest([pair['pair_id'],data['packet']])
            def checked(value):
                validate(value,evidence,one,state['scope']['issues'])
                if {r['pair_id'] for r in value['rows']} != {pair['pair_id']}:
                    raise ValueError('each supplied pair requires one comparison or DEFERRED row')
            old=progress['completed'].get(key)
            if old:
                if digest(old['result'])!=old['hash']:
                    raise WorkflowError('WORKFLOW_COMPARISON_HASH_MISMATCH','저장된 비교 결과의 해시가 다릅니다.',409)
                value=old['result']
                if value['rows']:checked(value)
            else:
                try:
                    value=ctx.model.decide('COMPARE',data,COMPARE,
                        'comparison_focus.issue의 요청 항목을 양쪽 원문으로 비교하라. item은 그 쟁점을 유지하며, 도입부의 설치·정의 설명으로 다른 요청 항목을 대신하지 않는다. '
                        'field_reviews와 gaps는 이전 의견이다. 현재 sources에 이미 확보된 내용이면 미확보 의견을 바로잡고 그 원문을 직접 검토한다. '
                        '단서·예외가 수식하는 주체·행위·항·호를 구분하라. 일부 항목에만 붙은 제한을 조 전체나 다른 항목에 확대하지 않는다. 적용 사실 미확인은 조건부 설명으로 남긴다. '
                        '근거 관계, 적용 범위, 기존 부족 기록은 참고 사항이며 의미 판단은 직접 한다. '
                        '명시 인용 관계가 없어도 내용상 대응하는 규정은 비교할 수 있다. '
                        '수치는 이번 판단에 필요한 차원만 검토한다. 확인되지 않은 조건·예외·판본은 이유나 unresolved에 남긴다. '
                        '확인한 범위에서 부합/내부 추가기준/상충/미비 후보를 판단하고, 판단 자체가 어려울 때만 DEFERRED로 둔다. '
                        '문구 차이 자체는 상충이 아니다. 미확보를 규정 부재로 단정하지 않는다. '
                        'citations에는 실제 제공된 양측 원문을 선택한다. DEFERRED여도 이해 가능한 설명을 남긴다.',checked)
                except WorkflowError as exc:
                    if exc.code!='WORKFLOW_REPAIR_EXHAUSTED':raise
                    value=deferred(pair,state['scope']['issues'],'MODEL_REPAIR_EXHAUSTED',evidence=evidence)
                    checked(value)
            progress['completed'][key]={'result':value,'hash':digest(value)}
            checkpoint(ctx,state,'COMPARE:'+pair['pair_id'],data,value)
            rows.extend(value['rows']);unresolved.extend(value['unresolved']);persist()
    return state['comparison']
