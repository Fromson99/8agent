"""Sidecar diagnostics: preserve exception identity and all loader write semantics."""
import functools
import json
import os
from pathlib import Path
import re
import threading
import time
import traceback


def safe_message(exc):
    message = str(exc)
    message = message.replace('\\r\\n','\n').replace('\\n','\n').replace('#n','\n')
    # A source literal can itself contain ORA-looking text. Remove a labelled SQL
    # dump before extracting codes, but PL/SQL: is part of the actual error.
    message = re.split(r'(?i)(?<![A-Z0-9_/])(?:query|statement|sql|parameters|binds|payload|request body)\s*[:=]', message)[0]
    # SQL text/bind payloads are not an error explanation. Preserve Oracle messages only.
    oracle = re.findall(r'(?:ORA|PLS)-\d{5}:[^\r\n]*', message)
    if oracle:
        message = '\n'.join(oracle)
    message = re.sub(r"'(?:''|[^'])*'", "'[REDACTED]'", message)
    message = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+',r'\1[REDACTED]',message)
    message = re.sub(r'(?i)((?:password|token|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+',r'\1[REDACTED]',message)
    for key, value in os.environ.items():
        if re.search(r'(?i)(password|token|secret|api.?key|embed_key)', key) and len(value) >= 6:
            message = message.replace(value, '[REDACTED]')
    if len(message) > 32768:
        message = message[:32768]+'\n[오류 메시지 32KiB 초과: 초과분 생략]'
    return message


def event(exc, context=None):
    chain, seen, current = [], set(), exc
    while current is not None and id(current) not in seen and len(chain) < 16:
        seen.add(id(current))
        chain.append({'type':type(current).__name__, 'message':safe_message(current)})
        current = current.__cause__ or current.__context__
    frames = [{'file':Path(f.filename).name,'line':f.lineno,'function':f.name}
              for f in traceback.extract_tb(exc.__traceback__)]
    return {'phase':'DIAGNOSTIC_ERROR','time':time.time(),'context':context or {},
            'causes':chain,'frames':frames}


def banner(value):
    context=value.get('context', {})
    lines=['========== 실행 오류: 중단됨 ==========',
           '단계: '+str(context.get('stage','실행 준비/기타')),
           '테이블: '+str(context.get('table','미확인')),
           '묶음 행 수: '+str(context.get('batch_rows','해당 없음'))]
    for cause in value.get('causes', []):
        lines.append(cause['type']+': '+cause['message'])
    codes=' '.join(c.get('message','') for c in value.get('causes',[]))
    if 'ORA-01691' in codes:
        lines.append('의미: 해당 테이블스페이스에서 LOB 세그먼트 확장 공간 할당 실패.')
    lines.append('후속 단계 중지. 실패한 묶음은 결과 확인 전 완료로 계산하지 않습니다.')
    return '\n'.join(lines)


def install(loader, output):
    """Wrap diagnostics only: same SQL, arguments, exception object and return value."""
    local=threading.local()
    output=Path(output)
    def report(exc, context):
        value=event(exc,context)
        try:
            with output.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(value,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
        except OSError as log_error:
            value['diagnostic_log_error']=type(log_error).__name__
        print(json.dumps(value,ensure_ascii=False),flush=True)
        return value
    original_batch=loader.Job.batch
    @functools.wraps(original_batch)
    def batch(job,key,rows,*args,**kwargs):
        previous=getattr(local,'context',{})
        local.context={'stage':'VERIFY' if kwargs.get('verify_only') else 'LOAD',
                       'table':job.contract.table(key),'batch_rows':len(rows)}
        try:
            return original_batch(job,key,rows,*args,**kwargs)
        finally:
            local.context=previous
    loader.Job.batch=batch
    for name in ('query','block'):
        original=getattr(loader.Database,name)
        def wrapper(original=original,name=name):
            @functools.wraps(original)
            def call(db,sql,*args,**kwargs):
                try:
                    return original(db,sql,*args,**kwargs)
                except BaseException as exc:
                    context=dict(getattr(local,'context',{}) or getattr(db,'_gold_context',{}))
                    context.setdefault('stage','DB_'+name.upper())
                    tables=re.findall(r'(?i)\b(?:INTO|FROM|UPDATE|TABLE|ON)\s+([A-Z][A-Z0-9_$#]*\.[A-Z][A-Z0-9_$#]*)',sql)
                    if tables:context.setdefault('table',tables[0])
                    report(exc,context)
                    raise
            return call
        setattr(loader.Database,name,wrapper())
    return report
