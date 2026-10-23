"""Opt-in bounded, request-scoped aggregate timings. Never logs call arguments."""
from contextvars import ContextVar
from functools import wraps
import hashlib
import heapq
import importlib
import inspect
import marshal
import os
import threading
import time

REVISION = 'genos-function-timing-20261022-r1'
_CURRENT = ContextVar('genos_function_timing', default=None)
_LOCAL = threading.local()
_INSTALL_LOCK = threading.Lock()
_INSTALLED = None
MAX_CALLS = 200000
MAX_KEYS = 20000
MAX_SECONDS = 900
MAX_EDGES = 512
# No profile of global JSON/hash/log calls: restrict overhead to selected paths.
TARGETS = {
 'legal_agent.tool_availability': ['filter_navigation','navigation_reason','article_plan','article_sequence','sequence_cost','read_cost','context_plans','require_navigation'],
 'legal_agent.unit_reading': ['offers','blocks'],
 'legal_agent.connected_exploration': ['menu','load_page'],
 'legal_agent.law_navigation': ['Investigation.view','Investigation.build_view','Investigation.save','Investigation.bounded_model_view','decision_schema'],
 'legal_agent.decision_projection': ['choose_read','read_candidate_rows'],
 'legal_agent.output_contract': ['DecisionJournal.state','DecisionJournal.reserve'],
 'legal_agent.repository': ['WorkRepository.evidence','WorkRepository.heads','WorkRepository.navigation_save','WorkRepository.flush_navigation','WorkRepository.save_view','WorkRepository.reserve_attempt','WorkRepository.finish_attempt'],
 'legal_agent.transport': ['GenosTransport.send_once','GenosTransport.send_stream_once'],
 'storage': ['Store.source','Store.sources','Store.check_unchanged','Store.binding_signature','verify_store_binding'],
 'search_selection': ['Selection.check_unchanged','runtime_binding'],
 'unit_fulltext': ['UnitFulltextIndex.rank','UnitFulltextIndex.rank_units','UnitFulltextIndex.law_groups_page','UnitFulltextIndex.article_groups_page','UnitFulltextIndex.hit_page','UnitFulltextIndex._projection'],
 'fulltext': ['FulltextIndex.rank','_search_forms'],
 'folder_navigation': ['bind_catalogue'],
 'team_scope': ['prepared_catalogue','generation_key'],
 'oracle_query_store': ['Store.source','Store.sources','Store.check_unchanged'],
 'oracle_query_fulltext': ['UnitIndex.rank','UnitIndex.article_groups_page','UnitIndex.hit_page'],
 'query_latency': ['rows'],
}


def _safe_emit(event, **fields):
    try:
        from semantic_runtime import observability as obs
        obs.event(obs.get_logger('function-timing'), event, probe_revision=REVISION, **fields)
    except Exception:
        # Measurement must never mask the application's result or exception.
        pass


