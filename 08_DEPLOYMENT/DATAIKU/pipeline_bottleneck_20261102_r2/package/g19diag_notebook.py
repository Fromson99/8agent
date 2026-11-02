"""Compact notebook panels with detailed numeric-only JSON alongside them."""
import fcntl
import html
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid
from g19diag_common import ContextError, context, prepared, error, read, write
from g19diag_snapshot import inventory, local_samples, historical_logs, resources

REPORT = None
OUTPUT = None
LAST_DRAW = 0.


def number(value, suffix=''):
    return '미측정' if value is None else (f'{value:,.3f}' if isinstance(value,float) else f'{value:,}')+suffix


def panel(title, rows, note='', status=''):
    esc = lambda x: html.escape(str(x))
    return ('<section style="max-width:940px;padding:12px 16px;border:1px solid #bbc9d7;border-radius:8px;'
            'background:white;color:#182c40;font:14px/1.4 Arial,\'Malgun Gothic\',sans-serif;text-align:left">'
            '<div style="font-size:19px;font-weight:bold">'+esc(title)+'</div><div style="margin:4px 0;color:#47627c">'+esc(status)+'</div>'
            '<table style="width:100%;border-collapse:collapse;font-size:13px">'+''.join(
                '<tr>'+''.join('<td style="padding:5px 6px;text-align:left;border-bottom:1px solid #e5ebf0;overflow-wrap:anywhere">'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+
            '</table><div style="font-size:12px;margin-top:8px">'+esc(note)+'</div></section>')


def display_html(value):
    try:
        from IPython.display import HTML, clear_output, display
    except ImportError:
        # No streaming logger fallback: the final result remains in REPORT.json.
        return
    clear_output(wait=True); display(HTML(value))


def show(page='요약', report=None):
    r = report or REPORT or {}; db = r.get('oracle', {}); items = r.get('items', [])
    rows = []
    if page == '경로':
        d=r.get('discovery',{})
        rows=[['기록 폴더', '저장된 상태', '대조 결과']]
        labels={'SOURCE_MATCH_NEEDS_PACKAGE':'원본 일치 / 실행코드 확인 필요','FRESH_1_STATE_VERIFIED':'새 _1 계약·코드 일치',
                'NO_VERIFIED_FRESH_1_PACKAGE':'새 _1 실행코드 미확인','SOURCE_RELEASE_MISMATCH':'원본 판본 불일치',
                'FILES_MISMATCH':'입력 파일 결속 불일치','GENERATION_BINDING':'원본 경로 불일치',
                'STATE_DIRECTORY_CONTRACT_MISMATCH':'계약과 기록 폴더 불일치','QUERY_RELEASE_MISMATCH':'검색 판본 불일치'}
        for s in d.get('states',[])[:8]:
            rows.append([Path(s['path']).name,s.get('status','미확인'),labels.get(s.get('reason'),s.get('reason','미확인'))])
        if not d.get('states'): rows.append(['기록 후보 미발견','',''])
        selected=d.get('selected') or {}
        if selected: rows.append(['선택 코드',Path(selected['package']).name,'정확한 해시 대조 완료'])
        note='중단·실패 상태도 진단 대상입니다. 최신 시각으로 임의 선택하지 않습니다. 전체 경로·후보·코드별 제외 사유는 REPORT.json에 보존됩니다.'
    elif page == '자료':
        samples = {(s.get('asset'),s.get('table')):s for s in r.get('samples', [])}
        rows = [['큰 종류 (상위 10)', '계획 행 수', '표본 평균 JSON bytes', '표본 읽기+JSON 초']]
        for i in items[:10]:
            s = samples.get((i['asset'],i['table']), {})
            rows.append([i['table'] or i['kind'], number(i['rows']), number(s.get('prefix_mean_json_bytes')), number(s.get('read_and_json_seconds'))])
        note = '상위 밖을 포함한 전체 종류는 REPORT.json에 있습니다. 표본은 앞32행이며 전체 평균·Oracle 물리용량이 아닙니다.'
    elif page == 'DB':
        rows = [['Oracle 조회', '상태', '왕복 포함 초']]
        rows += [[q['name'], q['status']+' '+','.join(q.get('error',{}).get('codes',[])), number(q.get('seconds'))] for q in db.get('queries',[]) if q['name'].startswith(('roundtrip','table stats','index stats','LOB','V$SQL','DB identity'))][:9]
        note = 'V$SQL 수치는 해당 커서 수명 누계입니다. 이번 실행 시간으로 합산하지 않습니다. 통계 행 수는 오래됐을 수 있습니다.'
    elif page == '삽입':
        groups = {}
        for p in db.get('insert_probes',[]): groups[(p['table'],p.get('kind'))] = p
        rows = [['대상 (각 종류의 마지막 시험)', '행', 'INSERT 초', '검증 초', '요청 초 / 상태']]
        for (table,kind), p in groups.items():
            rows.append([table+(' / '+kind.split('.')[-1] if kind else ''), number(p.get('rows')),
                         number(p.get('insert_db_seconds')),number(p.get('verify_db_seconds')),
                         number(p.get('request_seconds'))+' / '+p['status']])
        note = '진단 전용 키·앞32행 본문 반복·ROLLBACK 시험입니다. 실제 COMMIT 처리량/전체 완료시간은 아닙니다. DB 내부 시간 해상도는 0.01초입니다.'
    elif page == '이력':
        rows = [['기존 로그 관측 구간', '행 차이', '구간 초', '행/초']]
        rows += [[h['phase']+' / '+h['table'], number(h['row_delta']),number(h['observed_seconds']),number(h['rows_per_second'])] for h in r.get('historical',[])[:10]]
        note = '로그에서 읽은 구간만 표시합니다. 현재 데이터 결속 미확인 이력이며 하트비트를 배치 수로 세지 않습니다.'
    elif page == '실행':
        profile = r.get('profile', {})
        rows = [['실제 실행 측정', '호출 수', '자체 초', '포함 초']]
        metrics = sorted(profile.get('metrics',{}).items(), key=lambda x:-x[1]['exclusive_seconds'])
        rows += [[k, number(v['calls']),number(v['exclusive_seconds']),number(v['inclusive_seconds'])] for k,v in metrics[:10]]
        if not metrics: rows.append(['아직 실행 계측 없음', '', '', ''])
        note = '자체 시간만 합산할 수 있습니다. 포함 시간은 부모·자식이 겹칩니다. DB 요청에는 왕복·파싱·실행이 모두 포함됩니다.'
    else:
        total = sum(i['rows'] for i in items) if 'items' in r else None
        candidates = sum(i['rows'] for i in items if i['candidate']) if 'items' in r else None
        probes = db.get('insert_probes',[]); good = [p for p in probes if p['status']=='ROLLED_BACK_VERIFIED']
        pings = [q['seconds'] for q in db.get('queries',[]) if q['name'].startswith('roundtrip') and q['status']=='OK']
        rows = [['검색 예정 / 제외 검토', number(total)+' / '+number(candidates)+'행'],
                ['자료 종류 / SQLite 표본 성공', number(len(items) if 'items' in r else None)+' / '+number(sum(s.get('status')=='OK' for s in r['samples']) if 'samples' in r else None)],
                ['Oracle 왕복 중앙값', number(statistics.median(pings) if pings else None, '초')],
                ['INSERT·검증·롤백 확인', str(len(good))+'회 / 전체 기록 '+str(len(probes))+'건' if 'insert_probes' in db else '미실행'],
                ['Oracle 진단 상태', db.get('status','미측정')],
                ['실제 후속 단계 계측', r.get('profile',{}).get('status','미실행 — 별도 PROFILE 셀')],
                ['경로 → 자료 → DB → 삽입 → 이력 → 실행', 'SHOW_DIAG_PAGE("경로") 등으로 화면만 전환'],
                ['전체 수치 저장', str(OUTPUT.name if OUTPUT else '')+'/REPORT.json']]
        if r.get('loader_status'): rows.append(['기존 적재 기록',r['loader_status']+' — 재시작 없이 진단'])
        if r.get('error'):
            e=r['error']; reason=e.get('reason',e.get('type','미확인')) if isinstance(e,dict) else e
            rows.append(['진단 연결 중단',reason])
        if r.get('discovery'):
            d=r['discovery']; rows.append(['찾은 기록 / 원본 일치 / 새 _1 계약·코드 일치',str(len(d.get('states',[])))+' / '+str(d.get('source_matching_states',0))+' / '+str(d.get('fresh_matching_states',0))])
        note = '미측정은 0초가 아닙니다. 원문·SQL 값·벡터·인증 정보는 보고서에 저장하지 않습니다. 전체 목록은 파일에 보존됩니다.'
    value = panel('전체 적재 병목 진단 R2 · '+page, rows, note, r.get('status','준비 중'))
    display_html(value)
    return value


def progress(stage, detail=''):
    global LAST_DRAW
    if time.monotonic()-LAST_DRAW < 2: return
    LAST_DRAW = time.monotonic()
    display_html(panel('전체 적재 병목 진단', [[stage,detail]], '진행 화면을 교체합니다. 긴 로그는 출력하지 않습니다.', '진행 중'))


def output_dir():
    path = Path.cwd()/'gold-bottleneck-reports'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    path.mkdir(parents=True,exist_ok=False); return path


def snapshot(old_job='', state_dir='', package_dir='', insert_probes=True, hints=None):
    global REPORT, OUTPUT
    OUTPUT = output_dir(); REPORT = {'status':'RUNNING', 'mode':'snapshot_and_rollback_probes'}
    try:
        progress('실행 코드·기록 결속 확인')
        plan = prepared(old_job)
        REPORT['items'] = inventory(plan)
        ctx = context(old_job, state_dir, package_dir, hints=hints)
        REPORT['discovery'] = ctx.get('discovery',{})
        REPORT['binding'] = {'code':ctx['state']['binding']['code'], 'source_release':ctx['state']['binding']['source_release'],
                             'query_release':ctx['state']['binding']['query_release'],'descriptor_checksum':ctx['descriptor_checksum']}
        REPORT['items'] = inventory(ctx); REPORT['resources'] = resources(OUTPUT)
        REPORT['loader_status'] = ctx['state']['status']
        with (Path(ctx['state_dir'])/'job.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            REPORT['samples'] = local_samples(ctx, REPORT['items'], progress)
        REPORT['historical'] = historical_logs(Path.cwd()/'gold-progress-logs')
        config = {'context':ctx, 'insert_probes':insert_probes}
        write(OUTPUT/'worker-config.json',config)
        worker_output = OUTPUT/'oracle.json'
        env = dict(os.environ); env['PYTHONPATH'] = os.pathsep.join(str(s) for s in sys.path if isinstance(s,str))
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        started = time.monotonic(); timed_out = False
        with (OUTPUT/'worker.log').open('x') as log:
            process = subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('g19diag_oracle_worker.py')),str(OUTPUT/'worker-config.json'),str(worker_output)],stdout=log,stderr=subprocess.STDOUT,env=env)
            try:
                while process.poll() is None:
                    current = read(worker_output) if worker_output.exists() else {}
                    active = current.get('active_query') or {}
                    progress('Oracle / INSERT 시험', active.get('name','연결 준비'))
                    if time.monotonic()-started > 210 or (active and time.time()-active['started_epoch'] > 30):
                        timed_out = True; break
                    time.sleep(.5)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            REPORT['oracle'] = read(worker_output) if worker_output.exists() else {'status':'NO_WORKER_RESULT'}
            if timed_out:
                REPORT['oracle']['status'] = 'CLIENT_TIMEOUT_DB_OUTCOME_UNCONFIRMED'
                REPORT['oracle']['timeout_note'] = 'Child stopped; remote statement cancellation not certified; no retry. Probe namespaces retained for read-only reconciliation.'
            REPORT['oracle']['worker_exit'] = process.returncode
        REPORT['status'] = 'COMPLETE' if REPORT['oracle'].get('status') in ('COMPLETE','READONLY_COMPLETE') else 'PARTIAL'
    except ContextError as exc:
        REPORT['status']='CONTEXT_UNRESOLVED'
        REPORT['error']={**error(exc),'reason':str(exc)}
        REPORT['discovery']=exc.details
        REPORT['oracle']={'status':'NOT_STARTED_CONTEXT_UNRESOLVED'}
    except KeyboardInterrupt:
        REPORT['status'] = 'USER_INTERRUPTED_DB_OUTCOME_UNCONFIRMED'
        if 'worker_output' in locals() and worker_output.exists():
            REPORT['oracle'] = read(worker_output)
            REPORT['oracle']['status'] = 'CLIENT_INTERRUPTED_DB_OUTCOME_UNCONFIRMED'
    except Exception as exc:
        REPORT['status'] = 'STOPPED'; REPORT['error'] = {**error(exc), 'reason':str(exc)[:160] if isinstance(exc,ValueError) else '기존 노트북·OLD_JOB_DIR/STATE_DIR/PACKAGE_DIR 및 실행 중인 적재를 확인하세요.'}
    finally:
        write(OUTPUT/'REPORT.json',REPORT); show()
    return REPORT


