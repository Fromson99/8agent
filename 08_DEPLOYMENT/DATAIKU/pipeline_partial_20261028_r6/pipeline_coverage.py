"""Verified coverage metadata accompanies Dataiku's structured/load receipts."""
import csv,hashlib,io,json,sqlite3,zipfile
from pathlib import Path

VERSION='dataiku-partial-structure-v1'


def summary(value):
    return {k:value[k] for k in ('schema_version','coverage','selected_count','omitted_count','attempted_count','original_structure_ok')}


def validate(value):
    if value.get('schema_version')!=VERSION or value.get('coverage') not in {'PARTIAL','COMPLETE'}:raise ValueError('RETURN_COVERAGE_SCHEMA')
    for key in ('selected_count','omitted_count','attempted_count'):
        if type(value.get(key)) is not int or value[key]<0:raise ValueError('RETURN_COVERAGE_COUNT')
    selected=value['selected_document_ids'];omitted=value['omitted_documents']
    omitted_ids=[r['document_id'] for r in omitted]
    if (value['selected_count']<1 or len(selected)!=len(set(selected)) or len(omitted_ids)!=len(set(omitted_ids))
        or set(selected)&set(omitted_ids) or value['selected_count']!=len(selected) or value['omitted_count']!=len(omitted)
        or value['attempted_count']!=len(selected)+len(omitted)
        or (value['coverage']=='PARTIAL')!=bool(omitted)
        or type(value.get('original_structure_ok')) is not bool
        or value['original_structure_ok']!=not_omitted(omitted)):
        raise ValueError('RETURN_COVERAGE_COUNT')
    for r in omitted:
        if r['selection']=='INPUT_FAILED':continue
        if r['selection']!='SELECTED' or r['phases']['structure']['state']!='FAILED':raise ValueError('RETURN_OMISSION_STATE')
    return value


def not_omitted(rows):return not bool(rows)


def read(archive,expected_code):
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('RETURN_DUPLICATE')
        if z.getinfo('TRANSPORT.json').file_size>16*1024**2:raise ValueError('RETURN_MANIFEST_SIZE')
        m=json.loads(z.read('TRANSPORT.json'));meta=m['metadata']
        if meta.get('code_sha256')!=expected_code:raise ValueError('RETURN_CODE_BINDING')
        blobs={}
        for name in ('pipeline-coverage.json','excluded-documents.csv'):
            path='audit/'+name;info=z.getinfo(path)
            if info.file_size>16*1024**2:raise ValueError('RETURN_COVERAGE_SIZE')
            raw=z.read(path);declared=m['files'][path]
            if len(raw)!=declared['bytes'] or hashlib.sha256(raw).hexdigest()!=declared['sha256']:raise ValueError('RETURN_COVERAGE_HASH')
            blobs[name]=raw
        value=validate(json.loads(blobs['pipeline-coverage.json']))
        if meta.get('coverage')!=summary(value):raise ValueError('RETURN_COVERAGE_BINDING')
        return value,blobs


def verify_generation(generation,value):
    with sqlite3.connect((Path(generation)/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        actual={r[0] for r in db.execute('SELECT document_id FROM document')}
    if actual!=set(value['selected_document_ids']):raise ValueError('RETURN_GENERATION_COVERAGE')


def display(value):
    label='일부 문서 제외' if value['coverage']=='PARTIAL' else '전체 문서 완료'
    print('처리 범위: '+label+' | 성공 '+str(value['selected_count'])+' | 보류 '+str(value['omitted_count']),flush=True)
