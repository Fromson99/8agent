"""Reconcile one bound pending batch; allow only original insert-missing semantics."""
import functools
import json
import os
from pathlib import Path
import re
import time


def inspection_sql(contract,key,rows):
    """Reuse exact R1 JSON columns, empty CLOB and null comparison expressions."""
    checked=contract.validate(key,rows)
    if len(checked)!=len(rows):raise ValueError('RECOVERY_DUPLICATE_INPUT')
    sql,binds=contract.batch(key,rows,verify_only=True)
    prefix='SELECT COUNT(*) INTO n FROM '
    start=sql.index(prefix)+len(prefix)
    end=sql.index('; IF n<>:expected',start)
    clause=sql[start:end]
    source,rest=clause.split(' JOIN ',1)
    target,where=rest.split(' WHERE ',1)
    table=contract.table(key)
    if not target.startswith(table+' t ON ('):raise ValueError('RECOVERY_VERIFIER_SHAPE')
    first_pk='t.'+contract.col(key,contract.tables[key]['primary_key'][0])
    joined=source+' LEFT JOIN '+target
    columns=[n for n,c in contract.tables[key]['columns'].items() if not c['default']]
    # The original equal-expression for each column has balanced internal parentheses.
    predicates=[];depth=0;offset=0
    for index,ch in enumerate(where):
        if ch=='(':depth+=1
        elif ch==')':depth-=1
        if depth==0 and where[index+1:index+6]==' AND ':
            predicates.append(where[offset:index+1]);offset=index+6
    predicates.append(where[offset:])
    if len(predicates)!=len(columns):raise ValueError('RECOVERY_COMPARISON_SHAPE')
    names=[]
    for logical in contract.tables[key]['primary_key']:
        alias='s.c'+str(columns.index(logical))
        names.append("'"+contract.col(key,logical)+"='||SUBSTR("+alias+',1,80)')
    key_text="||','||".join(names)
    differences="||".join("CASE WHEN "+test+" THEN '' ELSE '"+contract.col(key,name)+",' END" for name,test in zip(columns,predicates))
    result='''DECLARE present_n NUMBER; matched_n NUMBER; details VARCHAR2(2000):=''; BEGIN
SELECT COUNT('''+first_pk+'''),NVL(SUM(CASE WHEN '''+first_pk+' IS NOT NULL AND '+where+''' THEN 1 ELSE 0 END),0)
INTO present_n,matched_n FROM '''+joined+''';
FOR r IN (SELECT '''+key_text+' AS row_key, '+differences+' AS fields FROM '+joined+' WHERE '+first_pk+''' IS NOT NULL AND CASE WHEN '''+where+''' THEN 0 ELSE 1 END=1 AND ROWNUM<=5) LOOP
details:=SUBSTR(details||' ['||r.row_key||' fields='||r.fields||']',1,1500);
WHILE LENGTHB(details)>1500 LOOP details:=SUBSTR(details,1,LENGTH(details)-1); END LOOP;
END LOOP;
ROLLBACK;
RAISE_APPLICATION_ERROR(-20043,'GOLD_RECONCILE_RESULT expected='||:expected||' matched='||matched_n||' missing='||(:expected-present_n)||' conflicts='||(present_n-matched_n)||'; details='||details);
EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;'''
    return result,binds


def parse_result(exc,expected):
    message=str(exc)
    codes=set(re.findall(r'(?:ORA|PLS)-\d{5}',message))
    if not codes or 'ORA-20043' not in codes or codes-{'ORA-20043','ORA-06512'}:
        raise exc
    found=re.findall(r'ORA-20043:\s*GOLD_RECONCILE_RESULT expected=(\d+) matched=(\d+) missing=(\d+) conflicts=(\d+); details=([^\r\n]*)',message)
    if not found:raise exc
    counts={tuple(map(int,r[:4])) for r in found}
    if len(counts)!=1:raise ValueError('RECOVERY_RESULT_AMBIGUOUS') from exc
    exp,matched,missing,conflicts=counts.pop()
    if exp!=expected or matched+missing+conflicts!=exp:
        raise ValueError('RECOVERY_RESULT_COUNT_MISMATCH') from exc
    # JDBC may append stack text after the native message; retain only our bounded sample.
    details=re.split(r'ORA-06512:|https?://|caused by:',found[0][4],maxsplit=1)[0].strip()
    return {'expected':exp,'matched':matched,'missing':missing,'conflicts':conflicts,'details':details}


