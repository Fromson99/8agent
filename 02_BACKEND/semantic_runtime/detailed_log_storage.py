"""Optional NFS diagnostics, separate from Oracle legal/resume authority.

Raw capture is bounded and asynchronous; QUEUED never means durable. Diagnostic
failure cannot redispatch a model or write its payload into Oracle/local files.
Imports/migration may request an explicit durable write before their own commit.
"""
from contextlib import contextmanager
import gzip,hashlib,json,os,queue,re,threading,time,uuid
from pathlib import Path

MARKER='nfs-agent-diagnostic-v1'
_QUEUE=queue.Queue(maxsize=64)
_LOCK=threading.Lock();_WORKER=None;_BYTES=0
_VALIDATED_ROOTS=set()

def oracle_mode():return os.environ.get('DP','').strip().lower() in ('oracle','1','true')
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()

def log_roots():
    values=[os.environ.get(k,'').strip() for k in ('GENOS_DETAIL_LOG_DIR','GENOS_SHARED_LOG_DIR','GENOS_SYSTEM_LOG_DIR')]
    runtime=os.environ.get('GENOS_RUNTIME_DIR','').strip()
    if not any(values) and runtime.startswith('/nfs-root/'):values.append(runtime.rstrip('/')+'/diagnostics')
    return tuple(os.path.normpath(v) for v in values if v and os.path.isabs(v) and os.path.normpath(v)!='/')

def diagnostic_path(value):
    text=os.path.normpath(os.path.abspath(os.fspath(value)))
    return any(text==root or text.startswith(root+'/') for root in (*log_roots(),*tuple(_VALIDATED_ROOTS)))

def require_nfs(root):
    """No directory creation or Oracle/local fallback before mount validation."""
    root=Path(root)
    if not root.is_absolute() or str(root)=='/':raise OSError('NFS_DIAGNOSTICS_PATH: absolute non-root path required')
    resolved=root.resolve();mounts=[]
    decode=lambda s:re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),s)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before,after=line.split(' - ',1);mount=Path(decode(before.split()[4]))
        if resolved==mount or mount in resolved.parents:mounts.append((len(mount.parts),after.split()[0]))
    if not mounts or max(mounts)[1] not in ('nfs','nfs4','cifs'):
        raise OSError('NFS_DIAGNOSTICS_MOUNT: configured detail root is not mounted NFS/CIFS')
    _VALIDATED_ROOTS.add(str(resolved))
    return resolved

def _write(ref,raw):
    root=require_nfs(ref['root']);relative=Path(ref['relative'])
    if relative.is_absolute() or '..' in relative.parts:raise OSError('NFS_DIAGNOSTICS_REFERENCE: unsafe relative path')
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as stream:
            with gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0,compresslevel=1) as zipped:zipped.write(raw)
            stream.flush();os.fsync(stream.fileno())
        try:os.link(temp,path)
        except FileExistsError:
            with gzip.open(path,'rb') as old:
                if old.read(len(raw)+1)!=raw:raise OSError('NFS_DIAGNOSTICS_COLLISION')
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)

def _worker():
    global _BYTES
    while True:
        ref,raw=_QUEUE.get()
        try:_write(ref,raw)
        except Exception as exc:
            # Avoid logging handlers that could enqueue their own diagnostics.
            try:os.write(2,('NFS_DIAGNOSTICS_CAPTURE_FAILED '+type(exc).__name__+' '+ref['sha256']+'\n').encode())
            except OSError:pass
        finally:
            with _LOCK:_BYTES-=len(raw)
            _QUEUE.task_done()

def capture(value,*,kind,owner,ident,durable=False):
    global _WORKER,_BYTES
    raw=encoded(value);key=digest(raw);roots=log_roots()
    ref={'storage':MARKER,'kind':kind,'sha256':key,'bytes':len(raw),'capture_status':'UNCONFIGURED'}
    if not roots:
        if durable:raise OSError('NFS_DIAGNOSTICS_REQUIRED: configure an NFS log root before importing raw history')
        return ref
    relative='agent-raw-v1/'+digest(str(owner).encode())+'/'+digest(encoded([ident,kind]))+'/'+key+'.json.gz'
    ref.update(root=roots[0],relative=relative)
    if durable:
        _write(ref,raw);ref['capture_status']='DURABLE';return ref
    with _LOCK:
        limit=int(os.environ.get('GENOS_DETAIL_LOG_QUEUE_MIB','64'))*1024*1024
        if _QUEUE.full() or _BYTES+len(raw)>limit:
            ref['capture_status']='CAPTURE_CAPACITY';return ref
        if _WORKER is None:
            _WORKER=threading.Thread(target=_worker,name='genos-nfs-raw-diagnostics',daemon=True);_WORKER.start()
        ref['capture_status']='QUEUED';_BYTES+=len(raw);_QUEUE.put_nowait((ref,raw))
    return ref

