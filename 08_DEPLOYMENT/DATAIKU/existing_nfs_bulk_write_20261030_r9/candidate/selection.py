"""Pick actual Dataiku RAW documents, at most one for each requested extension."""
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

EXTENSIONS=('.doc','.docx','.hwp','.hwpx')
LIMIT=256*1024*1024


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def load_json(folder,path,limit=64*1024*1024):
    with folder.get_download_stream(path) as f:data=f.read(limit+1)
    if len(data)>limit:raise ValueError('SOURCE_MANIFEST_TOO_LARGE')
    return json.loads(data)


def discover(project):
    candidates=[]
    for recipe in project.list_recipes():
        name=recipe.get('name','')
        if not name.startswith('LEGAL_02_STRUCTURE_GENOS_R1'):continue
        code=project.get_recipe(name).get_settings().get_code()
        tree=ast.parse(code)
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id!='run_recipe' or len(node.args)!=2:continue
            try:stage,cfg=map(ast.literal_eval,node.args)
            except (ValueError,TypeError):continue
            if stage=='structure' and isinstance(cfg,dict) and set(cfg)=={'landing','connection','raw','structured','load'}:
                if cfg['landing']!='ehA8dpVm' or not all(isinstance(x,str) and x for x in cfg.values()):continue
                candidates.append(cfg)
    unique={json.dumps(x,sort_keys=True):x for x in candidates}
    if len(unique)!=1:raise ValueError('SOURCE_FLOW_CONFIG_MISSING_OR_AMBIGUOUS')
    return next(iter(unique.values()))


def snapshot(landing,raw):
    receipt=load_json(landing,'RAW_INPUT.zip.receipt.json',1024*1024)
    if (receipt.get('archive')!='RAW_INPUT.zip' or not re.fullmatch('[0-9a-f]{64}',str(receipt.get('sha256','')))
        or type(receipt.get('bytes')) is not int or receipt['bytes']<=0):raise ValueError('SOURCE_RECEIPT_INVALID')
    prefix='snapshots/'+receipt['sha256']
    record=load_json(raw,prefix+'/manifest.json')
    if (record.get('format')!='legal-raw-s3-v1' or record.get('archive_sha256')!=receipt['sha256']
        or record.get('archive_bytes')!=receipt['bytes'] or not isinstance(record.get('files'),dict)):
        raise ValueError('SOURCE_SNAPSHOT_MISMATCH')
    for name,item in record['files'].items():
        if not name.startswith(('01_DATA/RAW/','01_DATA/INPUT_MAPPING/')):raise ValueError('SOURCE_MANIFEST_SCOPE')
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or str(p)!=name or '\\' in name:raise ValueError('SOURCE_PATH_INVALID')
        if (item.get('path')!=prefix+'/files/'+name or type(item.get('bytes')) is not int or item['bytes']<0
            or not re.fullmatch('[0-9a-f]{64}',str(item.get('sha256','')))):raise ValueError('SOURCE_OBJECT_INVALID')
    return record


def download(folder,item,target,limit=LIMIT):
    if item['bytes']>limit:raise ValueError('SAMPLE_FILE_TOO_LARGE')
    target.parent.mkdir(parents=True,exist_ok=True)
    total=0;h=hashlib.sha256()
    with folder.get_download_stream(item['path']) as src,target.open('xb') as out:
        while True:
            b=src.read(1024*1024)
            if not b:break
            total+=len(b)
            if total>item['bytes']:raise ValueError('SOURCE_OBJECT_SIZE')
            h.update(b);out.write(b)
    if total!=item['bytes'] or h.hexdigest()!=item['sha256']:raise ValueError('SOURCE_OBJECT_HASH')


def usable(name):
    p=PurePosixPath(name)
    return not p.name.startswith(('~$','.')) and p.suffix.lower() in EXTENSIONS


def pick(raw,record,work):
    """Smallest actual object per format; no synthetic substitution for missing types."""
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    rows={ext:{'extension':ext,'status':'NOT_FOUND'} for ext in EXTENSIONS}
    originals={n:v for n,v in record['files'].items() if n.startswith('01_DATA/RAW/')}
    for ext in EXTENSIONS:
        options=[(v['bytes'],n,v) for n,v in originals.items() if v['bytes']>0 and usable(n) and PurePosixPath(n).suffix.lower()==ext]
        if not options:continue
        size,name,item=min(options)
        target=work/('sample'+ext)
        if size>LIMIT:
            rows[ext].update(status='TOO_LARGE',source_name=name,bytes=size);continue
        download(raw,item,target)
        rows[ext].update(status='SELECTED',source_name=name,source_object=item['path'],
                         sha256=item['sha256'],bytes=size,file=target.name)
    # Some already-uploaded RAW snapshots retain the original inner ZIP. Inspect
    # at most eight small archives only for missing types, with no bulk extraction.
    archives=sorted((v['bytes'],n,v) for n,v in originals.items() if PurePosixPath(n).suffix.lower()=='.zip')
    scanned=0;notes=[]
    for size,name,item in archives:
        missing={e for e,r in rows.items() if r['status']=='NOT_FOUND'}
        if not missing:break
        if scanned>=8:notes.append({'status':'ZIP_SCAN_LIMIT','remaining_archives':len(archives)-scanned});break
        if size>512*1024*1024:notes.append({'status':'ZIP_TOO_LARGE','source_name':name});continue
        path=work/('archive-'+str(scanned)+'.zip');download(raw,item,path,512*1024*1024);scanned+=1
        try:
            with zipfile.ZipFile(path) as z:
                if len(z.namelist())!=len(set(z.namelist())):raise ValueError('SOURCE_ZIP_DUPLICATE')
                for ext in sorted(missing):
                    options=[i for i in z.infolist() if not i.is_dir() and i.file_size>0 and not (i.flag_bits&1) and not stat.S_ISLNK(i.external_attr>>16) and usable(i.filename) and PurePosixPath(i.filename).suffix.lower()==ext]
                    if not options:continue
                    info=min(options,key=lambda i:(i.file_size,i.filename))
                    if info.flag_bits&1 or stat.S_ISLNK(info.external_attr>>16) or not 0<info.file_size<=LIMIT:
                        notes.append({'status':'ZIP_MEMBER_UNUSABLE','source_name':name,'member':info.filename});continue
                    target=work/('sample'+ext);total=0
                    with z.open(info) as inp,target.open('xb') as out:
                        for b in iter(lambda:inp.read(1024*1024),b''):
                            total+=len(b)
                            if total>info.file_size:raise ValueError('SOURCE_ZIP_MEMBER_SIZE')
                            out.write(b)
                    if total!=info.file_size:raise ValueError('SOURCE_ZIP_MEMBER_SIZE')
                    rows[ext].update(status='SELECTED',source_name=name+'!'+info.filename,source_object=item['path'],
                                     archive_sha256=item['sha256'],member=info.filename,sha256=digest(target),bytes=total,file=target.name)
        finally:path.unlink(missing_ok=True)
    return {'version':'four-format-probe-input-v1','snapshot_sha256':record['archive_sha256'],
            'selection_policy':'smallest per extension, stable path tie-break; real RAW only',
            'documents':[rows[e] for e in EXTENSIONS],'notes':notes}
