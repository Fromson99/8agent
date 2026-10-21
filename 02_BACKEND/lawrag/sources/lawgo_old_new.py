"""Optional oldAndNew collector; metadata-bound aid, never a mapping oracle."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

GUIDE='https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=oldAndNewInfoGuide'


def parse(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('oldAndNew XML external entities forbidden')
    root=ET.fromstring(raw)
    def section(tag):
        node=root.find('.//'+tag)
        return {x.tag:(x.text or '').strip() for x in node} if node is not None else {}
    return {'source':'lawgo.oldAndNew','raw_sha256':hashlib.sha256(raw).hexdigest(),
        'exists':root.findtext('.//신구법존재여부','').strip(),
        'old':section('구조문_기본정보'),'new':section('신조문_기본정보'),
        'old_articles':[ET.tostring(x,encoding='unicode') for x in root.findall('.//구조문목록/조문')],
        'new_articles':[ET.tostring(x,encoding='unicode') for x in root.findall('.//신조문목록/조문')],
        'mapping_certified':False,'guide':GUIDE}


def bind(value,old_metadata,new_metadata):
    """Expected metadata must come from captured actual old/new body responses."""
    if value['exists']=='N':return {**value,'version_bound':False,'status':'UNAVAILABLE'}
    fields=('법령ID','법령일련번호','시행일자','공포일자')
    for side,expected in [('old',old_metadata),('new',new_metadata)]:
        for key in fields:
            if not expected.get(key) or str(value[side].get(key))!=str(expected[key]):
                raise ValueError('oldAndNew actual body/version mismatch: '+side+'/'+key)
    return {**value,'version_bound':True,'status':'AUXILIARY_ONLY'}


def collect(fetch,*,oc,mst,output,old_metadata,new_metadata):
    """fetch is the existing approved HttpClient / relay byte fetch callable.

    No invented relay address, API credential or fallback endpoint. Call after
    both immutable body versions have been collected by the normal batch.
    """
    if not isinstance(mst,str) or not mst.isdigit() or not oc:raise ValueError('explicit OC and MST required')
    url='https://www.law.go.kr/DRF/lawService.do?'+urlencode({'OC':oc,'target':'oldAndNew','MST':mst,'type':'XML'})
    raw=fetch(url)
    if not isinstance(raw,bytes):raise ValueError('collector requires exact response bytes')
    # Retain exact raw response, including errors. Never log a URL containing OC.
    out=Path(output);out.mkdir(parents=True,exist_ok=True);sha=hashlib.sha256(raw).hexdigest()
    path=out/(sha+'.xml')
    if path.exists() and path.read_bytes()!=raw:raise ValueError('raw artifact hash conflict')
    if not path.exists():path.write_bytes(raw)
    result=bind(parse(raw),old_metadata,new_metadata)
    receipt={**result,'raw_file':path.name,'requested_mst':mst}
    target=out/(sha+'.receipt.json')
    payload=json.dumps(receipt,ensure_ascii=False,indent=2)+'\n'
    if target.exists() and target.read_text()!=payload:raise ValueError('receipt conflict')
    if not target.exists():target.write_text(payload)
    return receipt