def drain(timeout=10):
    until=time.monotonic()+timeout
    while _QUEUE.unfinished_tasks and time.monotonic()<until:time.sleep(.01)
    return _QUEUE.unfinished_tasks==0

def is_reference(value):return isinstance(value,dict) and value.get('storage')==MARKER

def read(ref):
    if not is_reference(ref) or not ref.get('root') or not ref.get('relative'):raise OSError('NFS_DIAGNOSTICS_UNAVAILABLE')
    if os.path.normpath(ref['root']) not in log_roots():raise OSError('NFS_DIAGNOSTICS_SCOPE: root no longer configured')
    root=require_nfs(ref['root']);path=Path(ref['relative'])
    if path.is_absolute() or '..' in path.parts:raise OSError('NFS_DIAGNOSTICS_REFERENCE')
    with gzip.open(root/path,'rb') as stream:raw=stream.read(ref['bytes']+1)
    if len(raw)!=ref['bytes'] or digest(raw)!=ref['sha256']:raise OSError('NFS_DIAGNOSTICS_HASH')
    return json.loads(raw)

def request_record(request,*,owner,ident,durable=False):
    return capture(request,kind='model-request',owner=owner,ident=ident,durable=durable)

def event_record(payload,*,owner,ident,durable=False):
    if not isinstance(payload,dict):return payload
    diagnostic=payload.get('diagnostics')
    if not isinstance(diagnostic,dict) or not any(k in diagnostic for k in ('traceback','error_message')):return payload
    ref=capture(diagnostic,kind='event-diagnostics',owner=owner,ident=ident,durable=durable)
    result={**payload,'diagnostics':{k:v for k,v in diagnostic.items() if k not in ('traceback','error_message')}}
    result['diagnostics']['detail_ref']=ref
    if isinstance(result.get('error'),str):result['error']=diagnostic.get('error_code') or diagnostic.get('error_type') or 'DIAGNOSTIC_ERROR'
    return result

def expand_attempt(value):
    """Diagnostic readers only. Core recovery uses the Oracle structured reply."""
    result=dict(value);request=result.get('request')
    if is_reference(request):
        result['diagnostic_request']=request
        try:result['request']=read(request)
        except OSError:result['raw_request_unavailable']=True
    ref=(result.get('receipt') or {}).get('diagnostic_response')
    if is_reference(ref):
        try:result['response']=read(ref)
        except OSError:result['raw_response_unavailable']=True
    return result

def response_record(response,*,owner,ident,durable=False):
    if response is None:return None,None
    ref=capture(response,kind='model-response',owner=owner,ident=ident,durable=durable)
    if not isinstance(response,dict) or not isinstance(response.get('body_json'),dict):
        # Unit adapters may return the structured proposal directly.
        value=response if isinstance(response,dict) and not any(k in response for k in ('stream_events','body_json','raw_body','reasoning')) else {}
        return value,ref
    body=response['body_json'];choices=[]
    for choice in body.get('choices') or []:
        if not isinstance(choice,dict):continue
        message=choice.get('message') or {};saved={}
        content=message.get('content')
        if isinstance(content,str):
            try:structured=json.loads(content)
            except (ValueError,TypeError):structured=None
            if isinstance(structured,(dict,list)):saved['content']=content
        calls=[]
        for call in message.get('tool_calls') or []:
            function=call.get('function') or {}
            try:arguments=json.loads(function.get('arguments',''))
            except (ValueError,TypeError):continue
            if isinstance(arguments,(dict,list)):calls.append({k:call[k] for k in ('id','type','function') if k in call})
        if calls:saved['tool_calls']=calls
        choices.append({**{k:choice[k] for k in ('index','finish_reason') if k in choice},'message':saved})
    result={k:response[k] for k in ('status_code','acceptance','retry_after','schema_projection','stream_complete','body_sha256','response_bytes') if k in response}
    result['body_json']={**{k:body[k] for k in ('model','usage') if k in body},'choices':choices}
    return result,ref
