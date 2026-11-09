"""Reusable progress display. No execution, cancellation, retries, or log writes."""
from datetime import datetime, timedelta, timezone
from html import escape
import math
import re
import shutil
import sys
import time
import unicodedata

_UNSET = object()
_TERMINAL = {'SUCCEEDED', 'FAILED', 'STOPPED', 'UNKNOWN'}


def duration(seconds):
    if seconds is None: return '계산 중'
    hours, seconds = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(seconds, 60)
    return ('{}시간 '.format(hours) if hours else '')+'{}분 {}초'.format(minutes, seconds)


class _DefaultSink:
    def __init__(self):
        self.handle = None; self.rows = 0
        self.notebook_fallback = None
        try:
            from IPython import get_ipython
            from IPython.display import HTML, display, clear_output
        except ImportError:
            get_ipython = lambda: None
        shell = get_ipython()
        if shell is not None and getattr(shell, 'kernel', None) is not None:
            self.HTML = HTML
            self.handle = display(HTML('<div>작업 상태 준비 중</div>'), display_id=True)
            if self.handle is None:
                def replace(html):
                    clear_output(wait=True); display(HTML(html))
                self.notebook_fallback = replace
        self.tty = sys.stdout.isatty()

    def __call__(self, html, plain, final):
        if self.handle is not None:
            self.handle.update(self.HTML(html))
        elif self.notebook_fallback:
            self.notebook_fallback(html)
        elif self.tty:
            terminal = shutil.get_terminal_size((100, 30))
            width = max(1, terminal.columns-1)
            height = max(2, terminal.lines-2)
            lines = plain.splitlines()
            if len(lines) > height:
                lines = lines[:height-1]+['… 나머지는 전체 로그에서 확인하세요.']
            self.rows = min(self.rows, height)
            if self.rows: sys.stdout.write('\033[{}A\r'.format(self.rows))
            count = max(self.rows, len(lines))
            for index in range(count):
                line = lines[index] if index < len(lines) else ''
                line = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', line)
                clipped = []; used = 0
                for char in line:
                    size = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in 'WF' else 1
                    if used+size > width: break
                    clipped.append(char); used += size
                sys.stdout.write('\033[2K'+''.join(clipped)+'\n')
            self.rows = count; sys.stdout.flush()
        elif final:
            sys.stdout.write(plain+'\n'); sys.stdout.flush()


