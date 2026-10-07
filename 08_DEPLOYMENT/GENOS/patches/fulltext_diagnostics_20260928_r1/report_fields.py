"""Extend only validated log display AST nodes; never execute installed source."""
import ast
import textwrap


FIELDS = frozenset({
    'sql_count','sql_execute_ms','sql_first_row_ms','sql_fetch_ms','scope_filter_ms',
    'fetched_count','selected_count','work_ms','thread_cpu_ms',
    'cpu_throttled_usec_delta','cpu_nr_throttled_delta',
    'index_bytes','indexed_source_count','page_size','cache_size','mmap_size','temp_store',
    'connect_ms','facts_ms','uses_temp_sort','search_id','thread_id','concurrency_scope',
    'active_searches_at_start','active_searches_at_finish','active_searches_peak',
    'term_count','allowed_count','limit','scope_rejected_count','progress_event_count',
    'sql_status','sql_execute_cpu_ms','sql_first_row_cpu_ms','sql_fetch_cpu_ms',
    'sql_fetch_batch_count','sql_fetch_max_batch_ms','thread_non_cpu_ms','scheduler_wait_ms',
    'thread_read_chars_delta','thread_read_syscalls_delta','thread_read_bytes_delta',
    'minor_faults_delta','major_faults_delta','voluntary_switches_delta','involuntary_switches_delta',
    'source_lookup_count','source_cache_hits','source_sql_count','source_sql_execute_ms',
    'source_sql_fetch_ms','source_sql_cpu_ms','source_json_decode_ms','source_json_cpu_ms',
    'source_json_chars','source_sql_max_ms','source_load_errors','result_count','location_count',
    'route_handle_ms','bounds_tokenize_ms','bounds_enabled','mapping_status',
    'batch_no','batch_rows','batch_wall_ms','batch_cpu_ms',
})
DEFINITION='_FULLTEXT_DIAGNOSTIC_FIELD_NAMES = frozenset('+repr(sorted(FIELDS))+')'
HELPER='''def _fulltext_diagnostic_value(key, value):
    """Numbers and fixed status labels only; no question/source text."""
    if value is None:
        return 'null'
    if key in {'uses_temp_sort', 'bounds_enabled'}:
        return str(value).lower() if type(value) is bool else None
    if key == 'search_id':
        return value if isinstance(value, str) and _RUN_ID.fullmatch(value) else None
    if key == 'concurrency_scope':
        return value if value == 'process' else None
    if key in {'sql_status', 'mapping_status'}:
        return value if value in ('completed', 'failed') else None
    if type(value) in (int, float):
        if value == value and abs(value) != float('inf'):
            return str(value) if value >= 0 or key == 'cache_size' else None
    return None
'''


def signature(node):return ast.dump(node,include_attributes=False)


def one(values,description):
    values=list(values)
    if len(values)!=1:raise ValueError('report display structure incompatible: '+description)
    return values[0]


def transform(raw):
    tree=ast.parse(raw,feature_version=(3,11));edits=[]
    offsets=[0]
    for line in raw.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    def span(node):return offsets[node.lineno-1]+node.col_offset,offsets[node.end_lineno-1]+node.end_col_offset
    def segment(node):
        start,end=span(node);return raw[start:end].decode()
    def replace(node,value):
        start,end=span(node);edits.append((start,end,value.encode()))
    assignments=[n for n in tree.body if isinstance(n,ast.Assign)]
    def assignment(name):
        return [n for n in assignments if any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    live=one(assignment('_LIVE_FIELD_NAMES'),'live fields')
    present=assignment('_FULLTEXT_DIAGNOSTIC_FIELD_NAMES')
    if present:
        if signature(one(present,'fulltext fields'))!=signature(ast.parse(DEFINITION).body[0]):
            raise ValueError('fulltext display fields differ')
    else:
        start,_=span(live);edits.append((start,start,(DEFINITION+'\n').encode()))
    if not any(isinstance(n,ast.Name) and n.id=='_FULLTEXT_DIAGNOSTIC_FIELD_NAMES' for n in ast.walk(live.value)):
        replace(live.value,'('+segment(live.value)+') | _FULLTEXT_DIAGNOSTIC_FIELD_NAMES')
    cls=one((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_LiveLog'),'live class')
    helpers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_fulltext_diagnostic_value']
    if helpers:
        if signature(one(helpers,'fulltext helper'))!=signature(ast.parse(HELPER).body[0]):
            raise ValueError('fulltext display helper differs')
    else:
        start,_=span(cls);edits.append((start,start,(HELPER+'\n').encode()))
    emit=one((n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='emit'),'emit')
    loop=one((n for n in ast.walk(emit) if isinstance(n,ast.For)
              and isinstance(n.target,ast.Name) and n.target.id=='key'
              and signature(n.iter)==signature(ast.parse('sorted(_LIVE_FIELD_NAMES)',mode='eval').body)),'emit fields')
    safe=one((n for n in ast.walk(loop) if isinstance(n,ast.Assign) and len(n.targets)==1
              and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='safe'),'safe conversion')
    if not any(isinstance(n,ast.Name) and n.id=='_fulltext_diagnostic_value' for n in ast.walk(safe.value)):
        allowed=['_live_value(fields[key])',
                 '_live_diagnostic_value(key, fields[key]) if key in _LIVE_DIAGNOSTIC_FIELD_NAMES else _live_value(fields[key])']
        if signature(safe.value) not in [signature(ast.parse(s,mode='eval').body) for s in allowed]:
            raise ValueError('report safe field conversion differs')
        replace(safe.value,'_fulltext_diagnostic_value(key, fields[key]) if key in _FULLTEXT_DIAGNOSTIC_FIELD_NAMES else ('+segment(safe.value)+')')
    summary=one((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='format_readable_report'),'summary')
    candidates=[]
    for node in ast.walk(summary):
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='key':
            strings={n.value for n in ast.walk(node.iter) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
            if {'phase','duration_ms'}.issubset(strings):candidates.append(node)
    summary_loop=one(candidates,'summary service fields')
    if not any(isinstance(n,ast.Name) and n.id=='_FULLTEXT_DIAGNOSTIC_FIELD_NAMES' for n in ast.walk(summary_loop.iter)):
        start,_=span(summary_loop.body[0]);_,end=span(summary_loop.body[-1])
        old_body=raw[start:end].decode()
        # Dedent continuation lines without stripping any unrelated source bytes.
        indent=' '*summary_loop.body[0].col_offset
        old_body=textwrap.dedent(indent+old_body)
        new_body="if key in _FULLTEXT_DIAGNOSTIC_FIELD_NAMES:\n    if key in event:\n        safe = _fulltext_diagnostic_value(key, event[key])\n        if safe is not None:\n            fields.append(key + '=' + safe)\nelse:\n"+textwrap.indent(old_body,'    ')
        source='for key in ('+segment(summary_loop.iter)+') + tuple(sorted(_FULLTEXT_DIAGNOSTIC_FIELD_NAMES)):\n'+textwrap.indent(new_body,'    ')
        replace(summary_loop,source.replace('\n','\n'+' '*summary_loop.col_offset))
    else:
        if not any(isinstance(n,ast.Name) and n.id=='_fulltext_diagnostic_value' for n in ast.walk(summary_loop)):
            raise ValueError('summary fulltext fields lack typed conversion')
    last=len(raw)+1
    for start,end,value in sorted(edits,key=lambda e:(e[0],e[1]),reverse=True):
        if end>last:raise ValueError('overlapping report display edits')
        raw=raw[:start]+value+raw[end:];last=start
    ast.parse(raw,feature_version=(3,11));return raw
