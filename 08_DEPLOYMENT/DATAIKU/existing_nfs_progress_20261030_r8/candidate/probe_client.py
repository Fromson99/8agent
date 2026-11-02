"""Dataiku notebook owns sampling, transfer, progress and permanent test reports."""
import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import time
import uuid
import zipfile
import controller as c
import selection
import transport as t
from managed_job import ManagedJob

PURPOSE='document-format-probe-v1'
PREFIX='_pipeline/document-format-probes-v1/'


class Scope:
    def __init__(self,folder):self.folder=folder
    def list_paths_in_partition(self):
        return ['/'+p.lstrip('/')[len(PREFIX):] for p in self.folder.list_paths_in_partition() if p.lstrip('/').startswith(PREFIX)]
    def get_download_stream(self,path):return self.folder.get_download_stream(PREFIX+path.lstrip('/'))
    def upload_stream(self,path,stream):return self.folder.upload_stream(PREFIX+path.lstrip('/'),stream)


def status(wire):
    h=wire.call('PROBE_HEALTH')
    if h.get('code_sha256')!=c.EXPECTED or h.get('probe_purpose')!=PURPOSE:raise ValueError('DOCUMENT_PROBE_SERVER_PATCH_REQUIRED')
    p=h.get('preprocessor') or {}
    if not p.get('ready'):
        errors=[e for e in p.get('errors',[]) if isinstance(e,str) and e.startswith('POD_')]
        print('Pod 사전 확인:', ', '.join(errors),flush=True)
        raise ValueError('POD_EXISTING_PARSER_SETUP_NOT_READY')
    return h


def upload(store,wire,state,archives,paths):
    credentials=c.auth(store.value['compute'])
    for slot in ('raw','support'):
        path=paths[slot];offset=state['received'][slot]
        with path.open('rb') as f:
            f.seek(offset)
            while offset<archives[slot]['bytes']:
                block=f.read(t.CHUNK)
                if not block:raise ValueError('SAMPLE_ARCHIVE_TRUNCATED')
                state=c.budget_call(store,wire,'PUT',**credentials,slot=slot,offset=offset,
                    content=base64.b64encode(block).decode(),sha256=hashlib.sha256(block).hexdigest())
                offset+=len(block)
                if state['received'][slot]!=offset:raise ValueError('SAMPLE_UPLOAD_OFFSET')
    return state


def collect(store,wire,state,info,kind,work):
    if type(info.get('bytes')) is not int or not 0<info['bytes']<=4*1024**3:raise ValueError('PROBE_RETURN_SIZE')
    path=work/(kind+'.zip');offset=0;digest=hashlib.sha256()
    with path.open('wb') as out:
        while offset<info['bytes']:
            block=c.read_chunk(store,wire,state,kind,offset)
            if not block or offset+len(block)>info['bytes']:raise ValueError('PROBE_RETURN_SIZE')
            out.write(block);digest.update(block);offset+=len(block)
    if digest.hexdigest()!=info['sha256']:raise ValueError('PROBE_RETURN_HASH')
    blob=store.put_blob(path)
    store.value[kind+'_blob']=blob;store.value['phase']='RESULT_SAVED' if kind=='result' else 'AUDIT_SAVED';store.save()
    return path


