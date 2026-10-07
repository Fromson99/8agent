"""Host integration for the existing bound GENOS/local transport, without fallback.

Identity is resolved by the host before calling this factory. Client user IDs
are consistency checks and never become access grants.
"""
from pathlib import Path
from .corrected_memory import Memory, MemoryError
from .memory_rag import NativeRag

class RuntimeModel:
    """One native model session owns the entire turn's attempts, repairs and deadline."""
    def __init__(self,pipeline,runtime,body,principal,*,admission_lease=None,run_id=None,release=None):
        self.pipeline=pipeline;self.runtime=runtime;self.body=body;self.principal=principal
        self.session=None;self.resource=None
        self.admission_lease=admission_lease;self.run_id=run_id;self.release=release
    def invoke(self,system,data,schema,phase,*,timeout=None):
        self.ensure()
        session=self.session
        limit=min(180,session.context.remaining(),timeout if timeout is not None else 180)
        if limit<=1:raise TimeoutError('model phase time budget exhausted')
        return session.structured(system,data,schema,phase,limit,
                                  session.profile['max_output_tokens'])
    def ensure(self):
        if self.session is None:
            p=self.pipeline
            docs=list(self.principal['document_ids']) if getattr(p.term_agent,'unified',False) else self.body.get('document_ids') or list(self.principal['document_ids'])
            if not docs or not set(docs)<=set(self.principal['document_ids']):raise MemoryError('model context document scope denied')
            request={'question':self.body['question'],'document_ids':docs,'use_llm':True}
            from ..pipeline import route_question
            # The native authorization covers the host-approved envelope. The
            # case applies an explicit source prefix as a reversible filter.
            planning_question=route_question(request['question'])[0] if getattr(p.term_agent,'unified',False) else request['question']
            query=p.plan(planning_question,docs)
            self.resource=p.term_agent.open_session(request,query=query,runtime=self.runtime,
                **({'admission_lease':self.admission_lease} if self.admission_lease is not None else {}),
                **({'run_id':self.run_id,'release':self.release} if self.run_id is not None else {}),
                external_public_question=self.body.get('public_question') is True)
            self.session=self.resource.__enter__()
            if not hasattr(self.session,'structured'):
                self.close()
                raise MemoryError('memory requires bounded native structured model adapter')
            self.session.work.event('MEMORY_MODEL_SESSION',{
                'request_id':self.body['request_id'],'session_id':self.body['session_id']})
        return self.session
    def close(self):
        if self.session is not None:
            resource=self.resource;self.session=None;self.resource=None
            resource.__exit__(None,None,None)

def factory(pipeline,runtime,body,principal):
    directory=Path(runtime)/'corrected-memory';directory.mkdir(parents=True,exist_ok=True)
    model=RuntimeModel(pipeline,runtime,body,principal)
    memory=Memory(directory/'memory-v2.sqlite',NativeRag(pipeline,runtime,model.invoke),model.invoke)
    memory.model_resource=model
    return memory


def public_result(memory, result):
    """Use the existing chat source display contract without exposing obsolete evidence."""
    result=dict(result)
    if result.get('status')=='CLARIFY':
        return {**result,'answer':{'text':result.get('reason') or '수정할 질문이나 조건을 지정해 주세요.','claims':[]}}
    if result.get('status')=='REMAPPED':
        return {**result,'answer':{'text':'이 질문의 과거 경험 연결을 수정했습니다.','claims':[]}}
    answer=result.get('answer')
    if not isinstance(answer,dict):return result
    claims=[{**c,'source_ids':[c['source_id']]} for c in answer.get('claims',[])]
    result['answer']={**answer,'claims':claims}
    gid=result.get('goal_id')
    if gid:
        parts=memory.parts(gid)
        originals=parts.get('READ',{}).get('payload',{}).get('originals',[])
        used={c['source_id'] for c in claims}
        result['assembly']={'context':[{'id':x['source_id'],'document_id':x.get('document_id'),
            'document_name':x.get('document_name') or x.get('document_id') or x['source_id'],
            'ancestors':[{'title':x.get('heading') or x.get('unit_id') or x['source_id']}]}
            for x in originals if x['source_id'] in used]}
    return result
