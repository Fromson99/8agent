# Dataiku LEGAL_RAG Python 노트북. R6/R7 load 완료 뒤 실행.
ACTION = "vector"  # "check"는 연결·대상 확인만; 임베딩 호출/DB 쓰기 없음
OLD_JOB_DIR = ""  # R6에서 지정했다면 같은 값. 기본값은 이전 실행문과 동일.
EMBED_LLM_ID = "openai:genos-embedding:embedding-kure-v1"  # 이전 전달본의 내부 Mesh 연결
EMBED_DIMENSIONS = 1024
ZIP_NAME = "__ZIP_NAME__"
ZIP_SHA256 = "__ZIP_SHA256__"

import codecs
import collections
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
import dataiku

folder=dataiku.Folder('ehA8dpVm')
matches=[p for p in folder.list_paths_in_partition() if PurePosixPath(p).name==ZIP_NAME]
if len(matches)!=1:raise ValueError('관리 폴더 ehA8dpVm에 이번 _1 ZIP을 정확히 한 개 올리세요.')
with folder.get_download_stream(matches[0]) as stream:raw=stream.read(16*1024**2+1)
if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256:raise ValueError('ZIP_HASH_MISMATCH')
package=Path(tempfile.gettempdir())/('legal-gold-vector-structure-r4-'+ZIP_SHA256[:16])
package.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names=archive.namelist()
    if len(names)!=len(set(names)) or sum(i.file_size for i in archive.infolist())>32*1024**2:raise ValueError('ZIP_CONTENTS')
    manifest=json.loads(archive.read('CODE_MANIFEST.json'))
    if set(names)!=set(manifest['files'])|{'CODE_MANIFEST.json'}:raise ValueError('ZIP_MANIFEST')
    for item in archive.infolist():
        name=PurePosixPath(item.filename)
        if name.is_absolute() or '..' in name.parts or item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP_PATH')
        path=package.joinpath(*name.parts)
        if package.resolve() not in path.resolve().parents:raise ValueError('ZIP_ESCAPE')
        content=archive.read(item)
        if item.filename!='CODE_MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:raise ValueError('FILE_HASH')
        if path.exists():
            if path.read_bytes()!=content:raise ValueError('EXTRACTED_CODE_CHANGED')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(content)

if ACTION not in {"check", "vector"}:raise ValueError("ACTION_CHECK_OR_VECTOR")
old_job=Path(OLD_JOB_DIR) if OLD_JOB_DIR else Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
old_job=old_job.resolve(strict=True)
log_dir=Path.cwd()/'gold-progress-logs';log_dir.mkdir(exist_ok=True)
log_path=log_dir/(time.strftime('%Y%m%d-%H%M%S')+'-vector-structure-r4-'+uuid.uuid4().hex[:8]+'.log')
env=os.environ.copy()
env['PYTHONDONTWRITEBYTECODE']='1'
env['PYTHONPATH']=os.pathsep.join(p for p in sys.path if isinstance(p,str) and p)
env['G19_OLD_JOB_DIR']=str(old_job)
env['G19_DIAGNOSTIC_FILE']=str(log_path.with_suffix('.errors.jsonl'))
env['LEGAL_EMBED_LLM_ID']=EMBED_LLM_ID
env['LEGAL_EMBED_DIMENSIONS']=str(EMBED_DIMENSIONS)
sys.path.insert(0,str(package))
from vector_progress import render as render_vector_progress
from notebook_progress import Panel
panel=Panel(ACTION,EMBED_LLM_ID,EMBED_DIMENSIONS,old_job,log_path)
process=subprocess.Popen([sys.executable,'-u',str(package/'vector_stage.py'),ACTION],
                         cwd=str(package),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         start_new_session=True)
selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
decoder=codecs.getincrementaldecoder('utf-8')();pending='';started=time.monotonic();stop_sent=False
def graceful_interrupt(signum,frame):
    global stop_sent
    if stop_sent:raise KeyboardInterrupt
    stop_sent=True
    if process.poll() is None:process.send_signal(signal.SIGUSR1)
    panel.stop_requested()
previous_interrupt=signal.signal(signal.SIGINT,graceful_interrupt)
try:
    with log_path.open('x',encoding='utf-8') as log:
        log.write('Python: '+sys.version+'\nExecutable: '+sys.executable+'\n');log.flush()
        def consume(line):
            log.write(line+'\n');log.flush()
            panel.consume(line)
            try:
                message=render_vector_progress(json.loads(line))
            except (ValueError,KeyError,TypeError):
                message=None
            if message:
                log.write(message+'\n');log.flush()
        while True:
            try:
                events=selector.select(timeout=1)
            except KeyboardInterrupt:
                graceful_interrupt(signal.SIGINT,None)
                continue
            if not events:
                panel.update()
                continue
            chunk=os.read(process.stdout.fileno(),65536)
            if not chunk:
                pending+=decoder.decode(b'',final=True)
                if pending:consume(pending)
                break
            pending+=decoder.decode(chunk)
            while '\n' in pending:
                line,pending=pending.split('\n',1);consume(line)
        code=process.wait();consume('PROCESS_EXIT='+str(code))
    VECTOR_RESULT=panel.finish(code)
except BaseException as exc:
    panel.error=type(exc).__name__+': '+str(exc)
    VECTOR_RESULT=panel.finish(process.poll() if process.poll() is not None else 130)
    raise
finally:
    signal.signal(signal.SIGINT,previous_interrupt)
    selector.close()
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    process.stdout.close()
# The single status panel shows success/failure. VECTOR_RESULT retains the child
# exit code; full raw diagnostics remain in log_path (no scrolling traceback).
