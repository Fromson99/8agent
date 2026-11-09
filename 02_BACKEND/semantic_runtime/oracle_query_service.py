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
from .oracle_query_catalog import ACTIVE, active, channel_name, read_release, select_release
from .oracle_shared_cache import SharedRows
from .oracle_query_request import _request
from .physical_mapping import names as physical_names
from .oracle_query_state import StateSQL
from .oracle_query_store import Store

_REQUEST=ContextVar('oracle_data_request',default=None)


def _implicit_release(sql):
    """Neither DP_QUERY_CHANNEL nor DP_QUERY_RELEASE_ID: 'main', else the only channel.

    Dataiku loaders publish to their own g19_<hash> channel. Without a main row,
    a single published channel is unambiguous; several are never ranked or guessed.
    """
    channel='main'
    selected=active(sql,channel)
    if selected is None:
        p=physical_names(sql,'query_active',ACTIVE)
        rows=sql.query(f'SELECT {p.select("CHANNEL")} FROM {p.table} ORDER BY {p.c("CHANNEL")} FETCH FIRST 2 ROWS ONLY',
                       [],limit=2)
        if len(rows)>1:
            raise DPError('QUERY_ACTIVE_AMBIGUOUS: no main channel and several published channels; set DP_QUERY_CHANNEL')
        if rows:
            channel=channel_name(rows[0]['CHANNEL'])
            selected=active(sql,channel)
    if selected is None:
        raise DPError('QUERY_ACTIVE_MISSING: no completed release selected for channel')
    return {**selected,'channel':channel,'manifest':read_release(sql,selected['release_id'])}


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
    slot={'app':None,'agent_records':None,'cpu_started':time.process_time()}
    token=_REQUEST.set(slot)
    try:
        from .oracle_runtime_paths import using
        with using(None):
            yield slot
    finally:
        if slot['app'] is not None:
            slot['app'].state.pipeline.store.close()
        _REQUEST.reset(token)


def _stats():
    slot=_REQUEST.get()
    records=slot.get('agent_records') if slot else None
    return slot,getattr(getattr(records,'sql',None),'stats',None)


def sql_progress():
    """Cumulative SQL/Agent/CPU counters for model-call events (empty outside an Oracle request).

    request_cpu_ms is process CPU since the request started: other threads (log writers, a
    concurrent request) are included, so it is an upper bound for this request's own CPU.
    """
    slot,stats=_stats()
    if stats is None or not hasattr(stats,'progress'):return {}
    return {**stats.progress(),'cpu_ms_total':round((time.process_time()-slot['cpu_started'])*1000)}


def sql_summary():
    """This request's Oracle SQL totals and the process row cache, for one log line."""
    slot,stats=_stats()
    if stats is None:return None
    value=stats.summary()
    value['request_cpu_ms']=round((time.process_time()-slot['cpu_started'])*1000)
    cache=getattr(slot['agent_records'].sql,'shared_cache',None)
    if cache is not None:
        status=cache.status()
        value.update(cache_entries=status['entries'],cache_bytes=status['bytes'],cache_evictions=status['evictions'])
    return value