def profile(stage='', old_job='', state_dir='', package_dir='', hints=None):
    global REPORT, OUTPUT
    if stage not in ('load','verify_publish','vector'):
        REPORT = {'status':'실행 안 함', 'error':'PROFILE_STAGE를 load / verify_publish / vector 중 하나로 지정하면 그 실제 단계 한 개를 실행·계측합니다.'}
        show(); return REPORT
    OUTPUT = output_dir(); REPORT = {'status':'RUNNING','mode':'actual_stage_profile'}
    try:
        ctx=context(old_job,state_dir,package_dir,hints=hints)
        REPORT['discovery']=ctx.get('discovery',{})
    except Exception as exc:
        REPORT['status']='CONTEXT_UNRESOLVED'; REPORT['error']={**error(exc),'reason':str(exc)[:160]}
        if isinstance(exc,ContextError): REPORT['discovery']=exc.details
        write(OUTPUT/'REPORT.json',REPORT);show();return REPORT
    config = {'action':stage,'old_job':ctx['job'],'state_dir':ctx['state_dir'],'package_dir':ctx['package'],'output':str(OUTPUT)}
    write(OUTPUT/'profile-config.json',config)
    env = dict(os.environ); env['PYTHONPATH'] = os.pathsep.join(s for s in sys.path if isinstance(s,str)); env['PYTHONDONTWRITEBYTECODE']='1'
    with (OUTPUT/'original-stage.log').open('x') as log:
        process = subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('g19diag_profile_entry.py')),str(OUTPUT/'profile-config.json')],stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            while process.poll() is None:
                path = OUTPUT/'profile.json'
                if path.exists(): REPORT['profile'] = read(path)
                show('실행'); time.sleep(2)
        except KeyboardInterrupt:
            REPORT['status']='USER_INTERRUPTED_OUTCOME_UNCONFIRMED'
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            path = OUTPUT/'profile.json'
            if path.exists(): REPORT['profile']=read(path)
            REPORT['exit_code'] = process.returncode
            if REPORT['status']=='RUNNING': REPORT['status']='COMPLETE' if process.returncode==0 else 'STOPPED'
            if (OUTPUT/'profile-binding.json').exists(): REPORT['binding']=read(OUTPUT/'profile-binding.json')
            write(OUTPUT/'REPORT.json',REPORT); show('실행')
    return REPORT
