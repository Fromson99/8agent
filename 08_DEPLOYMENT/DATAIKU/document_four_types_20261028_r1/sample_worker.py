"""Isolated four-format compute branch: conversion/parsing only, no SQL/index/review."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
import transport as t
import probe_runtime

PURPOSE='document-format-probe-v1'
EXTENSIONS={'.doc','.docx','.hwp','.hwpx'}


def output_paths(folder):
    root=Path(folder)/'probe-output'
    paths={'probe/'+str(p.relative_to(root)):p for p in t.files(root)} if root.exists() else {}
    if (Path(folder)/'compute.log').is_file():paths['audit/compute.log']=Path(folder)/'compute.log'
    return paths


def export_partial(folder):
    return t.pack(output_paths(folder),Path(folder)/'audit.zip',metadata={'purpose':PURPOSE,'complete':False})


def compute(root,folder,archives,parser_sha):
    import worker
    worker.verify_code(root)
    for slot,info in archives.items():
        path=folder/(slot+'.zip')
        if path.stat().st_size!=info['bytes'] or t.sha(path)!=info['sha256']:raise ValueError('INPUT_HASH')
    inputs=folder/'probe-input'
    raw=t.unpack(folder/'raw.zip',inputs,prefixes=('documents/','selection.json'),max_bytes=1024**3+1024**2)
    control=t.unpack(folder/'support.zip',folder/'probe-control',prefixes=('control.json',),max_bytes=1024**2)
    if raw['metadata'].get('purpose')!=PURPOSE or control['metadata'].get('purpose')!=PURPOSE:raise ValueError('PROBE_INPUT_PURPOSE')
    selection=t.read(inputs/'selection.json')
    rows=selection.get('documents',[])
    if len(rows)!=4 or {r.get('extension') for r in rows}!=EXTENSIONS:raise ValueError('PROBE_FOUR_TYPES_REQUIRED')
    expected={'selection.json'}
    for row in rows:
        if row['status']=='SELECTED':
            name='documents/sample'+row['extension'];expected.add(name)
            path=t.checked(inputs,name)
            if row.get('file')!='sample'+row['extension'] or path.stat().st_size!=row['bytes'] or t.sha(path)!=row['sha256']:
                raise ValueError('PROBE_SELECTED_SOURCE_CHANGED')
        elif row['status'] not in {'NOT_FOUND','TOO_LARGE'}:raise ValueError('PROBE_INPUT_STATUS')
    if set(raw['files'])!=expected:raise ValueError('PROBE_EXTRA_INPUT')
    output=folder/'probe-output';output.mkdir()
    summary={'purpose':PURPOSE,'status':'RUNNING','snapshot_sha256':selection['snapshot_sha256'],
             'documents':[],'notes':selection.get('notes',[]),'application_review_calls':0,
             'parser_model_calls':'NOT_COUNTED','sql_writes':False,'indexing':False}
    t.write(output/'selection.json',selection);t.write(output/'summary.json',summary)
    sys.path[:0]=[str(root/'02_BACKEND'),str(root)]
    os.environ.update(GENOS_PREPROCESSOR_TRANSPORT='pod',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
    from lawrag.core import genos_pod as pod,genos_preprocessor as wire
    from lawrag.pipeline.raw_preprocess import pdf_check
    with probe_runtime.use(root,folder,parser_sha) as origin:
        summary['configuration']=origin
        for row in rows:
            item={**row,'conversion':'NOT_RUN','parsing':'NOT_RUN'};summary['documents'].append(item)
            if row['status']!='SELECTED':t.write(output/'summary.json',summary);continue
            directory=output/row['extension'][1:];directory.mkdir()
            source=inputs/('documents/sample'+row['extension']);started=time.monotonic()
            try:
                item.update(status='RUNNING',conversion='RUNNING');t.write(output/'summary.json',summary)
                result,receipt=pod.convert(source,folder/('conversion-'+row['extension'][1:]))
                shutil.copyfile(result,directory/'result.pdf');t.write(directory/'conversion.json',receipt)
                item.update(conversion='PASS',pages=pdf_check(directory/'result.pdf'),parsing='RUNNING');t.write(output/'summary.json',summary)
                settings=pod.Settings.from_env()
                with wire.using(settings,directory/'parser-evidence'):
                    document,receipt=pod.parse(directory/'result.pdf',settings)
                t.write(directory/'parsed.docling.json',document.model_dump(mode='json'));t.write(directory/'parse-receipt.json',receipt)
                data=json.loads((directory/'parser-evidence'/receipt['request_id']/'response.json').read_text())['data']
                (directory/'parsed.txt').write_text(data['full_text'],encoding='utf-8')
                if t.sha(source)!=row['sha256']:raise ValueError('PROBE_ORIGINAL_CHANGED')
                item.update(status='PASS',parsing='PASS',text_characters=len(data['full_text']),tables=len(document.tables))
            except Exception as exc:
                item['status']='FAILED';item['error_type']=type(exc).__name__
                if item['conversion']=='RUNNING':item['conversion']='FAILED'
                else:item['parsing']='FAILED'
                (directory/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
                conversion=folder/('conversion-'+row['extension'][1:])/'conversion.json'
                if conversion.is_file():shutil.copyfile(conversion,directory/'conversion.json')
                print('PROBE_FAILED',row['extension'],type(exc).__name__,flush=True)
            finally:
                item['elapsed_seconds']=round(time.monotonic()-started,3)
                item['original_unchanged']=t.sha(source)==row['sha256']
                t.write(output/'summary.json',summary)
                print('PROBE',row['extension'],item['conversion'],item['parsing'],flush=True)
    summary['status']='PASS' if all(r['status']=='PASS' for r in summary['documents']) else 'COMPLETED_WITH_FAILURE_OR_MISSING'
    summary['code_sha256']=t.sha(root/'CODE_PINS.json');t.write(output/'summary.json',summary)
    worker.verify_code(root)
    t.pack(output_paths(folder),folder/'result.zip',metadata={'purpose':PURPOSE,'complete':True,'code_sha256':summary['code_sha256']})


if __name__=='__main__':
    compute(Path(__file__).resolve().parent,Path(sys.argv[1]),json.loads(sys.argv[2]),sys.argv[3])
