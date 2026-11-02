import ast,hashlib,json,re,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent
B=P.parent/'existing_nfs_bulk_write_20261030_r9'
def sha(b):return hashlib.sha256(b).hexdigest()
base=B/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R9.zip'
assert sha(base.read_bytes())=='0afffaabcb542058e363c6ede78b9bf9bcb26e6ba7a47cca3998a3f974ed6943'
with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
names=set(old)|{'strict_resume.py'}
files={n:(P/'candidate'/n).read_bytes() for n in names}
pins=json.loads(files['client/CODE_PINS.json'])
for n in pins['files']:pins['files'][n]=sha(files['client/'+n])
files['client/CODE_PINS.json']=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
files['PACKAGE_FILES.json']=(json.dumps({n:sha(v) for n,v in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
changed=sorted(n for n in files if files[n]!=old.get(n))
assert set(changed)=={'PACKAGE_FILES.json','client/CODE_PINS.json','existing_client.py','strict_resume.py','client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py','client/02_BACKEND/lawrag/pipeline/oracle_transfer_progress.py'}
archive=P/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R10.zip'
for n,v in files.items():
 (P/'candidate'/n).write_bytes(v)
 if n.endswith('.py'):compile(v,n,'exec')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in sorted(files.items()):
  assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
  info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,v)
text=(B/'DATAIKU_EXISTING_NFS_LOAD_ONLY_R9.txt').read_text().replace('R9','R10')
text=text.replace(sha(base.read_bytes()),sha(archive.read_bytes()))
text=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str(archive.stat().st_size),text)
text=text.replace('QUERY_WRITE_ROWS = 500', 'RESUME_ONLY = True  # 재개 자료가 없으면 자동 재수신/재계산 없이 중단\nQUERY_WRITE_ROWS = 500')
text=text.replace('본문4MiB 상한 유지','JSON누적4MiB 묶음 목표 유지')
text=text.replace('검증만 최대100행; 쓰기는 기존20행','원문검증 최대100행; 원문쓰기는 기존20행')
text=text.replace('query_write_rows=QUERY_WRITE_ROWS)', 'query_write_rows=QUERY_WRITE_ROWS, resume_only=RESUME_ONLY)')
text=text.replace("    'projection_preflight': 'projection_preflight.py',", "    'strict_resume': 'strict_resume.py',\n    'projection_preflight': 'projection_preflight.py',")
compile(text,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R10.txt','exec')
(P/'DATAIKU_EXISTING_NFS_LOAD_ONLY_R10.txt').write_text(text)
report={'base_sha256':sha(base.read_bytes()),'members':len(files),'changed':changed,'preserved':len(files)-len(changed),'files':{n:{'bytes':(P/n).stat().st_size,'sha256':sha((P/n).read_bytes())} for n in (archive.name,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R10.txt')}}
(P/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n');print('Built R10:',len(files),'members;',len(changed),'changed; migration/full unchanged')
