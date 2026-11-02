"""Optional read-only view of the already-running notebook, without restarting it."""
import fcntl
import io
from pathlib import Path
import sys
import time
from flow_spec import ENGINE
from flow_runtime import old_job_path, read, dump, publish_insight
from flow_view import render
sys.path.insert(0,str(ENGINE))
from progress_display import Display,digest

def snapshot(old_job, baselines):
    contract=read(ENGINE/'contract.json');sha=digest(contract)
    directory=old_job.parent/('gold-shape-'+sha[:12])
    state=read(directory/'state.json')
    if state['binding']['contract']!=sha:raise ValueError('MONITOR_CONTRACT_MISMATCH')
    totals=Display(old_job,sha,'load').planned_totals(state)
    now=time.monotonic();records={}
    for name in ['receive','prepare','schema']:
        records[name]={'status':'SUCCESS','detail':'기존 실행에서 준비된 상태 참조','basis':'기존 작업 기록','updated_at':time.time()}
    failed=state.get('status') in {'FAILED','WRITE_UNCONFIRMED','VERIFY_FAILED'}
    for stage,groups in [('source',['source']),('query',['query']),('verify',['verify_source','verify_query'])]:
        done=sum(v.get('rows',0) for g in groups for v in state.get(g,{}).values())
        total=sum(totals[g.removeprefix('verify_')] for g in groups)
        status='SUCCESS' if done==total else 'RUNNING' if done else 'WAITING'
        if stage=='verify' and state['status']!='SOURCE_QUERY_VERIFIED' and done==total:status='RUNNING'
        if stage=='verify' and state['status']=='SOURCE_QUERY_VERIFIED':status='SUCCESS'
        if stage=='source' and not done:status='RUNNING'
        if stage=='query' and not done and sum(v.get('rows',0) for v in state.get('source',{}).values())==totals['source']:status='RUNNING'
        if failed and status=='RUNNING':status='FAILED'
        base=baselines.setdefault(stage,(now,done));elapsed=now-base[0]
        rate=(done-base[1])/elapsed if elapsed>=5 and done>base[1] else 0
        records[stage]={'status':status,'rows':done,'total':total,'elapsed':elapsed,
            'eta':max(0,total-done)/rate if rate else None,'basis':'기존 노트북 완료 기록 · 경과는 관찰 시작 기준',
            'detail':'기존 적재 관찰 · DB 쓰기/조회 없음','updated_at':time.time()}
    vector_paths=list((directory/'vectors').glob('*/state.json'))
    if failed:
        pending=state.get('pending') or {}
        active='verify' if pending.get('verify_only') or state.get('status')=='VERIFY_FAILED' else 'query' if pending.get('table')=='SRCH_ROW' else 'source'
        records[active]['status']='FAILED'
        records[active]['error']='기존 적재 중단: '+', '.join(state.get('last_error',{}).get('codes',[]))+' · 상세 문장은 기존 Job/노트북 로그 확인'
    if vector_paths:
        v=read(max(vector_paths,key=lambda p:p.stat().st_mtime))
        records['vector']={'status':'SUCCESS' if v['status']=='VECTORS_STORED_VERIFIED_NOT_ACTIVATED' else 'FAILED' if v['status']=='FAILED' else 'RUNNING',
            'rows':v['rows'],'total':v.get('total'),'detail':'기존 벡터 실행 관찰','basis':'벡터 저장 완료 기록','updated_at':time.time()}
    return records

def watch(cfg, refresh_seconds=15):
    import dataiku
    from IPython.display import HTML,clear_output,display
    old_job=old_job_path(dataiku.get_custom_variables());baselines={}
    while True:
        with (old_job.parent/'gold-flow-1.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                print('Flow 실행이 시작되어 기존 노트북 관찰을 종료합니다.');return
            records=snapshot(old_job,baselines)
            dataiku.Folder(cfg['folders']['report']).upload_stream('notebook-observation.json',io.BytesIO(dump(records)))
            publish_insight(records)
            clear_output(wait=True);display(HTML(render(records)))
        if not refresh_seconds:return
        time.sleep(max(5,refresh_seconds))
