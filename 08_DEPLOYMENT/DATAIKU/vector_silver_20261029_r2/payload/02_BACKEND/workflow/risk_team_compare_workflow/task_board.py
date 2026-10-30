"""Versioned issue/field ownership around the existing native RAG workflow."""
from copy import deepcopy
from pathlib import Path
import json
from ..contracts import digest, WorkflowError
from .contracts import obj, text, array, choice, CITATION, check_citations
from . import query_scope, retrieval, basis, compare
from semantic_runtime import research_state as continuity
from semantic_runtime.research_state import (
    ResearchLedger, PRIORITY, pending_tasks, register_task, reconcile_need,
    research_need_view, acquisition_status,
)

VERSION='comparison-research-v1'
CONFIG=json.loads(Path(__file__).with_name('comparison_fields.json').read_text())
SIDE=obj(status=choice('CONFIRMED','PARTIAL','MISSING','CONFLICT'),text={'type':'string'},
         citations=array(CITATION,0,100),dependencies=array(CITATION,0,100),
         scope_sufficient={'type':'boolean'},missing={'type':'string'})
FOLLOW=obj(side=choice('internal','external'),operation=choice('read_node','locate_provision','lookup_definition','follow_reference','search_structure','search_subtree','search_text'),
           locator_id={'type':['string','null']},query=text(),anchor_ids=array(text(),0,100),reason=text())
ITEM=obj(field=choice(*CONFIG['fields']),internal=SIDE,external=SIDE,
         content_status=choice('MATCH','DIFFERENT','UNKNOWN'),difference={'type':'string'},
         next_tasks=array(FOLLOW,0,2))
REVIEW=obj(items=array(ITEM,0,14))


def review_contract(fields,new_ids,incremental):
    schema=deepcopy(REVIEW)
    for side in ('internal','external'):
        schema['properties']['items']['items']['properties'][side]['properties']['need_resolution']=choice('OPEN','RESOLVED')
    follow=schema['properties']['items']['items']['properties']['next_tasks']['items']
    follow['properties'].update(priority=choice(*PRIORITY),priority_reason=text())
    follow['required']+=['priority','priority_reason']
    if incremental:
        schema['properties']['items']['minItems']=0
        item=schema['properties']['items']['items']
        item['required']=[k for k in item['required'] if k not in ('internal','external')]
        item['anyOf']=[{'required':['internal']},{'required':['external']}]
        item['properties']['task_plan_unchanged']={'const':True}
    updates=array(obj(evidence_id=choice(*new_ids) if new_ids else text(),
        disposition=choice('USED','CONTEXT','UNRELATED','UNRESOLVED'),
        fields=array(choice(*fields),0,len(fields)),reason=text()),len(new_ids),len(new_ids))
    # Optional host receipts are deliberately excluded from the model wire.
    updates['items']['properties'].update(declared_disposition=choice('USED'),binding_note=text())
    schema['properties']={'evidence_updates':updates,**schema['properties']}
    schema['required']=['evidence_updates',*schema['required']]
    return schema


def checked_update(value,sources,fields,locators,new_ids,incremental):
    chosen=[i['field'] for i in value['items']]
    if len(chosen)!=len(set(chosen)) or set(chosen)-set(fields):raise ValueError('unknown or duplicate updated field')
    trial=deepcopy(value)
    if incremental:
        for item in trial['items']:
            for side in ('internal','external'):
                item.setdefault(side,{'status':'MISSING','text':'','citations':[],'dependencies':[],
                    'scope_sufficient':False,'missing':'Validation placeholder only; committed prior side is preserved.'})
    checked(trial,sources,chosen if incremental else fields,locators)
    updates=value['evidence_updates']
    if sorted(r['evidence_id'] for r in updates)!=sorted(new_ids):raise ValueError('each newly delivered original needs exactly one disposition')
    for row in updates:
        if len(row['fields'])!=len(set(row['fields'])) or set(row['fields'])-set(fields):raise ValueError('unknown or duplicate affected field')
        if row['disposition']=='USED':
            if not row['fields']:raise ValueError('USED original must name affected fields')
            for field in row['fields']:
                item=next((i for i in value['items'] if i['field']==field),None)
                if not item or not any(c['evidence']==row['evidence_id'] for side in ('internal','external') for c in item.get(side,{}).get('citations',[])):
                    raise ValueError('USED original must be cited in each updated field')


def checked_needs(value,board,issue):
    for item in value['items']:
        for side in ('internal','external'):
            row=item.get(side,{})
            resolution=row.get('need_resolution')
            if resolution is None:continue
            need=board.get('research_needs',{}).get(continuity.need_id(issue,item['field'],side))
            if need is None:raise ValueError('need resolution has no existing field-side need')
            if resolution=='RESOLVED' and (row['missing'].strip() or not row['citations'] or not row['text'].strip()):
                raise ValueError('RESOLVED requires cited originals and reason, with no remaining missing')


