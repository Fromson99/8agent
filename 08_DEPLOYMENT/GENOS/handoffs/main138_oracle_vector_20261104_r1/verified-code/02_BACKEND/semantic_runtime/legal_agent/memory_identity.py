"""Validate session selectors behind the existing platform access boundary.

User/team/session IDs select stored state and document scope. They are not an
authentication grant; platform/API access remains the ingress responsibility.
"""
FIELDS = {'question','memory','session_id','request_id','user_id','team_id',
          'expected_revision','document_ids','use_llm','public_question','memory_authorization','scope',
          'query_kind','experience_id','question_id','after','limit',
          'investigation_id','investigation_revision','branch_id','unit_id','revision','event_id','artifact_id',
          'operation','arguments','ad_session_id','ad_channel','review_action'}


def validate_session(body, *, require_memory=True):
    from .corrected_memory import MemoryError
    if set(body)-FIELDS:raise MemoryError('unsupported memory request fields')
    if (require_memory and body.get('memory') is not True) or (body.get('use_llm',True) is not True and 'review_action' not in body):raise MemoryError('memory requires a model request')
    for field in ('team_id','session_id','request_id'):
        value=body.get(field)
        if not isinstance(value,str) or not value.strip() or len(value)>256 or value in ('anonymous','sess-anonymous'):
            raise MemoryError('stable '+field+' required')
    revision=body.get('expected_revision')
    if revision is not None and (type(revision) is not int or revision<1):raise MemoryError('invalid expected revision')
    from ..session_identity import bind
    try:
        _,principal=bind(body)
    except ValueError as exc:
        raise MemoryError(str(exc)) from exc
    return principal


def resolve(pipeline, body):
    from ..team_scope import select_documents
    from .corrected_memory import MemoryError
    principal=validate_session(body,require_memory=not getattr(pipeline.term_agent,'unified',False))
    allowed=set(select_documents(pipeline.store,principal['team_id']))
    external=getattr(pipeline.term_agent.transport,'public_scope',None)
    if external is not None:
        if body.get('public_question') is not True:raise MemoryError('external memory requires a public question')
        allowed &= set(external)
    if not allowed:raise MemoryError('no documents authorized for this principal')
    principal['document_ids']=sorted(allowed)
    return principal


def prepare(pipeline, runtime, body, trusted=None, *, require_memory=True):
    """Normalize at HTTP ingress once; all repositories receive the same key."""
    from ..session_identity import bind, reject_legacy
    from ..team_scope import select_documents
    from .corrected_memory import MemoryError
    try:
        normalized,principal=bind(body,trusted)
        # Validate the external envelope before replacing its selectors.
        validate_session({**body,'team_id':principal['team_id']},require_memory=require_memory)
        reject_legacy(runtime,{**body,'team_id':principal['team_id']})
    except ValueError as exc:
        raise MemoryError(str(exc)) from exc
    allowed=set(trusted['document_ids'] if trusted is not None else select_documents(pipeline.store,principal['team_id']))
    external=getattr(pipeline.term_agent.transport,'public_scope',None)
    if external is not None:
        if body.get('public_question') is not True:raise MemoryError('external memory requires a public question')
        allowed &= set(external)
    if not allowed:raise MemoryError('no documents authorized for this session')
    principal['document_ids']=sorted(allowed)
    return normalized,principal
