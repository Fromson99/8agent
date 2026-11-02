"""Recipe supervisor: durable per-run logs, heartbeat, dashboard, failure visibility."""
import codecs
import hashlib
import io
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import uuid
from flow_spec import ROOT, ENGINE, STAGES, INSIGHT
from flow_view import render

def dump(v): return json.dumps(v,ensure_ascii=False,sort_keys=True).encode()

def read(path):
    with Path(path).open('rb') as f: raw=f.read(32*1024**2+1)
    if len(raw)>32*1024**2: raise ValueError('FLOW_METADATA_SIZE')
    return json.loads(raw)

def old_job_path(variables):
    explicit=os.environ.get('LEGAL_GOLD_OLD_JOB_DIR') or variables.get('LEGAL_GOLD_OLD_JOB_DIR')
    if explicit: return Path(explicit).expanduser().resolve()
    retained=Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'
    if (retained/'full-state.json').exists() or (retained/'flow-inputs.json').exists():return retained.resolve()
    scratch=Path(os.environ.get('LEGAL_PIPELINE_SCRATCH') or variables.get('LEGAL_PIPELINE_SCRATCH') or tempfile.gettempdir())
    return (scratch/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2').resolve()

def observations(old_job, stage):
    sys.path.insert(0,str(ENGINE))
    from progress_display import digest
    c=read(ENGINE/'contract.json')
    directory=old_job.parent/('gold-shape-'+digest(c)[:12])
    state=read(directory/'state.json') if (directory/'state.json').exists() else {}
    result={}
    if state:
        from progress_display import Display
        totals=Display(old_job,digest(c),'load').planned_totals(state)
        prefix='verify_' if stage=='verify' else ''
        if stage in {'source','query','verify'}:
            groups=['source','query'] if stage=='verify' else [stage]
            result={'rows':sum(v.get('rows',0) for g in groups for v in state.get(prefix+g,{}).values()),
                    'total':sum(totals[g] for g in groups), 'basis':'저장 완료 기록' if stage!='verify' else '검증 완료 기록'}
    if stage=='vector':
        paths=list((directory/'vectors').glob('*/state.json'))
        if paths:
            latest=max(paths,key=lambda p:p.stat().st_mtime)
            v=read(latest)
            result={'rows':v['rows'], 'total':v.get('total'), 'basis':'벡터 DB 저장 완료 기록'}
    return result

def publish_insight(records):
    import dataiku.insights
    dataiku.insights.save_data(INSIGHT, render(records).encode('utf-8'), 'text/html',
                              label='Gold _1 · 데이터 적재 현황', encoding='utf-8')

def run(stage, cfg):
    import dataiku
    if stage not in {s[0] for s in STAGES}: raise ValueError('FLOW_STAGE')
    variables=dataiku.get_custom_variables(); old_job=old_job_path(variables)
    old_job.parent.mkdir(parents=True,exist_ok=True)
    work=old_job.parent/'gold-flow-logs';work.mkdir(exist_ok=True)
    run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+stage+'-'+uuid.uuid4().hex[:8]
    output=dataiku.Folder(cfg['folders'][stage])
    records={}
    for name,fid in cfg['folders'].items():
        folder=dataiku.Folder(fid,ignore_flow=True)
        if '/latest.json' in {'/'+p.lstrip('/') for p in folder.list_paths_in_partition()}:
            with folder.get_download_stream('latest.json') as f: records[name]=json.loads(f.read(2*1024**2))
    log_path=work/(run_id+'.log'); cfg_path=work/(run_id+'.config.json');cfg_path.write_bytes(dump(cfg))
    env=os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1',G19_OLD_JOB_DIR=str(old_job),G19_DIAGNOSTIC_FILE=str(work/(run_id+'.errors.jsonl')))
    env['PYTHONPATH']=os.pathsep.join(p for p in sys.path if isinstance(p,str) and p)
    current={'stage':stage,'status':'RUNNING','run_id':run_id,'updated_at':time.time(),'elapsed':0,
             'detail':'실행 시작','basis':'단계 실행 기록','log':'runs/'+run_id+'/log-*.txt','local_job':str(old_job)}
    records[stage]=current;started=time.monotonic();last_publish=0;offset=0;log_part=0
    initial=None;initial_time=None;observed_total=None;last_error=None
    def save(force=False):
        nonlocal last_publish,offset,log_part,initial,initial_time
        now=time.monotonic()
        if not force and now-last_publish<15:return
        last_publish=now;current.update(updated_at=time.time(),elapsed=now-started)
        try: obs=observations(old_job,stage)
        except (FileNotFoundError,KeyError): obs={}
        current.update(obs)
        if observed_total is not None: current['total']=observed_total
        n=current.get('rows');total=current.get('total')
        if n is not None and initial is None: initial=n;initial_time=now
        if n is not None and initial is not None and now>initial_time+5 and n>initial and total is not None:
            current['eta']=max(0,total-n)/((n-initial)/(now-initial_time))
        if current['status']=='SUCCESS':current['eta']=0
        output.upload_stream('latest.json',io.BytesIO(dump(current)))
        output.upload_stream('runs/'+run_id+'.json',io.BytesIO(dump(current)))
        # Chunk the full log, rather than retransmitting an ever-growing file each heartbeat.
        if log_path.exists():
            with log_path.open('rb') as f:
                f.seek(offset)
                while block:=f.read(1024**2):
                    output.upload_stream(f'runs/{run_id}/log-{log_part:06d}.txt',io.BytesIO(block))
                    offset+=len(block);log_part+=1
        html=render(records).encode()
        output.upload_stream('status.html',io.BytesIO(html))
        # Dashboard failure is visible; the durable recipe log remains authoritative.
        try: publish_insight(records)
        except Exception as exc: print('DASHBOARD_UPDATE_FAILED:',type(exc).__name__,str(exc),flush=True)
        print('FLOW_PROGRESS',json.dumps(current,ensure_ascii=False),flush=True)
    def consume(line):
        nonlocal last_error,observed_total
        print(line,flush=True)
        try:v=json.loads(line)
        except ValueError:
            import re
            match=re.search(r'벡터 ([\d,]+)/([\d,]+)행',line)
            if match:observed_total=int(match[2].replace(',',''))
            return
        if not isinstance(v,dict):return
        current['detail']=v.get('phase',current['detail'])
        if v.get('phase')=='FLOW_STAGE_RESULT':current['result']=v['result']
        if v.get('phase')=='DIAGNOSTIC_ERROR':
            from error_diagnostics import banner
            last_error=banner(v);current['error']=last_error
        if 'bytes_done' in v:current.update(rows=v['bytes_done'],total=v['bytes_total'],unit='바이트',basis='파일 수신 기록')
    process=None;selector=selectors.DefaultSelector()
    try:
        save(True)
        if stage=='vector':
            sys.path.insert(0,str(ENGINE))
            from mesh_embedding import resolve_settings
            conf=resolve_settings(os.environ,variables)
            env.update(LEGAL_EMBED_LLM_ID=conf['model'],LEGAL_EMBED_DIMENSIONS=str(conf['dimensions']))
        with log_path.open('x',encoding='utf-8') as log:
            process=subprocess.Popen([sys.executable,'-u',str(ROOT/'flow_entry.py'),stage,str(cfg_path)],
                                     cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            selector.register(process.stdout,selectors.EVENT_READ)
            decoder=codecs.getincrementaldecoder('utf-8')();pending=''
            while True:
                events=selector.select(timeout=5)
                if events:
                    chunk=os.read(process.stdout.fileno(),65536)
                    if not chunk:
                        pending+=decoder.decode(b'',final=True)
                        if pending: log.write(pending);log.flush();consume(pending)
                        break
                    pending+=decoder.decode(chunk)
                    while '\n' in pending:
                        line,pending=pending.split('\n',1);log.write(line+'\n');log.flush();consume(line)
                save()
            code=process.wait()
            if code:raise RuntimeError(last_error or '자식 작업 실패. Job 로그의 원문 오류를 확인하세요.')
        current.update(status='SUCCESS',detail=current.get('result',{}).get('origin') or current.get('result',{}).get('reuse') or '단계 완료')
        save(True)
        if current.get('result',{}).get('tables'):
            output.upload_stream('db-counts.json',io.BytesIO(dump(current['result']['tables'])))
    except BaseException as exc:
        current.update(status='FAILED',error=str(exc),detail='오류로 중단 · 완료 기록 보존')
        try:save(True)
        except Exception as save_error:print('FLOW_LOG_UPLOAD_FAILED:',type(save_error).__name__,flush=True)
        raise
    finally:
        selector.close()
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
        if process:process.stdout.close()
