"""Recognize only a fully recorded rejected429; it is never source delivery."""
import gzip
import hashlib
import json
import re
from common import read, sha


def rejected_429(directory, request_path):
    """Bounded raw response verification; missing/ambiguous evidence is unknown."""
    relative=str(request_path.relative_to(directory))
    match=re.fullmatch(r'model/call-([0-9]{3})-service/request\.json',relative)
    if not match:return {'status':'UNKNOWN'}
    number=int(match[1]);parent=request_path.parent
    try:
        events=[json.loads(line) for line in (directory/'physical-calls.jsonl').open()]
        ends=[e for e in events if e.get('event')=='END' and e.get('call')==number]
        if len(ends)!=1:return {'status':'UNKNOWN'}
        end=ends[0]
        if end.get('acceptance')!='KNOWN_REJECTED':return {'status':'OTHER','acceptance':end.get('acceptance')}
        receipt_path=parent/'response-receipt.json';body_path=parent/'response.json';raw_path=parent/'response-wire.bin.gz'
        receipt=read(receipt_path);body=read(body_path);stream=receipt.get('stream_receipt',{})
        if not (end.get('status')=='PROVIDER_FAILURE' and receipt.get('status_code')==429
                and receipt.get('acceptance')=='KNOWN_REJECTED' and receipt.get('stream_complete') is True
                and body==receipt.get('body_json') and body.get('error',{}).get('code')==429
                and stream.get('complete') is True and stream.get('http_complete') is True
                and end.get('stream_receipt')==stream
                and sha(raw_path)==stream.get('raw_wire_gzip_sha256')):
            return {'status':'UNKNOWN'}
        with gzip.open(raw_path,'rb') as source:
            raw=source.read(1024*1024+1)
        if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=stream.get('raw_wire_sha256'):
            return {'status':'UNKNOWN'}
        if json.loads(raw)!=body:return {'status':'UNKNOWN'}
        return {'status':'KNOWN_REJECTED_HTTP429','physical_call':number,'source_delivery':False,
            'files':{str(p.relative_to(directory)):sha(p) for p in
                (receipt_path,body_path,raw_path,directory/'physical-calls.jsonl')}}
    except (OSError,ValueError,TypeError,KeyError):return {'status':'UNKNOWN'}