def initialize(ctx,state):
    issues=state['scope']['issues'];rows={}
    for issue in issues:
        kind=issue.get('work_type') or ('ratio' if issue['numeric'] and not query_scope.enabled(ctx) else 'general')
        fields=issue.get('requested_fields') or CONFIG['profiles'][kind]
        if len(fields)!=len(set(fields)) or set(fields)-set(CONFIG['fields']):
            raise WorkflowError('WORKFLOW_FIELD_CONTRACT','유효한 비교 항목이 필요합니다.',409)
        issue['work_type']=kind;issue['requested_fields']=fields
        for field in fields:rows[issue['id']+':'+field]={'issue_id':issue['id'],'field':field,'revisions':[],'current':None}
    state['task_board']={'schema_version':VERSION,'config_hash':digest(CONFIG),'rows':rows,'tasks':{},'round':0,'reviewed':[]}
    ctx.repo.save(state)


def sources_for_issue(ctx,state,issue):
    from ..presentation import evidence
    from . import concepts
    values=concepts.originals(ctx,state) if concepts.enabled(ctx) else evidence(ctx,state)
    concept=next((i.get('concept') for i in state['scope']['issues'] if i['id']==issue),None)
    if concept:
        anchors={c['evidence'] for c in concept['internal_citations']}
        calls={r.get('result_request_id') for r in state['task_board']['tasks'].values()
               if r['task']['issue_id']==issue and r['task']['target_side']=='internal'}
        from ..presentation import valid_results
        anchors.update(i for r in valid_results(state) if r.get('request_id') in calls
                       for i in r.get('evidence_ids',[]))
        return [e for e in values if
            (e['side']=='internal' and (e['evidence_id'] in anchors or
                state.get('packet_evidence',{}).get(e['evidence_id']) in anchors)) or
            (e['side']=='external' and (not e['parent_issue_refs'] or issue in e['parent_issue_refs']))]
    # An unassigned source remains visible for semantic classification; it does
    # not acquire a guessed issue link. Known other issues are excluded here.
    return [e for e in values if not e['parent_issue_refs'] or issue in e['parent_issue_refs']]


def checked(value,sources,fields,locators):
    by={e['evidence_id']:e for e in sources}
    # Omission is unfinished review, not an invalid source or a fabricated
    # finding. Keep the unsubmitted row uncommitted for the partial report.
    chosen=[i['field'] for i in value['items']]
    if len(chosen)!=len(set(chosen)) or set(chosen)-set(fields):
        raise ValueError('unknown or duplicate reviewed field')
    for item in value['items']:
        for side in ('internal','external'):
            row=item[side];citations=row['citations']+row['dependencies'];check_citations(citations,by)
            if any(by[c['evidence']]['side']!=side for c in citations):raise ValueError('opposite-side clues cannot prove this side')
        for task in item['next_tasks']:
            if set(task['anchor_ids'])-set(by):raise ValueError('unknown research anchor')
            locator=locators.get(task['locator_id']) if task['locator_id'] else None
            if task['locator_id'] and locator is None:raise ValueError('unknown locator')
            if locator and locator['side']!=task['side']:raise ValueError('target locator belongs to other side')
            if task['operation'] in ('read_node','locate_provision','search_subtree','follow_reference') and not locator:raise ValueError('exact operation requires a verified target')
            if task['operation']=='follow_reference' and not (locator or {}).get('reference_id'):raise ValueError('reference operation requires a witnessed reference locator')


def partial_items(value,sources,fields,locators):
    """Keep independently valid observations; rejected proposals stay rejected."""
    items=[];errors=[]
    def empty():return {'status':'MISSING','text':'','citations':[],'dependencies':[],
        'scope_sufficient':False,'missing':'항목 제안 검증 실패 — 원문 적용 검토 미완료'}
    for field in fields:
        matches=[r for r in value['items'] if r['field']==field]
        safe={'field':field,'internal':empty(),'external':empty(),'content_status':'UNKNOWN','difference':'','next_tasks':[]}
        if len(matches)!=1:
            errors.append({'field':field,'part':'identity','error':'missing or duplicate field'});items.append(safe);continue
        raw=matches[0]
        for side in ('internal','external'):
            trial=deepcopy(safe);trial[side]=raw[side]
            try:checked({'items':[trial]},sources,[field],locators)
            except ValueError as exc:errors.append({'field':field,'part':side,'error':str(exc)})
            else:safe[side]=deepcopy(raw[side])
        trial={**safe,'content_status':raw['content_status'],'difference':raw['difference']}
        try:checked({'items':[trial]},sources,[field],locators)
        except ValueError as exc:errors.append({'field':field,'part':'comparison','error':str(exc)})
        else:
            safe=trial
        for task in raw['next_tasks']:
            trial={**safe,'next_tasks':[task]}
            try:checked({'items':[trial]},sources,[field],locators)
            except ValueError as exc:errors.append({'field':field,'part':'task','error':str(exc)})
            else:safe['next_tasks'].append(deepcopy(task))
        items.append(safe)
    result={'items':items};checked(result,sources,fields,locators)
    return result,errors

def retain_previous(item,old):
    """Keep prior grounded observations without overriding the new judgment."""
    for side in ('internal','external'):
        prior=old[side];new=item[side]
        alternatives=deepcopy(prior.get('alternatives',[]))
        if prior['citations']:
            alternatives.append({k:deepcopy(prior[k]) for k in ('text','citations','dependencies')})
        current={k:new[k] for k in ('text','citations','dependencies')}
        retained=[]
        for alternative in alternatives:
            if alternative!=current and alternative not in retained:retained.append(alternative)
        if retained:new['alternatives']=retained


def review(ctx,state):
    # Locator/packet SQL shares the investigation cutoff with model calls, so
    # a long source read cannot consume the time reserved for the final answer.
    with ctx.rag.port.source_reads(ctx.model.services.phase_context(ctx.context)):
        return _review(ctx,state)