def publish(store,path,work,name):
    returned=work/'returned'
    manifest=t.unpack(path,returned,prefixes=('probe/','audit/'),max_bytes=4*1024**3)
    if manifest['metadata'].get('purpose')!=PURPOSE:raise ValueError('PROBE_RETURN_PURPOSE')
    if manifest['metadata'].get('complete') and manifest['metadata'].get('code_sha256')!=c.EXPECTED:raise ValueError('PROBE_RETURN_CODE')
    summary=t.read(returned/'probe/summary.json') if (returned/'probe/summary.json').is_file() else {'status':'COMPUTE_FAILED_BEFORE_DOCUMENTS','documents':[]}
    expected=store.value['selection']['documents']
    rows=summary.get('documents',[])
    if any(r['extension'] not in selection.EXTENSIONS for r in rows):raise ValueError('PROBE_RETURN_DOCUMENT')
    if len({r['extension'] for r in rows})!=len(rows):raise ValueError('PROBE_RETURN_DUPLICATE')
    for row in rows:
        original=next(r for r in expected if r['extension']==row['extension'])
        for key in ('source_name','sha256','bytes'):
            if row.get(key)!=original.get(key):raise ValueError('PROBE_RETURN_SOURCE_BINDING')
        if row.get('status')=='PASS':
            if row.get('conversion')!='PASS' or row.get('parsing')!='PASS' or not row.get('original_unchanged'):
                raise ValueError('PROBE_RETURN_FALSE_SUCCESS')
            for artifact in ('result.pdf','parsed.txt','parsed.docling.json'):
                if not (returned/'probe'/row['extension'][1:]/artifact).is_file():raise ValueError('PROBE_RETURN_OUTPUT_MISSING')
    if manifest['metadata'].get('complete') and len(rows)!=4:raise ValueError('PROBE_RETURN_INCOMPLETE')
    if manifest['metadata'].get('complete'):
        all_pass=all(r.get('status')=='PASS' for r in rows)
        if (summary.get('status')=='PASS')!=all_pass:raise ValueError('PROBE_RETURN_FALSE_SUCCESS')
    else:
        summary['status']='CANCELLED' if store.value.get('last_state')=='CANCELLED' else 'COMPUTE_FAILED'
        observed={r['extension']:r for r in rows}
        rows=[]
        for original in expected:
            row=observed.get(original['extension'],{**original,'conversion':'NOT_RUN','parsing':'NOT_RUN'})
            if row['status'] in {'SELECTED','RUNNING'}:row['status']='INTERRUPTED'
            for key in ('conversion','parsing'):
                if row.get(key)=='RUNNING':row[key]='INTERRUPTED'
            rows.append(row)
        summary['documents']=rows
    # Publish only after the returned archive and original-document binding pass.
    # Keep the raw worker summary for audit and a normalized terminal summary.
    prefix='reports/'+name
    for p in t.files(returned):
        c.r.put_file(store.folder,prefix+'/'+str(p.relative_to(returned)),p)
    c.r.put_json(store.folder,prefix+'/summary.json',summary,work)
    store.value.update(summary=summary,report_prefix=PREFIX+prefix,phase='FINISHED');store.save()
    display(summary,store.value['report_prefix'])
    return summary


def display(summary,prefix):
    print('형식 | 원문 | PDF 변환 | 파싱 | 결과',flush=True)
    for r in summary.get('documents',[]):
        print(' | '.join(str(x) for x in [r['extension'],r.get('source_name','원문 없음'),r.get('conversion','NOT_RUN'),r.get('parsing','NOT_RUN'),r['status']]),flush=True)
    print('Dataiku 결과 폴더:',prefix,flush=True)