class ProgressPanel:
    """Caller supplies authoritative counters and final status; use one writer.

    sink(html, plain, final) can bind an existing UI or capture output in tests.
    """
    def __init__(self, title, log_path='', *, run_id='', interval=1.0,
                 timezone_hours=9, elapsed_label='실행 경과', sink=None,
                 clock=time.monotonic, wall_clock=None):
        if interval <= 0 or not math.isfinite(interval):
            raise ValueError('interval must be finite and positive')
        self.title, self.log_path, self.run_id = str(title), str(log_path), str(run_id)
        self.interval, self.elapsed_label = interval, elapsed_label
        self.clock = clock
        zone = timezone(timedelta(hours=timezone_hours))
        self.wall_clock = wall_clock or (lambda: datetime.now(zone))
        self.sink = sink or _DefaultSink()
        self.started = self.clock(); self.phase_started = self.started
        self.last_event = self.started; self.last_draw = -math.inf
        self.phase, self.unit, self.status = '준비 중', '건', 'RUNNING'
        self.done, self.total, self.baseline = 0, None, 0
        self.message, self.error, self.metrics = '', '', {}
        self.exit_code = None
        self.draw(force=True)

    @staticmethod
    def _counts(done, total):
        if type(done) is not int or done < 0:
            raise ValueError('done must be a nonnegative integer')
        if total is not None and (type(total) is not int or total < done):
            raise ValueError('total must be unknown or an integer >= done')

    def _running(self):
        if self.status in _TERMINAL:
            raise ValueError('terminal panel cannot accept further progress')

    def start_phase(self, phase, *, done=0, total=None, unit='건'):
        self._running(); self._counts(done, total)
        self.phase, self.done, self.total, self.unit = str(phase), done, total, str(unit)
        self.baseline = done; self.phase_started = self.clock(); self.last_event = self.phase_started
        self.metrics = {}; self.message = ''
        self.draw(force=True)

    def update(self, *, done=None, total=_UNSET, message=_UNSET, metrics=_UNSET):
        self._running()
        done = self.done if done is None else done
        total = self.total if total is _UNSET else total
        self._counts(done, total)
        if done < self.done:
            raise ValueError('counter decreased; start a new phase/run explicitly')
        if metrics is not _UNSET and not isinstance(metrics, dict):
            raise ValueError('metrics must be a dictionary')
        self.done, self.total = done, total
        if message is not _UNSET: self.message = str(message)
        if metrics is not _UNSET: self.metrics = dict(metrics)
        self.last_event = self.clock()
        self.draw()

    def stopping(self, message='중단 요청 전달 · 현재 처리 결과 저장 대기'):
        self._running(); self.status = 'STOPPING'; self.message = str(message)
        self.last_event = self.clock(); self.draw(force=True)

    def finish(self, status, *, completion_confirmed=False, exit_code=None, message='', error=''):
        self._running()
        if status not in _TERMINAL: raise ValueError('unknown terminal status')
        if status == 'SUCCEEDED' and (not completion_confirmed or exit_code not in (None, 0)):
            raise ValueError('success requires the job completion contract and a successful exit if applicable')
        self.status, self.exit_code = status, exit_code
        self.message, self.error = str(message), str(error)
        self.last_event = self.clock(); self.finished = self.last_event
        self.draw(force=True)
        return self.snapshot()

    def snapshot(self):
        now = getattr(self, 'finished', self.clock())
        elapsed = max(0, now-self.phase_started); added = self.done-self.baseline
        rate = added/elapsed if elapsed >= 3 and added > 0 else None
        remaining = None if self.total is None else self.total-self.done
        eta = remaining/rate if remaining is not None and rate else 0 if remaining == 0 else None
        if self.status in _TERMINAL and self.status != 'SUCCEEDED': eta = None
        percent = self.done/self.total*100 if self.total else None
        finish_at = self.wall_clock()+timedelta(seconds=eta) if eta is not None else None
        return {'title':self.title, 'run_id':self.run_id, 'phase':self.phase, 'status':self.status,
                'done':self.done, 'total':self.total, 'remaining':remaining, 'unit':self.unit,
                'percent':percent, 'rate':rate, 'elapsed_seconds':now-self.started,
                'eta_seconds':eta, 'estimated_finish':finish_at.isoformat(timespec='seconds') if finish_at else None,
                'last_event_age_seconds':max(0, self.clock()-self.last_event), 'metrics':dict(self.metrics),
                'message':self.message, 'error':self.error, 'exit_code':self.exit_code, 'log_path':self.log_path}

    def draw(self, force=False):
        now = self.clock()
        if not force and (self.status in _TERMINAL or now-self.last_draw < self.interval): return
        s = self.snapshot()
        states = {'RUNNING':'실행 중', 'STOPPING':'중단 처리 중', 'SUCCEEDED':'완료',
                  'FAILED':'실패', 'STOPPED':'중단됨', 'UNKNOWN':'결과 미확인'}
        lines = [self.title+' | '+states[self.status]+' | '+self.phase]
        quantity = '{:,}'.format(self.done)+' / '+('{:,}'.format(self.total) if self.total is not None else '전체량 미확정')+' '+self.unit
        lines.append(quantity+' | 남은 '+('{:,}'.format(s['remaining']) if s['remaining'] is not None else '미확정'))
        lines.append('진행률: '+('{:.2f}%'.format(s['percent']) if s['percent'] is not None else '미확정')+
                     ' | 속도: '+('{:.1f}{}/초'.format(s['rate'],self.unit) if s['rate'] is not None else '계산 중'))
        lines.append(self.elapsed_label+': '+duration(s['elapsed_seconds'])+' | 예상 잔여: '+duration(s['eta_seconds']))
        lines.append('예상 종료: '+(s['estimated_finish'] or '계산 중')+' | 마지막 관측: '+duration(s['last_event_age_seconds'])+' 전')
        if self.metrics: lines.append(' | '.join(str(k)+': '+str(v) for k,v in self.metrics.items()))
        if s['remaining'] == 0 and self.status not in _TERMINAL: lines.append('처리량 확인 완료 · 최종 완료 조건 확인 대기')
        if self.message: lines.append(self.message)
        if self.exit_code is not None: lines.append('종료 코드: '+str(self.exit_code))
        if self.run_id: lines.append('작업 ID: '+self.run_id)
        if self.log_path: lines.append('전체 로그: '+self.log_path)
        color = '#166534' if self.status == 'SUCCEEDED' else '#b91c1c' if self.status in ('FAILED','UNKNOWN') else '#1d4ed8'
        progress = min(100, max(0, s['percent'] or 0))
        html = '<div style="border:1px solid #cbd5e1;border-radius:8px;padding:14px;max-width:1100px">'
        html += '<b style="color:'+color+'">'+escape(lines[0])+'</b>'
        html += '<div style="height:10px;background:#e2e8f0;margin:10px 0"><div style="height:10px;background:'+color+';width:'+str(progress)+'%"></div></div>'
        html += '<pre style="white-space:pre-wrap;word-break:break-all;margin:0">'+escape('\n'.join(lines[1:]))+'</pre>'
        if self.error: html += '<pre style="white-space:pre-wrap;max-height:140px;overflow:auto;color:#b91c1c">'+escape(self.error)+'</pre>'
        html += '</div>'
        self.sink(html, '\n'.join(lines)+('\n'+self.error if self.error else ''), self.status in _TERMINAL)
        self.last_draw = now
