"""Sealed R8 + frozen ADR1181 build changes only. No field deployment."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.parent/'pipeline_export_20261028_r8'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R9'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R9.zip'
OLD_CODE='f88b1426f29bc16a862a1a67c72bff8a0d15b106a84aa2ca3dc9f80f4820c084'
R7_CODE='1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
OLD_ARCHIVE='GENOS_DATAIKU_COMPUTE_20261028_R8.zip'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def edit(source,old,new):
    assert source.count(old)==1,(old,source.count(old))
    return source.replace(old,new)
def writezip(path,files):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,10,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,raw)

def main():
    with zipfile.ZipFile(BASE/OLD_ARCHIVE) as z:original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json']);assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    candidate=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1181/balanced4/candidate.json'
    meta=json.loads(candidate.read_text());assert meta['arm_id']=='balanced4' and not meta['production_loadable']
    adopted=[]
    for row in meta['revisions'][-1]['files']:
        source=ROOT/row['frozen_path'];raw=source.read_bytes();assert sha(raw)==row['snapshot_sha256']
        if source.name=='worker.py':
            payload['worker.py']=raw;adopted.append('worker.py')
        else:
            name='02_BACKEND/semantic_runtime/unit_fulltext.py'
            old=original[name].decode();new=raw.decode();lines=old.splitlines(keepends=True)
            a=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='build')
            b=next(n for n in ast.parse(new).body if isinstance(n,ast.FunctionDef) and n.name=='build')
            lines[a.lineno-1:a.end_lineno]=new.splitlines(keepends=True)[b.lineno-1:b.end_lineno]
            payload[name]=''.join(lines).encode();adopted.append(name)
    assert payload['02_BACKEND/semantic_runtime/fulltext.py']==original['02_BACKEND/semantic_runtime/fulltext.py']
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,indent=2)+'\n').encode()
    code=sha(payload['CODE_PINS.json']);writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    (HERE/'worker.py').write_bytes(payload['worker.py'])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R8.zip') as z:client={n:z.read(n) for n in z.namelist()}
    client['COMPUTE_CODE_SHA256.txt']=(code+'\n').encode()
    s=client['checkpoint_upgrade.py'].decode()
    s=edit(s,'PREVIOUS_CODES = {',"PREVIOUS_CODES = {'"+OLD_CODE+"', ")
    s=edit(s,"if previous_code == '"+R7_CODE+"':", "if previous_code in {'"+R7_CODE+"', '"+OLD_CODE+"'}:")
    s=s.replace('SEALED_R7_FIXED_SKIP_NO_MODEL_PATH','SEALED_R7_R8_FIXED_SKIP_NO_MODEL_PATH')
    s=s.replace('LOSSLESS_BLOB_EXPORT_AND_BOUNDED_ROW_WRITER','BOUNDED_FOUR_WORKER_UNIT_INDEX')
    client['checkpoint_upgrade.py']=s.encode()
    client['updater.py']=client['updater.py'].replace(b'export-r8-before.json',b'speed-r9-before.json')
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text());client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text()
    boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R8.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R8.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    boot=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot);(HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_R8_{kind}.txt').read_text().replace(oldboot,boot).replace(repr(oldboot),repr(boot))
        s=s.replace('pipeline_export_r8_updater','pipeline_speed_r9_updater').replace('EXPORT_R8_FLOW_READY','SPEED_R9_FLOW_READY').replace('GENOS R8 적용','GENOS R9 적용')
        (HERE/f'DATAIKU_R9_{kind}.txt').write_text(s);ast.parse(s)
    old=(BASE/'install_compute.py').read_text();digest=sha((HERE/(SERVICE+'.zip')).read_bytes());oldhash=sha((BASE/OLD_ARCHIVE).read_bytes())
    installer=old.replace(OLD_ARCHIVE,SERVICE+'.zip').replace(oldhash,digest).replace(OLD_CODE,code).replace('install-r8','install-r9').replace('PIPELINE_R8','PIPELINE_R9').replace('sealed pipeline R8','sealed pipeline R9')
    installer=edit(installer,', CODE_SHA):',", '"+OLD_CODE+"', CODE_SHA):")
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")];oldembed=old[:old.index("if __name__ == '__main__':")]
    for name in ('GENOS_R8_INSTALL.txt','ROLLBACK_GENOS.txt'):
        s=(BASE/name).read_text().replace(oldembed,embedded).replace(OLD_ARCHIVE,SERVICE+'.zip').replace(oldhash,digest)
        s=s.replace('R8','R9').replace('export_r8','speed_r9')
        (HERE/name.replace('R8','R9')).write_text(s)
    for n,b in list(payload.items())+list(client.items()):
        if n.endswith('.py'):compile(b,n,'exec')
    save('CODE_MANIFEST.json',{'code_sha256':code,**json.loads(payload['CODE_PINS.json'])})
    save('BUILD.json',{'baseline_code_sha256':OLD_CODE,'code_sha256':code,'service_files':len(payload),
        'unchanged_baseline_files':sum(payload.get(n)==b for n,b in original.items()),
        'changed_files':[n for n,b in payload.items() if original.get(n)!=b],
        'candidate_manifest':str(candidate.relative_to(ROOT)),'candidate_manifest_sha256':sha(candidate.read_bytes()),
        'adopted':adopted,'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}})
    print('PREPARED_NOT_QUALIFIED',code,len(payload))

if __name__=='__main__':main()