class Collector:
    def __init__(self, *, max_calls=MAX_CALLS, max_keys=MAX_KEYS, max_seconds=MAX_SECONDS):
        self.start = time.perf_counter_ns()
        self.max_calls, self.max_keys = max_calls, max_keys
        self.deadline = self.start + int(max_seconds * 1e9)
        self.lock = threading.Lock()
        self.calls = self.skipped = self.inflight = self.max_inflight = 0
        self.rows, self.edges, self.slow = {}, {}, []
        self.keys, self.threads = set(), set()
        self.source_calls = self.source_repeats = self.source_keys_overflow = 0
        self.warnings = set()
        self.closed = False

    def enter(self, label, args, kwargs):
        now = time.perf_counter_ns()
        with self.lock:
            if self.closed or self.calls >= self.max_calls or now > self.deadline:
                self.skipped += 1
                self.warnings.add('COLLECTION_LIMIT_OR_CLOSED')
                return None
            self.calls += 1
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            self.threads.add(threading.get_ident())
            number = self.calls
            if label.endswith('.Store.source'):
                self.source_calls += 1
                did = args[1] if len(args) > 1 else kwargs.get('did')
                bid = args[2] if len(args) > 2 else kwargs.get('bid')
                # Never invoke repr/str on arbitrary application objects.
                if args and type(did) in (str,int) and type(bid) in (str,int) and len(str(did)) <= 512 and len(str(bid)) <= 512:
                    key = (label, id(args[0]), did, str(bid))
                    if key in self.keys:
                        self.source_repeats += 1
                    elif len(self.keys) < self.max_keys:
                        self.keys.add(key)
                    else:
                        self.source_keys_overflow += 1
                        self.warnings.add('SOURCE_UNIQUE_KEYS_LIMIT')
        return number

    def finish(self, frame, failed, error_type, candidate_count):
        end = time.perf_counter_ns()
        cpu = time.thread_time_ns() - frame['cpu']
        elapsed = end - frame['start']
        own = max(0, elapsed - frame['children'])
        own_cpu = max(0, cpu - frame['children_cpu'])
        with self.lock:
            self.inflight -= 1
            if self.closed:
                return elapsed, cpu
            label = frame['label']
            if label not in self.rows and len(self.rows) >= 255:
                label = 'OTHER_FUNCTION_LIMIT'
                self.warnings.add('FUNCTION_LIMIT')
            row = self.rows.setdefault(label, dict(calls=0, errors=0, wall_ns=0,
                self_ns=0, cpu_ns=0, self_cpu_ns=0, max_ns=0, candidate_total=0, candidate_max=0))
            row['calls'] += 1; row['errors'] += int(failed)
            row['wall_ns'] += elapsed; row['self_ns'] += own
            row['cpu_ns'] += cpu; row['self_cpu_ns'] += own_cpu
            row['max_ns'] = max(row['max_ns'], elapsed)
            row['candidate_total'] += candidate_count
            row['candidate_max'] = max(row['candidate_max'], candidate_count)
            edge_key = (frame['parent'], frame['label'])
            if edge_key in self.edges or len(self.edges) < MAX_EDGES:
                edge = self.edges.setdefault(edge_key, dict(calls=0,wall_ns=0,self_ns=0))
                edge['calls'] += 1; edge['wall_ns'] += elapsed; edge['self_ns'] += own
            else:
                self.warnings.add('EDGE_LIMIT')
            item = (elapsed, frame['number'], {'function':frame['label'], 'parent':frame['parent'],
                'start_ms':round((frame['start']-self.start)/1e6,3), 'duration_ms':round(elapsed/1e6,3),
                'self_ms':round(own/1e6,3), 'failed':failed, 'error_type':error_type})
            if len(self.slow) < 30: heapq.heappush(self.slow,item)
            elif item[:2] > self.slow[0][:2]: heapq.heapreplace(self.slow,item)
        return elapsed, cpu

    def summary(self):
        with self.lock:
            self.closed = True
            if self.inflight: self.warnings.add('INFLIGHT_AT_REQUEST_END')
            def convert(row):
                return {k[:-3]+'_ms' if k.endswith('_ns') else k:
                        round(v/1e6,3) if k.endswith('_ns') else v for k,v in row.items()}
            return {'schema_version':'genos-function-timing-v1',
                'request_scope_ms':round((time.perf_counter_ns()-self.start)/1e6,3),
                'measured_calls':self.calls, 'completed_calls':sum(r['calls'] for r in self.rows.values()),
                'skipped_calls':self.skipped, 'thread_count':len(self.threads),
                'inflight_calls':self.inflight,'warnings':sorted(self.warnings),
                'source_calls':self.source_calls,'source_unique_blocks':len(self.keys),
                'source_repeated_blocks':self.source_repeats,'source_untracked_blocks':self.source_keys_overflow,
                'functions':[{'function':k,**convert(v)} for k,v in sorted(self.rows.items())],
                'edges':[{'parent':k[0],'function':k[1],**convert(v)} for k,v in sorted(self.edges.items())],
                'slow_calls':[v[2] for v in sorted(self.slow,reverse=True)]}


def measured(function, label):
    @wraps(function)
    def wrapped(*args, **kwargs):
        collector = _CURRENT.get()
        if collector is None: return function(*args, **kwargs)
        try:
            number = collector.enter(label,args,kwargs)
        except Exception:
            collector.warnings.add('PROBE_ENTER_ERROR')
            return function(*args, **kwargs)
        if number is None: return function(*args, **kwargs)
        stack = getattr(_LOCAL,'stack',None)
        if stack is None: stack = _LOCAL.stack = []
        parent = stack[-1] if stack and stack[-1]['collector'] is collector else None
        frame = {'collector':collector,'number':number,'label':label,
            'parent':parent['label'] if parent else 'ROOT', 'children':0,'children_cpu':0,
            'start':time.perf_counter_ns(),'cpu':time.thread_time_ns()}
        stack.append(frame)
        failed = False; error_type = None
        candidates = len(args[2]) if label.endswith('.filter_navigation') and len(args)>2 and type(args[2]) is dict else 0
        try:
            return function(*args, **kwargs)
        except BaseException as exc:
            failed = True; error_type = type(exc).__name__
            raise
        finally:
            stack.pop()
            try:
                elapsed,cpu = collector.finish(frame,failed,error_type,candidates)
                if parent:
                    parent['children'] += elapsed
                    parent['children_cpu'] += cpu
            except Exception:
                collector.warnings.add('PROBE_FINISH_ERROR')
    wrapped._genos_timing_probe = REVISION
    return wrapped


