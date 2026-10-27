"""Opt-in bounded, request-scoped timing for GENOS code serving.

Three views of one request, all numeric/code-location only:
- model-call boundaries split the request into segments (PRE, G0, M1, G1, ... POST);
- a stack sampler attributes each segment's wall time to code lines, including
  code nobody thought to hook;
- selected function hooks count calls (source lookups, binding checks, ...).
Never records call arguments, return values, question/answer/source text or
exception messages. Measurement failures never change the request result.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import gc
import hashlib
import heapq
import importlib
import inspect
import marshal
import os
from pathlib import Path
import re
import sys
import threading
import time

REVISION = 'genos-function-timing-20261024-r2'
SCHEMA = 'genos-function-timing-v2'
_CURRENT = ContextVar('genos_function_timing', default=None)
_LOCAL = threading.local()
_INSTALL_LOCK = threading.Lock()
_INSTALLED = None
_BOUNDARIES = None
_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()
# The GC callback can run inside any allocation, including while a probe lock is
# held by the same thread. It therefore reads this tuple and appends without locks.
_ACTIVE_SNAPSHOT = ()
_GC_START = {}
MAX_GC_EVENTS = 200000
MAX_CALLS = 2000000
MAX_KEYS = 20000
MAX_SECONDS = 1900
MAX_EDGES = 512
MAX_SEGMENTS = 200
MAX_DEPTH = 512
SAMPLE_TABLE_LIMIT = 20000
FRAME_CACHE_LIMIT = 50000
DETAIL_SEGMENTS = 10
DEFAULT_INTERVAL_MS = 10
CODE_ROOT = Path(__file__).resolve().parent
PROBE_FILE = str(Path(__file__).resolve())
_UNSAFE = re.compile(r'[^A-Za-z0-9_./:<>-]')
_STAGE = re.compile(r'[A-Za-z0-9_.:-]{1,80}\Z')
# No profile of global JSON/hash/log calls: the sampler covers them without overhead.
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
# Leaf-module categories are a reading aid only, never a root-cause verdict.
CATEGORIES = (
 ('file_metadata', ('std:pathlib', 'std:genericpath', 'std:posixpath', 'std:os.py', 'std:stat')),
 ('json', ('std:json/',)),
 ('copy', ('std:copy.py',)),
 ('wait_thread_lock_queue', ('std:threading.py', 'std:queue.py', 'std:concurrent/')),
 ('network_or_event_loop', ('std:socket.py', 'std:ssl.py', 'std:http/client.py', 'std:selectors.py', 'std:asyncio/',
                            'std:urllib/request.py', 'pkg:httpx/', 'pkg:httpcore/', 'pkg:h11/', 'pkg:anyio/', 'pkg:starlette/')),
 ('json_schema_validation', ('pkg:jsonschema/', 'pkg:referencing/', 'pkg:jsonschema_specifications/')),
 ('logging', ('std:logging/',)),
 ('regex', ('std:re/', 'std:sre_')),
 ('hash_or_compress', ('std:hashlib.py', 'std:gzip.py', 'std:zlib', 'std:base64.py')),
 ('sqlite_module', ('std:sqlite3/',)),
)


def _safe_emit(event, **fields):
    try:
        from semantic_runtime import observability as obs
        obs.event(obs.get_logger('function-timing'), event, probe_revision=REVISION, **fields)
    except Exception:
        # Measurement must never mask the application's result or exception.
        pass


def _read(path):
    with open(path, 'rb') as source:
        return source.read(8192).decode('ascii', 'replace')


def _fields(path, names, separator=':'):
    try:
        out = {}
        for line in _read(path).splitlines():
            name, _, value = line.partition(separator)
            if name.strip() in names:
                out[names[name.strip()]] = int(value.split()[0])
        return out or None
    except Exception:
        return None


_IO = {'rchar':'read_chars','wchar':'write_chars','syscr':'read_calls','syscw':'write_calls',
       'read_bytes':'storage_read_bytes','write_bytes':'storage_write_bytes'}
_STATUS = {'voluntary_ctxt_switches':'voluntary_switches','nonvoluntary_ctxt_switches':'involuntary_switches'}


def _schedstat(path):
    try:
        cpu, wait, slices = (int(v) for v in _read(path).split()[:3])
        return {'sched_cpu_ns':cpu,'runqueue_wait_ns':wait,'timeslices':slices}
    except Exception:
        return None


def _cgroup():
    for path, names in (('/sys/fs/cgroup/cpu.stat', {'nr_throttled':'throttled_periods','throttled_usec':'throttled_us'}),
                        ('/sys/fs/cgroup/cpu/cpu.stat', {'nr_throttled':'throttled_periods','throttled_time':'throttled_ns'})):
        value = _fields(path, names, ' ')
        if value:
            if 'throttled_us' in value: value['throttled_ns'] = value.pop('throttled_us')*1000
            return value
    return None


def _snapshot():
    """Counters at a segment boundary; thread values belong to the calling thread."""
    return {'t':time.perf_counter_ns(),'thread':threading.get_ident(),'thread_cpu':time.thread_time_ns(),
            'process_cpu':time.process_time_ns(),'thread_io':_fields('/proc/thread-self/io',_IO),
            'thread_status':_fields('/proc/thread-self/status',_STATUS),
            'sched':_schedstat('/proc/thread-self/schedstat'),'process_io':_fields('/proc/self/io',_IO),
            'cgroup':_cgroup()}


def _delta(a, b, prefix=''):
    if not a or not b: return {}
    return {prefix+k:max(0,b[k]-a[k]) for k in a if k in b}


def _ms(ns): return round(ns/1e6, 3)


def _stage(value):
    value = str(value or '')
    return value if _STAGE.fullmatch(value) else 'other'


class Collector:
    def __init__(self, *, max_calls=MAX_CALLS, max_keys=MAX_KEYS, max_seconds=MAX_SECONDS,
                 hooks=True, interval_ms=DEFAULT_INTERVAL_MS):
        self.start = time.perf_counter_ns()
        self.max_calls, self.max_keys = max_calls, max_keys
        self.deadline = self.start + int(max_seconds * 1e9)
        self.hooks, self.interval_ms = hooks, interval_ms
        self.lock = threading.Lock()
        self.calls = self.skipped = self.inflight = self.max_inflight = 0
        self.rows, self.edges, self.slow = {}, {}, []
        self.keys, self.threads = set(), set()
        self.source_calls = self.source_repeats = self.source_keys_overflow = 0
        self.warnings = set()
        self.closed = False
        # Segment state: PRE -> G0 -> M1 -> G1 ... -> POST.
        self.model_depth = self.model_started = self.model_finished = 0
        self.window_depth = 0
        self.window_state = 'none'
        self.window_threads, self.thread_depth = {}, {}
        self.loop_thread = None
        self.pending_stage = None
        self.segments = []
        self.seg_stats, self.seg_functions = {}, {}
        # Sampling tables keyed by (segment, frame).
        self.leaf, self.own_lines, self.functions, self.stacks, self.categories = {}, {}, {}, {}, {}
        self.frame_cache, self.file_cache = {}, {}
        self.ticks = self.late_ticks = 0
        self.sampler_cpu_ns = 0
        self.overflow_ns = 0
        self.concurrency_peak = 1
        self.gc_events, self.gc_overflow = [], False
        self.open_segment = {'label':'PRE','start':_snapshot(),'meta':{}}
        self.segment_start = self.open_segment['start']['t']

    def warn(self, name):
        with self.lock: self.warnings.add(name)

    def stats(self, label):
        row = self.seg_stats.get(label)
        if row is None:
            row = self.seg_stats[label] = dict(source_calls=0, check_calls=0, hook_calls=0,
                                               samples=0, sampled_ns=0, late_ns=0, threads_max=0)
        return row

    def label(self):
        if self.model_depth > 0: return 'M'+str(self.model_started)
        if self.window_state == 'closed': return 'POST'
        if self.window_state == 'open' or self.model_finished: return 'G'+str(self.model_finished)
        return 'PRE'

    # ---- function hooks (R1 semantics, plus per-segment counts) ----
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
            ident = threading.get_ident()
            self.threads.add(ident)
            self.thread_depth[ident] = self.thread_depth.get(ident, 0)+1
            number = self.calls
            segment = self.label()
            stats = self.stats(segment)
            stats['hook_calls'] += 1
            if label.endswith('.check_unchanged'): stats['check_calls'] += 1
            if label.endswith('.Store.source'):
                self.source_calls += 1
                stats['source_calls'] += 1
                did = args[1] if len(args) > 1 else kwargs.get('did')
                bid = args[2] if len(args) > 2 else kwargs.get('bid')
                # Never invoke repr/str on arbitrary application objects.
                if args and type(did) in (str,int) and type(bid) in (str,int) and len(str(did)) <= 512 and len(str(bid)) <= 512:
                    entry = (label, id(args[0]), did, str(bid))
                    if entry in self.keys:
                        self.source_repeats += 1
                    elif len(self.keys) < self.max_keys:
                        self.keys.add(entry)
                    else:
                        self.source_keys_overflow += 1
                        self.warnings.add('SOURCE_UNIQUE_KEYS_LIMIT')
        return number, segment

    def finish(self, frame, failed, error_type, candidate_count):
        end = time.perf_counter_ns()
        cpu = time.thread_time_ns() - frame['cpu']
        elapsed = end - frame['start']
        own = max(0, elapsed - frame['children'])
        own_cpu = max(0, cpu - frame['children_cpu'])
        with self.lock:
            self.inflight -= 1
            ident = threading.get_ident()
            depth = self.thread_depth.get(ident, 1)-1
            if depth > 0: self.thread_depth[ident] = depth
            else: self.thread_depth.pop(ident, None)
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
            seg_key = (frame['segment'], label)
            if seg_key in self.seg_functions or len(self.seg_functions) < 5000:
                seg_row = self.seg_functions.setdefault(seg_key, dict(calls=0, wall_ns=0, self_ns=0))
                seg_row['calls'] += 1; seg_row['wall_ns'] += elapsed; seg_row['self_ns'] += own
            else:
                self.warnings.add('SEGMENT_FUNCTION_LIMIT')
            edge_key = (frame['parent'], frame['label'])
            if edge_key in self.edges or len(self.edges) < MAX_EDGES:
                edge = self.edges.setdefault(edge_key, dict(calls=0,wall_ns=0,self_ns=0))
                edge['calls'] += 1; edge['wall_ns'] += elapsed; edge['self_ns'] += own
            else:
                self.warnings.add('EDGE_LIMIT')
            item = (elapsed, frame['number'], {'function':frame['label'], 'parent':frame['parent'],
                'segment':frame['segment'], 'start_ms':_ms(frame['start']-self.start), 'duration_ms':_ms(elapsed),
                'self_ms':_ms(own), 'failed':failed, 'error_type':error_type})
            if len(self.slow) < 30: heapq.heappush(self.slow,item)
            elif item[:2] > self.slow[0][:2]: heapq.heapreplace(self.slow,item)
        return elapsed, cpu

    # ---- segment boundaries ----
    def boundary(self, change):
        snap = _snapshot()
        with self.lock:
            if self.closed: return
            before = self.label()
            change()
            after = self.label()
            if after == before: return
            self._close(snap)
            self._open(after, snap)

    def _close(self, end):
        seg = self.open_segment
        if seg is None: return
        start = seg['start']
        row = {'segment':seg['label'], 'start_ms':_ms(start['t']-self.start), 'wall_ms':_ms(end['t']-start['t']),
               'process_cpu_ms':_ms(max(0, end['process_cpu']-start['process_cpu'])),
               'same_thread':start['thread'] == end['thread'], **seg['meta']}
        if row['same_thread']:
            row['thread_cpu_ms'] = _ms(max(0, end['thread_cpu']-start['thread_cpu']))
            row.update(_delta(start['thread_io'], end['thread_io'], 'thread_'))
            row.update(_delta(start['thread_status'], end['thread_status'], 'thread_'))
            sched = _delta(start['sched'], end['sched'])
            if sched:
                row['runqueue_wait_ms'] = _ms(sched['runqueue_wait_ns'])
                row['timeslices'] = sched['timeslices']
        row.update(_delta(start['process_io'], end['process_io'], 'process_'))
        cgroup = _delta(start['cgroup'], end['cgroup'], 'cgroup_')
        if 'cgroup_throttled_ns' in cgroup: cgroup['cgroup_throttled_ms'] = _ms(cgroup.pop('cgroup_throttled_ns'))
        row.update(cgroup)
        if len(self.segments) < MAX_SEGMENTS: self.segments.append(row)
        else: self.warnings.add('SEGMENT_LIMIT')
        self.open_segment = None

    def _open(self, label, start):
        meta = {}
        if label.startswith('M'):
            meta['stage'] = self.pending_stage or 'other'
            if self.segments and self.segments[-1]['segment'][0] in 'GP':
                self.segments[-1]['next_stage'] = meta['stage']
        elif label.startswith('G') and self.segments and self.segments[-1]['segment'].startswith('M'):
            meta['previous_stage'] = self.segments[-1].get('stage', 'other')
        self.open_segment = {'label':label, 'start':start, 'meta':meta}
        self.segment_start = start['t']

    def model_enter(self, stage):
        stage = _stage(stage)
        def change():
            self.model_depth += 1
            if self.model_depth == 1:
                self.model_started += 1
                self.pending_stage = stage
        self.boundary(change)

    def model_exit(self):
        def change():
            if self.model_depth > 0:
                self.model_depth -= 1
                if self.model_depth == 0: self.model_finished += 1
        self.boundary(change)

    def window_enter(self):
        ident = threading.get_ident()
        def change():
            self.window_depth += 1
            self.window_threads[ident] = self.window_threads.get(ident, 0)+1
            self.window_state = 'open'
        self.boundary(change)

    def window_exit(self):
        ident = threading.get_ident()
        def change():
            self.window_depth = max(0, self.window_depth-1)
            remaining = self.window_threads.get(ident, 0)-1
            if remaining > 0: self.window_threads[ident] = remaining
            else: self.window_threads.pop(ident, None)
            if self.window_depth == 0: self.window_state = 'closed'
        self.boundary(change)

    def gc_event(self, end, duration, generation):
        # Lock-free by design (see _ACTIVE_SNAPSHOT); list.append is atomic.
        if self.closed: return
        if len(self.gc_events) < MAX_GC_EVENTS: self.gc_events.append((end, duration, generation))
        else: self.gc_overflow = True

    def _attribute_gc(self):
        events = sorted(self.gc_events)
        index = 0
        for seg in self.segments:
            start = self.start+int(seg['start_ms']*1e6); end = start+int(seg['wall_ms']*1e6)
            total = count = gen2 = 0
            while index < len(events) and events[index][0] < start: index += 1
            while index < len(events) and events[index][0] <= end:
                total += events[index][1]; count += 1; gen2 += events[index][2] == 2; index += 1
            seg['gc_ms'], seg['gc_count'], seg['gc_gen2'] = _ms(total), count, gen2

    # ---- stack sampling ----
    def _file(self, filename):
        cached = self.file_cache.get(filename)
        if cached is not None: return cached
        path = str(filename)
        # Libraries first: a virtualenv may live inside the checkout.
        if path == PROBE_FILE:
            result = ('probe', False)
        elif '/site-packages/' in path or '/dist-packages/' in path:
            result = ('pkg:'+re.split(r'/(?:site|dist)-packages/', path)[-1], False)
        elif re.search(r'/lib/python3\.[0-9]+/', path):
            result = ('std:'+re.split(r'/lib/python3\.[0-9]+/', path)[-1], False)
        elif path.startswith(str(CODE_ROOT)+os.sep):
            result = (path[len(str(CODE_ROOT))+1:], True)
        else:
            result = ('ext:'+Path(path).name, False)
        result = (_UNSAFE.sub('_', result[0])[:160], result[1])
        if len(self.file_cache) < 5000: self.file_cache[filename] = result
        return result

    def _code(self, code):
        """Per-code-object labels; line numbers are computed only where reported."""
        cached = self.frame_cache.get(code)
        if cached is not None: return cached
        name, own = self._file(code.co_filename)
        qual = _UNSAFE.sub('_', getattr(code, 'co_qualname', code.co_name))[:120]
        category = None if own else next((label for label, prefixes in CATEGORIES if name.startswith(prefixes)), None)
        result = (name+':'+qual, own, name, category)
        if len(self.frame_cache) < FRAME_CACHE_LIMIT: self.frame_cache[code] = result
        return result

    def _stack(self, frame):
        infos, leaf_line, own_line, depth = [], None, None, 0
        while frame is not None and depth < MAX_DEPTH:
            info = self._code(frame.f_code)
            if info[2] != 'probe':
                if not infos: leaf_line = info[0]+':'+str(frame.f_lineno or 0)
                if own_line is None and info[1]: own_line = info[0]+':'+str(frame.f_lineno or 0)
                infos.append(info)
            frame = frame.f_back; depth += 1
        return infos, leaf_line, own_line

    def _bump(self, table, entry, weight):
        row = table.get(entry)
        if row is None:
            if len(table) >= SAMPLE_TABLE_LIMIT:
                self.overflow_ns += weight; self.warnings.add('SAMPLE_TABLE_LIMIT')
                return
            row = table[entry] = [0, 0]
        row[0] += 1; row[1] += weight

    def sample(self, now, weight, late):
        with self.lock:
            if self.closed: return
            segment = self.label()
            # Time before this segment's boundary belongs to the previous segment; leave it unsampled.
            weight = max(0, min(weight, now-self.segment_start))
            targets = set(self.window_threads)
            targets.update(t for t, depth in self.thread_depth.items() if depth > 0)
            if self.loop_thread is not None and self.window_state != 'open': targets.add(self.loop_thread)
        frames = sys._current_frames()
        stacks = [self._stack(frames[t]) for t in targets if t in frames]
        del frames
        with self.lock:
            if self.closed: return
            self.ticks += 1
            if late: self.late_ticks += 1
            stats = self.stats(segment)
            stats['threads_max'] = max(stats['threads_max'], len(stacks))
            for infos, leaf_line, own_line in stacks:
                if not infos: continue
                stats['samples'] += 1; stats['sampled_ns'] += weight
                if late: stats['late_ns'] += weight
                leaf = infos[0]
                self._bump(self.leaf, (segment, leaf_line), weight)
                self._bump(self.own_lines, (segment, own_line or 'NO_OWN_FRAME'), weight)
                seen, own = set(), []
                for info in infos:
                    if info[1] and info[0] not in seen:
                        seen.add(info[0]); own.append(info[0]); self._bump(self.functions, (segment, info[0]), weight)
                path = tuple(reversed(own[:16]))+(() if leaf[1] else (leaf_line,))
                self._bump(self.stacks, (segment, path), weight)
                # Library frames between the leaf and our first own frame decide the category.
                category = 'own_code' if leaf[1] else 'other_library'
                for info in infos:
                    if info[1]: break
                    if info[3]:
                        category = info[3]; break
                self._bump(self.categories, (segment, category), weight)

    # ---- summary ----
    @staticmethod
    def _group(table):
        grouped = {}
        for (segment, frame), row in table.items():
            grouped.setdefault(segment, []).append((frame, row))
        return grouped

    @staticmethod
    def _top(grouped, segments, limit):
        merged = {}
        for segment in segments:
            for frame, (count, weight) in grouped.get(segment, ()):
                row = merged.setdefault(frame, [0, 0]); row[0] += count; row[1] += weight
        rows = heapq.nlargest(limit, merged.items(), key=lambda item: item[1][1])
        return [{'frame':frame, 'ms':_ms(weight), 'samples':count} for frame, (count, weight) in rows]

    def summary(self):
        end = _snapshot()
        with self.lock:
            self._close(end)
            self.closed = True
            if self.inflight: self.warnings.add('INFLIGHT_AT_REQUEST_END')
            if self.model_depth: self.warnings.add('MODEL_CALL_OPEN_AT_REQUEST_END')
            if self.window_state == 'none': self.warnings.add('RAG_WINDOW_NOT_SEEN')
            if self.concurrency_peak > 1: self.warnings.add('CONCURRENT_REQUESTS_IN_PROCESS')
            if self.gc_overflow: self.warnings.add('GC_EVENT_LIMIT')
            def convert(row):
                return {k[:-3]+'_ms' if k.endswith('_ns') else k:
                        _ms(v) if k.endswith('_ns') else v for k,v in row.items()}
            nonmodel = [s for s in self.segments if not s['segment'].startswith('M')]
            detail = {s['segment'] for s in sorted(nonmodel, key=lambda s: s['wall_ms'], reverse=True)[:DETAIL_SEGMENTS]}
            own_files = set()
            leaf, own_lines, functions, categories, stack_rows, hooked = (self._group(t) for t in (
                self.leaf, self.own_lines, self.functions, self.categories, self.stacks, self.seg_functions))
            for seg in self.segments:
                label = seg['segment']
                seg.update(convert(self.stats(label)))
            self._attribute_gc()
            for seg in self.segments:
                label = seg['segment']
                if label.startswith('M'):
                    seg['top_leaf'] = self._top(leaf, {label}, 3)
                    continue
                size = 12 if label in detail else 3
                seg['top_own_lines'] = self._top(own_lines, {label}, size)
                seg['top_functions'] = self._top(functions, {label}, size)
                seg['top_leaf'] = self._top(leaf, {label}, 8 if label in detail else 2)
                seg['categories'] = self._top(categories, {label}, 12)
                if label in detail:
                    rows = heapq.nlargest(10, hooked.get(label, ()), key=lambda item: item[1]['self_ns'])
                    seg['hooked_functions'] = [{'function':name, **convert(v)} for name, v in rows]
            labels = {s['segment'] for s in nonmodel}
            stacks = []
            for label in sorted(detail, key=lambda l: -next(s['wall_ms'] for s in nonmodel if s['segment'] == l)):
                rows = heapq.nlargest(6, stack_rows.get(label, ()), key=lambda item: item[1][1])
                stacks += [{'segment':label, 'ms':_ms(w), 'samples':c, 'frames':list(path)} for path, (c, w) in rows]
            aggregate = {'segments':len(nonmodel), 'wall_ms':round(sum(s['wall_ms'] for s in nonmodel), 3),
                         'own_lines':self._top(own_lines, labels, 40),
                         'functions':self._top(functions, labels, 40),
                         'leaf':self._top(leaf, labels, 25),
                         'categories':self._top(categories, labels, 12)}
            for group in (aggregate['own_lines'], *(s.get('top_own_lines', []) for s in self.segments)):
                own_files.update(row['frame'].split(':', 1)[0] for row in group if ':' in row['frame'])
            sampled_ns = sum(v['sampled_ns'] for v in self.seg_stats.values())
            result = {'schema_version':SCHEMA, 'probe_revision':REVISION,
                'request_scope_ms':_ms(time.perf_counter_ns()-self.start),
                'mode':'full' if self.hooks else 'sample', 'interval_ms':self.interval_ms,
                'measured_calls':self.calls, 'completed_calls':sum(r['calls'] for r in self.rows.values()),
                'skipped_calls':self.skipped, 'thread_count':len(self.threads),
                'inflight_calls':self.inflight,'warnings':sorted(self.warnings),
                'source_calls':self.source_calls,'source_unique_blocks':len(self.keys),
                'source_repeated_blocks':self.source_repeats,'source_untracked_blocks':self.source_keys_overflow,
                'model_calls':self.model_started, 'concurrency_peak':self.concurrency_peak,
                'sampling':{'ticks':self.ticks, 'late_ticks':self.late_ticks, 'sampled_ms':_ms(sampled_ns),
                            'sampler_cpu_ms':_ms(self.sampler_cpu_ns), 'overflow_ms':_ms(self.overflow_ns)},
                'segments':self.segments, 'nonmodel':aggregate, 'stacks':stacks,
                'functions':[{'function':k,**convert(v)} for k,v in sorted(self.rows.items())],
                'edges':[{'parent':k[0],'function':k[1],**convert(v)} for k,v in sorted(self.edges.items())],
                'slow_calls':[v[2] for v in sorted(self.slow,reverse=True)]}
        result['own_files'] = _file_hashes(sorted(f for f in own_files if not f.startswith(('std:','pkg:','ext:','NO_OWN')))[:200])
        return result


def _file_hashes(names):
    rows = []
    for name in names:
        try:
            path = (CODE_ROOT/name).resolve()
            path.relative_to(CODE_ROOT)
            rows.append({'file':name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        except Exception:
            rows.append({'file':name, 'sha256':None})
    return rows


def _gc_callback(phase, info):
    try:
        now = time.perf_counter_ns(); ident = threading.get_ident()
        if phase == 'start':
            _GC_START[ident] = now
            return
        started = _GC_START.pop(ident, None)
        if started is None: return
        for collector in _ACTIVE_SNAPSHOT: collector.gc_event(now, now-started, info.get('generation'))
    except Exception:
        pass


class Sampler:
    def __init__(self, collector, interval_ms):
        self.collector, self.interval = collector, interval_ms/1000
        self.stop_event = threading.Event()
        # A plain Thread starts with an empty context, so hooks never see this collector here.
        self.thread = threading.Thread(target=self.run, name='genos-timing-sampler', daemon=True)

    def run(self):
        cpu = time.thread_time_ns(); last = time.perf_counter_ns(); errors = 0
        nominal = int(self.interval*1e9)
        while not self.stop_event.wait(self.interval):
            now = time.perf_counter_ns(); weight = now-last; last = now
            try:
                self.collector.sample(now, weight, weight > 2*nominal)
            except Exception:
                errors += 1
                self.collector.warn('SAMPLER_ERROR')
                if errors >= 10:
                    self.collector.warn('SAMPLER_STOPPED_AFTER_ERRORS')
                    break
        self.collector.sampler_cpu_ns = time.thread_time_ns()-cpu

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive(): self.collector.warn('SAMPLER_JOIN_TIMEOUT')


def measured(function, label):
    @wraps(function)
    def wrapped(*args, **kwargs):
        collector = _CURRENT.get()
        if collector is None or not collector.hooks: return function(*args, **kwargs)
        try:
            entered = collector.enter(label,args,kwargs)
        except Exception:
            collector.warn('PROBE_ENTER_ERROR')
            return function(*args, **kwargs)
        if entered is None: return function(*args, **kwargs)
        number, segment = entered
        stack = getattr(_LOCAL,'stack',None)
        if stack is None: stack = _LOCAL.stack = []
        parent = stack[-1] if stack and stack[-1]['collector'] is collector else None
        frame = {'collector':collector,'number':number,'label':label,'segment':segment,
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
                collector.warn('PROBE_FINISH_ERROR')
    wrapped._genos_timing_probe = REVISION
    return wrapped


def measured_span(original):
    @contextmanager
    def wrapped(name, *, pressure=False, **fields):
        collector = _CURRENT.get()
        if collector is None or not collector.hooks:
            with original(name,pressure=pressure,**fields) as values: yield values
            return
        # Span labels are developer-authored identifiers, not arbitrary content.
        label = 'span.'+name if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',name) else 'span.other'
        try:
            entered = collector.enter(label,(),{})
        except Exception:
            collector.warn('PROBE_SPAN_ENTER_ERROR')
            entered = None
        if entered is None:
            with original(name,pressure=pressure,**fields) as values: yield values
            return
        number, segment = entered
        stack = getattr(_LOCAL,'stack',None)
        if stack is None: stack = _LOCAL.stack = []
        parent = stack[-1] if stack and stack[-1]['collector'] is collector else None
        frame = {'collector':collector,'number':number,'label':label,'segment':segment,
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
                collector.warn('PROBE_SPAN_FINISH_ERROR')
    wrapped._genos_timing_probe = REVISION
    return wrapped


def _boundary_call(collector, method, *args):
    try:
        getattr(collector, method)(*args)
    except Exception:
        collector.warn('BOUNDARY_ERROR')


def bounded_transport(original):
    """Model-call boundary from the existing physical transport timer."""
    @contextmanager
    def transport_attempt(stage, attempt_id):
        collector = _CURRENT.get()
        if collector is None:
            with original(stage, attempt_id): yield
            return
        _boundary_call(collector, 'model_enter', stage)
        try:
            with original(stage, attempt_id): yield
        finally:
            _boundary_call(collector, 'model_exit')
    transport_attempt._genos_timing_probe = REVISION
    return transport_attempt


def bounded_capture(original):
    """RAG worker-thread window from the existing request metrics capture."""
    @contextmanager
    def capture():
        collector = _CURRENT.get()
        if collector is None:
            with original() as metrics: yield metrics
            return
        _boundary_call(collector, 'window_enter')
        try:
            with original() as metrics: yield metrics
        finally:
            _boundary_call(collector, 'window_exit')
    capture._genos_timing_probe = REVISION
    return capture


def install_boundaries():
    global _BOUNDARIES
    with _INSTALL_LOCK:
        if _BOUNDARIES is not None: return _BOUNDARIES
        installed, missing = [], []
        try:
            metrics = importlib.import_module('semantic_runtime.execution_metrics')
            for name, wrap in (('transport_attempt', bounded_transport), ('capture', bounded_capture)):
                try:
                    original = getattr(metrics, name)
                    if getattr(original, '_genos_timing_probe', None) != REVISION:
                        setattr(metrics, name, wrap(original))
                    installed.append('execution_metrics.'+name)
                except Exception as exc:
                    missing.append('execution_metrics.'+name+':'+type(exc).__name__)
        except Exception as exc:
            missing.append('execution_metrics:'+type(exc).__name__)
        _BOUNDARIES = {'installed':installed, 'missing':missing}
        return _BOUNDARIES


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
            if getattr(latency.span, '_genos_timing_probe', None) != REVISION:
                latency.span = measured_span(latency.span)
            installed.append('query_latency.span')
        except Exception as exc:
            missing.append('query_latency.span:'+type(exc).__name__)
        _INSTALLED = {'installed':installed,'missing':missing,'loaded_code_fingerprints':[{'function':k,'sha256':v} for k,v in sorted(code.items())]}
        return _INSTALLED


def settings():
    """Environment switches; invalid values fall back to safe defaults with a warning."""
    warnings = []
    mode = os.environ.get('GENOS_FUNCTION_TIMING_MODE', 'full').strip().lower() or 'full'
    if mode not in ('full', 'sample'):
        warnings.append('INVALID_MODE_DEFAULT_FULL'); mode = 'full'
    raw = os.environ.get('GENOS_FUNCTION_TIMING_SAMPLE_MS', '').strip()
    interval = DEFAULT_INTERVAL_MS
    if raw:
        try:
            interval = int(raw)
            if not 2 <= interval <= 200: raise ValueError()
        except ValueError:
            warnings.append('INVALID_SAMPLE_MS_DEFAULT_10'); interval = DEFAULT_INTERVAL_MS
    return mode, interval, warnings


@contextmanager
def request_scope(request_id):
    """Synchronous scope used by the async dispatch wrapper and by tests."""
    setup = time.perf_counter()
    try:
        mode, interval, warnings = settings()
        coverage = {'boundaries':install_boundaries()}
        if mode == 'full': coverage.update(install())
        collector = Collector(hooks=mode == 'full', interval_ms=interval)
        collector.warnings.update(warnings)
        collector.loop_thread = threading.get_ident()
        sampler = Sampler(collector, interval)
    except Exception as exc:
        _safe_emit('timing.probe.failed',request_id=request_id,error_type=type(exc).__name__,stage='setup')
        yield None
        return
    global _ACTIVE_SNAPSHOT
    with _ACTIVE_LOCK:
        _ACTIVE.add(collector)
        _ACTIVE_SNAPSHOT = tuple(_ACTIVE)
        peak = len(_ACTIVE)
        for other in _ACTIVE: other.concurrency_peak = max(other.concurrency_peak, peak)
        if len(_ACTIVE) == 1 and _gc_callback not in gc.callbacks: gc.callbacks.append(_gc_callback)
    token = _CURRENT.set(collector)
    started = False
    try:
        try:
            sampler.thread.start(); started = True
        except Exception:
            collector.warn('SAMPLER_START_FAILED')
        _safe_emit('timing.probe.started',request_id=request_id,setup_ms=round((time.perf_counter()-setup)*1000,3),
            coverage=coverage, mode=mode, interval_ms=interval, max_calls=MAX_CALLS, max_seconds=MAX_SECONDS)
        yield collector
    finally:
        _CURRENT.reset(token)
        try:
            if started: sampler.stop()
        except Exception:
            collector.warn('SAMPLER_STOP_ERROR')
        with _ACTIVE_LOCK:
            _ACTIVE.discard(collector)
            _ACTIVE_SNAPSHOT = tuple(_ACTIVE)
            if not _ACTIVE:
                try: gc.callbacks.remove(_gc_callback)
                except ValueError: pass
        try:
            began = time.perf_counter()
            summary = collector.summary()
            _safe_emit('timing.probe.summary',request_id=request_id,profile=summary,
                       summary_ms=round((time.perf_counter()-began)*1000,3))
        except Exception as exc:
            _safe_emit('timing.probe.failed',request_id=request_id,error_type=type(exc).__name__,stage='summary')


def scope_call(function):
    """Wrap the existing async reported dispatch; reports close after this returns."""
    @wraps(function)
    async def wrapped(config,data,payload,question_body,started,report,request_id,api_type):
        allowed = {'LEGAL_AGENT','ELS_QUERY','RAG_ASK','WORKFLOW_RUN','WORKFLOW_RESUME'}
        is_call = str(payload.get('op','')).lower()=='call' and payload.get('path') in {
            '/v1/rag/ask','/v1/workflows/run','/v1/workflows/resume'}
        if os.environ.get('GENOS_FUNCTION_TIMING','').strip() != '1' or not (api_type in allowed or is_call):
            return await function(config,data,payload,question_body,started,report,request_id,api_type)
        with request_scope(request_id):
            return await function(config,data,payload,question_body,started,report,request_id,api_type)
    return wrapped
