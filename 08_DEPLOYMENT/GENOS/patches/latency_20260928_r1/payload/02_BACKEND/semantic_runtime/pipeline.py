"""Term retrieval -> source selection -> original context -> grounded answer."""
import json
import time
import uuid
from .contracts import Contracts
from . import observability as obs

log = obs.get_logger('rag')

class Pipeline:
    def __init__(self,root,store,provider=None,vector=None,*,implementation=None,legal_agent_profile=None,legal_agent_transport=None):
        self.store=store;self.contracts=Contracts(root);self.provider=provider
        config=next(x for x in self.contracts.pipeline['profiles']['legal-rag']['nodes'] if x['id']=='retrieve')['parameters']['term_agent']
        if not config.get('enabled'):raise ValueError('term navigation is required')
        config = {**config}
        if implementation is not None:
            config['implementation'] = implementation
        implementation=config.get('implementation','term-agent-v1')
        self.profile_id = {'legal-agent-v1': 'legal-agent-rag-v1', 'legal-agent-tools-v2': 'legal-agent-rag-v2', 'legal-agent-tools-v3': 'legal-agent-rag-v3', 'legal-agent-tools-v4': 'legal-agent-rag-v4', 'legal-agent-tools-v5': 'legal-agent-rag-v5'}.get(implementation, 'legal-rag')
        if self.profile_id == 'legal-rag' and config.get('legal_agent') and 'document-navigation-rag-v1' in self.contracts.pipeline['profiles']:
            self.profile_id = 'document-navigation-rag-v1'
        if implementation in ('legal-agent-v1', 'legal-agent-tools-v2', 'legal-agent-tools-v3', 'legal-agent-tools-v4', 'legal-agent-tools-v5'):
            from .legal_agent_adapter import ServingLegalAgent
            from .legal_agent.errors import ContractError
            if self.profile_id not in self.contracts.pipeline['profiles']:
                raise ContractError('explicit candidate profile required')
            config = dict(next(x for x in self.contracts.pipeline['profiles'][self.profile_id]['nodes']
                               if x['id'] == 'retrieve')['parameters']['term_agent'])
            self.term_agent = ServingLegalAgent(self, config, execution_profile=legal_agent_profile,
                                               transport=legal_agent_transport)
        elif implementation=='navigation-loop-v1':
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
            with obs.step(log,'plan.document_roles.load'):
                self._document_roles={did:role_of_metadata(json.loads(meta) if meta else {}) for did,meta in self.store.db.execute(
                    "SELECT document_id,json_extract(json,'$.document_metadata') FROM document")}
        else:
            obs.event(log,'plan.document_roles.cached',document_count=len(self._document_roles))
        return self._document_roles

    def scope_documents(self,scope):
        from .document_roles import in_scope
        return sorted(did for did,role in self.document_roles().items() if in_scope(role,scope))

    def plan(self,question,documents=None,scope=None,*,team_id=None):
        from .document_roles import DEFAULT_SCOPE
        default_scope = '전체' if self.profile_id in ('legal-agent-rag-v2', 'legal-agent-rag-v3', 'legal-agent-rag-v4', 'legal-agent-rag-v5') else DEFAULT_SCOPE
        if not isinstance(question,str) or not question.strip() or len(question)>10000:raise ValueError('question length must be 1..10000')
        documents=list(documents or [])
        original_documents=bool(documents)
        with obs.step(log,'plan.document_ids'):
            known={x[0] for x in self.store.db.execute('SELECT document_id FROM document')}
        if set(documents)-known:raise ValueError('document filter has unknown IDs')
        if documents and scope:raise ValueError('choose document_ids OR scope, not both')
        if not documents:
            with obs.step(log,'plan.scope_documents'):
                documents=self.scope_documents(scope or default_scope)
            if not documents:raise ValueError('scope has no documents in this generation: '+str(scope or default_scope))
        if team_id is not None:
            from .team_scope import select_documents
            with obs.step(log,'plan.team_documents'):
                team_documents=set(select_documents(self.store,team_id))
            if set(documents)-team_documents and original_documents:
                raise ValueError('document_ids include documents outside selected team')
            documents=sorted(set(documents)&team_documents)
            if not documents:raise ValueError('selected team and scope have no documents')
        value={'id':'query:'+uuid.uuid4().hex,'question':question,
               'generation_id':self.store.manifest['generation_id'],
               'scope':{'document_version_ids':documents}}
        with obs.step(log,'plan.query_validate',document_count=len(documents)):
            return self.contracts.validate(value,'urn:8-agent:term-runtime-v1','Query')

    def retrieve(self,plan,limit=40,use_llm=False):
        return self.term_agent.retrieve(plan,use_llm)

    def run(self,question,documents=None,use_llm=True,scope=None,*,execution_context=None,team_id=None):
        started=time.perf_counter()
        obs.event(log,'rag.prepare.started',diagnostic_revision='latency-20260928-r1',
                  team_selected=team_id is not None)
        with obs.step(log,'rag.runner_import'):
            from .stage_runner import StageRunner
        if team_id is not None:
            # Resolve the HTTP/CLI selector before the unchanged runtime Request port.
            # Every engine, request session and publication receives these fixed IDs.
            with obs.step(log,'rag.team_plan'):
                documents=self.plan(question,documents,scope,team_id=team_id)['scope']['document_version_ids']
            scope=None
        request={'question':question,'document_ids':documents or [],'use_llm':use_llm,
                 **({'scope':scope} if scope else {})}
        with obs.step(log,'rag.request_validate',document_count=len(request['document_ids'])):
            self.contracts.validate_port('runtime.request',request)
        with obs.step(log,'rag.runner_init'):
            runner=StageRunner(self)
        obs.event(log,'rag.started',question_chars=len(question or ''),document_filter_count=len(documents or []),use_llm=use_llm)
        if self.profile_id in ('legal-agent-rag-v1', 'legal-agent-rag-v2', 'legal-agent-rag-v3', 'legal-agent-rag-v4', 'legal-agent-rag-v5'):
            from .legal_agent.coordinator import run as coordinate
            from .legal_agent.publication import prepare,export
            from .legal_agent.errors import LegalAgentError,ContractError
            from jsonschema import ValidationError
            options=dict(execution_context or {})
            if 'runtime' not in options:
                from lawrag.platform.workspace import load_layout
                options['runtime']=load_layout(self.contracts.root).path('runtime')/'semantic'
            # Caller input (including document IDs) is validated before converting
            # candidate runtime/model failures into non-422 typed errors.
            with obs.step(log,'rag.plan'):
                query=self.plan(question,documents,scope)
            try:
                session_started=time.perf_counter()
                obs.event(log,'session.open.started')
                with self.term_agent.open_session(request,query=query,run_id=options.get('run_id'),
                        release=options.get('release'),runtime=options['runtime'],
                        external_public_question=options.get('external_public_question') is True) as session:
                    obs.event(log,'session.open.ready',duration_ms=int((time.perf_counter()-session_started)*1000))
                    obs.event(log,'rag.loop.started',elapsed_ms=int((time.perf_counter()-started)*1000))
                    result=coordinate(self,session,runner)
                    session.check_sources_unchanged()
                    if options.get('defer_publication') and self.profile_id == 'legal-agent-rag-v5':
                        from .legal_agent.deferred_publication import schedule
                        from .legal_agent.errors import AdmissionRejected
                        from queue import Full
                        envelope={**result,'run_id':session.context.run_id,
                                  'release':options.get('release'),
                                  'publication_status':'PENDING'}
                        try:
                            schedule(session.work.path,self.store.path,self.contracts.root,
                                     options['runtime']/'runs',result,options.get('release'))
                        except Full as exc:
                            raise AdmissionRejected('publication capacity reached') from exc
                        obs.event(log,'rag.answer_returning',run_id=session.context.run_id,
                                  publication_status='PENDING')
                        return envelope
                    obs.event(log,'publication.sync.started',run_id=session.context.run_id)
                    prepare(session.work,result,options.get('release'),self.contracts)
                    envelope=export(session.work,options['runtime']/'runs')
                    obs.event(log,'publication.sync.finished',run_id=session.context.run_id)
                    # Direct callers keep the Result port shape, but every success
                    # completes the journal/outbox lifecycle before returning.
                    return envelope if options.get('publish') else result
            except LegalAgentError:
                raise
            except (KeyError,ValueError,ValidationError) as exc:
                raise ContractError('legal-agent internal contract failed') from exc
        values={'$input.request':request}
        profile=self.contracts.pipeline['profiles'][self.profile_id]
        for step in profile['nodes']:
            runner.execute(step,values)
        output=values[profile['outputs']['result']]
        obs.event(log,'rag.finished',duration_ms=int((time.perf_counter()-started)*1000),run_ready=True)
        return output
