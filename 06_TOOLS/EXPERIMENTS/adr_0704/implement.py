from pathlib import Path
import subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0704/compact-display';S=C/'snapshot'
p=S/'02_BACKEND/semantic_runtime/execution_metrics.py'
p.write_text('''"""Request-local public timing from physical transport boundaries, never journal counts."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
from . import observability as obs

_CURRENT = ContextVar('rag_execution_metrics', default=None)
log = obs.get_logger('execution_metrics')

def purpose(value):
    value = str(value or '')
    if value.startswith(('memory-resolve','memory-command','memory-history','memory-reuse','memory-intent')): return 'request'
    if value.startswith(('source-law','select_sources','investigate')): return 'sources'
    if value.startswith(('memory-assess','review','repair','rebuttal')): return 'assessment'
    if value.startswith(('memory-compose','compose')): return 'answer'
    return 'model'

class Metrics:
    def __init__(self):
        self.started = time.perf_counter()
        self.calls = []
        self.lock = threading.Lock()

    def begin(self, stage):
        with self.lock:
            row = {'number': len(self.calls)+1, 'purpose': stage, 'duration_ms': None}
            self.calls.append(row)
            return row

    def finish(self, row, duration):
        with self.lock: row['duration_ms'] = duration

    def snapshot(self):
        with self.lock: calls = [dict(row) for row in self.calls]
        return {'schema_version': 'rag-execution-stats-v1', 'count_basis': 'transport-attempts',
                'llm_calls': len(calls), 'calls': calls,
                'llm_duration_ms': sum(row['duration_ms'] for row in calls if row['duration_ms'] is not None),
                'timing_complete': all(row['duration_ms'] is not None for row in calls),
                'request_duration_ms': max(0, int((time.perf_counter()-self.started)*1000))}

@contextmanager
def capture():
    metrics = Metrics(); token = _CURRENT.set(metrics)
    try: yield metrics
    finally:
        _CURRENT.reset(token)
        obs.event(log, 'execution.metrics', execution_stats=metrics.snapshot())

@contextmanager
def transport_attempt(stage, attempt_id):
    metrics = _CURRENT.get(); stage = purpose(stage)
    row = metrics.begin(stage) if metrics is not None else None
    started = time.perf_counter()
    obs.event(log, 'model.call.started', attempt_id=attempt_id, purpose=stage)
    try: yield
    finally:
        duration = max(0, int((time.perf_counter()-started)*1000))
        if metrics is not None: metrics.finish(row, duration)
        obs.event(log, 'model.call.finished', attempt_id=attempt_id, purpose=stage, duration_ms=duration)
''')
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target','02_BACKEND/semantic_runtime/execution_metrics.py','--upstream-state','absent'],cwd=R,check=True)
p=S/'02_BACKEND/semantic_runtime/legal_agent/gateway.py';s=p.read_text();old="with latency.span('model.transport',phase=phase,request_bytes=request_bytes,pressure=True):";assert old in s
s=s.replace(old,"from ..execution_metrics import transport_attempt\n                    with latency.span('model.transport',phase=phase,request_bytes=request_bytes,pressure=True), transport_attempt(view.get('source_stage') or view.get('phase') or phase, ident):");p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/app.py';s=p.read_text();old="    @app.post('/v1/rag/ask')\n    def ask(body:dict,request:Request=None):\n";assert old in s
new="""    @app.post('/v1/rag/ask')
    def ask(body:dict,request:Request=None):
        from .execution_metrics import capture
        with capture() as metrics:
            result = execute_ask(body, request)
            if isinstance(result, dict) and result.get('response_schema') != 'ad-mode-v1':
                result = {**result, 'execution_stats': metrics.snapshot()}
            return result

    def execute_ask(body:dict,request:Request=None):
""";s=s.replace(old,new);p.write_text(s)
p=S/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py';s=p.read_text();s=s.replace('rag-v6-live-cards-20261008-r4','rag-v6-compact-metrics-20261009-r1').replace('workflow-live-cards-20261008-r4','workflow-compact-cards-20261009-r1').replace('rag-current-judgment-20261008-r2','rag-compact-progress-20261009-r1').replace("DISPLAY_POLICY_REVISION = 'public-display-v1'","DISPLAY_POLICY_REVISION = 'public-display-v2'")
s=s.replace('        self.blocks = []','        self.blocks = []\n        self.summary_stages = set()',1)
a=s.index('    async def progress(self, event):');z=s.index('    @staticmethod\n    def _plain',a)
s=s[:a]+'''    async def progress(self, event):
        event = compact_event(event)
        if event is None or not self.show_progress or self.answer_seq:
            return
        stage = event['basis']['stage']
        if stage in self.summary_stages:
            return
        # A delayed lower-level event cannot make a finished phase look like a
        # new investigation. Detailed activity remains in the backend journal.
        if self.summary_stages and _SUMMARY_ORDER.index(stage) < max(_SUMMARY_ORDER.index(s) for s in self.summary_stages):
            return
        self.summary_stages.add(stage)
        self.flow_events.append(event)
        self.last_status = event['label']
        visible = event['label']+'\\n'+event['details'][0]
        self.blocks.append({'nodeId': 'rag-summary-'+stage, 'nodeLabel': 'Visible Reasoner',
            'status': 'FINISHED', 'data': {'output': {'content': json.dumps(
                {'visible_rationale': visible}, ensure_ascii=False)}}})
        await self._send('agentFlowExecutedData', list(self.blocks))

'''+s[z:]
# Compact public events can be safely consumed by SSE, native chat and editor copies.
idx=s.index('\ndef public_response(')
s=s[:idx]+'''
_SUMMARY_ORDER = ('request', 'search', 'sources', 'answer', 'complete')
_SUMMARIES = {
    'request': ('요청 확인', '질문과 확인할 사항을 정리합니다.'),
    'search': ('관련 문서 찾기', '문서명·목차·조문 구조에서 관련 범위를 찾습니다.'),
    'sources': ('선택한 원문 확인', '선택한 문서의 필요한 범위와 근거를 확인합니다.'),
    'answer': ('근거 검토·답변 작성', '확인한 근거와 조건·예외를 검토해 답변을 정리합니다.'),
    'complete': ('답변 준비 완료', '확인한 답변과 근거를 정리했습니다.'),
}

def compact_event(event):
    event = public_event(event)
    if event is None or event.get('kind') in {'heartbeat','model_wait','overflow'}: return None
    b = event['basis']; kind = event.get('kind'); raw = str(b.get('stage','')).upper()
    if b.get('kind') == 'PROGRESS_SUMMARY':
        stage = b.get('stage')
        if stage not in _SUMMARIES: return None
    elif b.get('name') == 'request.finished': stage = 'complete'
    elif raw in {'ASSESS','COMPOSE'} or b.get('kind') == 'CASE_JUDGMENT_ACCEPTED': stage = 'answer'
    elif raw in {'READ','SELECT'} or kind in {'reading','read_complete','selected','revised','review','decision'}: stage = 'sources'
    elif raw == 'RECALL' or kind == 'candidate': stage = 'search'
    else: stage = 'request'
    label, detail = _SUMMARIES[stage]
    return {**{k:event[k] for k in ('schema_version','request_id','run_id','seq','elapsed_ms') if k in event},
            'kind':'phase', 'label':label, 'details':[detail],
            'basis':{'kind':'PROGRESS_SUMMARY','stage':stage,'detail_mode':'summary'},
            'display_policy_revision':DISPLAY_POLICY_REVISION}


def _execution_html(body):
    value = body.get('execution_stats')
    if not isinstance(value,dict) or value.get('schema_version') != 'rag-execution-stats-v1': return ''
    calls = value.get('calls')
    valid_ms = lambda n: type(n) is int and 0 <= n <= 86400000
    if (not isinstance(calls,list) or len(calls)>1024 or type(value.get('llm_calls')) is not int
            or value['llm_calls'] != len(calls) or not valid_ms(value.get('request_duration_ms'))): return ''
    labels = {'request':'요청 확인','sources':'원문·근거 확인','assessment':'조건·예외 판단','answer':'답변 작성','model':'모델 처리'}
    for i,row in enumerate(calls,1):
        if (not isinstance(row,dict) or type(row.get('number')) is not int or row['number']!=i
                or row.get('purpose') not in labels or row.get('duration_ms') is not None and not valid_ms(row['duration_ms'])): return ''
    sec = lambda n: f'{n/1000:.2f}초'
    known = sum(r['duration_ms'] for r in calls if r['duration_ms'] is not None)
    complete = all(r['duration_ms'] is not None for r in calls)
    rows = ['<details><summary><strong>LLM 호출·처리 시간 · '+str(len(calls))+'회</strong></summary>',
            '<p>서버 요청 처리: '+sec(value['request_duration_ms'])+' · 모델 호출 시간 '+('합계' if complete else '확인된 합계')+': '+sec(known)+'</p>',
            '<p>전송 시도 기준이며 재시도도 각각 셉니다. 문서 열람·내부 처리 횟수와 다릅니다. 호출 시간 합계와 서버 요청 처리 시간은 별도입니다.</p>']
    if calls:
        rows += ['<table><thead><tr><th>호출</th><th>작업</th><th>소요 시간</th></tr></thead><tbody>']
        rows += ['<tr><td>'+str(r['number'])+'</td><td>'+labels[r['purpose']]+'</td><td>'+(sec(r['duration_ms']) if r['duration_ms'] is not None else '미확인')+'</td></tr>' for r in calls]
        rows += ['</tbody></table>']
    else: rows += ['<p>이번 요청에서는 모델을 호출하지 않았습니다.</p>']
    return '\\n'.join([*rows,'</details>'])

'''+s[idx:]
s=s.replace("node('search', '원문 본문 검색', search_details)","node('search', '관련 문서·근거 탐색', search_details)")
s=s.replace("    if not view:\n        return ''\n    def e(value):", "    if not view:\n        metrics = _execution_html(body)\n        return ('<!-- GENOS_JUDGMENT_VIEW_START -->\\n'+metrics+'\\n<!-- GENOS_JUDGMENT_VIEW_END -->') if metrics else ''\n    def e(value):")
s=s.replace('AI 판단 과정 보기 · 7단계','처리 상세 · 판단 근거와 LLM 호출')
s=s.replace("'<p>현재 질문의 판단 기록입니다. 단계 번호를 지정해 수정 방향을 알려 주세요.</p>']", "'<p>현재 질문의 판단 기록입니다. 아래 단계는 처리 구분이며 LLM 호출 횟수와 다릅니다.</p>', _execution_html(body)]")
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/progress.py';s=p.read_text().replace('rag-current-judgment-20261008-r2','rag-compact-progress-20261009-r1');s=s.replace('        self.seq = 0','        self.seq = 0\n        self.summary_stages = set()',1)
assert 'self.summary_stages = set()' in s
s=s.replace("event = views().public_event(event)","event = views().compact_event(event)")
s=s.replace("        if event is None:\n            return\n        try:\n            self.sink(event)","        if event is None:\n            return\n        stage = event['basis']['stage']\n        with self.sequence_lock:\n            if stage in self.summary_stages:\n                return\n            self.summary_stages.add(stage)\n        try:\n            self.sink(event)",1);p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(S)],cwd=R,check=True)
print('Compact display and physical transport metrics implemented in isolated snapshot')
