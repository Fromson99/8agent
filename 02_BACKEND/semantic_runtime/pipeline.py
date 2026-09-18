"""Term retrieval -> source selection -> original context -> grounded answer."""
import json
import time
import uuid
from .contracts import Contracts
from . import observability as obs

log = obs.get_logger('rag')

class Pipeline:
    def __init__(self,root,store,provider=None,vector=None,*,implementation=None):
        self.store=store;self.contracts=Contracts(root);self.provider=provider
        config=next(x for x in self.contracts.pipeline['profiles']['legal-rag']['nodes'] if x['id']=='retrieve')['parameters']['term_agent']
        if not config.get('enabled'):raise ValueError('term navigation is required')
        config = {**config}
        if implementation is not None:
            config['implementation'] = implementation
        implementation=config.get('implementation','term-agent-v1')
        if implementation=='navigation-loop-v1':
            from .navigation_agent import ServingNavigationAgent
            self.term_agent=ServingNavigationAgent(self,config)
        elif implementation=='document-navigation-v1':
            from .document_agent import ServingDocumentAgent
            self.term_agent=ServingDocumentAgent(self,config)
        elif implementation=='definition-scope-harness-v1':
            from .task_harness_agent import ServingTaskHarnessAgent
            self.term_agent=ServingTaskHarnessAgent(self,config)
        elif implementation=='term-agent-v1':
            from .term_agent import TermAgent
            self.term_agent=TermAgent(self,config)
        else:
            raise ValueError('unknown term agent implementation: '+implementation)

    def document_roles(self):
        """document_id -> role, from hash-bound stored metadata of this generation."""
        if getattr(self,'_document_roles',None) is None:
            from .document_roles import role_of_metadata
            self._document_roles={did:role_of_metadata(json.loads(meta) if meta else {}) for did,meta in self.store.db.execute(
                "SELECT document_id,json_extract(json,'$.document_metadata') FROM document")}
        return self._document_roles

    def scope_documents(self,scope):
        from .document_roles import in_scope
        return sorted(did for did,role in self.document_roles().items() if in_scope(role,scope))

    def plan(self,question,documents=None,scope=None):
        from .document_roles import DEFAULT_SCOPE
        if not isinstance(question,str) or not question.strip() or len(question)>10000:raise ValueError('question length must be 1..10000')
        documents=list(documents or [])
        known={x[0] for x in self.store.db.execute('SELECT document_id FROM document')}
        if set(documents)-known:raise ValueError('document filter has unknown IDs')
        if documents and scope:raise ValueError('choose document_ids OR scope, not both')
        if not documents:
            documents=self.scope_documents(scope or DEFAULT_SCOPE)
            if not documents:raise ValueError('scope has no documents in this generation: '+str(scope or DEFAULT_SCOPE))
        value={'id':'query:'+uuid.uuid4().hex,'question':question,
               'generation_id':self.store.manifest['generation_id'],
               'scope':{'document_version_ids':documents}}
        return self.contracts.validate(value,'urn:8-agent:term-runtime-v1','Query')

    def retrieve(self,plan,limit=40,use_llm=False):
        return self.term_agent.retrieve(plan,use_llm)

    def run(self,question,documents=None,use_llm=True,scope=None):
        import importlib.util
        from .contracts import sha
        config=self.contracts.pipeline
        profile=config['profiles']['legal-rag']
        started=time.perf_counter()
        values={'$input.request':{'question':question,'document_ids':documents or [],'use_llm':use_llm,
                                  **({'scope':scope} if scope else {})}}
        self.contracts.validate(values['$input.request'],'urn:8-agent:term-runtime-v1','Request')
        obs.event(log,'rag.started',question_chars=len(question or ''),document_filter_count=len(documents or []),use_llm=use_llm)
        for step in profile['nodes']:
            with obs.step(log,step['id'],engine=step['engine']):
                entry=config['engines'][step['engine']]
                path=self.contracts.root/entry['manifest']
                if sha(path)!=entry['sha256']:raise ValueError('engine manifest hash mismatch')
                manifest=json.loads(path.read_text())
                for file,expected in manifest['files'].items():
                    if sha(self.contracts.root/file)!=expected:raise ValueError('engine code hash mismatch')
                module_path=self.contracts.root/manifest['entrypoint']['path']
                spec=importlib.util.spec_from_file_location('semantic_runtime.stage_'+step['id'],module_path)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                inputs={k:values[v] for k,v in step['bindings'].items()}
                result=getattr(module,manifest['entrypoint']['function'])(inputs,step['parameters'],{'runtime':self})
                if set(result)!=set(manifest['outputs']):raise ValueError('engine output ports mismatch')
                for key,value in result.items():
                    contract=config['contracts'][manifest['outputs'][key]]
                    self.contracts.validate(value,'urn:8-agent:term-runtime-v1',contract['schema_definition'])
                    values[step['id']+'.'+key]=value
            current=next(iter(result.values())) if result else {}
            if step['id']=='retrieve':
                retrieval=current.get('retrieval',{})
                obs.event(log,'rag.retrieved',candidate_count=len(retrieval.get('candidates',[])),routes=retrieval.get('routes',{}),vector_status=retrieval.get('vector_status'))
            elif step['id']=='select':
                selection=current.get('selection',{})
                obs.event(log,'rag.selected',selected_count=len(selection.get('selected',[])),method=selection.get('method'))
            elif step['id']=='assemble':
                assembly=current.get('assembly',{})
                obs.event(log,'rag.assembled',context_count=len(assembly.get('context',[])),unresolved_count=len(assembly.get('unresolved',[])))
            elif step['id']=='answer':
                answer=current.get('answer',{})
                obs.event(log,'rag.answered',answer_chars=len(answer.get('text','')),claim_count=len(answer.get('claims',[])),unresolved_count=len(answer.get('unresolved',[])))
        output=values[profile['outputs']['result']]
        obs.event(log,'rag.finished',duration_ms=int((time.perf_counter()-started)*1000),run_ready=True)
        return output
