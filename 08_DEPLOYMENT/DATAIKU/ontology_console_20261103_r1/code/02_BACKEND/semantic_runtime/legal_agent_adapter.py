"""Opt-in double-harness adapter, retaining document/search/index compatibility."""
from contextlib import contextmanager
from .oracle_runtime_paths import Path
from types import SimpleNamespace
import threading
import time
from .contracts import digest, sha
from .document_agent import ServingDocumentAgent
from .storage import Store
from .legal_agent import domain as policies
from .legal_agent.context import RequestContext
from .legal_agent.errors import AdmissionRejected, ContractError, LegalAgentError
from .legal_agent.repository import WorkRepository
from .legal_agent.source_tools import SourceSession
from .legal_agent.gateway import ModelGateway
from .legal_agent.session import LegalSession
from .legal_agent.publication import owner_lock
from . import observability as obs

log = obs.get_logger('session')


class ServingLegalAgent(ServingDocumentAgent):
    def __init__(self, pipeline, config, *, execution_profile=None, transport=None):
        super().__init__(pipeline, config)
        self.unified = config.get('implementation') == 'legal-agent-unified-v6'
        if self.unified and config.get('unified_orchestration',{}).get('entrypoint')!='semantic_runtime.legal_agent.coordinator.run_case':
            raise ContractError('unified legal agent requires the common coordinator declaration')
        self.v5 = config.get('implementation') == 'legal-agent-tools-v5' or self.unified
        self.v4 = config.get('implementation') == 'legal-agent-tools-v4' or self.v5
        self.v3 = config.get('implementation') == 'legal-agent-tools-v3' or self.v4
        self.v2 = config.get('implementation') == 'legal-agent-tools-v2'
        if self.v5:
            from .legal_agent import workflow_tiers_policy as selected_policies
        elif self.v4:
            from .legal_agent import tiers_policy as selected_policies
        elif self.v3:
            from .legal_agent import relations_policy as selected_policies
        elif self.v2:
            from .legal_agent import tools_policy as selected_policies
        else:
            selected_policies = policies
        settings = config['legal_agent']
        self.domain = selected_policies.domain(policies.load_bound(pipeline.contracts.root, settings['domain']))
        self.profile = selected_policies.profile(execution_profile if execution_profile is not None else
                                       policies.load_bound(pipeline.contracts.root, settings['profile']))
        if self.unified and not self.profile.get('bounded_source_selection_enabled'):
            raise ContractError('unified legal agent requires bounded structured source adapter')
        self.transport = transport
        if self.profile['model_binding'] is not None:
            selected_policies.profile(self.profile, require_model=True)
            if self.transport is None:
                from .legal_agent.transport import GenosTransport
                self.transport = GenosTransport.from_environment(self.profile['model_binding'])
            if self.transport.binding != self.profile['model_binding']:
                raise ContractError('transport/model profile mismatch')
            with obs.step(log, 'bootstrap.model_validate'):
                self.startup_receipt = self.transport.validate_model()
        else:
            if transport is not None:
                raise ContractError('transport requires an explicit model profile')
            self.startup_receipt = {'verified': False, 'mode': 'SOURCE_ONLY_CONFIGURATION'}
        # Zero disables only the request-count gate; session isolation remains.
        request_limit = self.profile['max_concurrent_requests_per_process']
        self.admission = threading.BoundedSemaphore(request_limit) if request_limit else None
        if self.unified:
            selected_index = self.get_fulltext()
            if selected_index is not None and hasattr(selected_index, 'rank_units'):
                self.unit_fulltext = selected_index

    def retrieve(self, plan, use_llm=False):
        if use_llm:
            raise ContractError('model investigation requires a request-local LegalSession')
        result = super().retrieve(plan, False)
        result['term_agent']['implementation'] = self.config.get('implementation', 'legal-agent-v1')
        return result

    @contextmanager
    def admit(self, lease=None):
        if lease is not None:
            if lease.owner is not self or not lease.active:
                raise ContractError('invalid request admission lease')
            yield lease
            return
        if self.admission is not None and not self.admission.acquire(blocking=False):
            raise AdmissionRejected('request capacity reached')
        lease = SimpleNamespace(owner=self, active=True)
        try:
            yield lease
        finally:
            lease.active = False
            if self.admission is not None:
                self.admission.release()

    @contextmanager
    def open_session(self, request, *, query, run_id=None, release=None, runtime,
                     external_public_question=False, admission_lease=None,
                     requested_source_category=None):
        with self.admit(admission_lease):
            with self._open_session(request, query=query, run_id=run_id, release=release,
                                    runtime=runtime, external_public_question=external_public_question,
                                    requested_source_category=requested_source_category) as session:
                from .basis_links.execution import CURRENT
                binding=CURRENT.get()
                source=getattr(session.sources,'source',None)
                if binding and source is not None:
                    source.basis_factory,source.basis_principal=binding
                yield session

    @contextmanager
    def _open_session(self, request, *, query, run_id=None, release=None, runtime,
                      external_public_question=False, requested_source_category=None):
        from .contracts import cached_code_sha
        import os
        prepare_started=time.perf_counter();prepare_cpu=time.thread_time();phases={}
        @contextmanager
        def phase(name):
            start=time.perf_counter();cpu=time.thread_time()
            try:
                with obs.step(log,name):
                    yield
            finally:
                phases[name]={'wall_ms':round((time.perf_counter()-start)*1000,3),
                              'cpu_ms':round((time.thread_time()-cpu)*1000,3)}
        local_store = repo = None
        prepare_complete=False
        try:
            requires_model = request['use_llm']
            if requires_model and self.transport is None:
                raise ContractError('explicit deployment model profile required for model execution')
            with phase('session.store'):
                oracle=getattr(self.pipeline.store,'is_oracle_query',False)
                local_store = self.pipeline.store.reopen() if oracle else Store(self.pipeline.store.path, verify=False)
            if local_store.manifest != self.pipeline.store.manifest:
                raise ContractError('source generation binding changed')
            source_stat = local_store.binding_signature() if oracle else (local_store.path/'store.sqlite').stat()
            proxy = SimpleNamespace(store=local_store, contracts=self.pipeline.contracts, unit_fulltext=getattr(self,'unit_fulltext',None))
            source_agent = ServingDocumentAgent(proxy, self.config)
            obs.event(log, 'session.resources.started')
            resources_started=time.perf_counter();resources_cpu=time.thread_time()
            with source_agent.resources(query['scope']['document_version_ids']) as (index, tools, glossary, matcher):
                phases['session.resources']={'wall_ms':round((time.perf_counter()-resources_started)*1000,3),
                                             'cpu_ms':round((time.thread_time()-resources_cpu)*1000,3)}
                obs.event(log, 'session.resources.ready')
                binding = {k: local_store.manifest[k] for k in ('generation_id', 'store_sha256', 'export_allowed')}
                if requires_model and self.transport.binding['trust_zone'] == 'external':
                    binding['external_authorization'] = self.transport.authorize(
                        query, request, local_store.manifest,
                        public_question=external_public_question)
                binding.update(scope=query['scope'], domain_sha256=digest(self.domain), profile_sha256=digest(self.profile),
                               model=self.profile['model_binding'], index_sha256=index.manifest['index_sha256'],
                               glossary=glossary.binding, pipeline_sha256=cached_code_sha(self.pipeline.contracts.root/'00_SYSTEM/PIPELINE.json'),
                               release=release)
                if self.unified:
                    from .legal_agent.domain_control import DomainCatalogue
                    catalogue=DomainCatalogue.load(self.pipeline.contracts.root,self.config['legal_agent']['catalogue'])
                    binding['catalogue_hash']=catalogue.hash
                    binding['method_policy_hash']=catalogue.method_hash
                    binding['catalogue_binding']=self.config['legal_agent']['catalogue']
                    binding['contract_root']=str(self.pipeline.contracts.root)
                if requested_source_category is not None:
                    if requested_source_category not in ('internal', 'external'):
                        raise ContractError('invalid requested source category')
                    if any(matcher.document_catalogue[did]['category'] != requested_source_category
                           for did in query['scope']['document_version_ids']):
                        raise ContractError('requested source category and document scope disagree')
                    binding['requested_source_category'] = requested_source_category
                with phase('session.context'):
                    context = RequestContext.create(query, request, binding, self.profile['wall_seconds'], run_id)
                    from .legal_agent.workflow_execution import bind_context
                    context = bind_context(context)
                directory = Path(runtime)/'legal-agent/runs'/context.deadline_at[:10].replace('-', '')/context.run_id
                lock_started = time.perf_counter()
                with owner_lock(directory):
                    obs.event(log, 'session.owner_lock.acquired',
                              duration_ms=int((time.perf_counter()-lock_started)*1000))
                    if (directory/'journal.sqlite').exists():
                        raise ContractError('run ID already has a journal; use publication recovery')
                    repository_type, sources_type, session_type = WorkRepository, SourceSession, LegalSession
                    gateway_options = {}
                    if self.v2:
                        from .legal_agent.tools_repository import ToolsRepository
                        from .legal_agent.exploration_tools import ExplorationTools
                        from .legal_agent.tools_session import ToolsSession
                        from .legal_agent import tools_protocol, tools_policy
                        repository_type, sources_type, session_type = ToolsRepository, ExplorationTools, ToolsSession
                        gateway_options = {'message_protocol': tools_protocol, 'system': tools_policy.SYSTEM, 'prompts': tools_policy.PROMPTS}
                    if self.v3:
                        from .legal_agent.relations_repository import RelationsRepository
                        from .legal_agent.relations_tools import RelationsTools
                        from .legal_agent.relations_session import RelationsSession
                        from .legal_agent import relations_protocol, relations_policy
                        repository_type, sources_type, session_type = RelationsRepository, RelationsTools, RelationsSession
                        gateway_options = {'message_protocol': relations_protocol, 'system': relations_policy.SYSTEM, 'prompts': relations_policy.PROMPTS}
                    if self.v4:
                        from .legal_agent.tiers_repository import TiersRepository
                        from .legal_agent.tiers_tools import TiersTools
                        from .legal_agent.tiers_session import TiersSession
                        from .legal_agent import tiers_protocol, tiers_policy
                        repository_type, sources_type, session_type = TiersRepository, TiersTools, TiersSession
                        gateway_options = {'message_protocol': tiers_protocol, 'system': tiers_policy.SYSTEM, 'prompts': tiers_policy.PROMPTS}
                    if self.v5:
                        from .legal_agent.obligation_repository import ObligationRepository
                        from .legal_agent.workflow_tiers_tools import TiersTools
                        from .legal_agent.question_obligations import ObligationSession, SYSTEM, PROMPTS
                        from .legal_agent import obligation_protocol
                        repository_type, sources_type, session_type = ObligationRepository, TiersTools, ObligationSession
                        if self.profile.get('bounded_source_selection_enabled'):
                            from .legal_agent.bounded_source_session import BoundedSourceSession
                            session_type = BoundedSourceSession
                        gateway_options = {'message_protocol': obligation_protocol, 'system': SYSTEM, 'prompts': PROMPTS}
                    if self.unified:
                        from .legal_agent.unified_repository import UnifiedRepository
                        repository_type=UnifiedRepository
                    with phase('session.journal'):
                        repo = repository_type(directory/'journal.sqlite', context, self.profile)
                        from .legal_agent.workflow_execution import register
                        register(repo)
                    with phase('session.sources'):
                        sources = sources_type(local_store, tools, glossary, matcher, repo, context, self.profile)
                    with phase('session.gateway'):
                        gateway = ModelGateway(repo, context, self.profile, self.domain, self.transport, **gateway_options) if requires_model else None
                    try:
                        def check_sources_unchanged():
                            glossary.check_unchanged()
                            if oracle:
                                local_store.check_unchanged()
                                if local_store.binding_signature()!=source_stat:
                                    raise ContractError('Oracle request binding changed')
                                return
                            after = (local_store.path/'store.sqlite').stat()
                            if (source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns, source_stat.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                                raise ContractError('source artifact changed during request')
                        session = session_type(context, repo, sources, gateway, self.profile, local_store.manifest['data_status'])
                        session.check_sources_unchanged = check_sources_unchanged
                        if self.v4:
                            from .legal_agent.source_bundle import validate_current
                            repo.publication_guard = lambda value: validate_current(repo, value, local_store)
                        if self.unified:
                            from .legal_agent.unified_publication import validate_current as validate_case
                            repo.publication_guard=lambda value: validate_case(repo,value,local_store)
                        prepare_complete=True
                        obs.event(log,'session.prepare.timings',diagnostic_revision='request-prepare-20260929-r1',
                                  process_id=os.getpid(),prepare_status='READY',
                                  elapsed_ms=round((time.perf_counter()-prepare_started)*1000,3),
                                  thread_cpu_ms=round((time.thread_time()-prepare_cpu)*1000,3),phases=phases)
                        yield session
                        check_sources_unchanged()
                    except BaseException as exc:
                        repo.fail(getattr(exc, 'code', type(exc).__name__))
                        raise
        finally:
            if not prepare_complete:
                obs.event(log,'session.prepare.timings',diagnostic_revision='request-prepare-20260929-r1',
                          process_id=os.getpid(),prepare_status='FAILED',
                          elapsed_ms=round((time.perf_counter()-prepare_started)*1000,3),
                          thread_cpu_ms=round((time.thread_time()-prepare_cpu)*1000,3),phases=phases)
            if repo is not None:
                repo.close()
            if local_store is not None:
                local_store.close()
