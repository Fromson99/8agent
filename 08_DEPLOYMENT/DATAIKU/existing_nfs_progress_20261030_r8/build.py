import ast,hashlib,json,re,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent
B=P.parent/'existing_nfs_projection_20261030_r7'
def sha(b):return hashlib.sha256(b).hexdigest()
base=B/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R7.zip'
assert sha(base.read_bytes())=='a99d4d9eea3d226d5405b46c4f8a5154713e69787118cfe047339baf241bdc80'
with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
names=set(old)|{'projection_preflight.py','client/02_BACKEND/semantic_runtime/term_links.py'}
files={n:(P/'candidate'/n).read_bytes() for n in names}
pins=json.loads(files['client/CODE_PINS.json']);pins['files']['02_BACKEND/semantic_runtime/term_links.py']=''
for n in pins['files']:pins['files'][n]=sha(files['client/'+n])
files['client/CODE_PINS.json']=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
files['PACKAGE_FILES.json']=(json.dumps({n:sha(v) for n,v in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
changed=sorted(n for n in files if files[n]!=old.get(n))
assert set(changed)=={'PACKAGE_FILES.json','client/CODE_PINS.json','existing_client.py','projection_preflight.py','client/02_BACKEND/semantic_runtime/term_links.py',*['client/02_BACKEND/lawrag/pipeline/'+n for n in ['oracle_deferred_import.py','oracle_query_package.py','oracle_query_publish.py','oracle_transfer_progress.py']]}
archive=P/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R8.zip'
for n,v in files.items():
 (P/'candidate'/n).write_bytes(v)
 if n.endswith('.py'):compile(v,n,'exec')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for n,v in sorted(files.items()):
  assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
  info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,v)
text=(B/'send_load_only/DATAIKU_EXISTING_NFS_LOAD_ONLY_R7.txt').read_text().replace('R7','R8')
text=text.replace(sha(base.read_bytes()),sha(archive.read_bytes()))
text=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str(archive.stat().st_size),text)
text=text.replace("    'existing_client': 'existing_client.py',", "    'projection_preflight': 'projection_preflight.py',\n    'existing_client': 'existing_client.py',")
compile(text,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R8.txt','exec')
(P/'DATAIKU_EXISTING_NFS_LOAD_ONLY_R8.txt').write_text(text)
report={'base_sha256':sha(base.read_bytes()),'members':len(files),'changed':changed,'preserved':len(files)-len(changed),'files':{n:{'bytes':(P/n).stat().st_size,'sha256':sha((P/n).read_bytes())} for n in (archive.name,'DATAIKU_EXISTING_NFS_LOAD_ONLY_R8.txt')}}
(P/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n');print('Built R8:',len(files),'members;',len(changed),'changed; migration/full unchanged')