def run(dataiku,work,name='doc_formats_20261028_r1',action='run'):
    if dataiku.default_project_key()!='LEGAL_RAG':raise ValueError('LEGAL_RAG_PROJECT_REQUIRED')
    if action not in {'run','cancel','status'}:raise ValueError('PROBE_ACTION')
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    project=dataiku.api_client().get_project('LEGAL_RAG');cfg=selection.discover(project)
    raw=dataiku.Folder(cfg['raw']);landing=dataiku.Folder(cfg['landing']);out=Scope(dataiku.Folder(cfg['structured']))
    record=selection.snapshot(landing,raw)
    variables=dataiku.get_custom_variables();wire=c.remote(variables)
    binding={'purpose':PURPOSE,'source_snapshot':record['archive_sha256'],'raw_folder':cfg['raw'],
             'service_code':c.EXPECTED,'endpoint_sha256':hashlib.sha256(wire.url.encode()).hexdigest()}
    store=ManagedJob(out,name,binding)
    if store.value.get('phase')=='FINISHED':display(store.value['summary'],store.value['report_prefix']);return store.value['summary']
    if action=='status':print(json.dumps({k:store.value.get(k) for k in ('phase','last_state','report_prefix')},ensure_ascii=False));return
    if action=='cancel':
        if 'compute' not in store.value:print('시작된 계산 없음');return
        c.budget_call(store,wire,'CANCEL',**c.auth(store.value['compute']))
        store.value['cancel_requested']=True;store.save()
        print('취소 요청 저장. 같은 RUN_NAME으로 run을 실행하면 종료 상태와 진단을 수집합니다.');return
    if store.value.get('result_blob') or store.value.get('audit_blob'):
        blob=store.value.get('result_blob') or store.value['audit_blob'];path=work/'saved.zip';store.get_blob(blob,path)
        return publish(store,path,work,name)
    health=status(wire)
    if 'raw_blob' not in store.value:
        selected=selection.pick(raw,record,work/'samples')
        t.write(work/'selection.json',selected)
        paths={'selection.json':work/'selection.json'}
        for row in selected['documents']:
            if row['status']=='SELECTED':paths['documents/'+row['file']]=work/'samples'/row['file']
        if len(paths)==1:
            summary={'status':'NO_MATCHING_DOCUMENTS','documents':selected['documents']}
            store.value.update(selection=selected,summary=summary,phase='FINISHED',report_prefix=PREFIX+'reports/'+name)
            c.r.put_json(out,'reports/'+name+'/summary.json',summary,work);store.save();display(summary,store.value['report_prefix']);return summary
        t.pack(paths,work/'raw.zip',metadata={'purpose':PURPOSE})
        t.write(work/'control.json',{'purpose':PURPOSE})
        t.pack({'control.json':work/'control.json'},work/'support.zip',metadata={'purpose':PURPOSE})
        store.value.update(selection=selected,raw_blob=store.put_blob(work/'raw.zip'),support_blob=store.put_blob(work/'support.zip'),
                           deadline=time.time()+7200,phase='SELECTED',reserved_http_calls=0);store.save()
    archives={slot:{k:store.value[slot+'_blob'][k] for k in ('bytes','sha256')} for slot in ('raw','support')}
    if 'compute' not in store.value:
        store.value.update(compute={'instance':health['instance'],'handle':uuid.uuid4().hex,'handle_token':secrets.token_hex(32),
            'code_sha256':c.EXPECTED,'parser_config_sha256':health['preprocessor']['config_sha256']},phase='OPEN_INTENT');store.save()
    state=store.value['compute']
    try:
        current=c.budget_call(store,wire,'OPEN',**c.auth(state),archives=archives,deadline=store.value['deadline']-120,purpose=PURPOSE)
        if current['state']=='RECEIVING':
            paths={slot:work/(slot+'.zip') for slot in ('raw','support')}
            for slot,path in paths.items():store.get_blob(store.value[slot+'_blob'],path)
            current=upload(store,wire,current,archives,paths)
            store.value['phase']='RUN_INTENT';store.save()
            current=c.budget_call(store,wire,'RUN',**c.auth(state))
        while current['state'] not in {'COMPLETE','FAILED','CANCELLED'}:
            store.value.update(phase='COMPUTING',last_state=current['state']);store.save()
            time.sleep(2)
            current=c.budget_call(store,wire,'POLL',**c.auth(state))
        store.value['last_state']=current['state'];store.save()
        kind='result' if current['state']=='COMPLETE' else 'audit'
        if not current.get(kind):
            if current['state']!='CANCELLED':raise ValueError('PROBE_FAILED_WITHOUT_RETURN')
            summary={'status':'CANCELLED','documents':[{**r,'status':'CANCELLED' if r['status']=='SELECTED' else r['status'],'conversion':'NOT_RUN','parsing':'NOT_RUN'} for r in store.value['selection']['documents']]}
            c.r.put_json(out,'reports/'+name+'/summary.json',summary,work)
            c.budget_call(store,wire,'CLOSE',**c.auth(state))
            store.value.update(phase='FINISHED',summary=summary,report_prefix=PREFIX+'reports/'+name);store.save();display(summary,store.value['report_prefix']);return summary
        path=collect(store,wire,state,current[kind],kind,work)
        try:c.budget_call(store,wire,'CLOSE',**c.auth(state),**{kind+'_sha256':current[kind]['sha256']})
        except Exception:
            store.value['cleanup_pending']=True;store.save();print('반환 데이터 저장 완료; 임시 핸들 정리는 미확인')
        return publish(store,path,work,name)
    except KeyboardInterrupt:
        c.budget_call(store,wire,'CANCEL',**c.auth(state));store.value['cancel_requested']=True;store.save()
        print('취소 요청됨. 같은 RUN_NAME으로 다시 실행하면 종료 확인/진단만 이어집니다.');raise
