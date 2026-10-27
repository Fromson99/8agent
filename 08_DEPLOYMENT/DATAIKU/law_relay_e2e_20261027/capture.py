"""Bounded, sequential public-source capture for a user-requested example.

No model call or internal relay access. Private OC is never printed or delivered.
"""
import ast
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

import requests

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIVATE=HERE/'private_raw'
RESULTS=HERE/'evidence'


def load_oc():
    values=[s.split('=',1)[1].strip() for s in (ROOT/'.env').read_text().splitlines() if s.startswith('LAW_OC=')]
    assert len(values)==1
    raw=values[0]
    value=ast.literal_eval(raw) if raw[:1] in ('"',"'") else raw
    assert value and isinstance(value,str)
    return value


def redact(value):
    value=str(value)
    oc=load_oc()
    for s in sorted({oc,quote(oc,safe=''),quote_plus(oc)},key=len,reverse=True):value=value.replace(s,'{기관_OC}')
    return re.sub(r'(?i)(OC=)[^&\s<>"\']+',r'\1{기관_OC}',value)


def allowed(url):
    p=urlsplit(url)
    return p.scheme in ('http','https') and p.hostname in ('www.law.go.kr','law.go.kr') and p.port in (None,80,443)


def fetch(label,url,params=None,max_bytes=32*1024*1024):
    os.umask(0o077)
    PRIVATE.mkdir(exist_ok=True,mode=0o700);RESULTS.mkdir(exist_ok=True)
    report_path=RESULTS/(label+'.json')
    if report_path.exists():raise RuntimeError('Existing capture label; do not repeat request')
    report={'label':label,'started_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'external WSL public-origin request; no Dataiku or company-relay execution',
            'method':'GET','requested_url':redact(url),'params':{k:('{기관_OC}' if k=='OC' else v) for k,v in (params or {}).items()},
            'max_bytes':max_bytes,'max_redirects':4,'automatic_retries':0,'hops':[]}
    session=requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0','Accept':'*/*','Accept-Language':'ko-KR,ko;q=0.9'})
    start=time.monotonic(); raw_path=PRIVATE/(label+'.body');total_deadline=start+75
    try:
        for redirect in range(5):
            if not allowed(url):raise RuntimeError('Redirect outside allowed law.go.kr hosts')
            if time.monotonic()>total_deadline:raise TimeoutError('capture deadline exceeded')
            if redirect:time.sleep(1)
            with session.get(url,params=params,timeout=(8,20),allow_redirects=False,stream=True) as r:
                params=None
                hop={'url':redact(r.url),'status':r.status_code,'headers':{k:redact(v) for k,v in r.headers.items() if k.lower() in ('content-type','content-disposition','content-length','location','date','server')}}
                report['hops'].append(hop)
                if r.status_code in (301,302,303,307,308) and r.headers.get('Location'):
                    url=urljoin(r.url,r.headers['Location'])
                    continue
                size=0;digest=hashlib.sha256();prefix=b''
                with raw_path.open('xb') as f:
                    for block in r.iter_content(chunk_size=65536):
                        if time.monotonic()>total_deadline:raise TimeoutError('capture deadline exceeded')
                        if not block:continue
                        size+=len(block)
                        if size>max_bytes:raise RuntimeError('capture byte limit exceeded')
                        f.write(block);digest.update(block)
                        if len(prefix)<1024:prefix+=block[:1024-len(prefix)]
                report.update({'status':r.status_code,'content_type':r.headers.get('Content-Type',''),
                    'content_disposition':redact(r.headers.get('Content-Disposition','')),
                    'final_url':redact(r.url),'bytes':size,'sha256':digest.hexdigest(),
                    'first_16_bytes_hex':prefix[:16].hex(),'private_body':raw_path.name,'transport_complete':True})
                if r.status_code!=200 or 'html' in r.headers.get('Content-Type','').lower():
                    report['response_preview']=redact(prefix.decode('utf-8',errors='replace'))[:800]
                break
        else:raise RuntimeError('redirect limit exceeded')
    except Exception as exc:
        report.update({'transport_complete':False,'error_class':type(exc).__name__,'error':redact(str(exc))})
    finally:
        session.close();report['elapsed_seconds']=round(time.monotonic()-start,3)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    print(json.dumps(fetch('01_body_http','http://www.law.go.kr/DRF/lawService.do',
         {'OC':load_oc(),'target':'admrul','type':'XML','LM':'금융투자업규정'},max_bytes=16*1024*1024),ensure_ascii=False))
