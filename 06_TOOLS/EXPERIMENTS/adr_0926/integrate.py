"""Integrate reviewed files only; concurrent working files remain untouched."""
from pathlib import Path
import hashlib,json,tarfile,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
tests=ET.parse(A/'artifacts/tests.xml');suites=list(tests.iter('testsuite'))
assert sum(int(x.get('tests',0)) for x in suites)==8
assert all(int(x.get('failures',0))+int(x.get('errors',0))==0 for x in suites)
b=read(D/'binding.json');C=R/b['code_root'];base=read(D/'baseline.json');preview=read(A/'artifacts/packager-preview.json');staged=dict(base['manifest']['files'])
for row in preview['changes']:
    if row['after'] is None:staged.pop(row['path'],None)
    else:staged[row['path']]=row['after']
assert staged==b['serving_files']
assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
changes=read(D/'working-deltas.json');drift=read(D/'concurrent-working-only.json')['preserved']
assert all((sha(R/x['path']) if (R/x['path']).exists() else None)==x['before'] and sha(C/x['path'])==x['after'] for x in changes)
assert all(sha(R/n)==v['current'] for n,v in drift.items())
backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
with tarfile.open(backup,'w:gz') as tar:
    for x in changes:
        if x['before'] is not None:tar.add(R/x['path'],arcname=x['path'],recursive=False)
with tarfile.open(backup,'r:gz') as tar:
    for x in changes:
        if x['before'] is not None:
            with tar.extractfile(x['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==x['before']
put(A/'artifacts/working-integration-plan.json',{'changes':changes,'backup':str(backup.relative_to(R)),'backup_sha256':sha(backup),'rollback':'Verify listed after hashes, restore existing files from backup and remove only listed newly created files; preserve concurrent files.'})
for x in changes:
    p=R/x['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((C/x['path']).read_bytes())
assert all(sha(R/n)==(drift[n]['current'] if n in drift else h) for n,h in b['serving_files'].items())
put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'candidate':b['candidate'],'serving_files':len(staged),'preserved_working_only':drift,'active_pointer_changed':False,'genos_changed':False})
print('Integrated',len(changes),'reviewed files; preserved',len(drift),'concurrent files')
