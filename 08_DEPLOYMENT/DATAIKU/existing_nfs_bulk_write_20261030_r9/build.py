import ast,hashlib,json,re,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent
B=P.parent/'existing_nfs_progress_20261030_r8'
def sha(b):return hashlib.sha256(b).hexdigest()
base=B/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R8.zip'
assert sha(base.read_bytes())=='aa5fffb50615794874abeec0203cba3480cc3ab525361cc4c6ac88c544e42b40'
with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
names=set(old)
files={n:(P/'candidate'/n).read_bytes() for n in names}
pins=json.loads(files['client/CODE_PINS.json'])
for n in pins['files']:pins['files'][n]=sha(files['client/'+n])
files['client/CODE_PINS.json']=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
files['PACKAGE_FILES.json']=(json.dumps({n:sha(v) for n,v in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
changed=sorted(n for n in files if files[n]!=old.get(n))
assert set(changed)=={'PACKAGE_FILES.json','client/CODE_PINS.json','existing_client.py','client/02_BACKEND/semantic_runtime/oracle_query_catalog.py','client/02_BACKEND/semantic_runtime/contracts.py','client/02_BACKEND/semantic_runtime/full_glossary.py','projection_preflight.py','client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py','client/02_BACKEND/lawrag/pipeline/oracle_transfer_progress.py'}
archive=P/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R9.zip'
for n,v in files.items():
 (P/'candidate'/n).write_bytes(v)
 if n.endswith('.py'):compile(v,n,'exec')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in sorted(files.items()):
  assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
  info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,v)
text=(B/'DATAIKU_EXISTING_NFS_LOAD_ONLY_R8.txt').read_text().replace('R8','R9')
text=text.replace(sha(base.read_bytes()),sha(archive.read_bytes()))
text=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str(archive.stat().st_size),text)

text=text.replace('CLOB_BATCH_READS = 32', 'QUERY_WRITE_ROWS = 500  # 검색행 쓰기 최대행수 20..500, 본문4MiB 상한 유지\nCLOB_BATCH_READS = 32')
text=text.replace('verify_batch_rows=VERIFY_BATCH_ROWS)', 'verify_batch_rows=VERIFY_BATCH_ROWS, query_write_rows=QUERY_WRITE_ROWS)')
compile(text,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R9.txt','exec')
(P/'DATAIKU_EXISTING_NFS_LOAD_ONLY_R9.txt').write_text(text)
report={'base_sha256':sha(base.read_bytes()),'members':len(files),'changed':changed,'preserved':len(files)-len(changed),'files':{n:{'bytes':(P/n).stat().st_size,'sha256':sha((P/n).read_bytes())} for n in (archive.name,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R9.txt')}}
(P/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n');print('Built R9:',len(files),'members;',len(changed),'changed; migration/full unchanged')
