"""Host-only exact CM export grant. Never labels private CM questions public.

The selected product files, source ACL, prompts, schema and budgets are unchanged.
Each cell uses a new empty runtime. The trusted host authorization context is
restricted to the exact frozen question and current MAIN's public source scope.
"""
from common import *
import importlib,hashlib
from contextvars import ContextVar
from copy import deepcopy

def install(t,pkg,f,case,baseline):
 errors=importlib.import_module(pkg+'.errors');workflow=importlib.import_module(pkg+'.workflow_execution')
 grant=read(DES/'authorization.json');corpus=read(DES/'corpus.json');expected=case['request']['json']['question'];allowed=set(case['request']['json']['document_ids']);original_scope=set(t.public_scope)
 assert allowed<=original_scope and allowed==set(grant['document_ids'])
 token_var=ContextVar('approved_cm_case',default=None);previous=workflow.authorization
 def authorization():return previous() or token_var.get()
 workflow.authorization=authorization
 class Authorized(type(t)):
  @property
  def public_scope(self):return tuple(sorted(allowed))
  def authorize(self,query,request,manifest,*,public_question=True):
   if (token_var.get() is None or not public_question or request.get('question',query.get('question'))!=expected or not request['use_llm'] or not set(query['scope']['document_version_ids']) or set(query['scope']['document_version_ids'])-allowed):raise errors.ContractError('CM exact question/source authorization mismatch')
   for n in ('authorization.json','corpus.json'):
    rel=str((DES/n).relative_to(ROOT));assert sha(DES/n)==f['inputs'][rel]
   assert sha(self.grant_path)==self.grant_hash and sha(self.policy_path)==self.policy_hash
   assert manifest['generation_id']==self.grant['generation_id'] and manifest['store_sha256']==self.grant['source_store_sha256'] and manifest['export_allowed'] is False
   return {'kind':'USER_AUTHORIZED_CM_EXPERIMENT','authorization_sha256':sha(DES/'authorization.json'),'grant_sha256':self.grant_hash,'policy_sha256':self.policy_hash,'case_id':case['id'],'question_sha256':hashlib.sha256(expected.encode()).hexdigest(),'public_question_asserted':True,'scope_document_ids':sorted(query['scope']['document_version_ids'])}
  def validate_authorization(self,context):
   identity=(context.run_id,context.binding_hash,context.query['id'])
   # Native API may open a fresh context before finding its cached response.
   # Authorization belongs to the exact case/question/source grant, not one
   # ephemeral context. Each context still keeps its own original deadline.
   assert context.request['question']==expected
   deadlines=getattr(self,'_cm_context_deadlines',{})
   if identity in deadlines:assert context.deadline<=deadlines[identity]
   else:deadlines[identity]=context.deadline
   self._cm_context_deadlines=deadlines
   receipt=self.authorize(context.query,{**context.request,'question':expected},{'generation_id':context.binding['generation_id'],'store_sha256':context.binding['store_sha256'],'export_allowed':context.binding['export_allowed']},public_question=True)
   assert context.binding['external_authorization']==receipt and context.binding['model']==self.binding
 t.__class__=Authorized
 async def invoke(service,request):
  assert request==case['request']
  handle=token_var.set({'kind':'USER_AUTHORIZED_CM_EXPERIMENT','case_id':case['id'],'authorization_sha256':sha(DES/'authorization.json'),'no_prior_history':True})
  try:return await service({},deepcopy(request))
  finally:token_var.reset(handle)
 return invoke
