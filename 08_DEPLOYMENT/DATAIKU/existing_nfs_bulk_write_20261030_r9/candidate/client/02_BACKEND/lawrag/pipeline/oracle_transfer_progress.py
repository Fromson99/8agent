"""Scoped data-job progress; SQLite callbacks enforce cancellation/budgets.

No source bodies, SQL bind values or credentials are logged. A heartbeat is
explicitly process telemetry, not evidence of completed data rows.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time

from semantic_runtime.oracle_dp_io import BudgetPause, atomic_json
import json

_CURRENT = ContextVar('oracle_transfer_progress', default=None)


class Progress:
    def __init__(self, folder, emit, *, interval=15):
        self.folder=Path(folder); self.emit=emit; self.interval=interval
        self.started=time.monotonic(); self.changed=self.started
        self.fields={'phase':'STARTING','rows_checked':0,'rows_added':0,'sqlite_steps':0}
        self.deadline=None; self.stop=threading.Event(); self.lock=threading.Lock()
        self.error=None
        self.temp=Path(os.environ.get('SQLITE_TMPDIR') or tempfile.gettempdir())

    def snapshot(self):
        with self.lock: result=dict(self.fields); changed=self.changed
        result.update(elapsed_seconds=int(time.monotonic()-self.started),
                      phase_seconds=int(time.monotonic()-changed),
                      cpu_seconds=round(time.process_time(),1),
                      free_bytes=shutil.disk_usage(self.folder).free,
                      temp_dir_hint=str(self.temp),temp_free_bytes=shutil.disk_usage(self.temp).free)
        try:
            for line in Path('/proc/self/status').read_text().splitlines():
                if line.startswith('VmRSS:'):result['rss_kib']=int(line.split()[1])
        except OSError: pass
        return result

    def set(self, phase=None, **fields):
        with self.lock:
            if phase is not None:
                self.fields.update(phase=phase);self.changed=time.monotonic()
                for key in ('table','asset','file','bytes_done','bytes_total',
                            'rows_total','rows_processed','rows_prepared'):self.fields.pop(key,None)
            self.fields.update(fields)
        if phase is not None:self.emit('PHASE',**self.snapshot())

    def check(self):
        if self.error is not None:raise self.error
        if self.deadline is not None and time.time()>=self.deadline:
            raise BudgetPause('EXPORT_BUDGET: checkpoint retained; same original deadline')
        if shutil.disk_usage(self.folder).free<512*1024**2:
            raise BudgetPause('DISK_LOW: less than 512MiB; preserve partial DB and free/extend storage')
        if shutil.disk_usage(self.temp).free<512*1024**2:
            raise BudgetPause('TEMP_DISK_LOW: SQLite temporary filesystem has less than 512MiB')
        if Path('/proc/meminfo').exists():
            available=next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'))
            if available<512*1024**2:raise BudgetPause('RAM_LOW: preserve checkpoint')

    def run(self):
        while not self.stop.wait(self.interval):
            try:
                self.check();self.emit('PROGRESS',**self.snapshot())
            except Exception as exc:
                self.error=exc
                # Main thread/SQLite callback owns interruption and durable failure.
                return


@contextmanager
def tracking(folder, emit, *, interval=15):
    progress=Progress(folder,emit,interval=interval);token=_CURRENT.set(progress)
    thread=threading.Thread(target=progress.run,daemon=True);thread.start()
    try:yield progress
    finally:
        progress.stop.set();thread.join(timeout=2);_CURRENT.reset(token)


def report(phase=None, **fields):
    progress=_CURRENT.get()
    if progress is not None:progress.set(phase,**fields)


def check():
    progress=_CURRENT.get()
    if progress is not None:progress.check()


def console_event(folder, status, **fields):
    """One honest progress line, plus durable lightweight metadata only."""
    record = {'at':time.time(), 'status':status, **fields}
    folder = Path(folder)
    with (folder/'progress.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n')
    atomic_json(folder/'progress-latest.json', record)
    parts = ['[진행]', str(fields.get('phase','STARTING')),
             '경과='+str(fields.get('elapsed_seconds',0))+'초',
             '단계='+str(fields.get('phase_seconds',0))+'초']
    file = fields.get('asset') or fields.get('file')
    if file: parts.append('파일='+str(file))
    if fields.get('table'):parts.append('테이블='+str(fields['table']))
    if fields.get('asset_total'):
        parts.append('파일순서='+str(fields.get('asset_index','?'))+'/'+str(fields['asset_total']))
    if fields.get('rows_total') is not None:
        n, total = fields.get('rows_processed',0), fields['rows_total']
        parts.append('해당표='+str(n)+'/'+str(total)+'행')
    elif fields.get('rows_prepared') is not None:
        parts.append('준비생성='+str(fields['rows_prepared'])+'행')
    if fields.get('bytes_total'):
        parts.append('바이트='+str(fields.get('bytes_done','?'))+'/'+str(fields['bytes_total']))
    if fields.get('write_requests_this_run') is not None:
        parts.append('이번적재='+str(fields.get('write_rows_this_run',0))+'행/'+str(fields['write_requests_this_run'])+'요청')
        parts.append('최근요청='+str(fields.get('write_rows_last_request',0))+'행')
    parts += ['SQLite작업량='+str(fields.get('sqlite_steps',0)),
              'CPU누적='+str(fields.get('cpu_seconds',0))+'초',
              '임시여유(후보경로)='+str(round(fields.get('temp_free_bytes',0)/1024**3,3))+'GiB']
    print(' | '.join(parts),flush=True)


@contextmanager
def sqlite_work(db):
    """Observe actual SQLite VM work, including blocking GROUP BY/ORDER BY."""
    progress=_CURRENT.get()
    if progress is None:yield;return
    failure=[];last=[0.0]
    def callback():
        try:
            with progress.lock:progress.fields['sqlite_steps']+=10000
            if time.monotonic()-last[0]>=1:
                progress.check();last[0]=time.monotonic()
            return 0
        except BaseException as exc:
            failure.append(exc);return 1
    db.set_progress_handler(callback,10000)
    try:
        yield
    except sqlite3.OperationalError:
        if failure:raise failure[0] from None
        raise
    finally:db.set_progress_handler(None,0)