def _review(ctx,state):
    from ..presentation import packets,valid_results
    from importlib import import_module
    native=import_module(ctx.rag.port.services.__class__.__module__.rsplit('.',1)[0]+'.comparison_research_bridge')
    board=state['task_board'];ledger=ResearchLedger(board);general=query_scope.enabled(ctx)
    for issue in state['scope']['issues']:
        values=sources_for_issue(ctx,state,issue['id']);ids=[e['evidence_id'] for e in values]
        lead_catalogue=native.investigation_leads(ctx.rag.port,valid_results(state))
        lead_view=native.lead_view(lead_catalogue)
        queue=list(packets(ctx,state,'ITEMS',ids=ids))
        while queue:
            data,visible=queue.pop(0)
            locators=native.locators(ctx.rag.port,visible,lead_view)
            data={k:data[k] for k in ('question','as_of','sources','budget','deadline_at','packet')}
            data.update(investigation_leads=lead_view,issue=issue,fields={f:CONFIG['fields'][f] for f in issue['requested_fields']},
                        locators=locators,previous=[board['rows'][issue['id']+':'+f]['current'] for f in issue['requested_fields']],
                        attempt_status={s:r['status'] for s,r in state.get('rag_attempts',{}).items()})
            incremental=general and all(r is not None for r in data['previous'])
            new_ids=ledger.new_review_sources(issue['id'],visible) if general else []
            if general:
                data.update(research_requirements=issue.get('requirements',[]),new_evidence_ids=new_ids,
                    review_mode='UPDATE' if incremental else 'INITIAL',
                    unresolved_research=ledger.needs(issue['id'],ctx.definition.manifest['max_recoveries']),
                    research_task_history=continuity.history(board,issue=issue['id']),
                    investigation_budget={'used':ledger.used_followups,'limit':ctx.definition.manifest['max_recoveries']})
                data['sources'].sort(key=lambda e:e['evidence_id'] not in new_ids)
            from ..presentation import projected_size
            if projected_size(data)>ctx.model.services.profile['max_context_chars']-6000:
                if len(visible)<2:raise WorkflowError('WORKFLOW_CONTEXT_UNIT_TOO_LARGE','하나의 항목 원문과 조사 위치가 입력 한도를 초과했습니다.')
                midpoint=len(visible)//2
                for subset in reversed((visible[:midpoint],visible[midpoint:])):
                    selected={e['evidence_id'] for e in subset}
                    fragment={**data,'sources':[e for e in data['sources'] if e['evidence_id'] in selected]}
                    fragment['packet']={**data['packet'],'dependency_closure_complete':False}
                    queue.insert(0,(fragment,subset))
                continue
            input_key=ledger.review_input(issue['id'],data['sources'],data['attempt_status'],lead_view)
            key=digest(['review-state-v2',input_key])
            if not ledger.review_allowed(incremental=incremental,new_ids=new_ids,key=key,input_key=input_key):continue
            if not ctx.request['use_llm']:continue
            instructions=(
                '설정된 항목만 원문으로 대조한다. 항목별 내규·외규의 확인 내용과 조건·예외·표 헤더/단위/주석·명시 참조 의존 원문을 구분한다. '
                '상태와 충분성은 원문을 보고 판단한다. 미확보 이유도 text에 설명할 수 있다. MISSING은 확인하지 못했다는 뜻이며 규정 부재의 증명은 아니다. '
                '부분 원문에서 필요한 조건이나 참조가 빠졌다면 missing에 적고, 인용은 실제로 읽은 근거만 선택한다. '
                '문구 차이는 MATCH/DIFFERENT로 설명할 수 있지만 준수·위반·법적 부합을 확정하지 않는다. 반대쪽 내용과 수치는 해당 쪽의 증거가 아니다. '
                'investigation_leads는 자식이 발견한 조사 위치다. 미리보기는 인용 근거가 아니다. 필요한 후보는 locator_id로 read_node를 선택한다. '
                '연결된 B를 읽고 새 원문이 들어오면 기존 A의 판단도 함께 재검토한다. 미열람·불확실성은 설명하되 이미 확보한 원문은 활용한다. '
                '정말 필요한 추가 원문만 next_tasks에 넣는다. 제공된 locator에서 읽을 위치를 선택하고 조사할 내용을 query에 적는다. 도구와 근거 연결은 시스템이 정한다. '
                '정확 대상이 없으면 locator_id=null이며 원문에 있는 업무·대상·의무를 검색어로 삼는다. 원문 부족을 사용자 사실 부족으로 바꾸지 않는다. '
                '단서·예외가 한정하는 정확한 항목과 그 밖의 항목을 나누어 판단한다. 일부 항목의 주체 제한을 조문 전체로 확대하지 않는다. '
                '이전 확인은 previous에 있다. 현재 sources에서 확보된 원문은 이전 missing보다 우선하며, 이미 확보된 내용을 다시 미확보로 옮기지 않는다. 문장 표현만 달라진 것은 충돌이 아니다. 의미가 양립할 수 없을 때만 CONFLICT로 판단하라. '
            )
            if general:
                instructions+=(query_scope.DEPENDENCY_SCOPE +
                    ' research_requirements의 각 요구에 필요한 원문을 확인한다. '
                    'CORE는 질문의 직접 요구를 답하는 원문, DEPENDENCY는 적용 범위·정의·위임·조건·예외 확인, CONTEXT는 보충 배경이다. '
                    'next_tasks에는 CORE·DEPENDENCY 중 필요한 조사만 제안한다. priority_reason에는 대응하는 질문의 요구와 추가 원문이 어떤 답·적용 판단을 바꿀 수 있는지 구체적으로 쓴다. '
                    'CONTEXT만 보충하려는 조사는 next_tasks에 넣지 않고 설명에 남긴다. 질문의 필수 의존 조사를 CONTEXT로 낮춰 생략하지 않는다. '
                    '필수 조사 중 확인된 정확한 읽기 대상이 광범위 검색보다 먼저 실행된다. 검색 실패·미확보를 규정 부재로 판단하지 않는다. '
                    '종류·대상·업권이 다른 기준을 빈 항목을 채우기 위해 대신 사용하지 않는다. '
                    'INITIAL과 UPDATE 모두 new_evidence_ids의 모든 원문별 evidence_updates를 먼저 판단한다. 이유는 짧은 한 문장으로 쓴다. USED는 해당 원문을 items의 영향받는 항목에서 실제 인용한다. 어느 항목에 쓰였는지의 연결은 시스템이 이 인용에서 조립한다. '
                    'CONTEXT는 기존 판단에 영향을 주지 않는 보충, UNRELATED는 적용 범위가 다른 자료, UNRESOLVED는 영향 판단 미완료이며 각각 이유를 적는다. '
                    'UPDATE의 items에는 새 원문·단서·조사 결과로 내용·인용·부족·추가 조사가 바뀐 항목만 반환한다. 변경이 없으면 items=[]로 답하며 이전 항목은 보존된다. '
                    'UPDATE는 바뀐 쪽마다 field, side(internal 또는 external), status, text, citations, missing을 반환한다. 같은 항목의 양쪽을 바꾸면 side별로 한 번씩 낸다. 기존 internal/external 중첩 양식도 허용한다. 생략한 쪽은 보존한다. '
                    '새 원문이 구체 기준·조건·예외를 제공하면 이를 관련 항목에 반영하고 해당 미확인 문구를 갱신한다. '
                    'INITIAL에서는 요청된 항목을 검토하되 판단하지 못한 항목은 생략할 수 있다. 생략은 검토 미완료로 보존되며 규정 부재나 검토 완료를 뜻하지 않는다. read_only_history는 이전 검토 기록이며 제출 양식이 아니다. '
                    '이전 기록의 원문은 현재 sources와 함께 검토하되 현재 citation_options에서만 인용을 선택한다. '
                    'unresolved_research의 기존 미확보가 해소되면 해당 field·side에 need_resolution=RESOLVED, 원문 인용과 해소 이유(text)를 쓴다. 미해소는 OPEN이며 생략·빈 missing·빈 next_tasks만으로 해소되지 않는다. '
                    'read_only_history와 제출 양식의 판단 이름은 status/text/missing이다. '
                    'research_task_history에서 완료된 동일 원문 요청을 반복하지 않는다. 이미 읽은 원문의 대상이 질문과 다르면 그 원문을 다시 읽기보다 다른 후보나 범위 내 검색으로 필요한 대상을 조사한다. ')
            schema=review_contract(issue['requested_fields'],new_ids,incremental) if general else REVIEW
            def validate(v):
                if general:
                    checked_update(v,visible,issue['requested_fields'],locators,new_ids,incremental)
                    checked_needs(v,board,issue['id'])
                else:checked(v,visible,issue['requested_fields'],locators)
            terminal_error=None
            accepted=False
            policy=ctx.definition.manifest.get('execution_policy',{})
            if policy:
                attempts=board.setdefault('review_attempts',{}).setdefault(issue['id'],[])
                if key not in attempts:
                    if len(attempts)>=policy['max_reviews_per_issue']:
                        raise ctx.model.services.BudgetExhausted('comparison issue review limit reached')
                    attempts.append(key);ctx.repo.save(state)
            try:
                value=ctx.model.decide('ITEMS',data,schema,instructions,validate)
                validate(value);accepted=True
                item_proposals=value['items']
                if not incremental:
                    submitted={i['field'] for i in item_proposals}
                    missing=[f for f in issue['requested_fields'] if f not in submitted
                        and board['rows'][issue['id']+':'+f]['current'] is None]
                    if missing:
                        omission={'issue_id':issue['id'],'input_hash':key,'fields':missing,
                            'evidence_ids':[e['evidence_id'] for e in visible],
                            'status':'NOT_COMPLETED','automatic_retry':False}
                        if omission not in board.setdefault('review_omissions',[]):
                            board['review_omissions'].append(omission)
                            ctx.repo.work.event('WORKFLOW_ITEMS_INCOMPLETE',omission)
            except (WorkflowError,ctx.model.services.BudgetExhausted,ctx.model.services.TransportError) as exc:
                if isinstance(exc,WorkflowError) and exc.code!='WORKFLOW_REPAIR_EXHAUSTED':raise
                if not isinstance(exc,WorkflowError):terminal_error=exc
                rejected=ctx.model.rejected_proposals('ITEMS',data,schema,instructions)
                if not rejected:
                    if general:
                        ledger.quarantine(input_key)
                        board.setdefault('evidence_updates',[]).extend({'issue_id':issue['id'],'input_hash':key,'evidence_id':ident,
                            'disposition':'UNRESOLVED','fields':[],'reason':'갱신 응답 형식 검증 실패 — 원문은 보존했으며 영향 판단은 미완료',
                            'origin':'SYSTEM_FAILURE'} for ident in new_ids)
                        board.setdefault('update_failures',[]).append({'input_hash':key,'code':getattr(exc,'code',type(exc).__name__),
                            'new_evidence_ids':new_ids,'proposal_accepted':False})
                        ctx.repo.save(state)
                    raise
                item_proposals=[]
                ledger.quarantine(input_key)
                for record in rejected:
                    fields=[f for f in issue['requested_fields'] if any(i.get('field')==f for i in record['proposal'].get('items',[]))] if incremental else issue['requested_fields']
                    proposal=deepcopy(record['proposal']);omitted={}
                    if incremental:
                        for item in proposal.get('items',[]):
                            omitted[item['field']]=[s for s in ('internal','external') if s not in item]
                            for side in omitted[item['field']]:
                                item[side]={'status':'MISSING','text':'','citations':[],'dependencies':[],
                                    'scope_sufficient':False,'missing':'Validation placeholder only'}
                    partial,errors=partial_items(proposal,visible,fields,locators)
                    if incremental:
                        for item in partial['items']:
                            for side in ('internal','external'):
                                if side in omitted.get(item['field'],[]) or any(e['field']==item['field'] and e['part']==side for e in errors):item.pop(side,None)
                        partial['items']=[i for i in partial['items'] if 'internal' in i or 'external' in i]
                    if general:
                        for item in partial['items']:item['next_tasks']=[t for t in item['next_tasks'] if t.get('priority') in PRIORITY and t.get('priority_reason')]
                    item_proposals.extend(partial['items'])
                    audit={'input_hash':key,'call_id':record['call_id'],'proposal_hash':digest(record['proposal']),'errors':errors,'partial_hash':digest(partial),'original_proposal_accepted':False}
                    if audit not in board.setdefault('rejected_proposals',[]):board['rejected_proposals'].append(audit)
                ctx.repo.work.event('WORKFLOW_ITEMS_PARTIAL',{'issue_id':issue['id'],'input_hash':key,'rejected_calls':[r['call_id'] for r in rejected],'original_proposals_accepted':False})
                if general:
                    board.setdefault('evidence_updates',[]).extend({'issue_id':issue['id'],'input_hash':key,'evidence_id':ident,
                        'disposition':'UNRESOLVED','fields':[],'reason':'항목 갱신 제안 검증 실패 — 원문은 보존했으며 영향 판단은 미완료','origin':'SYSTEM_FAILURE'} for ident in new_ids)
            for item in item_proposals:
                row=board['rows'][issue['id']+':'+item['field']];old=row['current']
                changed_sides=[side for side in ('internal','external') if side in item]
                keep_tasks=item.pop('task_plan_unchanged',False)
                if incremental:
                    for side in ('internal','external'):
                        if side not in item:item[side]=deepcopy(old[side])
                    if keep_tasks:item['next_tasks']=deepcopy(old['next_tasks'])
                if old:
                    retain_previous(item,old)
                ledger.record_item(issue['id'],item,key)
                selected_tasks=[]
                def compile_proposal(proposed):
                    task=native.compile_task(ctx.rag.port,issue['id'],item['field'],proposed,locators,visible)
                    return ledger.register(task,proposed,general)
                if not keep_tasks:
                    for proposed in item['next_tasks']:selected_tasks.append(compile_proposal(proposed))
                if general and accepted:
                    for side in changed_sides:
                        ledger.reconcile(issue,item['field'],side,item[side],key,selected_tasks,compile_proposal)
            ledger.commit_review(issue['id'],visible,key,accepted=accepted,general=general,
                updates=value['evidence_updates'] if general and accepted else [],input_key=input_key)
            ctx.repo.save(state)
            if terminal_error is not None:raise terminal_error
    # Legal comparison only sees field-linked originals and their dependencies.
    state['review_evidence_ids']=sorted({c['evidence'] for r in board['rows'].values() if r['current']
        for side in ('internal','external') for c in r['current'][side]['citations']+r['current'][side]['dependencies']})
    ctx.repo.save(state)


