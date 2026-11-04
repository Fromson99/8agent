"""Immutable content addressed work JSON, local or Dataiku managed-folder streams.

No S3 HEAD/CAS claim: mutable workflow ownership lives in the SQL transaction.
Identical keys encode identical bytes; an existing different body fails closed.
"""
import io,json,re
from pathlib import Path
from ..contracts import digest
from ..legal_agent.errors import ContractError
MAX_BYTES=2_000_000

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def path_for(key):
    if not re.fullmatch('[0-9a-f]{64}',key):raise ContractError('work content key')
    return 'objects/'+key+'.json'

class LocalFolderStore:
    def __init__(self,root):self.root=Path(root)
    def put(self,value):
        raw=encode(value);key=digest(value)
        if len(raw)>MAX_BYTES:raise ContractError('work object too large')
        p=self.root/path_for(key);p.parent.mkdir(parents=True,exist_ok=True)
        try:
            with p.open('xb') as f:f.write(raw);f.flush()
        except FileExistsError:pass
        if p.read_bytes()!=raw:raise ContractError('work object changed')
        return key
    def get(self,key):
        with (self.root/path_for(key)).open('rb') as f:raw=f.read(MAX_BYTES+1)
        return decode(key,raw)

class DataikuFolderStore:
    def __init__(self,folder):self.folder=folder
    def put(self,value):
        raw=encode(value);key=digest(value)
        if len(raw)>MAX_BYTES:raise ContractError('work object too large')
        # Same content-key can be safely uploaded by two writers; SQL owns CAS.
        self.folder.upload_stream(path_for(key),io.BytesIO(raw))
        if self.get(key)!=value:raise ContractError('managed folder write verification')
        return key
    def get(self,key):
        with self.folder.get_download_stream(path_for(key)) as f:raw=f.read(MAX_BYTES+1)
        return decode(key,raw)

def decode(key,raw):
    if len(raw)>MAX_BYTES:raise ContractError('work object too large')
    value=json.loads(raw)
    if digest(value)!=key:raise ContractError('work object hash mismatch')
    return value
