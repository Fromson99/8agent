from ..contracts import WorkflowError


def normalize(body,principal):
    value=body.get('input')
    if not isinstance(value,dict) or set(value)-{'internal_document_id','mode','continuation_of','scope_policy','publish_candidates','skip_research_errors'}:
        raise WorkflowError('BASIS_DISCOVERY_INPUT','선택 내규와 조사 모드를 지정해 주세요.')
    if value.get('internal_document_id') not in principal['document_ids']:
        raise WorkflowError('WORKFLOW_SCOPE_DENIED','선택 내규의 접근권한이 없습니다.',403)
    if value.get('mode','discover') not in ('discover','revalidate'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','discover 또는 revalidate를 선택해 주세요.')
    if value.get('scope_policy','block-v1') not in ('block-v1','parent-overlap-v1'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','지원하지 않는 조사 범위 정책입니다.')
    if type(value.get('publish_candidates',False)) is not bool:
        raise WorkflowError('BASIS_DISCOVERY_INPUT','publish_candidates는 boolean이어야 합니다.')
    if type(value.get('skip_research_errors',False)) is not bool:
        raise WorkflowError('BASIS_DISCOVERY_INPUT','skip_research_errors는 boolean이어야 합니다.')
    if body.get('question') or body.get('q'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','전체 내규 조사는 input의 문서 선택을 사용합니다.')
    if 'continuation_of' in value:
        import re
        if not isinstance(value['continuation_of'],str) or not re.fullmatch('[a-f0-9]{32}',value['continuation_of']):
            raise WorkflowError('BASIS_DISCOVERY_INPUT','이어서 조사할 run_id가 잘못되었습니다.')
    return {'input':{'internal_document_id':value['internal_document_id'],'mode':value.get('mode','discover'),
                     **({k:value[k] for k in ('scope_policy','publish_candidates','skip_research_errors') if k in value}),
                     **({'continuation_of':value['continuation_of']} if 'continuation_of' in value else {})}}


def schema(internal,external):
    return {'type':'object','properties':{
        'links':{'type':'array','items':{'type':'object','properties':{
            'internal_ref':{'type':'string','enum':internal},
            'external_refs':{'type':'array','minItems':1,'items':{'type':'string','enum':external}},
            'kind':{'enum':['BASIS','IMPLEMENTS','RELATED']},'reason':{'type':'string','minLength':1}},
            'required':['internal_ref','external_refs','kind','reason'],'additionalProperties':False}},
        'notes':{'type':'array','items':{'type':'string'}}},
        'required':['links','notes'],'additionalProperties':False}


def failure_detail(exc):
    return {'type':type(exc).__name__,'code':getattr(exc,'code',type(exc).__name__),
            'message':str(exc)}


def skippable_detail(detail):
    """An allowlist for isolated research failures, never a generic success path."""
    pair=(detail.get('type'),detail.get('code'))
    if pair==('ContractError','INTERNAL_CONTRACT_ERROR'):
        return detail.get('message')=='source return task missing'
    return pair in {
        ('ProposalError','MODEL_PROPOSAL_INVALID'),
        ('TransportError','MODEL_TRANSPORT_ERROR'),
        ('ToolExecutionError','SOURCE_TOOL_ERROR'),
        ('InvestigationPending','SOURCE_INVESTIGATION_INCOMPLETE'),
        ('WorkflowError','BASIS_READ_FAILED'),
        ('WorkflowError','WORKFLOW_REPAIR_EXHAUSTED')}


def skippable(exc):
    # A wrapped integrity/cancellation error must retain its original boundary.
    import errno
    from semantic_runtime.legal_agent.errors import LegalAgentError
    seen=set();cause=exc
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause,(KeyboardInterrupt,SystemExit,MemoryError)):
            return False
        if isinstance(cause,OSError) and cause.errno in (
                errno.ENOSPC,errno.EDQUOT,errno.ENOMEM,errno.EIO,
                errno.EROFS,errno.EACCES,errno.EPERM):
            return False
        if isinstance(cause,(LegalAgentError,WorkflowError)) and not skippable_detail(failure_detail(cause)):
            return False
        cause=cause.__cause__ or cause.__context__
    return skippable_detail(failure_detail(exc))


class RecordedResearchFailure(Exception):
    def __init__(self,detail,call_id):
        super().__init__(detail['message'])
        self.detail,self.call_id=detail,call_id


def research_call(ctx,action,call_id,*,source=False):
    """Recover the failure/checkpoint gap using the original failed call receipt."""
    import json
    from ..contracts import digest,encoded
    if ctx.request['input'].get('skip_research_errors'):
        old=ctx.repo.call(call_id)
        if old and old['status']=='FAILED':
            expected=action if source else {k:action[k] for k in ('operation','side','args')}
            if old['kind']!=('source' if source else 'rag') or old['input_json']!=encoded(expected):
                raise WorkflowError('WORKFLOW_CALL_CONFLICT','실패 호출의 입력이 변경되었습니다.',409)
            detail=json.loads(old['error_json'])
            events=ctx.repo.db.execute(
                "SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_CALL_FAILED' "
                "AND json_extract(journal_text(payload_json),'$.call_id')=?",(call_id,)).fetchall()
            if len(events)!=1:
                raise WorkflowError('WORKFLOW_CALL_INTEGRITY','실패 호출의 원래 기록을 확인할 수 없습니다.',409)
            event=json.loads(events[0][0])
            if digest(event)!=events[0][1] or any(detail.get(k)!=event.get(k) for k in ('type','code','message')):
                raise WorkflowError('WORKFLOW_CALL_INTEGRITY','실패 호출의 원래 기록이 변경되었습니다.',409)
            # This exact defect has no semantic correction. Other failures
            # require the original chain-aware classification receipt.
            permitted=detail.get('type')=='ContractError' and skippable_detail(detail)
            classified=ctx.repo.db.execute(
                "SELECT payload_json,payload_hash FROM event WHERE kind='BASIS_RESEARCH_FAILURE_CLASSIFIED' "
                "AND json_extract(journal_text(payload_json),'$.call_id')=?",(call_id,)).fetchall()
            if classified:
                if len(classified)!=1:
                    raise WorkflowError('WORKFLOW_CALL_INTEGRITY','실패 분류 기록이 중복되었습니다.',409)
                value=json.loads(classified[0][0])
                if (digest(value)!=classified[0][1] or value['detail']!=detail
                        or value['input_hash']!=digest(expected)):
                    raise WorkflowError('WORKFLOW_CALL_INTEGRITY','실패 분류 기록이 변경되었습니다.',409)
                permitted=value['skippable'] is True
            if permitted:
                raise RecordedResearchFailure(detail,call_id)
            raise WorkflowError('BASIS_RESEARCH_FAILURE_UNSAFE','이전 실패는 자동 건너뛰기 대상으로 확인되지 않았습니다.',409)
    method=ctx.rag.source_call if source else ctx.rag.call
    try:
        return method(action,call_id=call_id)
    except Exception as exc:
        if ctx.request['input'].get('skip_research_errors'):
            ctx.repo.work.event('BASIS_RESEARCH_FAILURE_CLASSIFIED',{
                'call_id':call_id,'detail':failure_detail(exc),'input_hash':digest(action),
                'skippable':skippable(exc)})
        raise
