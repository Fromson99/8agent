"""Append-only managed-folder checkpoints and streamed content-addressed results.

One active Dataiku scenario per JOB_NAME is required: managed folders have no CAS.
No credentials are printed. Job capability tokens are stored in restricted folders.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import time
import transport as t


def bounded_read(stream,limit):
    chunks=[];count=0
    while True:
        block=stream.read(min(t.CHUNK,limit+1-count))
        if not block:break
        count+=len(block)
        if count>limit:raise ValueError('CHECKPOINT_SIZE')
        chunks.append(block)
    return b''.join(chunks)


class ManagedJob:
    def __init__(self, folder, name, binding):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ValueError('JOB_NAME')
        self.folder=folder;self.prefix='_pipeline/jobs/'+name+'/';self.seq=0
        checkpoints=[]
        for path in folder.list_paths_in_partition():
            p=path.lstrip('/')
            if p.startswith(self.prefix+'checkpoint-'):
                m=re.fullmatch(re.escape(self.prefix)+r'checkpoint-(\d{10})-([0-9a-f]{64})\.json',p)
                if not m:raise ValueError('CHECKPOINT_NAME')
                checkpoints.append((int(m[1]),m[2],path))
        if checkpoints:
            seq,sha,path=max(checkpoints)
            if sum(n==seq for n,_,_ in checkpoints)!=1:raise ValueError('CONCURRENT_JOB_CHECKPOINT')
            with folder.get_download_stream(path) as f:raw=bounded_read(f,1024*1024)
            if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('CHECKPOINT_HASH')
            self.value=json.loads(raw);self.seq=seq
            if self.value['binding']!=binding:raise ValueError('JOB_BINDING_CHANGED: use a new explicit JOB_NAME')
        else:
            self.value={'binding':binding,'deadline':time.time()+7*86400,'reserved_sql_calls':0,'phase':'NEW'}
            self.save()

    def save(self):
        raw=json.dumps(self.value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>1024*1024:raise ValueError('CHECKPOINT_SIZE')
        sha=hashlib.sha256(raw).hexdigest();seq=self.seq+1
        name=self.prefix+f'checkpoint-{seq:010d}-{sha}.json'
        self.folder.upload_stream(name,io.BytesIO(raw))
        with self.folder.get_download_stream(name) as f:check=bounded_read(f,len(raw))
        if check!=raw:raise ValueError('CHECKPOINT_READBACK')
        self.seq=seq

    def put_blob(self,path):
        path=Path(path);sha=t.sha(path);size=path.stat().st_size
        remote='_pipeline/blobs/'+sha+'.zip'
        paths={p.lstrip('/') for p in self.folder.list_paths_in_partition()}
        if remote not in paths:
            with path.open('rb') as f:self.folder.upload_stream(remote,f)
        h=hashlib.sha256();count=0
        with self.folder.get_download_stream(remote) as f:
            for block in iter(lambda:f.read(t.CHUNK),b''):
                count+=len(block)
                if count>size:raise ValueError('BLOB_SIZE')
                h.update(block)
        if count!=size or h.hexdigest()!=sha:raise ValueError('BLOB_READBACK')
        return {'path':remote,'sha256':sha,'bytes':size}

    def get_blob(self,info,path):
        path=Path(path)
        if path.exists():
            if path.stat().st_size!=info['bytes'] or t.sha(path)!=info['sha256']:raise ValueError('LOCAL_BLOB_CONFLICT')
            return
        path.parent.mkdir(parents=True,exist_ok=True);partial=path.with_suffix('.restore-partial')
        if partial.is_symlink() or path.is_symlink():raise ValueError('SYMLINK_REFUSED')
        h=hashlib.sha256();count=0
        with self.folder.get_download_stream(info['path']) as src,partial.open('wb') as dst:
            for block in iter(lambda:src.read(t.CHUNK),b''):
                count+=len(block)
                if count>info['bytes']:raise ValueError('BLOB_SIZE')
                h.update(block);dst.write(block)
        if count!=info['bytes'] or h.hexdigest()!=info['sha256']:raise ValueError('BLOB_HASH')
        partial.replace(path)

    def checkpoint_client(self,job):
        job=Path(job);state=t.read(job/'client.json')
        if 'raw_blob' not in self.value:
            self.value['raw_blob']=self.put_blob(job/'RAW_INPUT.zip')
        if state['status']=='DOWNLOADED' and 'result_blob' not in self.value:
            self.value['result_blob']=self.put_blob(job/'result.zip')
        self.value['client']=state;self.value['phase']=state['status'];self.save()

    def restore(self,job):
        job=Path(job);job.mkdir(parents=True,exist_ok=True)
        if 'client' in self.value:t.write(job/'client.json',self.value['client'])
        for key,name in [('raw_blob','RAW_INPUT.zip'),('result_blob','result.zip')]:
            if key in self.value:self.get_blob(self.value[key],job/name)


class BudgetClient:
    """Reserve calls before execution; loss of local disk never resets the job budget."""
    def __init__(self,client,store,max_calls=1000000):
        self.client=client;self.store=store;self.remaining=0;self.max_calls=max_calls
        self.SQL_PATH=client.SQL_PATH;self.schema_map=client.schema_map
    def request(self,*args,**kwargs):
        from semantic_runtime.oracle_dp_io import BudgetPause
        if time.time()>=self.store.value['deadline']:raise BudgetPause('JOB_DEADLINE_EXHAUSTED')
        if not self.remaining:
            previous=self.store.value['reserved_sql_calls']
            grant=min(64,self.max_calls-previous)
            if grant<=0:raise BudgetPause('JOB_SQL_BUDGET_EXHAUSTED')
            self.store.value['reserved_sql_calls']=previous+grant
            self.store.save() # Never issue a write if the budget checkpoint is uncertain.
            self.remaining=grant
        self.remaining-=1
        return self.client.request(*args,**kwargs)