def acquisition_key(task):
    return continuity.acquisition_key(task)


def research(ctx,state):
    ledger=ResearchLedger(state['task_board'])
    limit=ctx.definition.manifest['max_recoveries']
    while ledger.available(limit):
        pending=ledger.pending(query_scope.enabled(ctx))
        if not pending:break
        record=pending[0];task=record['task'];side=task['target_side']
        if ledger.reuse(record):
            ctx.repo.save(state);return True
        old=state.get('rag_results',{}).get(side,{})
        if state.get('rag_attempts',{}).get(side,{}).get('status')=='failed' or not old.get('continuation',{}).get('goal_id'):
            ledger.block(record,'기존 조사 실패 또는 재개 가능한 사건 없음')
            ctx.repo.save(state);return True
        previous=ctx.repo.call(record.get('previous_request_id',old['request_id']))['result']
        ledger.begin(record,old);ctx.repo.save(state)
        ok=retrieval.discover(ctx,state,side,question=task['missing_target'],research_task=task,previous_result=previous)
        ledger.finish(record,state['rag_attempts'][side],ok)
        ctx.repo.save(state)
        # Every acquisition outcome is consumed by review, even an empty or
        # failed return. The ledger prevents identical input from calling twice.
        return True
    return False


def execute(ctx):
    from . import concepts
    state=ctx.repo.state()['checkpoint']
    while True:
        ctx.context.remaining();stage=state['stage']
        if state.get('finalization'):
            raise ctx.model.services.BudgetExhausted('resume saved finalization; investigation remains stopped')
        if ctx.definition.manifest.get('execution_policy') and stage not in ('VERIFY_BASIS','COMPARE','REPORT','END'):
            ctx.model.services.phase_context(ctx.context).remaining()
        if stage=='INTAKE':
            state['scope']=query_scope.prepare(ctx);initialize(ctx,state);state['stage']='FIND_INTERNAL'
        elif stage=='FIND_INTERNAL':
            retrieval.discover(ctx,state,'internal')
            state['stage']='DEFINE_CONCEPTS' if concepts.enabled(ctx) else 'FIND_EXTERNAL'
        elif stage=='DEFINE_CONCEPTS':
            anchored=concepts.prepare(ctx,state)
            if anchored:initialize(ctx,state)
            state['stage']='FIND_EXTERNAL' if anchored else 'REPORT'
        elif stage=='FIND_EXTERNAL':retrieval.discover(ctx,state,'external');state['stage']='ITEM_REVIEW'
        elif stage=='ITEM_REVIEW':review(ctx,state);state['stage']='ITEM_RESEARCH'
        elif stage=='ITEM_RESEARCH':state['stage']='ITEM_REVIEW' if research(ctx,state) else 'VERIFY_BASIS'
        elif stage=='VERIFY_BASIS':state['basis']=basis.from_items(ctx,state);state['stage']='COMPARE'
        elif stage=='COMPARE':state['comparison']=compare.compare(ctx,state);state['stage']='REPORT'
        elif stage=='REPORT':
            value=report(ctx,state);ctx.rag.port.verify_all();state['stage']='END'
            return ctx.repo.save(state,status=value['status'],result=value)
        elif stage=='END':return ctx.repo.state()['result']
        else:raise WorkflowError('WORKFLOW_TASK_STATE','과제 계약에 없는 실행 상태입니다.',409)
        ctx.repo.save(state)


