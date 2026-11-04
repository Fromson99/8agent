"""Closed memory-operation catalogue. This is not a legal concept ontology."""
METHODS={
 'CASE_START':{'action':'START','stage':'INTENT','purpose':'새 질문의 목적과 조건을 분리한다'},
 'FACT_UPDATE':{'action':'CORRECT','stage':'ASSESS','purpose':'현재 사건 사실만 바꾸고 적용 판단을 다시 확인한다'},
 'STATE_RESTORE':{'action':'CORRECT','stage':'NONE','purpose':'기록된 특정 이벤트의 조건을 정확히 복원한다'},
 'PURPOSE_REVISE':{'action':'CORRECT','stage':'INTENT','purpose':'질문 자체의 수행 목적을 변경한다'},
 'RESEARCH_REPLAN':{'action':'CORRECT','stage':'PLAN','purpose':'문서 범위·검색 계획과 필요한 조건을 수정한다'},
 'RESEARCH_REENTER':{'action':'FOLLOW','stage':None,'purpose':'사용자가 지정한 조사 단계부터 다시 검토한다'},
 'ANSWER_PRESENT':{'action':'PRESENT','stage':'COMPOSE','purpose':'판단과 조건을 유지하고 최종 표현만 바꾼다'},
 'HISTORY_EXPLAIN':{'action':'INSPECT','stage':'NONE','purpose':'실제 정정 이벤트와 현재 판단 근거를 조회해 설명한다'},
 'EXPERIENCE_CONFIRM':{'action':'FINALIZE','stage':'NONE','purpose':'사용자가 확인한 현재 최종 판단 묶음을 발행한다'},
 'EXPERIENCE_REUSE':{'action':'REUSE','stage':'COMPOSE','purpose':'현재 조건과 동등한 최종 확인 경험을 활용한다'},
 'WIKI_RELINK':{'action':'REMAP','stage':'NONE','purpose':'위키의 경험 연결만 정정한다'},
 'NEED_TARGET':{'action':'CLARIFY','stage':'NONE','purpose':'기록에서 요청 대상을 특정할 수 없어 확인한다'},
}
FIELDS=('task','source_category','document_ids','facts','queries')

def offered(context):
    """Expose only commands with at least one currently valid host-owned target."""
    goals=context['goals'];ids=[g['id'] for g in goals]
    ready=[g['id'] for g in goals if g.get('status')=='READY' and g.get('command_ready',True)]
    restorable=[g['id'] for g in goals if any(e.get('after') for e in g.get('events',[]))]
    knowledge=[k['id'] for k in context.get('knowledge',[])]
    result={}
    for name,method in METHODS.items():
        targets=([None] if name=='CASE_START' else [None,*ids] if name=='NEED_TARGET' else
                 ready if name in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM') else
                 restorable if name=='STATE_RESTORE' else
                 [None,*ids] if name=='EXPERIENCE_REUSE' and knowledge else
                 ids if name!='EXPERIENCE_REUSE' else [])
        if name=='WIKI_RELINK' and not knowledge:targets=[]
        from .tool_policy import assess_availability
        if assess_availability('memory',name,binding=None,reason=None if targets else 'NO_VALID_TARGET').offered:
            result[name]={**method,'targets':targets}
    return result

def require_offered(command,context):
    item=offered(context).get(command.get('method_id'))
    if item is None or command.get('target') not in item['targets']:
        raise ValueError('memory method or target unavailable in current state')

