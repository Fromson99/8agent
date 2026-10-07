"""Low-impact, stdlib-only navigation diagnostics. Never modify/signal the build."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def process(pid):
    path=Path('/proc')/str(pid)
    try:
        raw=(path/'stat').read_text(); fields=raw[raw.rfind(')')+2:].split()
        io={}
        try:
            for line in (path/'io').read_text().splitlines():
                k,v=line.split(':',1);io[k]=int(v.strip())
        except (OSError,ValueError):pass
        try:wchan=(path/'wchan').read_text().strip()
        except OSError:wchan='unavailable'
        return dict(pid=pid,start_ticks=int(fields[19]),state=fields[0],ppid=int(fields[1]),
                    cpu_ticks=int(fields[11])+int(fields[12]),io=io,wchan=wchan)
    except (OSError,ValueError,IndexError):return None

def discover(dev, run):
    found=[]
    scripts={dev/'06_TOOLS/OFFLINE/genos_reindex_runner.py',dev/'06_TOOLS/OFFLINE/genos_optimized_rebuild.py'}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if path.stat().st_uid!=os.getuid():continue
            argv=[x.decode(errors='replace') for x in (path/'cmdline').read_bytes().split(b'\0') if x]
            if not any(Path(x).is_absolute() and Path(x).resolve() in scripts for x in argv):continue
            if 'build' not in argv:continue
            if argv[argv.index('--run-id')+1]!=run:continue
            if Path(argv[argv.index('--dev')+1]).resolve()!=dev:continue
            value=process(int(path.name))
            if value:found.append(value)
        except (OSError,ValueError,IndexError):continue
    return found

def database_paths(data, run, identities):
    root=(data/'TERM_RELEASES'/run).resolve(); paths=set()
    for row in identities:
        try:
            for fd in (Path('/proc')/str(row['pid'])/'fd').iterdir():
                try:
                    p=fd.resolve()
                    if p.is_relative_to(root) and p.name=='navigation.sqlite':paths.add(p)
                except OSError:pass
        except OSError:pass
    for pattern in ('reindex/.baseline-*/generation/navigation/navigation.sqlite',
                    'reindex/baseline/generation/navigation/navigation.sqlite',
                    'reindex/baseline/audit/navigation/navigation.sqlite'):
        for path in root.glob(pattern):
            if path.resolve().is_relative_to(root):paths.add(path.resolve())
    return sorted(paths)

def sizes(paths):
    result={}
    for path in paths:
        for suffix in ('','-journal','-wal','-shm'):
            p=Path(str(path)+suffix)
            try:result[str(p)]=p.stat().st_size
            except OSError:pass
    return result

def log_status(data,run):
    root=data/'LOGS'/run; rows=[]
    for pattern in ('reindex-only-r8/*/run.log','reindex-only-r9/*/run.log'):
        for p in root.glob(pattern):
            try:
                with p.open('rb') as f:
                    f.seek(max(0,p.stat().st_size-128000));lines=f.read().decode(errors='replace').splitlines()
                sql=[];phase=None;docs=None
                for line in lines:
                    m=re.search(r'NAVIGATION glossary-evidence\.sql-(\d+) elapsed=([\d.]+)s(?: thread_cpu=([\d.]+)s)?',line)
                    if m:sql.append(dict(sql_number=int(m[1]),seconds=float(m[2]),thread_cpu_seconds=float(m[3]) if m[3] else None))
                    m=re.search(r'NAVIGATION ([a-z0-9_.-]+) elapsed=',line)
                    if m:phase=m[1]
                    m=re.search(r'indexed_documents=(\d+|unknown)/(\d+)',line)
                    if m:docs=dict(completed=m[1],total=int(m[2]))
                    if 'fulltext-index-only' in line and 'START' in line:phase='fulltext-index-only'
                rows.append(dict(log_path=str(p),mtime=p.stat().st_mtime,last_phase=phase,
                                 last_completed_sql=sql[-1] if sql else None,completed_sql_in_tail=sql,documents=docs))
            except OSError:pass
    return sorted(rows,key=lambda x:x['mtime'],reverse=True)

def sql_statements(source):
    tree=ast.parse(source.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LinkProjector')
    ctor=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    finish=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='finish')
    schema=next(ast.literal_eval(n.args[0]) for n in ast.walk(ctor) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr=='executescript' and n.args)
    queries=[]
    for n in ast.walk(finish):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='execute' and n.args:
            try:q=ast.literal_eval(n.args[0])
            except (ValueError,TypeError):continue
            if isinstance(q,str):queries.append((n.lineno,q))
    return schema,sorted(queries)

def offline_plans(dev):
    source=dev/'02_BACKEND/semantic_runtime/term_links.py'
    schema,queries=sql_statements(source)
    db=sqlite3.connect(':memory:')
    try:
        db.executescript(schema)
        db.execute('CREATE TABLE occurrence(term_id TEXT,source_id TEXT,PRIMARY KEY(term_id,source_id))')
        rows=[]
        for seq,(line,sql) in enumerate(queries,1):
            try:
                if sql.startswith(('CREATE TEMP TABLE','CREATE INDEX','DROP TABLE')):
                    db.execute(sql);plan=['DDL in empty in-memory schema only']
                else:plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+sql)]
                rows.append(dict(static_sql_sequence=seq,line=line,sql=sql,plan=plan))
            except sqlite3.Error as e:rows.append(dict(static_sql_sequence=seq,line=line,error=str(e)))
        return dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),sqlite_version=sqlite3.sqlite_version,
                    scope='installed code / empty in-memory schema; no field build mutation, no SQL time benchmark',queries=rows)
    finally:db.close()

def inspect_database(path):
    """No row counts, integrity_check, ANALYZE, checkpoints or data reads."""
    wal=Path(str(path)+'-wal')
    if wal.exists() and wal.stat().st_size:
        return dict(path=str(path),status='SKIPPED_ACTIVE_WAL',reason='avoid creation/access changes to shared WAL metadata')
    deadline=time.monotonic()+.3
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
    try:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA busy_timeout=100')
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        indexes={}
        for table in ('link_occurrence','occurrence_evidence','link_catalogue','occurrence'):
            indexes[table]=[dict(name=r[1],unique=bool(r[2]),partial=bool(r[4]),
                                columns=[c[2] for c in db.execute('PRAGMA index_info("'+r[1].replace('"','""')+'")')])
                            for r in db.execute('PRAGMA index_list("'+table+'")')]
        sql="UPDATE link_occurrence SET status='HELD',reason='NO_ACCEPTED_CATALOGUE_CANDIDATE' WHERE status='ACCEPTED' AND NOT EXISTS(SELECT 1 FROM occurrence_evidence e WHERE e.occurrence_id=link_occurrence.id AND e.status='ACCEPTED')"
        plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+sql)]
        return dict(path=str(path),status='READABLE',indexes=indexes,sql9_plan=plan,
                    page_size=db.execute('PRAGMA page_size').fetchone()[0],
                    page_count=db.execute('PRAGMA page_count').fetchone()[0],
                    note='metadata and EXPLAIN only; UPDATE was NOT executed')
    except sqlite3.Error as e:return dict(path=str(path),status='UNAVAILABLE',error=str(e))
    finally:db.close()

def inspect_bounded(path):
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--inspect-db',str(path)],
                              capture_output=True,text=True,timeout=2)
        if result.returncode==0:return json.loads(result.stdout)
        return dict(path=str(path),status='UNAVAILABLE',error=result.stderr[-500:])
    except (subprocess.TimeoutExpired,ValueError,OSError):return dict(path=str(path),status='TIMEOUT_OR_UNAVAILABLE')

def main():
    if len(sys.argv)==3 and sys.argv[1]=='--inspect-db':
        try:print(json.dumps(inspect_database(Path(sys.argv[2]))))
        except OSError as e:print(json.dumps(dict(status='UNAVAILABLE',error=str(e))))
        return
    parser=argparse.ArgumentParser()
    parser.add_argument('--dev',type=Path,required=True);parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--run-id',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=7);parser.add_argument('--interval',type=float,default=5)
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',args.run_id):parser.error('Invalid run ID')
    if not 2<=args.samples<=25 or not 1<=args.interval<=10:parser.error('samples 2..25, interval 1..10')
    args.dev=args.dev.resolve();args.data_root=args.data_root.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    try:os.nice(10)
    except OSError:pass
    print('DIAGNOSTIC START: read-only, no signals, no large table scans; Python',sys.version.split()[0],flush=True)
    identities=discover(args.dev,args.run_id)
    print('BUILD PIDS:',[r['pid'] for r in identities],'selected run:',args.run_id,flush=True)
    samples=[];previous={};last=time.monotonic();hz=os.sysconf('SC_CLK_TCK')
    paths=database_paths(args.data_root,args.run_id,identities)
    for number in range(args.samples):
        if number:time.sleep(args.interval)
        now=time.monotonic();rows=[]
        for identity in identities:
            value=process(identity['pid'])
            if not value or value['start_ticks']!=identity['start_ticks']:
                print('BUILD EXITED / PID CHANGED:',identity['pid'],flush=True);continue
            old=previous.get(value['pid']);metrics={}
            if old:
                dt=now-last
                metrics['cpu_cores_used']=round((value['cpu_ticks']-old['cpu_ticks'])/hz/dt,3)
                for k in ('rchar','wchar','read_bytes','write_bytes'):
                    if k in value['io'] and k in old['io']:metrics[k+'_per_second']=round((value['io'][k]-old['io'][k])/dt)
            rows.append({**value,'rates':metrics});previous[value['pid']]=value
            print('LIVE',number,'pid=',value['pid'],'state=',value['state'],'wait=',value['wchan'],json.dumps(metrics),flush=True)
        paths=sorted(set(paths)|set(database_paths(args.data_root,args.run_id,identities)))
        files=sizes(paths)
        print('DB BYTES:',json.dumps(files),flush=True)
        logs=log_status(args.data_root,args.run_id)
        if logs:print('LAST PHASE:',logs[0]['last_phase'],'LAST COMPLETED SQL:',logs[0]['last_completed_sql'],flush=True)
        sample=dict(time_utc=datetime.now(timezone.utc).isoformat(),processes=rows,files=files,logs=logs)
        samples.append(sample)
        with (args.output/'samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(sample,ensure_ascii=False)+'\n')
        last=now
    try:plans=offline_plans(args.dev)
    except (OSError,ValueError,StopIteration,SyntaxError) as e:plans=dict(error=type(e).__name__+': '+str(e))
    save(args.output/'code-query-plans.json',plans)
    dbs=[inspect_bounded(p) for p in paths]
    save(args.output/'db-metadata.json',dbs)
    logs=samples[-1]['logs'];latest=logs[0] if logs else None
    last_sql=latest.get('last_completed_sql') if latest else None
    evidence_active=bool(samples[-1]['processes'] and latest and
                         str(latest.get('last_phase','')).startswith('glossary-evidence'))
    summary=dict(run_id=args.run_id,dev=str(args.dev),data_root=str(args.data_root),identities=identities,
                 active_build_found=bool(samples[-1]['processes']),
                 last_log=latest,likely_next_sql=last_sql['sql_number']+1 if last_sql and evidence_active else None,
                 database_metadata=dbs,read_only=True,field_statement_confirmed=False,
                 limitations=['Heartbeat does not prove SQL progress','Next SQL is inference from last completion, not a live stack',
                              'Process read/write counters include page cache and filesystem metadata; not NFS throughput',
                              'Busy database metadata may be unavailable; no retry loop or large table scans',
                              'No document text, term labels, full argv or environment values collected'])
    save(args.output/'report.json',summary)
    lines=['선택 run: '+args.run_id,'구축 PID: '+str([r['pid'] for r in identities])]
    lines+=['최근 단계: '+str(latest.get('last_phase') if latest else '로그 확인 불가'),
            '마지막 완료 SQL: '+str(last_sql),'다음 SQL 추정: '+str(summary['likely_next_sql']),
            '현재 SQL 확정: 불가(외부 관찰; 프로세스 스택 미수집)',
            'CPU 1.0 core 전후: CPU 처리 신호 / 낮은 CPU와 I/O 대기: 저장장치 대기 후보',
            'CPU·입출력 변화 없음: 잠금/대기/종료 등 확인 필요. 단일 샘플로 확정 금지.',
            '잠긴 DB는 조회 생략. 원본 DB·구축 프로세스·코드는 변경하지 않았습니다.',
            '상세: samples.jsonl, code-query-plans.json, db-metadata.json, report.json']
    (args.output/'summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines),flush=True);print('DIAGNOSTIC DONE:',args.output,flush=True)

if __name__=='__main__':main()