def unreviewed_sources(state, by, cited, *, all_read=False):
    """Only committed child-adopted spans, never exploratory/context originals.

    Called when field review failed. A source is preserved as an unread judgment
    task, not assigned to a field and not promoted to a legal comparison claim.
    Normal publication and already-cited sides keep their reviewed selection.
    """
    from ..presentation import valid_results
    reviewed_sides={by[i]['side'] for i in cited}
    selected=set()
    for result in valid_results(state):
        side=result.get('side')
        if (result.get('status') not in ('completed','partial') and result.get('bundle',{}).get('export_mode')!='READ_ORIGINALS') or (side in reviewed_sides and not all_read):
            continue
        bundle=result.get('bundle',{})
        if bundle.get('side')!=side:
            raise WorkflowError('WORKFLOW_SOURCE_SIDE','보존 원문의 조사 구분이 다릅니다.',409)
        allowed=set(result.get('evidence_ids',[])) & set(bundle.get('evidence_ids',[]))
        if bundle.get('export_mode')=='READ_ORIGINALS' or (all_read and bundle.get('export_mode')=='SOURCE_HANDOFF'):
            if any(i not in by or by[i]['side']!=side for i in allowed):
                raise WorkflowError('WORKFLOW_STALE_EVIDENCE','보존 원문의 출처가 일치하지 않습니다.',409)
            selected.update(allowed)
        for claim in bundle.get('claims',[]):
            for ident in claim.get('evidence_ids',[]):
                if ident not in allowed or ident not in by or by[ident]['side']!=side:
                    raise WorkflowError('WORKFLOW_STALE_EVIDENCE','보존 원문의 채택 기록이 일치하지 않습니다.',409)
                selected.add(ident)
    return [by[i] for i in sorted(selected-cited)]