def environment_binding():
    names=('GENOS_ORACLE_AGENT_NAMESPACE','GENOS_ORACLE_AGENT_MEMORY_MIB','GENOS_ORACLE_TABLE_MAPPING','GENOS_STATE_DIR','GENOS_JOURNAL_STORAGE','GENOS_RUNTIME_LIMIT_MIB','GENOS_RUNTIME_RESERVE_MIB','GENOS_RUNTIME_MIN_FREE_MIB','GENOS_RAG_INITIAL_SEARCH','GENOS_EMBED_URL','GENOS_BASE_URL','GENOS_EMBED_SERVING_ID','GENOS_EMBED_KEY','DP','DP_QUERY_RELEASE_ID','DP_QUERY_CHANNEL','GENOS_RUNTIME_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR',
           'GENOS_EMBED_PROFILE_SHA256','GENOS_EMBED_MODEL','GENOS_EMBED_API_PREFIX','GENOS_GATEWAY_API_PREFIX',
           'GENOS_EMBED_ID','GENOS_EMBED_TOKEN','GENOS_URL',
           'GENOS_EMBED_TENANT_ID','GENOS_EMBED_TIMEOUT','GENOS_EMBED_CONNECT_TIMEOUT',
           'GENOS_ORACLE_GOLD_OWNER','ORACLE_ORDS_BASE_URL','LLMOPS_ORDS_BASE_URL','ORACLE_ORDS_SCHEMA',
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
        self.shared_rows=SharedRows(self.client,self.environment)
        self.release_id=os.environ.get('DP_QUERY_RELEASE_ID','').strip() or None
        self.implicit_channel=not self.release_id and not os.environ.get('DP_QUERY_CHANNEL','').strip()
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
                      'serving_data_cache':'process-memory' if self.shared_rows.enabled else False,
                      'serving_data_cache_revision':self.shared_rows.status()['revision'],
                      'serving_data_cache_mib':self.shared_rows.settings['mib'],
                      'state_storage':'oracle','persistent_sqlite':False,
                      'record_computation':'request-local-memory',
                      'query_channel':self.channel,'query_release_id':self.release_id,
                      'dp_environment_binding':self.environment,'service_entry_sha256':host._sha(Path(host.__file__))}
        mapping=getattr(self.client,'schema_map',None)
        if mapping is not None:
            self.binding.update(physical_mapping_profile=mapping.profile,
                                physical_mapping_sha256=mapping.target_sha256)
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
        sql.shared_cache=self.shared_rows
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
                if getattr(schema,'profile',None) in ('development_g19_1','gold'):
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
        if self.implicit_channel:
            selected=_implicit_release(sql)
        else:
            selected=select_release(sql,release_id=self.release_id,channel=self.channel)
        manifest=selected['manifest'];snapshot=Snapshot.open(sql,manifest['source_release_id'])
        if manifest['dataset_version']!=snapshot.dataset_version or manifest['source_manifest']!=snapshot.manifest:
            raise DPError('QUERY_SOURCE_BINDING: selected query/source release differs')
        allowed=set(snapshot.manifest['scope']['document_version_ids'])-snapshot.excluded
        from . import observability as obs
        obs.event(obs.get_logger('oracle.query'),'oracle.release.selected',query_release_id=selected['release_id'],
                  query_channel=selected.get('channel',self.channel),
                  pointer_revision=selected['revision'],generation_id=snapshot.generation_id,
                  data_provider='oracle',serving_data_cache=self.shared_rows.enabled)
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
        # Pin and validate descriptors only. Do not walk corpus/search tables here; the
        # declared-name list (units holding 이하) is built in a background thread instead.
        request=self.request();store=Store(request)
        try:
            from .oracle_query_index import Index
            from .oracle_query_fulltext import UnitIndex
            store.selection.require_latest();Index(store);fulltext=UnitIndex(request)
            return {'data_provider':'oracle','mode':'oracle-query','state_storage':'oracle','persistent_sqlite':False,'nfs_required':False,'query_release_id':request.release_id,
                    'query_pointer_revision':request.pointer_revision,'document_count':len(request.sources.allowed),
                    'serving_data_cache':'process-memory' if self.shared_rows.enabled else False,
                    'shared_rows':self.shared_rows.status(),'source_downloaded':False,'sql_calls':request.sql.calls,
                    'declared_names_preload':self.preload_declared_names(fulltext.manifest['index_sha256'])}
        finally: store.close()

    def preload_declared_names(self,identity):
        """Build the declared-name list off the request path (local Oracle, 1,547 documents:
        a request-path build took 47 s of SQL). Requests meanwhile use what is cached."""
        if os.environ.get('GENOS_DECLARED_NAMES_PRELOAD','on').strip().lower() in ('0','off','false','no'):
            return 'off'
        from .legal_agent.declared_names import CACHE
        if not CACHE.reserve(identity):return 'running'
        def run():
            from . import observability as obs
            log=obs.get_logger('oracle.query');started=time.monotonic();calls=None
            try:
                with request_context():
                    request=self.request();store=Store(request)
                    try:
                        from .oracle_query_index import Index
                        from .oracle_query_fulltext import UnitIndex
                        documents=sorted(request.sources.allowed);tools=Index(store).tools(documents)
                        try:
                            fulltext=UnitIndex(request)
                            found,report=CACHE.documents(fulltext,fulltext,tools.sources,documents,preload=True)
                        finally:tools.db.close()
                        calls=request.sql.calls
                    finally:store.close()
                obs.event(log,'declared_names.preload',state='READY',seconds=round(time.monotonic()-started,3),sql_calls=calls,
                          documents=report['documents'],read_units=report['read_units'],
                          declaring_documents=sum(bool(v) for v in found.values()),declarations=sum(len(v) for v in found.values()))
            except Exception as exc:
                obs.event(log,'declared_names.preload',level=40,state='FAILED',error_type=type(exc).__name__,
                          seconds=round(time.monotonic()-started,3),exc_info=True)
            finally:
                CACHE.release(identity)
        from contextvars import Context
        thread=threading.Thread(target=lambda:Context().run(run),name='declared-names-preload',daemon=True)
        try:thread.start()
        except BaseException:
            CACHE.release(identity);raise
        return 'started'
