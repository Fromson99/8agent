from ..contracts import WorkflowError


def normalize(body,principal):
    value=body.get('input')
    if not isinstance(value,dict) or set(value)-{'internal_document_id','mode','continuation_of','scope_policy','publish_candidates'}:
        raise WorkflowError('BASIS_DISCOVERY_INPUT','선택 내규와 조사 모드를 지정해 주세요.')
    if value.get('internal_document_id') not in principal['document_ids']:
        raise WorkflowError('WORKFLOW_SCOPE_DENIED','선택 내규의 접근권한이 없습니다.',403)
    if value.get('mode','discover') not in ('discover','revalidate'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','discover 또는 revalidate를 선택해 주세요.')
    if value.get('scope_policy','block-v1') not in ('block-v1','parent-overlap-v1'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','지원하지 않는 조사 범위 정책입니다.')
    if type(value.get('publish_candidates',False)) is not bool:
        raise WorkflowError('BASIS_DISCOVERY_INPUT','publish_candidates는 boolean이어야 합니다.')
    if body.get('question') or body.get('q'):
        raise WorkflowError('BASIS_DISCOVERY_INPUT','전체 내규 조사는 input의 문서 선택을 사용합니다.')
    if 'continuation_of' in value:
        import re
        if not isinstance(value['continuation_of'],str) or not re.fullmatch('[a-f0-9]{32}',value['continuation_of']):
            raise WorkflowError('BASIS_DISCOVERY_INPUT','이어서 조사할 run_id가 잘못되었습니다.')
    return {'input':{'internal_document_id':value['internal_document_id'],'mode':value.get('mode','discover'),
                     **({k:value[k] for k in ('scope_policy','publish_candidates') if k in value}),
                     **({'continuation_of':value['continuation_of']} if 'continuation_of' in value else {})}}


def schema(internal,external):
    return {'type':'object','properties':{
        'links':{'type':'array','items':{'type':'object','properties':{
            'internal_ref':{'type':'string','enum':internal},
            'external_refs':{'type':'array','minItems':1,'items':{'type':'string','enum':external}},
            'kind':{'enum':['BASIS','IMPLEMENTS','RELATED']},'reason':{'type':'string','minLength':1,'maxLength':4000}},
            'required':['internal_ref','external_refs','kind','reason'],'additionalProperties':False}},
        'notes':{'type':'array','items':{'type':'string','maxLength':2000}}},
        'required':['links','notes'],'additionalProperties':False}