def report(ctx,state,status=None,code=None):
    from .report import build,literal,cell
    from ..presentation import evidence
    legacy=dict(state);legacy.pop('task_board',None)
    value=build(ctx,legacy,status,code)
    from . import concepts
    by={e['evidence_id']:e for e in (concepts.originals(ctx,state) if concepts.enabled(ctx) else evidence(ctx,state))}
    available_sides={e['side'] for e in unreviewed_sources(state,by,set(),all_read=True)} if code else set()
    omitted_source_ids={ident for record in state['task_board'].get('review_omissions',[])
        if any(state['task_board']['rows'][record['issue_id']+':'+field]['current'] is None
               for field in record['fields']) for ident in record['evidence_ids']}
    if omitted_source_ids-set(by):
        raise WorkflowError('WORKFLOW_STALE_EVIDENCE','미검토 원문의 결속이 다릅니다.',409)
    available_sides.update(by[ident]['side'] for ident in omitted_source_ids)
    items=[];cited=set();lines=['항목별 LLM 검토 의견','', '| 쟁점·항목 | 내규 확인 | 외규 확인 | 내용 차이 | 남은 확인 |','|---|---|---|---|---|']
    for key,row in state['task_board']['rows'].items():
        current=deepcopy(row['current']);issue=next(i for i in state['scope']['issues'] if i['id']==row['issue_id'])
        if current is None:
            current={'field':row['field'],'content_status':'UNKNOWN','difference':'','next_tasks':[],**{s:{'status':'MISSING','text':'','citations':[],'dependencies':[],'scope_sufficient':False,'missing':'조사 또는 항목 검토 미완료'} for s in ('internal','external')}}
        def rendered(side):
            r=current[side];refs=r['citations']+r['dependencies']
            for alternative in r.get('alternatives',[]):refs+=alternative['citations']+alternative['dependencies']
            check_citations(refs,by);cited.update(c['evidence'] for c in refs)
            return (r['text'] or ('항목 검토 미완료 — 확보 원문 참조' if side in available_sides else '미확보'))+(' (근거 미선택)' if r['text'] and not r['citations'] else '')+''.join(' ['+c['evidence']+']' for c in r['citations'])+''.join(' / 이전 확인: '+a['text']+''.join(' ['+c['evidence']+']' for c in a['citations']) for a in r.get('alternatives',[]))
        missing='; '.join(current[s]['missing'] for s in ('internal','external') if current[s]['missing'])
        lines.append('| '+' | '.join(cell(x) for x in [issue['label']+' / '+CONFIG['fields'][row['field']],rendered('internal'),rendered('external'),current['difference'] or '미확인',missing or '항목 범위 검토 완료'])+' |')
        items.append({'issue_id':row['issue_id'],**current,'legal_assessment':'LLM 검토 의견 — 근거와 함께 사용자 검토 가능'})
    # Failed first review must not hide a successful native source return.
    # These exact excerpts remain explicitly unreviewed and outside field claims.
    retained=unreviewed_sources(state,by,cited|set(value['evidence_refs']),all_read=True) if code else []
    retained.extend(by[ident] for ident in sorted(omitted_source_ids-cited-set(value['evidence_refs'])-
                    {e['evidence_id'] for e in retained}))
    if query_scope.enabled(ctx):
        failed_ids={r['evidence_id'] for r in state['task_board'].get('evidence_updates',[]) if r.get('origin')=='SYSTEM_FAILURE' or r['disposition']=='UNRESOLVED'}
        unknown=failed_ids-set(by)
        if unknown:raise WorkflowError('WORKFLOW_STALE_EVIDENCE','검토 실패 원문의 결속이 다릅니다.',409)
        retained_ids={e['evidence_id'] for e in retained}
        retained.extend(by[i] for i in sorted(failed_ids-cited-set(value['evidence_refs'])-retained_ids))
    value['unreviewed_sources']=[{'evidence_id':e['evidence_id'],'side':e['side'],
        'field_review_status':'NOT_COMPLETED','legal_assessment':'UNVERIFIED'} for e in retained]
    if retained:
        lines.extend(['','확보한 원문 — 항목별 검토 미완료',
            '아래는 실제 읽은 원문입니다. 항목 대응·예외·적용 범위와 법적 부합 여부는 아직 확인하지 못했습니다.'])
        for e in retained:
            lines.extend(['',('내규' if e['side']=='internal' else '외규')+' · '+
                literal(e['metadata']['document_name']+' '+e['metadata'].get('heading',''))+' ['+e['evidence_id']+']',
                '> '+literal(e['text']).replace('\n','\n> ')])
        cited.update(e['evidence_id'] for e in retained)
    cards=value['assembly']['term_agent']['source_bundle']['sources'];known={c['selection_id'] for c in cards}
    for ident in sorted(cited-known):
        e=by[ident];cards.append({'selection_id':ident,'document_id':e['document_id'],'document_name':e['metadata']['document_name'],
            'coordinate_label':e['metadata'].get('heading',''),'generation_id':e['generation_id'],'source_artifact_hash':e['source_artifact_hash'],
            'spans':e['spans'],'excerpt':e['text'],'side':e['side'],'content_read':True,'interpretation_status':'UNVERIFIED','coverage':'READ_SPANS_ONLY'})
    bundle=value['assembly']['term_agent']['source_bundle'];bundle.pop('bundle_hash',None);bundle['bundle_hash']=digest(bundle)
    value['evidence_refs']=sorted(set(value['evidence_refs'])|cited)
    value['evidence_summary']['reported']=len(cards)
    value['comparison_items']={'schema_version':VERSION,'items':items}
    incomplete=[i for i in items if i['content_status']=='UNKNOWN' or any(i[s]['status']!='CONFIRMED' or not i[s]['citations'] or not i[s]['scope_sufficient'] for s in ('internal','external'))]
    if incomplete:
        if value['status']=='completed':value['status']='partial'
        value['answer']['answer_status']='PARTIAL'
        gaps=[i['issue_id']+' / '+CONFIG['fields'][i['field']]+' — 항목 확인 미완료' for i in incomplete]
        value['unresolved']=list(dict.fromkeys(value['unresolved']+gaps))
        value['answer']['unresolved']=[{'reason':g} for g in value['unresolved']]
    value['research_attempts']={k:{'status':r['status'],'task':r['task'],'result_request_id':r.get('result_request_id')} for k,r in state['task_board']['tasks'].items()}
    value['latest_rag_attempts']=state.get('rag_attempts',{})
    value['item_validation_failures']=state['task_board'].get('rejected_proposals',[])
    value['item_review_omissions']=deepcopy(state['task_board'].get('review_omissions',[]))
    if query_scope.enabled(ctx):
        value['evidence_updates']=deepcopy(state['task_board'].get('evidence_updates',[]))
        value['update_failures']=deepcopy(state['task_board'].get('update_failures',[]))
        value['research_needs']=research_need_view(state['task_board'],limit=ctx.definition.manifest['max_recoveries'])
        value['research_priorities']={k:{f:r.get(f) for f in ('priority','priority_reason','queue_order','status')} for k,r in state['task_board']['tasks'].items()}
        pending_updates=[r for r in value['evidence_updates'] if r['disposition']=='UNRESOLVED']
        if pending_updates:
            if value['status']=='completed':value['status']='partial'
            value['answer']['answer_status']='PARTIAL'
            value['unresolved']=list(dict.fromkeys(value['unresolved']+['확보 원문의 항목 반영 미완료 — '+r.get('binding_note',r['reason']) for r in pending_updates]))
            value['answer']['unresolved']=[{'reason':g} for g in value['unresolved']]
    # One opinion table. Detailed field observations remain in comparison_items.
    text=value['answer']['text'];start=text.index('| 비교 항목 |');end=text.index('\n\n추가 확인 사항',start)
    table=['| 비교사항 | 내규 확인 | 외규 확인 | LLM 의견·이유 | 남은 확인 |','|---|---|---|---|---|']
    pairs={p['pair_id']:p for p in state.get('basis',{}).get('pairs',[])}
    from .report import VERDICTS
    for final in state.get('comparison',{}).get('rows',[]):
        issue_id=pairs[final['pair_id']]['issue_id'];issue=next(i for i in state['scope']['issues'] if i['id']==issue_id)
        related=[i for i in items if i['issue_id']==issue_id]
        def side_text(side):
            return '\n'.join(CONFIG['fields'][i['field']]+': '+(i[side]['text'] or '미확보')+
                ''.join(' ['+c['evidence']+']' for c in i[side]['citations'])+
                ''.join(' / 이전 확인: '+a['text']+''.join(' ['+c['evidence']+']' for c in a['citations']) for a in i[side].get('alternatives',[])) for i in related) or '항목 검토 미완료'
        remaining=list(dict.fromkeys(final['unresolved']+[i[s]['missing'] for i in related for s in ('internal','external') if i[s]['missing']]))
        table.append('| '+' | '.join(cell(x) for x in (issue['label'],side_text('internal'),side_text('external'),
            VERDICTS[final['verdict']]+' — '+final['difference']+' '+final['reason'],'; '.join(remaining)))+' |')
    if len(table)==2:
        for item in items:
            issue=next(i for i in state['scope']['issues'] if i['id']==item['issue_id'])
            table.append('| '+' | '.join(cell(x) for x in (issue['label']+' / '+CONFIG['fields'][item['field']],
                item['internal']['text'] or '미확보',item['external']['text'] or '미확보',item['difference'] or '비교 검토 미완료',
                '; '.join(item[s]['missing'] for s in ('internal','external') if item[s]['missing'])))+' |')
    # Append all field-cited originals, including those not selected by COMPARE.
    tail=[]
    original_ids={e['selection_id'] for e in value['assembly']['term_agent']['source_bundle']['sources']}
    for ident in sorted(cited):
        if '['+ident+']\n>' in text:continue
        e=by[ident];tail.extend(['',literal(e['metadata']['document_name']+' '+e['metadata'].get('heading',''))+' ['+ident+']',
            '> '+literal(e['text']).replace('\n','\n> ')])
    value['answer']['text']=text[:start]+'\n'.join(table)+text[end:]+'\n'.join(tail)
    if value.get('evidence_updates'):
        notes=['','확보 원문 검토']
        labels={'USED':'판단에 반영','CONTEXT':'보충 자료','UNRELATED':'적용 대상 다름','UNRESOLVED':'영향 미확인'}
        for update in value['evidence_updates']:
            e=by[update['evidence_id']]
            note=update['reason']+(' / '+update['binding_note'] if update.get('binding_note') else '')
            notes.append('- '+labels[update['disposition']]+' · '+literal(e['metadata']['document_name']+' '+e['metadata'].get('heading',''))+': '+literal(note))
        value['answer']['text']+='\n'.join(notes)
    if value.get('research_needs'):
        open_needs=[n for n in value['research_needs'] if n['status']!='RESOLVED']
        if open_needs:
            notes=['','남아 있는 원문 조사']
            labels={'BUDGET_EXHAUSTED':'이번 조사 한도에 도달','QUEUED':'추가 조사 대기','ATTEMPT_RECORDED':'조사 이력 있음·미확인 유지','NO_TASK':'실행 대상 미확정'}
            for need in open_needs:
                notes.append('- '+('내규' if need['side']=='internal' else '외규')+' · '+literal(need['missing'])+' — '+labels[need['execution_state']])
            value['answer']['text']+='\n'.join(notes)
    ctx.repo.work.event('RESEARCH_STATE_SUMMARY',ResearchLedger(state['task_board']).audit(
        state.get('rag_results',{}),limit=ctx.definition.manifest['max_recoveries']))
    from . import concepts,concept_report
    if concepts.enabled(ctx):
        value=concept_report.apply(ctx,state,value,by)
    from . import finalize
    value=finalize.apply(state,value,by)
    return value
