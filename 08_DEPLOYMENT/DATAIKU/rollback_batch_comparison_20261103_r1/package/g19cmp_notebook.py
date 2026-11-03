"""Bounded worker lifecycle and saved-result-only notebook panels."""
import hashlib
import html
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from g19cmp_common import context, read, write, error, identifier, literal

REPORT = None
OUTPUT = None


def display(value):
    from IPython.display import HTML, clear_output, display as draw
    clear_output(wait=True)
    draw(HTML(value))


def panel(title, rows, note='', status=''):
    esc = lambda v: html.escape(str(v))
    return ('<section style="max-width:1000px;padding:16px;border:1px solid #bac8d7;'
            'background:white;color:#243a50;font:14px Arial,sans-serif">'
            '<b style="font-size:20px">'+esc(title)+'</b><p>'+esc(status)+'</p>'
            '<table style="width:100%;border-collapse:collapse">'+''.join(
                '<tr>'+''.join('<td style="padding:6px;border-bottom:1px solid #ddd">'+esc(v)+'</td>' for v in row)+'</tr>'
                for row in rows)+'</table><p>'+esc(note)+'</p></section>')


def number(value):
    return '미측정' if value is None else f'{value:,.3f}' if isinstance(value,float) else str(value)


def show(page='요약', report=None):
    r = REPORT if report is None else report
    r = r or {}
    note='저장 결과만 표시합니다. SQL/INSERT를 다시 실행하지 않습니다.'
    if page in ('응답','배치'):
        phase = 'response' if page=='응답' else 'batch'
        left,right = ('normal','exception') if phase=='response' else ('baseline','large')
        rows=[['종류 / 회차','같은 행 수',left+' 요청초',right+' 요청초','요청 수 좌/우']]
        for group in r.get('summaries',[]):
            if group['phase']!=phase:continue
            for p in group['pairs']:
                rows.append([group['kind']+' / '+str(p['pair']+1),p['rows'],number(p[left+'_request_s']),
                    number(p[right+'_request_s']),str(p[left+'_requests'])+'/'+str(p[right+'_requests'])])
            rows.append([group['kind']+' 중앙값 비율(우/좌)',number(group['median_right_over_left']),group['status'],'',''])
        note+=' 요청초는 해당 표본의 모든 배치 요청시간 합입니다. 3쌍 완료 시만 비율을 표시합니다. 총 적재시간·개선율 보장이 아닙니다.'
    elif page=='정확성':
        rows=[['종류','동일행/충돌/누락 검사','결과']]
        rows += [[p['kind'],p['mode'],p['status']] for p in r.get('integrity',[])]
        rows.append(['원래 state.json 내용 보존','SHA-256 전후 동일',str(r.get('original_state_unchanged','미확인'))])
        note+=' 실제 pending 재개·COMMIT·전수검증은 이 검사에 포함되지 않습니다.'
    elif page=='상태':
        rows=[['구분','상태']]
        rows += [[p['kind'],p['status']+' / '+str(p.get('sample_rows',0))+'행'] for p in r.get('source_samples',[])]
        rows += [[p.get('kind',p.get('target','')),p['reason']] for p in r.get('skipped',[])]
        rows += [['중단 이유',str(r.get('reason',r.get('error','없음')))],['SQL 요청 수',r.get('queries','미측정')]]
        note+=' 미측정·중단은 0초가 아닙니다. 실패 뒤 자동 재실행하지 않습니다.'
    else:
        good=[p for p in r.get('trials',[]) if p['status']=='ROLLED_BACK_VERIFIED' and p['phase']!='warmup']
        complete=[p for p in r.get('summaries',[]) if p['complete_pairs']==3]
        rows=[['정상/진단응답 비교 완료 종류',sum(p['phase']=='response' for p in complete)],
              ['기존/확대배치 비교 완료 종류',sum(p['phase']=='batch' for p in complete)],
              ['롤백·잔여0 확인 시험',len(good)],['경과 초',number(r.get('elapsed_s'))],
              ['기존 적재 상태',r.get('original_loader_status','미확인')],
              ['원래 state.json 내용 보존',r.get('original_state_unchanged','미확인')],
              ['결과 파일',str(OUTPUT/'COMPARISON.json') if OUTPUT else r.get('output','미확인')]]
        if r.get('error'):rows.append(['중단',str(r.get('reason',r['error']))])
        note+=' SHOW_COMPARE_PAGE("응답"), ("배치"), ("정확성"), ("상태"). 용량·전체 완료시간은 별도 확인이 필요합니다.'
    value=panel('Oracle 추가 비교 검사 R1 · '+page,rows,note,r.get('status','미실행'))
    display(value)
    return value


def stop_child(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=5)


