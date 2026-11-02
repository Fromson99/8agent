import ast,hashlib,json,re,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent
B=P.parent/'existing_nfs_deferred_verify_20261030_r6b'
def sha(b):return hashlib.sha256(b).hexdigest()
base=B/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R6B.zip'
assert sha(base.read_bytes())=='c2a91252dccfad7595e685dc0942e2252baa88964e636945cc725cdc21613406'
with zipfile.ZipFile(base) as z:old={n:z.read(n) for n in z.namelist()}
files={n:(P/'candidate'/n).read_bytes() for n in old}
files['existing_client.py']=files['existing_client.py'].replace(b'existing-nfs-20261030-r6',b'existing-nfs-20261030-r7')
pins=json.loads(files['client/CODE_PINS.json'])
for n in pins['files']:pins['files'][n]=sha(files['client/'+n])
files['client/CODE_PINS.json']=(json.dumps(pins,sort_keys=True,indent=2)+'\n').encode()
files['PACKAGE_FILES.json']=(json.dumps({n:sha(v) for n,v in files.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode()
changed=[n for n in files if files[n]!=old[n]]
assert set(changed)=={'existing_client.py','client/CODE_PINS.json','PACKAGE_FILES.json','client/02_BACKEND/lawrag/pipeline/oracle_query_publish.py','client/02_BACKEND/lawrag/pipeline/oracle_deferred_import.py'}
archive=P/'DATAIKU_EXISTING_NFS_CLIENT_20261030_R7.zip'
for n,v in files.items():
    (P/'candidate'/n).write_bytes(v)
    if n.endswith('.py'):compile(v,n,'exec')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for n,v in sorted(files.items()):
        assert not n.lower().endswith(('.zip','.js','.jsx','.mjs','.cjs'))
        info=zipfile.ZipInfo(n,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,v)
text=(B/'DATAIKU_EXISTING_NFS_RUN_R6B.txt').read_text().replace('R6B','R7')
text=text.replace(sha(base.read_bytes()),sha(archive.read_bytes()))
text=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str(archive.stat().st_size),text)
compile(text,'DATAIKU_EXISTING_NFS_RUN_R7.txt','exec')
(P/'DATAIKU_EXISTING_NFS_RUN_R7.txt').write_text(text)
(P/'BUILD.json').write_text(json.dumps({'base_sha256':sha(base.read_bytes()),'changed':changed,'preserved':len(files)-len(changed),'files':{n:{'bytes':(P/n).stat().st_size,'sha256':sha((P/n).read_bytes())} for n in (archive.name,'DATAIKU_EXISTING_NFS_RUN_R7.txt')}},indent=2)+'\n')
print('Built R7:',len(files),'members;',len(changed),'changed; full/migration unchanged')
