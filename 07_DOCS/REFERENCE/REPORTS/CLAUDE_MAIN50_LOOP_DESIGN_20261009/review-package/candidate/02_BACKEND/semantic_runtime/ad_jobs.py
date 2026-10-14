"""Durable SQL schedules and a fenced, restartable wiki worker."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import os
import socket
import threading
import time
import traceback
from .ad_store import Store, ident, features, table_exists


def error_detail(exc):
    from .observability import _redact_secrets
    # Preserve schema paths and cause chain. Only credentials are redacted.
    return _redact_secrets(''.join(traceback.format_exception(type(exc),exc,exc.__traceback__)))


def record_error(store, exc, stage, *, session=None, job=None, operation=None):
    key=ident('E');detail=error_detail(exc)
    from .observability import _redact_secrets
    message=_redact_secrets(str(exc))
    store.db.execute('INSERT INTO ad_error VALUES(?,?,?,?,?,?,?,?,?,?)',
        (key,session,job,operation,stage,type(exc).__name__,message,detail,0,time.time()))
    return {'id':key,'stage':stage,'error_type':type(exc).__name__,'message':message,'detail':detail,'retryable':False}


def schedule_time(text, now=None):
    import re
    tz=ZoneInfo('Asia/Seoul');current=datetime.fromtimestamp(now or time.time(),tz)
    repeat=86400 if '매일' in text else 0
    explicit=re.search(r'(\d{4}-\d{2}-\d{2})[ T]+(\d{1,2}):(\d{2})',text)
    if explicit:
        result=datetime.fromisoformat(explicit.group(1)+'T'+explicit.group(2).zfill(2)+':'+explicit.group(3)).replace(tzinfo=tz)
    else:
        m=re.search(r'(오전|오후|저녁|밤|아침|새벽)?\s*(\d{1,2})\s*(?:시|:)(?:\s*(\d{1,2})\s*분?)?',text)
        if '자정' in text:hour,minute=0,0
        elif '정오' in text:hour,minute=12,0
        elif m:
            part,h,minu=m.groups();hour=int(h);minute=int(minu or 0)
            if part in ('오후','저녁','밤'):hour=0 if hour==12 and part in ('저녁','밤') else hour%12+12
            elif part=='오전' and hour==12:hour=0
            elif not part and hour==12:raise ValueError('AD_TIME_AMBIGUOUS: 12시는 정오인가요, 자정인가요?')
        else:raise ValueError('AD_TIME: 예: 야간작업 시작 예약 저녁 12시 / 2026-10-07 00:00 / 매일 자정')
        if not 0<=hour<=23 or not 0<=minute<=59:raise ValueError('AD_TIME: invalid hour/minute')
        result=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if '내일' in text:result+=timedelta(days=1)
        elif result<=current:result+=timedelta(days=1)
    if result<=current:raise ValueError('AD_TIME: 예약 시각이 이미 지났습니다.')
    return result.timestamp(),repeat,result.isoformat()


def enqueue(store, session, workspace, *, schedule=None, due=None):
    db=store.db
    old=db.execute("SELECT id FROM ad_job WHERE workspace=? AND status IN('QUEUED','RUNNING') ORDER BY created_at LIMIT 1",(workspace,)).fetchone()
    if old:return old[0]
    key=ident('J');enabled=features(db,workspace)['wiki']
    db.execute('INSERT INTO ad_job(id,workspace,session,schedule,scheduled_for,status,created_at) VALUES(?,?,?,?,?,?,?)',
               (key,workspace,session,schedule,due,'QUEUED' if enabled else 'PAUSED',time.time()))
    if table_exists(db,'sw_queue'):
        db.execute("""INSERT INTO ad_job_item(job,queue_id,scope,investigation,revision)
          SELECT ?,q.id,q.scope,q.aggregate_id,q.revision FROM sw_queue q JOIN sw_scope s ON s.id=q.scope
          WHERE s.team=? AND q.consumer='wiki' AND q.status IN('PENDING','RUNNING','QUARANTINED')""",(key,workspace))
    db.execute('UPDATE ad_job SET total=(SELECT count(*) FROM ad_job_item WHERE job=?) WHERE id=?',(key,key))
    db.execute('UPDATE ad_session SET last_job=? WHERE id=?',(key,session))
    return key


def schedule_tick(store, now=None):
    now=now or time.time();db=store.db
    with store.transaction():
        for row in db.execute('SELECT * FROM ad_schedule WHERE enabled=1 AND due_at<=? ORDER BY due_at',(now,)).fetchall():
            if not features(db,row['workspace'])['wiki']:continue
            # A busy workspace keeps the due occurrence pending; no silent loss.
            if db.execute("SELECT 1 FROM ad_job WHERE workspace=? AND status IN('QUEUED','RUNNING')",(row['workspace'],)).fetchone():continue
            enqueue(store,row['session'],row['workspace'],schedule=row['id'],due=row['due_at'])
            next_due=row['due_at']+row['repeat_seconds']
            if row['repeat_seconds']:
                while next_due<=now:next_due+=row['repeat_seconds']
            db.execute('UPDATE ad_schedule SET enabled=?,last_due_at=due_at,due_at=? WHERE id=?',
                       (int(bool(row['repeat_seconds'])),next_due if row['repeat_seconds'] else row['due_at'],row['id']))


def run_one(store, compile_item, *, now=None):
    now=now or time.time();db=store.db
    with store.transaction():
        stale=[r[0] for r in db.execute("SELECT id FROM ad_job WHERE status='RUNNING' AND lease_until<?",(now,))]
        for key in stale:
            db.execute("UPDATE ad_job SET status='QUEUED',lease=NULL WHERE id=?",(key,))
            db.execute("UPDATE ad_job_item SET status='PENDING' WHERE job=? AND status='RUNNING'",(key,))
        row=db.execute("SELECT j.* FROM ad_job j JOIN ad_feature f ON f.workspace=j.workspace WHERE j.status='QUEUED' AND j.desired='RUN' AND f.wiki=1 AND NOT EXISTS(SELECT 1 FROM ad_job x WHERE x.workspace=j.workspace AND x.status='RUNNING') ORDER BY j.created_at LIMIT 1").fetchone()
        if not row:return None
        job=dict(row);token=ident('lease:')
        db.execute("UPDATE ad_job SET status='RUNNING',lease=?,lease_until=?,heartbeat=?,started_at=COALESCE(started_at,?) WHERE id=?",(token,now+360,now,now,job['id']))
        item=db.execute("SELECT * FROM ad_job_item WHERE job=? AND status='PENDING' ORDER BY queue_id LIMIT 1",(job['id'],)).fetchone()
        if not item:
            failed=db.execute("SELECT count(*) FROM ad_job_item WHERE job=? AND status='FAILED'",(job['id'],)).fetchone()[0]
            db.execute('UPDATE ad_job SET status=?,finished_at=?,lease=NULL WHERE id=?',('PARTIAL' if failed and job['completed'] else 'FAILED' if failed else 'SUCCEEDED',time.time(),job['id']))
            return job['id']
        item=dict(item);db.execute("UPDATE ad_job_item SET status='RUNNING',attempts=attempts+1,started_at=? WHERE job=? AND queue_id=?",(time.time(),job['id'],item['queue_id']))
    def guard():
        current=db.execute('SELECT desired,lease,lease_until FROM ad_job WHERE id=?',(job['id'],)).fetchone()
        if not current or current['lease']!=token or current['lease_until']<time.time():raise ValueError('AD_LEASE: worker lease expired')
        if current['desired']!='RUN' or not features(db,job['workspace'])['wiki']:raise ValueError('AD_STOPPED: job paused/cancelled or wiki disabled')
    try:
        guard();result=compile_item(job,item,guard)
        with store.transaction():
            guard()
            continuing=any(r.get('status')=='CONTINUE' for r in result.get('results',[]))
            db.execute("UPDATE ad_job_item SET status=?,finished_at=?,detail=? WHERE job=? AND queue_id=?",('PENDING' if continuing else 'DONE',None if continuing else time.time(),json.dumps(result,ensure_ascii=False),job['id'],item['queue_id']))
            db.execute("UPDATE ad_job SET completed=(SELECT count(*) FROM ad_job_item WHERE job=? AND status='DONE'),failed=(SELECT count(*) FROM ad_job_item WHERE job=? AND status='FAILED'),status='QUEUED',heartbeat=?,lease=NULL WHERE id=? AND lease=?",(job['id'],job['id'],time.time(),job['id'],token))
    except Exception as exc:
        with store.transaction():
            current=db.execute('SELECT * FROM ad_job WHERE id=?',(job['id'],)).fetchone()
            if not current or current['lease']!=token:return job['id']
            stopped=current['desired']!='RUN' or not features(db,job['workspace'])['wiki']
            if stopped:
                db.execute("UPDATE ad_job_item SET status='PENDING' WHERE job=? AND queue_id=?",(job['id'],item['queue_id']))
                state='CANCELLED' if current['desired']=='CANCEL' else 'PAUSED'
            else:
                error=record_error(store,exc,'wiki.compile',session=job['session'],job=job['id'])
                db.execute("UPDATE ad_job_item SET status='FAILED',finished_at=?,detail=? WHERE job=? AND queue_id=?",(time.time(),error['detail'],job['id'],item['queue_id']))
                db.execute('UPDATE ad_job SET failed=failed+1 WHERE id=?',(job['id'],));state='QUEUED'
            db.execute('UPDATE ad_job SET status=?,heartbeat=?,lease=NULL WHERE id=?',(state,time.time(),job['id']))
    return job['id']


_threads={};_lock=threading.Lock()


def ensure_worker(path, compile_item):
    """One lightweight poller per process; SQL lease fences other processes."""
    key=str(path)
    with _lock:
        if key in _threads and _threads[key].is_alive():return
        def loop():
            while True:
                store=None
                try:
                    store=Store(path)
                    worker=socket.gethostname()+':'+str(os.getpid())
                    store.db.execute("INSERT INTO ad_worker VALUES(?,?,?,'POLLING',NULL) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,status='POLLING',error=NULL",(worker,os.getpid(),time.time()))
                    schedule_tick(store);run_one(store,compile_item)
                except Exception as exc:
                    if store is not None:
                        try:
                            store.db.execute("UPDATE ad_worker SET status='FAILED',error=?,heartbeat=? WHERE id=?",(error_detail(exc),time.time(),worker))
                            sessions=store.db.execute("SELECT DISTINCT session FROM ad_schedule WHERE enabled=1 UNION SELECT DISTINCT session FROM ad_job WHERE status IN ('QUEUED','RUNNING')").fetchall()
                            for row in sessions:record_error(store,exc,'worker.poll',session=row[0])
                        except Exception:pass
                finally:
                    if store:store.close()
                time.sleep(2)
        thread=threading.Thread(target=loop,name='wiki-ad-sql-worker',daemon=True)
        _threads[key]=thread;thread.start()
