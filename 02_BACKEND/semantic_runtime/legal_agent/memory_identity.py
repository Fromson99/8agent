"""Authenticate a trusted workflow assertion, never a client-supplied user grant.

The workflow owns the signing key and binds platform identity/team before signing.
Local callers must use the same trusted adapter or inject a principal resolver.
"""
import hashlib
import hmac
import json
import os
import time

EXCLUDED = {'API_TYPE', 'channel', 'memory_authorization'}
FIELDS = {'question','memory','session_id','request_id','user_id','team_id',
          'expected_revision','document_ids','use_llm','public_question','memory_authorization','scope',
          'query_kind','experience_id','question_id','after','limit',
          'investigation_id','investigation_revision','branch_id','unit_id','revision','event_id','artifact_id',
          'operation','arguments','ad_session_id','ad_channel'}


def signed_bytes(body, issued_at):
    return json.dumps({'issued_at':issued_at,'request':{k:v for k,v in body.items() if k not in EXCLUDED}},
                      sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


def verify_assertion(body, key=None, now=None, *, require_memory=True):
    from .corrected_memory import MemoryError
    key=key if key is not None else os.environ.get('GENOS_MEMORY_SIGNING_KEY','')
    if len(key)<32:raise MemoryError('trusted memory signing adapter is not configured')
    auth=body.get('memory_authorization')
    if not isinstance(auth,dict) or set(auth)!={'issued_at','signature'}:raise MemoryError('memory assertion required')
    stamp=auth['issued_at'];now=time.time() if now is None else now
    if type(stamp) is not int or abs(now-stamp)>900:raise MemoryError('memory assertion expired')
    signature=auth['signature']
    if not isinstance(signature,str) or not hmac.compare_digest(signature,hmac.new(key.encode(),signed_bytes(body,stamp),hashlib.sha256).hexdigest()):
        raise MemoryError('memory assertion invalid')
    if set(body)-FIELDS:raise MemoryError('unsupported memory request fields')
    if (require_memory and body.get('memory') is not True) or body.get('use_llm',True) is not True:raise MemoryError('memory requires a model request')
    for field in ('user_id','team_id','session_id','request_id'):
        value=body.get(field)
        if not isinstance(value,str) or not value.strip() or len(value)>256 or value in ('anonymous','sess-anonymous'):
            raise MemoryError('stable authenticated '+field+' required')
    revision=body.get('expected_revision')
    if revision is not None and (type(revision) is not int or revision<1):raise MemoryError('invalid expected revision')
    return {'user_id':body['user_id'],'team_id':body['team_id']}


def resolve(pipeline, body):
    from ..team_scope import select_documents
    from .corrected_memory import MemoryError
    principal=verify_assertion(body,require_memory=not getattr(pipeline.term_agent,'unified',False))
    allowed=set(select_documents(pipeline.store,principal['team_id']))
    external=getattr(pipeline.term_agent.transport,'public_scope',None)
    if external is not None:
        if body.get('public_question') is not True:raise MemoryError('external memory requires a public question')
        allowed &= set(external)
    if not allowed:raise MemoryError('no documents authorized for this principal')
    principal['document_ids']=sorted(allowed)
    return principal