def monitor(process, output, started):
    while process.poll() is None:
        current=read(output) if output.exists() else {}
        active=current.get('active') or {}
        display(panel('Oracle 추가 비교 검사 R1',[[active.get('name','연결 준비'),
            str(round(time.monotonic()-started))+'초',str(current.get('queries',0))+' 요청']],
            '화면만 갱신합니다. 원래 적재는 재개하지 않습니다.','RUNNING'))
        if time.monotonic()-started>660 or (active and time.time()-active['started_epoch']>60):
            return 'CLIENT_TIMEOUT_DB_OUTCOME_UNCONFIRMED'
        time.sleep(2)
    return None


def run(old_job='',state_dir='',package_dir='',hints=None):
    global REPORT, OUTPUT
    OUTPUT=(Path.cwd()/'gold-comparison-reports'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    REPORT={'status':'PREPARING','output':str(OUTPUT/'COMPARISON.json')}
    final=OUTPUT/'COMPARISON.json'; worker_output=OUTPUT/'worker-result.json'
    ctx=None; before=None; process=None; override=None
    try:
        display(panel('추가 검사 준비',[['실행 코드·원본·기존 적재 상태','정확한 결속 확인 중']]))
        package=Path(__file__).resolve().parent
        manifest=read(package/'MANIFEST.json')
        for relative,sha in manifest['files'].items():
            path=(package/relative).resolve(strict=True)
            if package not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise ValueError('COMPARISON_PACKAGE_CHANGED')
        ctx=context(old_job,state_dir,package_dir,hints=hints)
        before=hashlib.sha256((Path(ctx['state_dir'])/'state.json').read_bytes()).hexdigest()
        config={'context':ctx,'run_id':uuid.uuid4().hex,
            'plan_sha256':hashlib.sha256((package/'PLAN.json').read_bytes()).hexdigest(),
            'diagnostic_manifest':manifest}
        write(OUTPUT/'worker-config.json',config)
        env=dict(os.environ)
        env['PYTHONPATH']=os.pathsep.join([str(package)]+[str(p) for p in sys.path if isinstance(p,str)])
        env['PYTHONDONTWRITEBYTECODE']='1'
        with (OUTPUT/'worker.log').open('x') as log:
            process=subprocess.Popen([sys.executable,'-u',str(package/'g19cmp_worker.py'),
                str(OUTPUT/'worker-config.json'),str(worker_output)],stdout=log,stderr=subprocess.STDOUT,env=env)
            started=time.monotonic()
            try:override=monitor(process,worker_output,started)
            except KeyboardInterrupt:override='USER_INTERRUPTED_DB_OUTCOME_UNCONFIRMED'
            except Exception as exc:
                override='MONITOR_FAILED_DB_OUTCOME_UNCONFIRMED';REPORT['monitor_error']=error(exc)
            finally:stop_child(process)
        REPORT=read(worker_output) if worker_output.exists() else {'status':'CHILD_NO_RESULT','error':{'type':'ChildExit','exit_code':process.returncode}}
        if process.returncode and not override:override='CHILD_EXIT_DB_OUTCOME_UNCONFIRMED'
        if override:
            REPORT['worker_status_before_stop']=REPORT.get('status');REPORT['status']=override
            REPORT['db_cancellation_confirmed']=False
            REPORT['reason']='DBA 확인 전 재실행 금지; 클라이언트 중단은 서버 실행 취소 확인이 아님'
    except Exception as exc:
        REPORT.update(status='PREPARATION_STOPPED',error=error(exc),reason=str(exc)[:200])
        if hasattr(exc,'details'):REPORT['discovery']=exc.details
    finally:
        if process is not None:stop_child(process)
        if ctx is not None:
            try:
                after=hashlib.sha256((Path(ctx['state_dir'])/'state.json').read_bytes()).hexdigest()
                REPORT.update(original_state_sha256_before=before,original_state_sha256_after=after,original_state_unchanged=before==after)
            except OSError:REPORT['original_state_unchanged']='UNCONFIRMED'
            if REPORT.get('original_state_unchanged') is not True:
                REPORT['status']='STOPPED_ORIGINAL_STATE_UNCONFIRMED'
            releases=sorted({p['probe_release'] for p in REPORT.get('trials',[]) if p.get('probe_release')})
            if releases:
                table=ctx['contract']['tables']['SRCH_ROW']
                target=identifier(table['owner'])+'.'+identifier(table['name'])
                column=identifier(table['columns'][table['primary_key'][0]]['name'])
                queries=['-- 서버 세션 종료/롤백 확인 후 각 결과 N=0인지 확인. 자동 실행/DELETE 없음.']
                queries += ['SELECT '+literal(v)+' AS PROBE_RELEASE, COUNT(*) AS N FROM '+target+' WHERE '+column+'='+literal(v)+';' for v in releases]
                (OUTPUT/'CHECK_PROBE_ROWS.sql').write_text('\n'.join(queries)+'\n',encoding='utf-8')
                REPORT['reconciliation_select_file']=str(OUTPUT/'CHECK_PROBE_ROWS.sql')
        REPORT['output']=str(final)
        write(final,REPORT)
    show()
    return REPORT