def inspect(job,key,rows):
    from lawrag.pipeline.oracle_query_dataiku import render
    statement,binds=inspection_sql(job.contract,key,rows)
    rendered=render(statement,binds,write=True)
    # JDBC's CLOB support is a PL/SQL block. This block does SELECT + ROLLBACK only;
    # the application error is a bounded result channel, not a failed INSERT.
    job.db.calls+=1
    try:
        job.db.executor.query_to_df('SELECT 1 AS OK FROM DUAL',pre_queries=[rendered],post_queries=['ROLLBACK'])
    except Exception as exc:
        return parse_result(exc,len(rows))
    raise ValueError('RECOVERY_RESULT_MISSING')


def install(loader,path,inspector=inspect):
    original=loader.Job.batch
    path=Path(path)
    def record(phase,**fields):
        event={'phase':phase,'time':time.time(),**fields}
        # A durable receipt is required before opening the one-batch retry gate.
        with path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
        print(json.dumps(event,ensure_ascii=False),flush=True)
    @functools.wraps(original)
    def batch(job,key,rows,next_progress=None,section=None,slot=None,verify_only=False):
        pending=job.state.get('pending')
        if not pending or verify_only:
            return original(job,key,rows,next_progress=next_progress,section=section,slot=slot,verify_only=verify_only)
        job.guard()
        marker={'table':key,'rows':len(rows),'sha256':loader.digest(rows),'verify_only':verify_only,
                'section':section,'slot':slot,'next':next_progress}
        if marker!=pending:raise loader.Stop('PENDING_BATCH_BINDING_MISMATCH')
        table=job.contract.table(key)
        record('RECOVERY_CHECK_STARTED',table=table,batch_rows=len(rows),input_sha256=marker['sha256'],
               binding_sha256=loader.digest(job.state['binding']))
        result=inspector(job,key,rows)
        if (set(result)-{'expected','matched','missing','conflicts','details'} or
            any(type(result.get(k)) is not int or result[k]<0 for k in ('expected','matched','missing','conflicts')) or
            result['expected']!=len(rows) or result['matched']+result['missing']+result['conflicts']!=len(rows)):
            raise loader.Stop('RECOVERY_RESULT_INVALID')
        record('RECOVERY_CHECK_RESULT',table=table,**result)
        if result['conflicts']:
            raise loader.Stop('RECOVERY_CONTENT_CONFLICT: '+str(result['conflicts'])+'행; '+result.get('details',''))
        previous=job.retry_missing
        job.retry_missing=bool(result['missing'])
        try:
            record('RECOVERY_INSERT_MISSING' if result['missing'] else 'RECOVERY_ACK_EXISTING',table=table,
                   missing=result['missing'],matched=result['matched'],retry_scope='this exact pending batch only')
            # R1 rechecks, INSERTs only absent PKs, verifies all content, then commits.
            # A conflict arriving after inspection is still rolled back by R1.
            answer=original(job,key,rows,next_progress=next_progress,section=section,slot=slot,verify_only=verify_only)
            record('RECOVERY_COMPLETE',table=table,missing_before=result['missing'],pending_cleared=job.state.get('pending') is None)
            return answer
        except BaseException as exc:
            record('RECOVERY_FAILED',table=table,error_type=type(exc).__name__)
            raise
        finally:
            job.retry_missing=previous
    loader.Job.batch=batch
