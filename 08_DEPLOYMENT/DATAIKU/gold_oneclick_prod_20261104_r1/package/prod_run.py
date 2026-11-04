"""One synchronous notebook call: no Flow, recipes, datasets or scenario creation."""
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback
import uuid

from prod_config import ENGINE, STAGES, target
from prod_guard import check, probe, failure_hint
from prod_panel import ProgressPanel
from prod_state import dump, initialize
from prod_storage import open_folder


def configure(params, project):
    allowed={'CODE_FOLDER_ID','INPUT_FOLDER_ID','ORACLE_CONNECTION','EXPECTED_DB_USER','GOLD_OWNER',
             'TABLE_PREFIX','TABLE_NAMES','EMBED_MODEL','EMBED_DIMENSIONS','WORK_DIR'}
    if set(params)-allowed: raise ValueError('UNKNOWN_ONECLICK_PARAMETER:'+','.join(sorted(set(params)-allowed)))
    p=dict(params,TARGET_MODE='GOLD',EXPECTED_PARTS=34,ACTIVATE_NEW_VECTOR_HEAD=True,
           EXPECTED_ARCHIVE='genos-rag-data-20261007T002029Z-7c0b050f.zip',
           ORIGINAL_SHA_FILE='ORIGINAL.sha256',PARTS_SHA_FILE='PARTS.sha256')
    p.setdefault('TABLE_PREFIX','IDD_B003_LGL_');p.setdefault('TABLE_NAMES',{})
    p.setdefault('WORK_DIR','')
    p['INPUT_FOLDER_ID']=p.get('INPUT_FOLDER_ID') or p.get('CODE_FOLDER_ID')
    check(p, project)
    if p.get('WORK_DIR') and not Path(p['WORK_DIR']).expanduser().is_absolute():
        raise ValueError('WORK_DIR_MUST_BE_ABSOLUTE')
    cfg={'version':'gold-oneclick-production-20261104-r1','project':project,'params':p,
         'input_folder':p['INPUT_FOLDER_ID'],'folders':{'report':p['CODE_FOLDER_ID']},'target':target(p)}
    # Owner/model/input changes get BOTH new local and remote scopes. Never reset prior state.
    identity=dict(cfg,params={k:v for k,v in p.items() if k!='WORK_DIR'})
    key=hashlib.sha256(dump(identity)).hexdigest()[:24]
    cfg['storage']={'input':'','result':'_gold_oneclick_prod_r1/'+key+'/result'}
    root=(Path(p['WORK_DIR'] or Path(tempfile.gettempdir())/'gold-oneclick-production').expanduser()/key).resolve()
    return cfg,root


def atomic(path, value):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_bytes(dump(value)); tmp.replace(path)


class LiveLog:
    """Raw log never loses lines; the display uses only the most recent event."""
    def __init__(self, file):
        self.file=file; self.lock=threading.Lock(); self.buffer=''; self.event=None
    def write(self, text):
        with self.lock:
            self.file.write(text); self.file.flush(); self.buffer+=text
            while '\n' in self.buffer:
                line,self.buffer=self.buffer.split('\n',1)
                try:value=json.loads(line)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and 'phase' in value:self.event=value
            # An unusually large partial line remains in the full log, not in RAM.
            if len(self.buffer)>65536:self.buffer=''
        return len(text)
    def flush(self):
        with self.lock:self.file.flush()
    def take(self):
        with self.lock:
            value=self.event;self.event=None;return value