def install():
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED is not None: return _INSTALLED
        installed, missing, code = [], [], {}
        for relative, names in TARGETS.items():
            try: module = importlib.import_module('semantic_runtime.'+relative)
            except Exception as exc:
                missing.extend(relative+'.'+name+':'+type(exc).__name__ for name in names)
                continue
            for name in names:
                label = relative+'.'+name
                try:
                    owner = module
                    for part in name.split('.')[:-1]: owner=getattr(owner,part)
                    attr = name.split('.')[-1]
                    original = getattr(owner,attr)
                    if not inspect.isfunction(original) or inspect.iscoroutinefunction(original) or inspect.isgeneratorfunction(original):
                        raise TypeError('unsupported callable')
                    if getattr(original,'_genos_timing_probe',None) != REVISION:
                        code[label]=hashlib.sha256(marshal.dumps(original.__code__)).hexdigest()
                        setattr(owner,attr,measured(original,label))
                    installed.append(label)
                except Exception as exc:
                    missing.append(label+':'+type(exc).__name__)
        try:
            latency = importlib.import_module('semantic_runtime.query_latency')
            latency.span = measured_span(latency.span)
            installed.append('query_latency.span')
        except Exception as exc:
            missing.append('query_latency.span:'+type(exc).__name__)
        _INSTALLED = {'installed':installed,'missing':missing,'loaded_code_fingerprints':[{'function':k,'sha256':v} for k,v in sorted(code.items())]}
        return _INSTALLED


def scope_call(function):
    """Wrap the existing async reported dispatch; reports close after this returns."""
    @wraps(function)
    async def wrapped(config,data,payload,question_body,started,report,request_id,api_type):
        allowed = {'LEGAL_AGENT','ELS_QUERY','RAG_ASK','WORKFLOW_RUN','WORKFLOW_RESUME'}
        is_call = str(payload.get('op','')).lower()=='call' and payload.get('path') in {
            '/v1/rag/ask','/v1/workflows/run','/v1/workflows/resume'}
        if os.environ.get('GENOS_FUNCTION_TIMING','').strip() != '1' or not (api_type in allowed or is_call):
            return await function(config,data,payload,question_body,started,report,request_id,api_type)
        setup = time.perf_counter()
        try:
            coverage = install()
            collector = Collector()
        except Exception as exc:
            _safe_emit('timing.probe.failed',request_id=request_id,error_type=type(exc).__name__,stage='setup')
            return await function(config,data,payload,question_body,started,report,request_id,api_type)
        _safe_emit('timing.probe.started',request_id=request_id,setup_ms=round((time.perf_counter()-setup)*1000,3),
            coverage=coverage, max_calls=MAX_CALLS, max_seconds=MAX_SECONDS)
        token = _CURRENT.set(collector)
        try:
            return await function(config,data,payload,question_body,started,report,request_id,api_type)
        finally:
            _CURRENT.reset(token)
            try:
                summary = collector.summary()
                _safe_emit('timing.probe.summary',request_id=request_id,profile=summary)
            except Exception as exc:
                _safe_emit('timing.probe.failed',request_id=request_id,error_type=type(exc).__name__,stage='summary')
    return wrapped


def measured_span(original):
    from contextlib import contextmanager
    @contextmanager
    def wrapped(name, *, pressure=False, **fields):
        collector = _CURRENT.get()
        if collector is None:
            with original(name,pressure=pressure,**fields) as values: yield values
            return
        # Span labels are developer-authored identifiers, not arbitrary content.
        import re
        label = 'span.'+name if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',name) else 'span.other'
        try:
            number = collector.enter(label,(),{})
        except Exception:
            collector.warnings.add('PROBE_SPAN_ENTER_ERROR')
            number = None
        if number is None:
            with original(name,pressure=pressure,**fields) as values: yield values
            return
        stack = getattr(_LOCAL,'stack',None)
        if stack is None: stack = _LOCAL.stack = []
        parent = stack[-1] if stack and stack[-1]['collector'] is collector else None
        frame = {'collector':collector,'number':number,'label':label,
            'parent':parent['label'] if parent else 'ROOT','children':0,'children_cpu':0,
            'start':time.perf_counter_ns(),'cpu':time.thread_time_ns()}
        stack.append(frame)
        failed=False;error_type=None
        try:
            with original(name,pressure=pressure,**fields) as values: yield values
        except BaseException as exc:
            failed=True;error_type=type(exc).__name__
            raise
        finally:
            stack.pop()
            try:
                elapsed,cpu=collector.finish(frame,failed,error_type,0)
                if parent:
                    parent['children']+=elapsed;parent['children_cpu']+=cpu
            except Exception:
                collector.warnings.add('PROBE_SPAN_FINISH_ERROR')
    return wrapped
