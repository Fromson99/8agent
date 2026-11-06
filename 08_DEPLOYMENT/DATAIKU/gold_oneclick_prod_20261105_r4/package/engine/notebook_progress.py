"""One notebook display area; raw output is retained by the launcher in a file."""
from datetime import datetime, timedelta, timezone
from html import escape
import json
import sys
import time
from progress_display import duration


COMPLETE = 'VECTORS_STORED_INSERT_ACK_NOT_ACTIVATED'


class Panel:
    def __init__(self, action, model, dimensions, checkpoint, log_path, publish=None):
        self.action, self.model, self.dimensions = action, model, dimensions
        self.checkpoint, self.log_path = str(checkpoint), str(log_path)
        self.started = time.monotonic(); self.last_update = -1e30
        self.phase = '준비 중'; self.planning = {}; self.progress = {}; self.total = None
        self.sdk_calls = 0; self.batch = ''; self.notice = ''; self.error = ''
        self.exit_code = None; self.finished = False; self.complete = False; self.checked = False
        self.eta_at = None; self.remaining = None; self.percent = 0
        self._publish = publish or self._display_publisher()
        self.update(force=True)

    def _display_publisher(self):
        try:
            from IPython import get_ipython
            from IPython.display import HTML, display, clear_output
        except ImportError:
            get_ipython = lambda: None
        shell = get_ipython()
        if shell is not None and getattr(shell, 'kernel', None) is not None:
            handle = display(HTML('<div>벡터 작업 준비 중</div>'), display_id=True)
            if handle is not None:
                return lambda html, plain: handle.update(HTML(html))
            def replace(html, plain):
                clear_output(wait=True); display(HTML(html))
            return replace
        # Non-notebook terminals overwrite the same block. The intended Dataiku
        # notebook path above uses display_data/update_display_data, without JS.
        return lambda html, plain: (sys.stdout.write('\033[2J\033[H'+plain+'\n'), sys.stdout.flush())

    def consume(self, line):
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            value = None
        if not isinstance(value, dict):
            return
        phase = value.get('phase','')
        self.sdk_calls = value.get('sdk_calls', self.sdk_calls)
        if phase == 'VECTOR_PLANNING':
            self.phase = '구조 단위 준비'; self.planning = value
            total = value.get('total_sources',0)
            self.percent = value.get('completed_sources',0)/total*100 if total else 0
            self._eta(value.get('remaining_seconds'))
        elif phase in ('VECTOR_PLAN_COMPLETE','VECTOR_PLAN_REUSED'):
            self.total = value['total_rows']; self.phase = '전체량 확정 / 적재 준비'
            self.planning = {'completed_sources':value['total_sources'], 'total_sources':value['total_sources'],
                             'planned_rows':value['total_rows']}
            self.notice = '전체 적재 대상 {:,}벡터 / {:,}개 원문'.format(value['total_rows'],value['total_sources'])
            self.percent = 0; self._eta(None)
        elif phase == 'VECTOR_PROGRESS':
            self.phase = '벡터 적재'; self.progress = value; self.total = value['total_rows']
            self.percent = value['rows']/self.total*100 if self.total else 0
            self._eta(value.get('remaining_seconds'))
        elif phase == 'VECTOR_EMBEDDING':
            self.phase = '임베딩 응답 대기 / 벡터 적재'
        elif phase == 'VECTOR_INSERT_ACK':
            self.batch = '{:,}행 · DB {:.3f}초'.format(value['batch_rows'],value['request_s'])
        elif phase == 'VECTOR_PREVIOUS_RESETTING':
            self.phase = '기존 R1/R2 벡터 삭제 중'
        elif phase in ('VECTOR_PREVIOUS_RESET_COMPLETE','VECTOR_PREVIOUS_RESET_ALREADY_DONE'):
            self.notice = '이전 R1/R2 벡터 정리 완료 · NFS 원문/검색 데이터 유지'
        elif phase == 'DIAGNOSTIC_ERROR':
            self.phase = '오류로 중단'
            causes = value.get('causes',[])
            self.error = '\n'.join(str(c.get('type',''))+': '+str(c.get('message','')) for c in causes) or json.dumps(value,ensure_ascii=False)
        elif phase == COMPLETE:
            self.complete = True; self.phase = '적재 완료 · 서비스 활성화 별도'; self.percent = 100
            self.progress['rows'] = value.get('rows',self.progress.get('rows',0))
            self._eta(0)
        elif phase == 'VECTOR_CHECK_PASS':
            self.checked = True; self.phase = '연결·대상 확인 완료 (쓰기 없음)'
        self.update(force=phase in ('DIAGNOSTIC_ERROR',COMPLETE,'VECTOR_CHECK_PASS'))

    def _eta(self, seconds):
        self.remaining = seconds
        self.eta_at = datetime.now(timezone(timedelta(hours=9)))+timedelta(seconds=seconds) if seconds is not None else None

    def stop_requested(self):
        self.notice = '중단 요청 전달: 현재 응답/체크포인트 저장 후 종료합니다. 두 번째 중단은 강제 종료입니다.'
        self.update(force=True)

    def finish(self, code):
        self.exit_code = code; self.finished = True
        success = code == 0 and ((self.action=='check' and self.checked) or (self.action=='vector' and self.complete))
        if not success:
            self.phase = '중단 / 미완료'
            if not self.error:
                self.error = '프로세스 종료 {} · 완료 확인 없음. 전체 로그를 확인하세요.'.format(code)
        self.update(force=True)
        return {'status':'COMPLETE' if success else 'FAILED_OR_STOPPED', 'process_exit':code,
                'log_path':self.log_path, 'completion_marker_seen':self.complete,
                'check_marker_seen':self.checked}

    def lines(self):
        values = ['벡터 구조 적재 R4 | '+self.phase,
                  '모델: {} | {}차원'.format(self.model,self.dimensions)]
        if self.planning:
            p = self.planning
            values.append('원문 준비: {:,}/{:,}개 | 계획 벡터: {:,}'.format(p.get('completed_sources',0),p.get('total_sources',0),p.get('planned_rows',0)))
        if self.total is not None:
            done = self.progress.get('rows',0)
            values.append('적재: {:,}/{:,}행 | 남은 {:,}행'.format(done,self.total,max(0,self.total-done)))
        rate = self.progress.get('rows_per_second')
        values.append('진행률: {:.2f}% | 속도: {} | SDK 호출: {:,}'.format(self.percent,
                      '{:.1f}행/초'.format(rate) if rate is not None else '계산 중', self.sdk_calls))
        values.append('경과: {} | 예상 잔여: {} | 예상 종료: {}'.format(duration(time.monotonic()-self.started),
                      duration(self.remaining),self.eta_at.strftime('%m-%d %H:%M:%S KST') if self.eta_at else '계산 중'))
        if self.batch: values.append('최근 DB 묶음: '+self.batch)
        if self.notice: values.append(self.notice)
        if self.exit_code is not None: values.append('프로세스 종료 코드: '+str(self.exit_code))
        values.append('체크포인트 기준: '+self.checkpoint)
        values.append('전체 로그: '+self.log_path)
        return values

    def update(self, force=False):
        now = time.monotonic()
        if not force and now-self.last_update < 1:
            return
        lines = self.lines(); color = '#b91c1c' if self.error else '#166534' if self.complete else '#1d4ed8'
        html = ('<div style="border:1px solid #cbd5e1;border-radius:8px;padding:14px;max-width:1100px">'
                '<b style="color:'+color+'">'+escape(lines[0])+'</b>'
                '<div style="height:10px;background:#e2e8f0;margin:10px 0"><div style="height:10px;background:'+color+';width:'+str(min(100,max(0,self.percent)))+'%"></div></div>'
                '<pre style="white-space:pre-wrap;word-break:break-all;margin:0">'+escape('\n'.join(lines[1:]))+'</pre>')
        if self.error:
            html += '<pre style="white-space:pre-wrap;max-height:140px;overflow:auto;color:#b91c1c">'+escape(self.error)+'</pre>'
        html += '</div>'
        self._publish(html,'\n'.join(lines)+('\n'+self.error if self.error else ''))
        self.last_update = now
