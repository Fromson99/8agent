"""GENOS Oracle request factory. Only code/configuration survives a request.

Source data and mutable Agent records stay in Oracle. Runtime paths are logical
identifiers; no NFS mount, serving-local journal, or data fallback is required.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
from .oracle_runtime_paths import Path
import re
import threading
import time

from .oracle_dp import client_from_environment
from .oracle_dp_io import DPError,digest
from .oracle_query import Snapshot
from .oracle_query_catalog import select_release
from .oracle_query_request import _request
from .oracle_query_state import StateSQL
from .oracle_query_store import Store

_REQUEST=ContextVar('oracle_data_request',default=None)


class ValidatedTransport:
    """Cache endpoint validation only; model outputs remain request-local."""
    def __init__(self,transport):
        self.transport,self.receipt,self.lock=transport,None,threading.Lock()
    def __getattr__(self,name): return getattr(self.transport,name)
    def validate_model(self):
        with self.lock:
            if self.receipt is None: self.receipt=self.transport.validate_model()
            return dict(self.receipt)


@contextmanager
def request_context():
    existing=_REQUEST.get()
    if existing is not None:
        yield existing
        return
    slot={'app':None,'agent_records':None}
    token=_REQUEST.set(slot)
    try:
        from .oracle_runtime_paths import using
        with using(None):
            yield slot
    finally:
        if slot['app'] is not None:
            slot['app'].state.pipeline.store.close()
        _REQUEST.reset(token)


def environment_binding():
    names=('GENOS_ORACLE_AGENT_NAMESPACE','GENOS_ORACLE_AGENT_MEMORY_MIB','GENOS_ORACLE_TABLE_MAPPING','GENOS_STATE_DIR','GENOS_JOURNAL_STORAGE','GENOS_RUNTIME_LIMIT_MIB','GENOS_RUNTIME_RESERVE_MIB','GENOS_RUNTIME_MIN_FREE_MIB','GENOS_RAG_INITIAL_SEARCH','GENOS_EMBED_URL','GENOS_BASE_URL','GENOS_EMBED_SERVING_ID','GENOS_EMBED_KEY','DP','DP_QUERY_RELEASE_ID','DP_QUERY_CHANNEL','GENOS_RUNTIME_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR',
           'GENOS_EMBED_PROFILE_SHA256','GENOS_EMBED_MODEL','GENOS_EMBED_API_PREFIX','GENOS_GATEWAY_API_PREFIX',
           'GENOS_EMBED_TENANT_ID','GENOS_EMBED_TIMEOUT','GENOS_EMBED_CONNECT_TIMEOUT',
           'ORACLE_ORDS_BASE_URL','LLMOPS_ORDS_BASE_URL','ORACLE_ORDS_SCHEMA',
           'ORACLE_ORDS_CLIENT_ID','ORACLE_ORDS_CLIENT_SECRET')
    return digest({name:os.environ.get(name,'') for name in names})


def external_path(value,name):
    if not value or not Path(value).is_absolute():
        raise DPError('QUERY_STATE_PATH: '+name+' must name an absolute external shared directory')
    path=Path(value).resolve()
    def decode(v): return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),v)
    mounts=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before,after=line.split(' - ',1)
        mount=Path(decode(before.split()[4]))
        if path==mount or mount in path.parents:
            mounts.append((len(mount.parts),after.split()[0]))
    if not mounts or max(mounts)[1] not in ('nfs','nfs4','cifs'):
        raise DPError('QUERY_STATE_PATH: '+name+' must be mounted NFS/CIFS, not serving-local storage')
    return path


def external_runtime():
    from .oracle_runtime_paths import DEFAULT_ROOT,roots
    roots()  # Validate logical identifiers only; never inspect their mounts.
    return Path(os.environ.get('GENOS_RUNTIME_DIR') or DEFAULT_ROOT).resolve()


class Factory:
    is_oracle_query_factory=True

    def __init__(self,host):
        self.host=host
        self.environment=environment_binding()
        self.runtime=external_runtime()
        self.root=host._ROOT
        self.client=client_from_environment()
        self.release_id=os.environ.get('DP_QUERY_RELEASE_ID','').strip() or None
        self.channel=os.environ.get('DP_QUERY_CHANNEL','').strip() or (None if self.release_id else 'main')
        if self.release_id and self.channel:
            raise DPError('QUERY_CONFIG: choose DP_QUERY_RELEASE_ID or DP_QUERY_CHANNEL')
        pipeline=host._json(self.root/'00_SYSTEM/PIPELINE.json')
        self.implementation=os.environ.get('GENOS_RAG_IMPLEMENTATION','').strip() or pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent'].get('implementation')
        if self.implementation not in ('legal-agent-tools-v5','legal-agent-unified-v6'):
            raise DPError('QUERY_CONFIG: direct Oracle serving requires the maintained v5/v6 source tools')
        file='profile-unified-v6.json' if self.implementation=='legal-agent-unified-v6' else 'profile-tools-v5.json'
        profile=host._json(self.root/'00_SYSTEM/LEGAL_AGENT'/file)
        configured=host._genos_v5_environment_binding(profile)
        self.transport=None
        if configured is not None:
            profile,transport=configured
            self.transport=ValidatedTransport(transport)
        from .legal_agent.workflow_tiers_policy import profile as validate
        self.profile=validate(host._investigation_profile(host._genos_v5_wait_profile(host._genos_v5_admission_profile(profile))))
        slots=self.profile['max_concurrent_requests_per_process']
        self.admission=threading.BoundedSemaphore(slots) if slots else None
        self.binding={'mode':'oracle-query','data_provider':'oracle','source_storage':'oracle','diagnostic_storage':'nfs',
                      'serving_data_cache':False,'state_storage':'oracle','persistent_sqlite':False,
                      'record_computation':'request-local-memory',
                      'query_channel':self.channel,'query_release_id':self.release_id,
                      'dp_environment_binding':self.environment,'service_entry_sha256':host._sha(Path(host.__file__))}
        self.recovery_started=False
        self.recovery_lock=threading.Lock()
        self.agent_schema_verified=False
        self.agent_schema_lock=threading.Lock()
        from .oracle_runtime_paths import configure
        configure(self.record_provider)

    def record_provider(self):
        from .oracle_agent_records import AgentRecords,RecordSQL
        slot=_REQUEST.get()
        if slot is not None and slot.get('agent_records') is not None:
            return slot['agent_records']
        sql=RecordSQL(self.client,binding=self.environment,deadline=time.monotonic()+self.profile['wall_seconds'],max_calls=10000)
        records=AgentRecords(sql,namespace=os.environ.get('GENOS_ORACLE_AGENT_NAMESPACE','genos-rag'))
        if slot is not None:slot['agent_records']=records
        return records

    def request(self):
        if environment_binding()!=self.environment:
            raise DPError('QUERY_CONFIG_CHANGED: restart after changing Oracle connection/runtime selection')
        external_runtime()
        records=self.record_provider()
        with self.agent_schema_lock:
            if not self.agent_schema_verified:
                schema=getattr(self.client,'schema_map',None)
                if getattr(schema,'profile',None)=='development_g19_1':
                    schema.preflight(records.sql)
                records.preflight();self.agent_schema_verified=True
        from .oracle_runtime_paths import roots
        for root in roots():
            migration=records.state('a1:head:'+digest({'migration_root':root}))
            if migration and migration['value'].get('status')!='COMPLETE':
                raise DPError('AGENT_MIGRATION_INCOMPLETE: finish the stopped-writer import before serving')
        with self.agent_schema_lock:
            if not self.agent_schema_verified:
                records.preflight();self.agent_schema_verified=True
        sql=records.sql
        selected=select_release(sql,release_id=self.release_id,channel=self.channel)
        manifest=selected['manifest'];snapshot=Snapshot.open(sql,manifest['source_release_id'])
        if manifest['dataset_version']!=snapshot.dataset_version or manifest['source_manifest']!=snapshot.manifest:
            raise DPError('QUERY_SOURCE_BINDING: selected query/source release differs')
        allowed=set(snapshot.manifest['scope']['document_version_ids'])-snapshot.excluded
        from . import observability as obs
        obs.event(obs.get_logger('oracle.query'),'oracle.release.selected',query_release_id=selected['release_id'],
                  pointer_revision=selected['revision'],generation_id=snapshot.generation_id,
                  data_provider='oracle',serving_data_cache=False)
        return _request(sql,selected['release_id'],selected['revision'],snapshot,manifest,allowed)

    def application(self):
        slot=_REQUEST.get()
        if slot is not None and slot['app'] is not None: return slot['app']
        from .app import create_app
        request=self.request();store=Store(request)
        store.recovery_factory=lambda:Store(self.request())
        binding={**self.binding,'query_release_id':request.release_id,'query_pointer_revision':request.pointer_revision,
                 'generation_id':request.snapshot.generation_id,'dataset_version':request.snapshot.dataset_version}
        try:
            app=create_app(self.runtime,None,contracts_root=self.root,release=binding,
                provider=self.host._provider(self.root,self.runtime,store.manifest),vector=False,
                implementation=self.implementation,legal_agent_profile=self.profile,legal_agent_transport=self.transport,
                workspace_root=self.root,runtime_root=self.runtime,data_store=store)
            app.state.pipeline.term_agent.admission=self.admission
            app.state.oracle_binding=binding
            if slot is not None: slot['app']=app
            self.start_recovery()
            return app
        except BaseException:
            store.close()
            raise

    def start_recovery(self):
        with self.recovery_lock:
            if self.recovery_started: return
            self.recovery_started=True
        def recover():
            from . import observability as obs
            try:
                with request_context():
                    app=self.application();pipeline=app.state.pipeline
                    from .legal_agent.publication import recover as recover_publication
                    from .legal_agent.source_bundle import validate_current
                    def publication_guard(repo,value):
                        if repo.VERSION==6:
                            from .legal_agent.unified_publication import validate_current as validate_case
                            return validate_case(repo,value,pipeline.store)
                        return validate_current(repo,value,pipeline.store)
                    recover_publication(self.runtime/'legal-agent/runs',self.runtime/'runs',
                        publication_guard=publication_guard,
                        contracts=pipeline.contracts,release=app.state.oracle_binding)
                    from .legal_agent.shortcut_store import selected_store
                    if self.implementation=='legal-agent-unified-v6' and selected_store(self.runtime).is_file():
                        from .legal_agent.shortcut_cases import ShortcutCases
                        cases=ShortcutCases(selected_store(self.runtime),None,None)
                        try:cases.recover_requests()
                        finally:cases.close()
                    if self.implementation=='legal-agent-unified-v6' and (self.runtime/'case-memory/cases-v3.sqlite').is_file():
                        from .legal_agent.case_repository import CaseRepository
                        cases=CaseRepository(self.runtime/'case-memory/cases-v3.sqlite',None,None)
                        try: cases.recover_requests()
                        finally: cases.close()
            except Exception:
                obs.event(obs.get_logger('oracle.query'),'oracle.publication_recovery.failed',level=40,exc_info=True)
        from contextvars import Context
        threading.Thread(target=lambda:Context().run(recover),name='oracle-publication-recovery',daemon=True).start()

    def warmup(self):
        # Pin and validate descriptors only. Do not walk corpus/search tables.
        request=self.request();store=Store(request)
        try:
            from .oracle_query_index import Index
            from .oracle_query_fulltext import UnitIndex
            store.selection.require_latest();Index(store);UnitIndex(request)
            return {'data_provider':'oracle','mode':'oracle-query','state_storage':'oracle','persistent_sqlite':False,'nfs_required':False,'query_release_id':request.release_id,
                    'query_pointer_revision':request.pointer_revision,'document_count':len(request.sources.allowed),
                    'serving_data_cache':False,'source_downloaded':False,'sql_calls':request.sql.calls}
        finally: store.close()