def normalize(c,context):
    c=dict(c)
    mode=c.get('document_scope_mode')
    key=c.get('method_id')
    if mode=='KEEP':
        if c.get('document_ids') is not None:raise ValueError('KEEP scope must not change document IDs')
    elif mode=='AUTHORIZED':
        if key not in ('CASE_START','EXPERIENCE_REUSE','RESEARCH_REPLAN'):raise ValueError('authorized scope change requires a new question, reuse or replan')
        if c.get('document_ids') is not None:raise ValueError('AUTHORIZED scope is host-owned; document_ids must be null')
        if c.get('target') is not None:
            if key!='RESEARCH_REPLAN':raise ValueError('existing experience reuse must keep scope')
            # Authorization remains host-owned; never serialize its inventory into a command.
            pass
    elif mode=='EXPLICIT':
        if not c.get('document_ids'):raise ValueError('explicit scope requires document IDs')
    else:raise ValueError('document_scope_mode required')
    method=METHODS.get(c.get('method_id'))
    if method is None:raise ValueError('method_id must be an offered registered method')
    require_offered(c,context)
    c['action']=method['action']
    if method['stage'] is not None:c['stage']=method['stage']
    key=c['method_id'];given={f for f in FIELDS if c.get(f) is not None and not(f=='source_category' and c[f]=='KEEP')}
    scope_change=c.get('search_scope_change') or {}
    scope_changed=scope_change.get('operation','KEEP')!='KEEP'
    if scope_changed and key not in ('CASE_START','PURPOSE_REVISE','RESEARCH_REPLAN'):
        raise ValueError('search scope changes require a new question or research/purpose revision')
    if key in ('ANSWER_PRESENT','HISTORY_EXPLAIN','EXPERIENCE_CONFIRM','WIKI_RELINK','RESEARCH_REENTER'):
        if given or c.get('restore_fields'):raise ValueError(key+' cannot edit case facts, purpose, search or scope')
    if key=='FACT_UPDATE':
        if given!={'facts'} or c.get('restore_fields'):raise ValueError('FACT_UPDATE changes only facts; use RESEARCH_REPLAN for new search requirements')
    if key=='PURPOSE_REVISE' and not c.get('task'):raise ValueError('PURPOSE_REVISE requires changed task, not a condition or presentation request')
    if key=='RESEARCH_REPLAN' and not (given & {'queries','document_ids','source_category'} or scope_changed or mode=='AUTHORIZED'):raise ValueError('RESEARCH_REPLAN requires a retrieval-plan or scope change')
    if key=='RESEARCH_REENTER' and c.get('stage') not in ('INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE'):raise ValueError('RESEARCH_REENTER requires an explicitly selected stage')
    if key=='STATE_RESTORE':
        fs=c.get('restore_fields') or []
        if not fs:raise ValueError('STATE_RESTORE requires original event and restored fields')
        goals={g['id']:g for g in context['goals']};es=goals.get(c.get('target'),{}).get('events',[])
        origin=next((e for e in es if e['id']==c.get('restore_event')),None)
        if origin is None:raise ValueError('restore event is not offered for the selected goal')
        for f in given:
            if f not in fs or c[f]!=origin['after'][f]:raise ValueError('restoration cannot hide a different explicit state edit')
        c['stage']='INTENT' if 'task' in fs else 'PLAN' if set(fs)&{'source_category','document_ids','queries','search_scope'} else 'ASSESS'
    elif c.get('restore_fields') or c.get('restore_event') is not None:raise ValueError('restore fields require STATE_RESTORE')
    if key=='CASE_START' and c.get('target') is not None:raise ValueError('new case target must be null')
    return c

def history_projection(events):
    out=[]
    for e in events:
        before=e['before'] or {};after=e['after'];changed=[f for f in (*FIELDS,'search_scope') if before.get(f)!=after.get(f)]
        out.append({'event_id':e['id'],'kind':e['kind'],'correction_ordinal':e.get('correction_ordinal'),
          'utterance':e['utterance'],'method_id':e['command'].get('method_id'),'reason':e['command'].get('reason'),
          'restore_event':e['command'].get('restore_event'),'restore_fields':e['command'].get('restore_fields',[]),
          'changes':{f:{'before':before.get(f),'after':after.get(f)} for f in changed}})
    return out

def history_answer(events,answer):
    import json
    records=history_projection(events);lines=['현재 판단과 실제 수정 이력입니다.','',answer['text'],'','수정 이력:']
    names={'task':'질문 목적','source_category':'문서 구분','document_ids':'문서 범위','facts':'사건 조건','queries':'검색 계획','search_scope':'직접 검색 범위'}
    for r in records:
        label='최초 질문' if r['kind'] in ('START','REUSE') else str(r['correction_ordinal'])+'차 정정' if r['correction_ordinal'] else '표현·검토 요청'
        lines.append(f"- [{r['event_id']}] {label}: {r['utterance']}")
        for f,v in r['changes'].items():lines.append('  '+names[f]+': '+json.dumps(v['before'],ensure_ascii=False)+' → '+json.dumps(v['after'],ensure_ascii=False))
        if r['restore_event'] is not None:lines.append(f"  기록 [{r['restore_event']}]의 지정 조건을 복원했습니다.")
        if r['method_id']:lines.append('  적용 방법: '+r['method_id']+' — '+METHODS[r['method_id']]['purpose'])
    lines+=['','현재 판단의 원문 근거:']
    for c in answer['claims']:lines.append('- '+c['text']+' / '+c['source_id']+' / 원문: '+c['quote'])
    return {**answer,'text':'\n'.join(lines)},records
