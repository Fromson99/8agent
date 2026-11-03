"""Notebook launcher and saved-result views. Views never access Oracle."""
import hashlib
import html
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from g19sql_common import locate, read, write, error

REPORT={}
OUTPUT=None


def draw(title, rows, note=''):
    esc=lambda v:html.escape('미확인' if v is None else str(v))
    value='<section style="max-width:1150px;padding:16px;border:1px solid #b9c8d6;background:white;color:#243a50;font:14px Arial"><b style="font-size:20px">'+esc(title)+'</b><table style="width:100%;border-collapse:collapse">'
    value+=''.join('<tr>'+''.join('<td style="padding:6px;border-bottom:1px solid #ddd">'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)
    value+='</table><p>'+esc(note)+'</p></section>'
    return value


def display(value):
    from IPython.display import HTML, clear_output, display as show_html
    clear_output(wait=True);show_html(HTML(value))


def page(result, name='요약', cursor=1):
    q=result.get('queries',{})
    qr=lambda n:q.get(n,{}).get('rows',[])
    note='저장 결과만 표시합니다. SQL/INSERT를 실행하지 않습니다. '
    if name=='시간':
        rows=[['종류/표본수','전체 요청초','복원초','INSERT초','값 검증초','롤백초','미분리 잔여초']]
        for item in result.get('timing',[]):
            m=item['medians']
            rows.append([item['kind']+' / '+str(len(item['samples']))]+[round(m[k],4) if k in m else None for k in ('request_s','payload_db_s','insert_db_s','verify_db_s','rollback_db_s','unseparated_s')])
        note+='이전 진단예외 3회 값의 항목별 중앙값. 합계 중앙값과 각 중앙값 합은 다를 수 있습니다. 복원/INSERT에는 JSON 처리 등이 포함됩니다. 잔여는 네트워크 단독이 아니며 파싱·JDBC·연결 비용 등이 미분리입니다. DB 시계 0.01초 해상도.'
    elif name=='인덱스':
        rows=[['예상 PK 열',', '.join(result.get('binding',{}).get('pk_columns',[]))]]
        rows += [['인덱스','종류/상태/가시성','열 순서','PK 열이 선두인가','통계시각']]
        rows += [[r['OWNER']+'.'+r['INDEX_NAME'],str(r['INDEX_TYPE'])+'/'+str(r['STATUS'])+'/'+str(r['VISIBILITY']),', '.join(r['columns']),r['pk_leading_columns'],r.get('LAST_ANALYZED')] for r in result.get('index_summary',[])]
        rows += [['PK/UNIQUE 제약',r['CONSTRAINT_NAME'],r['CONSTRAINT_TYPE'],r['STATUS'],r['VALIDATED']] for r in qr('constraints')]
        rows += [['테이블 통계',r.get('NUM_ROWS'),r.get('BLOCKS'),r.get('PARTITIONED'),r.get('LAST_ANALYZED')] for r in qr('table_stats')]
        rows += [['통계 상태',r.get('STALE_STATS'),r.get('STATTYPE_LOCKED'),'',r.get('LAST_ANALYZED')] for r in qr('stats_state')]
        note+='인덱스 존재는 사용 증명이 아닙니다. 통계 행수는 현재 행수가 아닙니다. PARTITIONED=YES면 개별 파티션 상태는 미확인입니다. 권한·조회 상태는 상태 페이지에서 확인하세요.'
    elif name=='계획':
        rows=[['번호/instance/SQL_ID/child','최근 활동(서버)','누적 실행수','캐시 계획 연산','마지막 starts 기록']]
        for i,r in enumerate(result.get('plan_summary',[]),1):
            ops=sorted({p['OPERATION']+' '+(p.get('OPTIONS') or '') for p in r['operations']})
            rows.append([str(i)+' / '+str(r['INST_ID'])+' / '+r['SQL_ID']+' / '+str(r['CHILD_NUMBER']),r['LAST_ACTIVE_TIME'],r['EXECUTIONS'],', '.join(ops),r['nonzero_last_starts']])
        note+='최근24시간 같은 접속 계정·대상 테이블의 최대12개 후보. 이전 비교 실행과 정확히 연결됐다는 뜻은 아닙니다. FULL SCAN/HASH JOIN 자체만으로 잘못된 계획이라고 판단하지 않습니다. SHOW_SQL_CHECK("계획상세", 1)로 번호별 상세.'
    elif name=='계획상세':
        if type(cursor) is not int or not 1<=cursor<=12:raise ValueError('CURSOR_NUMBER_1_TO_12')
        plans=result.get('plan_summary',[])
        r=plans[cursor-1] if len(plans)>=cursor else {}
        stats={x['ID']:x for x in qr(r.get('key','')+'_runtime')}
        rows=[['ID/부모','연산','객체','예상 행수','마지막 실제 행수/starts','예상 TEMP bytes','마지막 workarea TEMP bytes','PK조건 접근/필터']]
        for p in qr(r.get('key','')+'_plan'):
            s=stats.get(p['ID'],{})
            flags='; '.join(str(i+1)+':'+str(p.get('PK_ACCESS_'+str(i+1)))+'/'+str(p.get('PK_FILTER_'+str(i+1))) for i in range(len(result.get('binding',{}).get('pk_columns',[]))))
            rows.append([str(p['ID'])+'/'+str(p.get('PARENT_ID')),p['OPERATION']+' '+(p.get('OPTIONS') or ''),str(p.get('OBJECT_NAME') or ''),p.get('CARDINALITY'),str(s.get('LAST_OUTPUT_ROWS'))+'/'+str(s.get('LAST_STARTS')),p.get('TEMP_SPACE'),s.get('LAST_TEMPSEG_SIZE'),flags])
        note+='예상과 실제를 구분합니다. 실제 통계는 미수집/NULL일 수 있고 마지막 실행이 이번 비교였는지는 미확인입니다. 적응형 계획의 starts=0 연산을 실제 실행으로 세지 않습니다. PK번호는 인덱스 페이지의 열 순서이며 조건 문자열에 열명이 있는지만 표시합니다(완전한 의미 검증 아님). 누적/중첩 연산시간을 합하지 않습니다.'
    elif name=='TEMP':
        rows=[['instance / 접속계정','SQL_ID / TEMP생성 SQL_ID','공간','종류','현재 블록 수']]
        rows += [[str(r['INST_ID'])+' / '+r['USERNAME'],str(r.get('SQL_ID'))+' / '+str(r.get('SQL_ID_TEMPSEG')),r['TABLESPACE'],r['SEGTYPE'],r['BLOCKS']] for r in qr('current_account_temp')]
        note+='현재 접속계정 전체의 한 시점입니다. 같은 계정을 쓰는 다른 작업이 포함될 수 있어 우리 작업에 귀속하지 않습니다. 블록 크기 미조회이므로 bytes로 환산하지 않습니다. 빈 결과는 과거 TEMP=0 증명이 아닙니다. 캐시 workarea TEMP는 임시 LOB 전체 사용량을 포함하지 않습니다.'
    elif name=='상태':
        rows=[['전체',result.get('status')],['오류',str(result.get('error','없음'))]]
        rows += [[n,v['status'],','.join(v.get('codes',[])),v.get('returned_rows'),round(v.get('seconds',0),3)] for n,v in q.items()]
        rows += [['이전 비교 제외',str(r)] for r in result.get('comparison_skipped',[])]
        note+='UNAVAILABLE=권한/뷰/컬럼 미지원. TRUNCATED=제한 초과. 빈 목록·NULL은 정상/0으로 확정하지 않습니다. 생성된 DBA_READONLY_CHECK.sql은 DBA가 같은 DB/PDB에서 실행할 조회문입니다.'
    else:
        b=result.get('binding',{})
        rows=[['수집 상태',result.get('status')],['대상',str(b.get('owner'))+'.'+str(b.get('table'))],
              ['기존 적재 상태',result.get('loader_status')],['기존 state.json 보존',result.get('original_state_unchanged')],
              ['저장된 세부시간 종류',len(result.get('timing',[]))],['캐시 실행계획 후보',len(result.get('cursors',[]))],
              ['실행한 SELECT 수',result.get('queries_count',0)],['이번 DB 쓰기/DDL/실모델','0 / 0 / 0'],
              ['과거 비교의 TEMP 최대치','미측정 — 사후 조회로 복원 보장 불가'],['결과 파일',result.get('output')]]
        if result.get('error'):rows.append(['중단',str(result['error'])])
        note+='COLLECTED도 SQL 최적화/적재완료 판정이 아닙니다. SHOW_SQL_CHECK("시간"/"인덱스"/"계획"/"TEMP"/"상태"). 기존 WRITE_UNCONFIRMED·용량·unit 미측정은 그대로입니다.'
    return draw('Oracle 인덱스·조인·TEMP 확인 R1 · '+name,rows,note)


def show(name='요약', cursor=1):
    display(page(REPORT,name,cursor))


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run(explicit='',hints=()):
    global REPORT,OUTPUT
    OUTPUT=(Path.cwd()/'gold-sql-check-reports'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    REPORT={'status':'PREPARING','queries':{}}
    process=None
    try:
        path=locate(explicit,hints)
        package=Path(__file__).resolve().parent
        manifest=read(package/'MANIFEST.json')
        for name,sha in manifest['files'].items():
            code=(package/name).resolve(strict=True)
            if package not in code.parents or hashlib.sha256(code.read_bytes()).hexdigest()!=sha:raise ValueError('DIAGNOSTIC_CODE_CHANGED')
        write(OUTPUT/'config.json',{'comparison_path':str(path)})
        env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
        env['PYTHONPATH']=os.pathsep.join([str(package)]+[s for s in sys.path if isinstance(s,str)])
        with (OUTPUT/'worker.log').open('x') as log:
            process=subprocess.Popen([sys.executable,'-u',str(package/'g19sql_worker.py'),str(OUTPUT/'config.json'),str(OUTPUT)],stdout=log,stderr=subprocess.STDOUT,env=env)
            start=time.monotonic();override=None
            try:
                while process.poll() is None:
                    current=read(OUTPUT/'worker-result.json') if (OUTPUT/'worker-result.json').exists() else {}
                    active=current.get('active') or {}
                    display(draw('인덱스·조인·TEMP 읽기 전용 확인',[[active.get('name','기존 결과·코드 결속 확인'),current.get('queries_count',0),round(time.monotonic()-start,1)]],'Oracle SELECT만 수행합니다.'))
                    if time.monotonic()-start>280 or (active and time.time()-active['started_epoch']>45):
                        override='CLIENT_TIMEOUT_REMOTE_SELECT_UNCONFIRMED';break
                    time.sleep(1)
            except KeyboardInterrupt:override='USER_INTERRUPTED_REMOTE_SELECT_UNCONFIRMED'
            finally:stop(process)
        REPORT=read(OUTPUT/'worker-result.json') if (OUTPUT/'worker-result.json').exists() else {'status':'CHILD_NO_RESULT','queries':{}}
        if override:
            REPORT.update(status=override,remote_select_cancellation_confirmed=False)
        elif process.returncode:REPORT.update(status='CHILD_EXIT_UNCONFIRMED',exit_code=process.returncode)
    except Exception as exc:
        REPORT.update(status='PREPARATION_STOPPED',error=error(exc))
    finally:
        if process is not None:stop(process)
        REPORT['output']=str(OUTPUT/'SQL_CHECK.json')
        write(OUTPUT/'SQL_CHECK.json',REPORT)
    show()
    return REPORT
