"""The existing legal_agent owns model, source tools and all seven checkpoints."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from .memory_rag import NativeRag, NativeExecution
from .corrected_memory import MemoryError, digest


class UnifiedRag(NativeRag):
    def __init__(self,pipeline,runtime,model,catalogue):
        super().__init__(pipeline,runtime,model.invoke)
        self.model=model;self.domain=catalogue
        from ..contracts import cached_code_sha
        code=digest({name:cached_code_sha(Path(__file__).with_name(name)) for name in
            ('law_title_hints.py','request_entry.py','corrected_memory.py','memory_methods.py','memory_rag.py','case_repository.py','knowledge_repository.py',
             'domain_control.py','procedure_memory.py','wiki_execution.py','core_evidence_route.py','shortcut_cases.py','unified_rag.py','unified_runtime.py','unified_publication.py',
             'source_recall.py','source_recall_global.py','source_selection.py','unit_reading.py','unit_selection.py','unit_relations.py','relation_read_policy.py',
             'law_candidates.py','law_navigation.py','investigation_chain.py','evidence_inventory.py','investigation_contracts.py','completion_contracts.py','completion_execution.py','completion_budget.py','memory_binding.py')})
        self.binding.update(catalogue_hash=catalogue.hash,method_policy_hash=catalogue.method_hash,
            profile=digest(pipeline.term_agent.profile),code=code,
            pipeline=digest(pipeline.contracts.pipeline))

    @contextmanager
    def open(self,state,principal,body):
        # Command resolution has already opened this same native session.
        s=self.model.ensure()
        docs=self.documents(state,principal)
        if not set(docs)<=set(s.work.binding['scope']['document_version_ids']):raise MemoryError('case scope escaped native authorization')
        current=self.retrieval_question(state)
        # Run ID, query ID, binding and deadline remain immutable. Only the
        # effective question and reversible source filter advance in this run.
        s.context=replace(s.context,query={**s.context.query,'question':current},
            request={**s.context.request,'question':current})
        s.sources.context=s.context;s.sources.scope=docs;s.sources.scope_set=frozenset(docs)
        s.sources.source.context=s.context;s.sources.source.scope=docs
        s.sources.root=s.sources.handle('R',{'documents':docs})
        s.work.event('CASE_EXECUTION_CONTEXT',{'request_id':body['request_id'],
            'session_id':body['session_id'],'state_hash':digest(state),'documents':docs})
        execution=getattr(self,'execution_class',UnifiedExecution)(self,s,state,principal)
        yield execution
        s.check_sources_unchanged()


class UnifiedExecution(NativeExecution):
    def bind_previous(self,parts):
        read=parts.get('READ',{}).get('payload')
        if not read:return
        self.host.verify(read)
        evidence=[]
        selected=parts.get('SELECT',{}).get('payload',{})
        all_evidence={e['evidence_id']:e for e in read['evidence']+selected.get('selected_evidence',[])}
        self.host.verify({'binding':read['binding'],'evidence':list(all_evidence.values())})
        for raw in all_evidence.values():
            if raw['document_id'] not in self.s.sources.scope:continue
            current={**raw,'evidence_id':'E'+digest([self.s.context.run_id,raw['evidence_id']])[:28]}
            self.s.sources.source.verify(current);evidence.append(current)
        if evidence:
            self.s.work.record_observation({'tool':'case_evidence_rebind','args':{'origin_hash':digest(read)}},
                {'status':'REUSED','origin_binding':read['binding']},evidence,verify=self.s.sources.source.verify)

    def invoke(self,system,data,schema,phase,*,timeout=None):
        if hasattr(self,'domain_choice'):
            data={**data,'domain_choice':self.domain_choice,'catalogue':self.host.domain.value,
                'concept_policy':'Unregistered labels are discovery observations, never reviewed ontology concepts.'}
        return super().invoke(system,data,schema,phase,timeout=timeout)

    def record(self,stage,payload,*,origin=None):
        with self.s.work.transaction():
            seq=self.s.work.event('CASE_JUDGMENT_VALIDATED',{'stage':stage,'payload_hash':digest(payload),
                'domain_choice':self.domain_choice,'origin':origin})
            ident='case:'+stage
            dependencies=[('case_stage','case:'+previous) for previous in
                self.host_stages_before(stage) if any(h['entity_id']=='case:'+previous for h in self.s.work.heads('case_stage',current=True))]
            head=self.s.work.put('case_stage',ident,payload,seq,dependencies=dependencies,
                evidence_ids=[e['evidence_id'] for e in self.s.work.evidence()] if stage in ('READ','SELECT','ASSESS','COMPOSE') else [])
        # put returns a version; use the head to keep the ref unambiguous.
        h=self.s.work.head('case_stage',ident)
        self.last_judgment_ref={'run_id':self.s.context.run_id,'kind':'case_stage',
            'entity_id':ident,'version':h['version'],'payload_hash':digest(payload),
            'choice_id':self.domain_choice['choice_id']}
        self.pending_judgment = {'stage':stage,'payload_hash':digest(payload),
            'validated_seq':seq,'origin':origin,'domain_choice':self.domain_choice}

    @staticmethod
    def host_stages_before(stage):
        from .corrected_memory import STAGES
        return STAGES[:STAGES.index(stage)]

    def rebind(self,stage,payload):
        self.domain_choice=self.host.domain.select(stage,self.state,self.s)
        self.record(stage,payload,origin={'payload_hash':digest(payload),'reason':'verified confirmed experience'})

    def stage(self,stage,state,parts,utterance,format):
        self.domain_choice=self.host.domain.select(stage,state,self.s)
        from .corrected_memory import Reenter
        try:
            payload=super().stage(stage,state,parts,utterance,format)
        except Reenter as recovery:
            self.s.work.event('CASE_STAGE_REENTRY', {'from_stage':stage,'stage':recovery.stage,
                'gaps':recovery.payload.get('gaps',[]),'reason':recovery.reason})
            raise
        self.record(stage,payload)
        return payload
