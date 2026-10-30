"""Idempotent source calls retaining RAG receipts, canonical spans and cursors."""
from ..contracts import WorkflowError, digest, encoded
import json


class RagAdapter:
    def __init__(self, repository, port):
        self.repo, self.port = repository, port

    def call(self, action, *, call_id):
        canonical = {k:action[k] for k in ('operation','side','args')}
        old = self.repo.intent(call_id, 'rag', canonical)
        if old['status'] == 'COMPLETE':
            self.port.verify_all()
            return old['result']
        if old['status'] == 'FAILED':
            raise WorkflowError('WORKFLOW_PREVIOUS_TOOL_FAILURE', '실패한 동일 도구 요청은 자동 반복하지 않습니다.')
        try:
            if action['operation'] == 'ask_rag':
                from importlib import import_module
                native = import_module(self.port.services.__class__.__module__.rsplit('.',1)[0]+'.workflow_rag')
                result = native.execute(self.port, action, call_id)
            else:
                raise WorkflowError('WORKFLOW_LEGACY_TOOL_DISABLED', '대사는 기존 RAG 전체 실행만 호출합니다.')
            self.repo.finish(call_id, result)
            return result
        except Exception as exc:
            # Durable diagnostic only: no success or evidence is manufactured.
            self.repo.failure(call_id, exc)
            raise
        finally:
            self.repo.db.execute('UPDATE workflow_active_tool SET call_id=NULL WHERE singleton=1')

    def evidence(self):
        self.port.verify_all()
        return self.port.evidence()

    def source_call(self,action,*,call_id):
        old=self.repo.intent(call_id,'source',action)
        if old['status']=='COMPLETE':
            self.port.verify_all();return old['result']
        if old['status']=='FAILED':raise WorkflowError('WORKFLOW_PREVIOUS_TOOL_FAILURE','실패한 동일 원문 요청을 자동 반복하지 않습니다.')
        try:
            result=self.port.execute(action);self.repo.finish(call_id,result);return result
        except Exception as exc:
            self.repo.failure(call_id,exc);raise
