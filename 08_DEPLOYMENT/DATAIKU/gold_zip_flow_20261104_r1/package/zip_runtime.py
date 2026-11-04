"""One recipe invocation, shared-workspace guard and durable per-stage result/logs."""
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
from zip_config import ROOT, ENGINE, STAGES


def dump(value): return json.dumps(value,ensure_ascii=False,sort_keys=True).encode()


def read_folder(folder,path):
    names = {p.lstrip('/') for p in folder.list_paths_in_partition()}
    if path not in names: return None
    with folder.get_download_stream(path) as f: raw=f.read(32*1024**2+1)
    if len(raw)>32*1024**2: raise ValueError('REMOTE_STATE_LIMIT')
    return json.loads(raw)


def initialize(cfg,root,remote):
    root.mkdir(parents=True,exist_ok=True)
    path = root/'workspace.json'
    binding = hashlib.sha256(dump({k:v for k,v in cfg.items() if k!='scenario'})).hexdigest()
    saved = read_folder(remote,'workspace.json')
    local = json.loads(path.read_text()) if path.exists() else None
    if saved is not None and local!=saved:
        raise ValueError('CHECKPOINT_WORKSPACE_MISSING_OR_CHANGED: 이전 WORK_DIR와 체크포인트를 복구하세요. 새 INSERT/임베딩 없음.')
    if local is not None and local['binding']!=binding: raise ValueError('WORKSPACE_CONFIG_CHANGED')
    if local is None:
        local={'binding':binding,'token':uuid.uuid4().hex,'root':str(root),'created':time.time()}
        path.write_bytes(dump(local))
    if saved is None: remote.upload_stream('workspace.json',io.BytesIO(dump(local)))
    return local


class Tee:
    def __init__(self,screen,file): self.screen,self.file,self.lock=screen,file,threading.Lock()
    def write(self,text):
        with self.lock: self.screen.write(text); self.file.write(text); self.file.flush()
        return len(text)
    def flush(self):
        with self.lock: self.screen.flush(); self.file.flush()


def run(stage,cfg):
    import dataiku
    if stage not in {s[0] for s in STAGES}: raise ValueError('UNKNOWN_FLOW_STAGE')
    sys.path[:0]=[str(ENGINE),str(ENGINE/'vendor'),str(ENGINE/'vendor/02_BACKEND')]
    import zip_pipeline as pipeline
    params=cfg['params']
    root=Path(params.get('WORK_DIR') or (Path(tempfile.gettempdir())/'legal-gold-zip-flow'/cfg['project'])).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    remote=dataiku.Folder(cfg['folders']['report'],ignore_flow=True)
    output=dataiku.Folder(cfg['folders'][stage],ignore_flow=True)
    with (root/'flow.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('GOLD_ZIP_FLOW_ALREADY_RUNNING') from None
        initialize(cfg,root,remote)
        run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+stage+'-'+uuid.uuid4().hex[:8]
        logs=root/'logs';logs.mkdir(exist_ok=True)
        path=logs/(run_id+'.log')
        status={'stage':stage,'run_id':run_id,'status':'RUNNING','started_at':time.time(),'local_work':str(root)}
        stop=threading.Event(); upload_lock=threading.Lock();offset=0;part=0
        def save():
            nonlocal offset,part
            with upload_lock:
                status['updated_at']=time.time()
                output.upload_stream('latest.json',io.BytesIO(dump(status)))
                output.upload_stream('runs/'+run_id+'.json',io.BytesIO(dump(status)))
                if path.exists():
                    with path.open('rb') as f:
                        f.seek(offset)
                        while True:
                            block=f.read(1024**2)
                            if not block: break
                            output.upload_stream('runs/'+run_id+'/log-%06d.txt'%part,io.BytesIO(block))
                            offset+=len(block);part+=1
        def heartbeat():
            while not stop.wait(15):
                try: save()
                except Exception as exc: print('RESULT_UPLOAD_FAILED',type(exc).__name__,flush=True)
        worker=threading.Thread(target=heartbeat,daemon=True)
        try:
            save();worker.start()
            with path.open('x',encoding='utf-8') as log:
                tee=Tee(sys.stdout,log)
                with redirect_stdout(tee),redirect_stderr(tee):
                    status['result']=pipeline.execute(stage,cfg,root)
                    if stage == 'report':
                        for name in ('report.json','serving-mapping.json','documents.json','embedding-profile.json'):
                            if (root/name).is_file():
                                with (root/name).open('rb') as stream: output.upload_stream(name,stream)
            status['status']='SUCCESS'
        except BaseException as exc:
            status.update(status='FAILED',error_type=type(exc).__name__,error=str(exc))
            raise
        finally:
            stop.set()
            if worker.ident: worker.join(timeout=2)
            status['ended_at']=time.time()
            # A failed result upload remains a failed recipe; never fabricate completion.
            save()
