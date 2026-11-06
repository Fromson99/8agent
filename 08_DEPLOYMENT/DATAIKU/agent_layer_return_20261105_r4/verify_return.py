"""Result transfer failure boundaries, using the sealed DSS download function."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
import zipfile

HERE=Path(__file__).resolve().parent

def check():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        with zipfile.ZipFile(HERE/'DATAIKU_AGENT_FLOW_R4.zip') as z:z.extractall(root/'flow')
        sys.path.insert(0,str(root/'flow'))
        from dataiku_return import download
        raw=secrets.token_bytes(1100000)
        receipt={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        state={'deadline':time.time()+60,'auth':{'handle':'fixture'}}
        calls=[]
        class Remote:
            def call(self,op,**args):
                assert op=='READ' and args['kind']=='result'
                offset=args['offset'];calls.append(offset)
                data=raw[offset:offset+1024**2]
                return {'offset':offset,'bytes':len(data),'total_bytes':len(raw),
                        'content':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()}
        remote=Remote()
        folder=root/'resume';folder.mkdir()
        (folder/'genos-result.partial').write_bytes(raw[:17003])
        result=download(remote,state,receipt,folder)
        assert result.read_bytes()==raw and calls==[17003,17003+1024**2]
        n=len(calls);assert download(remote,state,receipt,folder)==result and len(calls)==n
        cases=['partial_download_resumes_exact_offset','completed_download_reused_without_READ']
        class Bad(Remote):
            def call(self,*a,**kw):
                row=super().call(*a,**kw);row['sha256']='0'*64;return row
        folder=root/'bad';folder.mkdir()
        try:download(Bad(),state,receipt,folder)
        except ValueError as exc:assert str(exc)=='RETURN_CHUNK_INVALID'
        else:raise AssertionError('tampered return chunk accepted')
        assert not (folder/'genos-result.zip').exists() and (folder/'genos-result.partial').stat().st_size==0
        cases.append('bad_chunk_digest_rejected_before_publish')
        folder=root/'whole';folder.mkdir()
        try:download(remote,state,dict(receipt,sha256='0'*64),folder)
        except ValueError as exc:assert str(exc)=='RETURN_ARCHIVE_HASH'
        else:raise AssertionError('bad whole digest accepted')
        assert not (folder/'genos-result.zip').exists()
        cases.append('whole_result_digest_rejected_before_publish')
        folder=root/'deadline';folder.mkdir()
        n=len(calls)
        try:download(remote,dict(state,deadline=time.time()-1),receipt,folder)
        except ValueError as exc:assert str(exc)=='ORIGINAL_JOB_DEADLINE_EXCEEDED'
        else:raise AssertionError('expired deadline accepted')
        assert len(calls)==n
        cases.append('original_deadline_blocks_new_READ')
        return {'status':'PASS','cases':cases}

if __name__=='__main__':print(json.dumps(check(),indent=2))
