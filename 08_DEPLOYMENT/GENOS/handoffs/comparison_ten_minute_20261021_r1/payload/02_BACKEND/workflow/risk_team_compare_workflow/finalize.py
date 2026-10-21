"""Bounded answer from committed originals after research stops; no tool loop."""
from copy import deepcopy
from ..contracts import digest, WorkflowError
from ..presentation import evidence, projected_size
from .contracts import check_citations


SCHEMA={'type':'object','additionalProperties':False,'required':['paragraphs','unresolved'],
    'properties':{
        'paragraphs':{'type':'array','maxItems':12,'items':{'type':'object',
            'additionalProperties':False,'required':['text','citations'],'properties':{
                'text':{'type':'string','minLength':1,'maxLength':1600},
                'citations':{'type':'array','minItems':1,'maxItems':16,'items':{
                    'type':'object','additionalProperties':False,'required':['evidence','quote'],
                    'properties':{'evidence':{'type':'string'},'quote':{'type':'string','minLength':1}}}}}}},
        'unresolved':{'type':'array','maxItems':24,'items':{'type':'string','maxLength':800}}}}


def prepare(ctx,state,error):
    saved=state.setdefault('finalization',{'status':'PREPARING',
        'reason':'탐색·검토 한도 또는 실행 오류로 추가 조사를 종료했습니다.',
        'unknown_at_stop':list(state.get('gaps',[])),
        'cause':getattr(error,'code',type(error).__name__)})
    # Save the terminal mode before any further operation; resume cannot reopen
    # research or reset its original wall/call allowance.
    ctx.repo.save(state)
    if saved['status'] in ('COMPLETE','SAVED_EVIDENCE_ONLY','NO_SOURCES'):return
    values=evidence(ctx,state)
    if not values:
        saved['status']='NO_SOURCES';ctx.repo.save(state);return
    if not ctx.request['use_llm']:
        saved['status']='SAVED_EVIDENCE_ONLY';ctx.repo.save(state);return
    data={'question':ctx.request['question'],'as_of':ctx.request['as_of'],
        'sources':[], 'remaining_unknown':saved['unknown_at_stop'],
        'stop_reason':saved['reason']}
    # A single answer request. Exact large originals stay in the published
    # appendix even if they cannot fit this synthesis; never truncate a clause.
    limit=ctx.model.services.profile['max_context_chars']-8000
    omitted=[]
    for e in values:
        row={k:e[k] for k in ('evidence_id','side','document_id','metadata','spans')}
        data['sources'].append(row)
        if projected_size(data)>limit:
            data['sources'].pop();omitted.append(e['evidence_id'])
    if not data['sources']:
        saved.update(status='SAVED_EVIDENCE_ONLY',omitted_from_synthesis=omitted)
        ctx.repo.save(state);return
    # Freeze the input after the first reservation, including on process resume.
    data_hash=digest(data)
    if saved.get('input_hash',data_hash)!=data_hash:
        raise WorkflowError('WORKFLOW_FINALIZATION_CHANGED','마무리 답변의 원문 결속이 바뀌었습니다.',409)
    saved.update(input_hash=data_hash,omitted_from_synthesis=omitted,status='PREPARING')
    ctx.repo.save(state)
    offered={e['evidence_id']:e for e in values if e['evidence_id'] in {s['evidence_id'] for s in data['sources']}}
    def checked(value):
        for paragraph in value['paragraphs']:check_citations(paragraph['citations'],offered)
    value=ctx.model.decide('FINALIZE',data,SCHEMA,
        '추가 탐색과 재검토는 종료되었다. 현재 사용자 질문에 대해 확보한 원문으로 답할 수 있는 내용을 한국어로 최대한 설명한다. '
        '각 문단에 실제 제공된 원문 인용을 선택한다. 비교 가능한 양측 원문이 있으면 차이와 조건을 설명하고, '
        '한쪽만 확보했다면 그쪽에서 확인되는 내용과 대응 쪽 미확보를 구분한다. '
        '내규는 내규, 외규는 외규의 근거로 사용하고 서로의 적용 근거를 대신하지 않는다. '
        '적용 범위·예외·판본·수치가 불확실하면 unresolved에 남긴다. 미확보를 규정 부재로 단정하지 않는다. '
        '새 조사나 사용자에게 원문을 찾아 달라는 요구 없이 확인 범위의 답변을 완성한다. '
        '법률 정답 인증이 아닌 원문 기반 검토 의견이다. 답할 근거가 없으면 paragraphs=[]와 미확인 사유를 반환한다.',checked)
    checked(value)
    saved.update(status='COMPLETE',value=value,value_hash=digest(value))
    ctx.repo.save(state)


def apply(state,result,by):
    saved=state.get('finalization')
    if not saved:return result
    lines=['추가 탐색을 종료하고 지금까지 확인한 내용으로 답변합니다.','']
    value=saved.get('value')
    if value:
        if digest(value)!=saved['value_hash']:
            raise WorkflowError('WORKFLOW_FINALIZATION_HASH','저장된 마무리 답변의 해시가 다릅니다.',409)
        for paragraph in value['paragraphs']:
            check_citations(paragraph['citations'],by)
            # All originals are published on the stopped path. Do not introduce
            # a citation that the answer consumer cannot resolve.
            if {c['evidence'] for c in paragraph['citations']}-set(result['evidence_refs']):
                raise WorkflowError('WORKFLOW_FINALIZATION_SOURCE','마무리 답변의 출처 연결이 없습니다.',409)
            from .report import literal
            refs=list(dict.fromkeys(c['evidence'] for c in paragraph['citations']))
            lines.extend([literal(paragraph['text'])+' '+''.join('['+ident+']' for ident in refs),''])
        result['unresolved']=list(dict.fromkeys(result['unresolved']+value['unresolved']))
        result['answer']['unresolved']=[{'reason':r} for r in result['unresolved']]
        if value['unresolved']:
            from .report import literal
            lines.extend(['남은 확인: '+literal(' / '.join(value['unresolved'])),''])
    elif result['evidence_refs']:
        lines.extend(['추가 답변 작성을 완료하지 못해 저장된 검토 의견과 확보 원문을 아래에 제공합니다.',''])
    result['answer']['text']='\n'.join(lines)+result['answer']['text']
    result['finalization']={k:deepcopy(v) for k,v in saved.items() if k not in ('value','input_hash','value_hash','unknown_at_stop')}
    result['answer']['answer_status']='PARTIAL'
    return result