def run(params, *, panel_sink=None):
    import dataiku
    cfg,root=configure(params,dataiku.api_client().get_default_project().project_key)
    sys.path[:0]=[str(ENGINE),str(ENGINE/'vendor'),str(ENGINE/'vendor/02_BACKEND')]
    import prod_pipeline as pipeline
    pipeline.code_binding()
    root.mkdir(parents=True,exist_ok=True)
    remote=open_folder(cfg,'result')
    run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    logs=root/'logs';logs.mkdir(exist_ok=True)
    log_path=logs/(run_id+'.log')
    status={'run_id':run_id,'status':'RUNNING','started_at':time.time(),'stage':'storage',
            'stages':{},'work_dir':str(root),'remote_folder':params['CODE_FOLDER_ID'],
            'remote_prefix':cfg['storage']['result'],'log_path':str(log_path)}
    with (root/'oneclick.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('ONECLICK_ALREADY_RUNNING') from None
        panel=ProgressPanel('Gold 운영 데이터 34조각 · 한 번에 적재',str(log_path),run_id=run_id,sink=panel_sink)
        screen_lock=threading.RLock(); stop=threading.Event(); vector_started=False
        offset=0; chunk=0
        with log_path.open('x',encoding='utf-8') as raw_log:
            writer=LiveLog(raw_log)
            def save(remote_write=True):
                nonlocal offset,chunk
                status['updated_at']=time.time()
                atomic(root/'latest.json',status);atomic(logs/(run_id+'.json'),status)
                if not remote_write:return
                with log_path.open('rb') as f:
                    f.seek(offset)
                    while True:
                        block=f.read(1024**2)
                        if not block:break
                        remote.upload_stream('runs/'+run_id+'/log-%06d.txt'%chunk,io.BytesIO(block))
                        offset+=len(block);chunk+=1
                value=dump(status)
                remote.upload_stream('runs/'+run_id+'.json',io.BytesIO(value))
                remote.upload_stream('latest.json',io.BytesIO(value))
                with remote.get_download_stream('latest.json') as f:
                    if f.read(len(value)+1)!=value:raise ValueError('STATUS_READBACK_MISMATCH')
            def tick():
                nonlocal vector_started
                while not stop.wait(1):
                    event=writer.take()
                    with screen_lock:
                        if panel.status!='RUNNING':continue
                        if event:
                            if event.get('phase')=='VECTOR_PROGRESS' and status['stage']=='vector':
                                rows,total=event['rows'],event['total_rows']
                                if not vector_started:
                                    panel.start_phase('임베딩·벡터 적재',done=rows,total=total,unit='행')
                                    vector_started=True
                                else:panel.update(done=rows,total=total)
                            panel.update(message=str(event.get('phase')),
                                         metrics={k:event[k] for k in ('table','rows','total_rows','sdk_calls') if k in event})
                        panel.draw()
            worker=threading.Thread(target=tick,daemon=True)
            worker.start()
            try:
                with redirect_stdout(writer),redirect_stderr(writer):
                    # Probe only a prefix inside the already working upload folder.
                    probe(remote,'기존 업로드 폴더의 결과 경로')
                    initialize(cfg,root,remote)
                    atomic(root/'config.json',cfg)
                    save()
                    for stage,code,label,_ in STAGES:
                        status['stage']=stage
                        status['stages'][stage]={'status':'RUNNING','started_at':time.time()}
                        with screen_lock:
                            vector_started=False;writer.take()
                            panel.start_phase(label,unit='행')
                            panel.update(message='완료한 단계 '+str(sum(v['status']=='SUCCESS' for v in status['stages'].values()))+'/8')
                        save()
                        value=pipeline.execute(stage,cfg,root)
                        status['stages'][stage].update(status='SUCCESS',ended_at=time.time(),result=value)
                        save()
                    report=status['stages']['report']['result']
                    if report.get('status')!='GOLD_LOADED' or not report.get('row_counts_and_publications_verified'):
                        raise ValueError('FINAL_GOLD_VERIFICATION_REQUIRED')
                    for name in ('report.json','serving-mapping.json','documents.json','embedding-profile.json'):
                        value=(root/name).read_bytes()
                        remote.upload_stream(name,io.BytesIO(value))
                        with remote.get_download_stream(name) as f:
                            if f.read(len(value)+1)!=value:raise ValueError('RESULT_READBACK_MISMATCH:'+name)
                    status.update(status='SUCCESS',ended_at=time.time(),counts=report['counts'])
                    save()
                stop.set();worker.join(timeout=2)
                panel.finish('SUCCEEDED',completion_confirmed=True,
                             message='PRODUCTION_GOLD_LOADED · '+json.dumps(report['counts'],ensure_ascii=False))
                print('PRODUCTION_GOLD_LOADED')
                print('결과:',params['CODE_FOLDER_ID']+'/'+cfg['storage']['result']+'/report.json')
                print('작업 경로:',str(root))
                return {'status':'PRODUCTION_GOLD_LOADED','counts':report['counts'],
                        'work_dir':str(root),'result_prefix':cfg['storage']['result'],'run_id':run_id}
            except BaseException as exc:
                stop.set();worker.join(timeout=2)
                writer.write(traceback.format_exc())
                outcome='STOPPED_OR_UNKNOWN' if isinstance(exc,KeyboardInterrupt) else 'FAILED'
                hint=failure_hint(exc)
                status.update(status=outcome,ended_at=time.time(),error_type=type(exc).__name__,error=str(exc),hint=hint)
                writer.write(hint+'\n')
                current=status['stages'].get(status['stage'])
                if current and current['status']=='RUNNING':current.update(status=outcome,error=str(exc))
                save(remote_write=False)
                try:save()
                except Exception as upload_exc:
                    writer.write('결과 업로드 실패: '+type(upload_exc).__name__+': '+str(upload_exc)+'\n')
                panel.finish('UNKNOWN' if isinstance(exc,KeyboardInterrupt) else 'FAILED',
                             message=hint,error=traceback.format_exc())
                raise
