"""Derive a narrowly patched, hash-bound compute/client pair from sealed R7."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.parent/'pipeline_skip_parser_20261028_r7'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R8'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R8.zip'
OLD_CODE='1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
OLD_ARCHIVE='GENOS_DATAIKU_COMPUTE_20261028_R7.zip'

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
def functions_from_work(source,relative,names):
    work=(ROOT/relative).read_text();new_nodes={n.name:n for n in ast.parse(work).body if isinstance(n,ast.FunctionDef)}
    lines=source.splitlines(keepends=True)
    for node in reversed(ast.parse(source).body):
        if isinstance(node,ast.FunctionDef) and node.name in names:
            n=new_nodes[node.name];lines[node.lineno-1:node.end_lineno]=work.splitlines(keepends=True)[n.lineno-1:n.end_lineno]
    return ''.join(lines)

def main():
    with zipfile.ZipFile(BASE/OLD_ARCHIVE) as z:original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json']);assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    n='02_BACKEND/lawrag/pipeline/oracle_query_publish.py'
    s=functions_from_work(original[n].decode(),n,{'asset_schema','_asset_rows'})
    payload[n]=edit(s,'from collections import defaultdict','from collections import defaultdict\nimport base64').encode()
    n='02_BACKEND/lawrag/pipeline/oracle_query_package.py'
    payload[n]=functions_from_work(original[n].decode(),n,{'export','_export'}).encode()
    s=original['worker.py'].decode()
    s=edit(s,'import os\n','import os\nimport json\nimport time\nfrom contextlib import contextmanager\n')
    s=edit(s,'def process_group_rss(group):', '''@contextmanager
def phase_timing(phase):
    started=time.monotonic();status='FAILED'
    try:
        yield
        status='COMPLETE'
    finally:
        print('PHASE_RESULT '+json.dumps({'phase':phase,'status':status,
              'seconds':round(time.monotonic()-started,3)}),flush=True)

def process_group_rss(group):''')
    s=edit(s,"query.export(generation, output / 'query', seconds=21600, direct_parts=True)",
             "query.export(generation, output / 'query', seconds=21600, database_only=True)")
    start=s.index('        print(\'PHASE \'+phase,flush=True)')
    end=s.index('    verify_code(root)',start)
    s=s[:start]+'        with phase_timing(phase):\n'+''.join('    '+line if line.strip() else line for line in s[start:end].splitlines(keepends=True))+s[end:]
    payload['worker.py']=s.encode();(HERE/'worker.py').write_text(s)
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,indent=2)+'\n').encode()
    code=sha(payload['CODE_PINS.json']);writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R7.zip') as z:client={n:z.read(n) for n in z.namelist()}
    client['COMPUTE_CODE_SHA256.txt']=(code+'\n').encode()
    s=client['checkpoint_upgrade.py'].decode()
    s=edit(s,'PREVIOUS_CODES = {',"PREVIOUS_CODES = {'"+OLD_CODE+"', ")
    # Unlike R3-R6, the exact sealed R7 pipeline forbids all parser/review calls.
    # A missing audit is not a reason to reset budgets or invent zero-use evidence.
    # Record the static no-model basis, and keep every terminal/input/budget guard.
    s=edit(s,'    # Check the snapshot again',"    if previous_code == '"+OLD_CODE+"':\n        if old.get('audit_blob'):\n            from upgrade_review import require_zero_review\n            proof = require_zero_review(store,old)\n        else:\n            proof = {'basis':'SEALED_R7_FIXED_SKIP_NO_MODEL_PATH', 'code_sha256':previous_code,\n                     'audit_available':False, 'field_calls_measured':False}\n    # Check the snapshot again")
    s=s.replace("'reason': 'PREPROCESSOR_BYPASSED_BY_USER'","'reason': 'LOSSLESS_BLOB_EXPORT_AND_BOUNDED_ROW_WRITER'")
    client['checkpoint_upgrade.py']=s.encode()
    client['updater.py']=client['updater.py'].replace(b'skip-parser-r7-before.json',b'export-r8-before.json')
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text());client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
    writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text()
    boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R7.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R7.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    boot=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot);(HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_R7_{kind}.txt').read_text().replace(oldboot,boot).replace(repr(oldboot),repr(boot)).replace('pipeline_skip_r7_updater','pipeline_export_r8_updater')
        s=s.replace('SKIP_R7_FLOW_READY','EXPORT_R8_FLOW_READY').replace('GENOS R7 적용','GENOS R8 적용')
        (HERE/f'DATAIKU_R8_{kind}.txt').write_text(s);ast.parse(s)
    old=(BASE/'install_compute.py').read_text()
    digest=sha((HERE/(SERVICE+'.zip')).read_bytes());oldhash=sha((BASE/OLD_ARCHIVE).read_bytes())
    installer=old.replace(OLD_ARCHIVE,SERVICE+'.zip').replace(oldhash,digest).replace(OLD_CODE,code).replace('install-r7','install-r8').replace('PIPELINE_R7','PIPELINE_R8').replace('sealed pipeline R7','sealed pipeline R8')
    installer=edit(installer,', CODE_SHA):',", '"+OLD_CODE+"', CODE_SHA):")
    (HERE/'install_compute.py').write_text(installer)
    embedded=installer[:installer.index("if __name__ == '__main__':")];oldembed=old[:old.index("if __name__ == '__main__':")]
    for name in ('GENOS_R7_INSTALL.txt','ROLLBACK_GENOS.txt'):
        s=(BASE/name).read_text().replace(oldembed,embedded).replace(OLD_ARCHIVE,SERVICE+'.zip').replace(oldhash,digest)
        s=s.replace('Skip PDF preprocessor and converter by user request','Fix lossless binary export and remove redundant return work')
        s=s.replace('R7','R8')
        (HERE/name.replace('R7','R8')).write_text(s)
    for n,b in list(payload.items())+list(client.items()):
        if n.endswith('.py'):compile(b,n,'exec')
    save('CODE_MANIFEST.json',{'code_sha256':code,**json.loads(payload['CODE_PINS.json'])})
    save('BUILD.json',{'baseline_code_sha256':OLD_CODE,'code_sha256':code,'service_files':len(payload),
        'unchanged_baseline_files':sum(payload.get(n)==b for n,b in original.items()),
        'changed_files':[n for n,b in payload.items() if original.get(n)!=b],
        'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}})
    print('BUILT',code,len(payload))

if __name__=='__main__':main()
