"""Bounded summaries of existing R7/R8 logs. Does not contact GENOS."""
import json
import math
import re


class Timing:
    def __init__(self):
        self.pending = b''
        self.bytes = self.lines = 0
        self.phase = None
        self.completed = []
        self.generation = []
        self.rebuild = {}
        self.export = []
        self.export_last = None
        self.errors = []
        self.coverage = {}
        self.seen = []

    @staticmethod
    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    def feed(self, block):
        self.bytes += len(block)
        if self.bytes > 256*1024**2:
            raise ValueError('LOG_SIZE_LIMIT')
        rows = (self.pending + block).split(b'\n')
        self.pending = rows.pop()
        if len(self.pending) > 1024**2:
            raise ValueError('LOG_LINE_LIMIT')
        for raw in rows:
            self.line(raw.decode('utf-8', errors='replace').rstrip('\r'))

    def line(self, line):
        self.lines += 1
        if self.lines > 2_000_000:
            raise ValueError('LOG_LINE_COUNT_LIMIT')
        match = re.fullmatch(r'PHASE (STRUCTURE|PREPARE|INDEX|RETURN|SELECT_VERIFIED_SUCCESSES)', line)
        if match:
            self.phase = match[1]
            self.seen.append(self.phase)
        match = re.fullmatch(r'GENERATION (\S+) seconds=([0-9.]+) reused=(True|False)', line)
        if match:
            seconds = float(match[2])
            if self.number(seconds):
                self.generation.append({'stage': match[1], 'seconds': seconds, 'reused': match[3]=='True'})
        tag, _, raw = line.partition(' ')
        if tag not in ('REBUILD', 'PHASE', 'PROGRESS', 'PHASE_RESULT') or not raw.startswith('{'):
            # Only fixed error codes, never whole log lines or document contents.
            if 'QUERY_EXPORT_BLOB' in line and 'QUERY_EXPORT_BLOB' not in self.errors:
                self.errors.append('QUERY_EXPORT_BLOB')
            return
        try:
            value = json.loads(raw)
        except ValueError:
            self.errors.append('MALFORMED_' + tag)
            return
        if not isinstance(value, dict):
            return
        if tag == 'PHASE_RESULT':
            if value.get('phase') in {'STRUCTURE','PREPARE','INDEX','RETURN'} and self.number(value.get('seconds')):
                self.completed.append({k:value.get(k) for k in ('phase','status','seconds')})
        elif tag == 'REBUILD':
            phase = str(value.get('phase',''))[:100]
            if value.get('status') in {'DONE','FAILED','INTERRUPTED'} and self.number(value.get('elapsed_seconds')):
                self.rebuild[phase] = {k:value.get(k) for k in ('status','elapsed_seconds')}
            if self.number(value.get('total_elapsed_seconds')):
                self.coverage['index_observed_seconds'] = max(self.coverage.get('index_observed_seconds',0),value['total_elapsed_seconds'])
        elif self.phase == 'RETURN' and self.number(value.get('elapsed_seconds')) and isinstance(value.get('phase'),str):
            elapsed = value['elapsed_seconds']
            phase = value['phase'][:100]
            if self.export_last and elapsed < self.export_last['elapsed']:
                self.errors.append('EXPORT_TIMER_RESET')
            if tag == 'PHASE':
                if self.export_last:
                    self.export.append({'phase':self.export_last['phase'],
                        'observed_seconds':max(0,elapsed-self.export_last['started'])})
                self.export_last = {'phase':phase,'started':elapsed,'elapsed':elapsed}
            elif self.export_last and self.export_last['phase'] == phase:
                self.export_last['elapsed'] = elapsed
            for key in ('elapsed_seconds','cpu_seconds','rss_kib','rows_added','rows_checked'):
                if self.number(value.get(key)):
                    self.coverage['export_'+key] = value[key]
        if len(self.completed)+len(self.generation)+len(self.export)+len(self.errors)+len(self.seen)>4000:
            raise ValueError('EVENT_COUNT_LIMIT')

    def result(self):
        export = list(self.export)
        if self.export_last:
            export.append({'phase':self.export_last['phase'],
                'observed_seconds':max(0,self.export_last['elapsed']-self.export_last['started']),
                'last_interval_incomplete':True})
        return {'log_bytes':self.bytes,'log_lines':self.lines,'phase_starts':self.seen,
                'phase_results':self.completed,'completed_generation_stages':self.generation,
                'rebuild_timings_nested_do_not_sum':self.rebuild,
                'export_intervals_observed':export,'observed_lower_bounds':self.coverage,
                'error_codes':self.errors,'trailing_partial_line_bytes':len(self.pending),
                'whole_02_seconds':None,
                'note':'R7 has no complete wall-time for every phase. Missing times remain unknown. Nested rebuild timers must not be summed.'}


def collect(folder, controller, latest):
    state = latest['value']
    handle = (state.get('compute') or {}).get('handle','')
    if not re.fullmatch(r'[0-9a-f]{32}',handle):
        raise ValueError('SAVED_HANDLE_MISSING')
    committed = state.get('log_offset',0)
    if type(committed) is not int or not 0 <= committed <= 256*1024**2:
        raise ValueError('LOG_OFFSET_LIMIT')
    prefix = 'attempts/'+handle+'/logs/'
    chunks = []
    for path in folder.list_paths_in_partition():
        relative = path.lstrip('/')
        match = re.fullmatch(re.escape(prefix)+r'(\d{16})\.log',relative)
        if match and int(match[1]) < committed:
            chunks.append((int(match[1]),relative))
    if len(chunks)>50000:
        raise ValueError('LOG_CHUNK_COUNT_LIMIT')
    timing, offset = Timing(), 0
    for start,path in sorted(chunks):
        if start != offset:
            raise ValueError('LOG_GAP_OR_OVERLAP_AT_'+str(offset))
        with folder.get_download_stream(path) as stream:
            block = controller.bounded_read(stream,controller.t.CHUNK)
        if not block or start+len(block)>committed:
            raise ValueError('LOG_CHUNK_RANGE')
        timing.feed(block)
        offset += len(block)
    if offset != committed:
        raise ValueError('LOG_INCOMPLETE_AT_'+str(offset))
    result = timing.result()
    result.update(saved_state=state.get('phase'),result_saved=bool(state.get('result_blob')),
                  all_committed_logs_read=True,genos_contacted=False,job_restarted=False)
    return result
