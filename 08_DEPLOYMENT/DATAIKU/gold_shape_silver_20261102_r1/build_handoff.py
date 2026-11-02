"""Build the exact checked code ZIP and its matching complete notebook TXT."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import zipfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'package'
ROOT=HERE.parents[2]
sys.path.insert(0,str(PACKAGE))
from gold_io import Contract

def sha(raw):return hashlib.sha256(raw).hexdigest()
def put(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

contract=Contract(PACKAGE/'contract.json')
lines=['-- REVIEW COPY: use the supplied Python runner for create-if-missing and exact schema checks.',
       '-- These CREATE statements are not a blind rerun script; existing objects are preserved.',
       '-- Oracle native VECTOR support is required. Tablespace placement follows each owner default.']
for key in contract.tables:
    lines.extend(['\n-- '+key,contract.ddl(key).rstrip(';')+';'])
    lines.extend(x.rstrip(';')+';' for x in contract.indexes(key))
(PACKAGE/'01_CREATE_GOLD_SHAPE_REVIEW.sql').write_text('\n'.join(lines)+'\n')
with (PACKAGE/'TABLES.csv').open('w',newline='') as stream:
    writer=csv.writer(stream);writer.writerow(['group','logical_table','development_target','columns'])
    for key,t in contract.tables.items():writer.writerow([t['group'],key,contract.table(key),len(t['columns'])])

# The original registration schema has a single owner. Preserve it separately;
# the actual per-table development placement is explicit in contract.json.
(PACKAGE/'PLACEMENT_NOTE.txt').write_text(
    'contract.json is the executable development placement: Gold13 tables across SIDDS/SIDDA plus Agent4.\n'
    'registration_r18.json is the unchanged Gold registration reference, not a ready serving override.\n'
    'No active service mapping or existing channel is switched by this handoff.\n')
original=ROOT/'08_DEPLOYMENT/DATAIKU/existing_nfs_set_bulk_20261031_r11/DATAIKU_EXISTING_NFS_CLIENT_20261031_R11.zip'
with zipfile.ZipFile(original) as old:
    vendor=list((PACKAGE/'vendor').rglob('*.py'))
    for p in vendor:
        rel=p.relative_to(PACKAGE/'vendor').as_posix()
        name=rel if rel=='strict_resume.py' else 'client/'+rel
        assert p.read_bytes()==old.read(name),name
files={}
for p in sorted(PACKAGE.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts or p.name=='CODE_MANIFEST.json':continue
    assert p.suffix.lower() not in {'.pyc','.js','.jsx','.mjs','.cjs','.zip'}
    if p.suffix=='.py':compile(p.read_bytes(),str(p),'exec')
    files[p.relative_to(PACKAGE).as_posix()]=sha(p.read_bytes())
put(PACKAGE/'CODE_MANIFEST.json',{'version':'gold-shape-code-v1','files':files})
zip_name='DATAIKU_GOLD_SHAPE_20261102_R1.zip'
with zipfile.ZipFile(HERE/zip_name,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in [*files,'CODE_MANIFEST.json']:
        info=zipfile.ZipInfo(name,date_time=(2026,11,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o100644<<16
        z.writestr(info,(PACKAGE/name).read_bytes())
zip_sha=sha((HERE/zip_name).read_bytes())
text=(HERE/'launch_template.py').read_text().replace('__ZIP_NAME__',zip_name).replace('__ZIP_SHA256__',zip_sha)
assert '__ZIP_NAME__' not in text and '__ZIP_SHA256__' not in text
compile(text,'DATAIKU_GOLD_SHAPE_RUN_R1.txt','exec')
(HERE/'DATAIKU_GOLD_SHAPE_RUN_R1.txt').write_text(text)
with zipfile.ZipFile(HERE/zip_name) as z:
    assert z.testzip() is None
    assert set(z.namelist())==set(files)|{'CODE_MANIFEST.json'}
    assert all(sha(z.read(n))==h for n,h in files.items())
    assert sum(i.file_size for i in z.infolist())<=32*1024**2
assert (HERE/zip_name).stat().st_size<=16*1024**2
names=[zip_name,'DATAIKU_GOLD_SHAPE_RUN_R1.txt','GUIDE.txt','DBA_INQUIRY.txt','EXISTING_MIGRATION.txt']
attachments=[{'name':n,'bytes':(HERE/n).stat().st_size,'sha256':sha((HERE/n).read_bytes())} for n in names]
validation={'status':'LOCAL_VALIDATED_FIELD_NOT_EXECUTED','contract_tests':24,
            'native_contracts':json.loads((HERE/'NATIVE_CONTRACTS.json').read_text()),
            'vendor_python_files_exact_r11':len(vendor),'package_files':len(files)+1,
            'gold_tables':13,'gold_columns':60,'agent_tables':4,'agent_columns':26,
            'zip_integrity':True,'execution_txt_compiles':True,'nested_zip':False,'javascript_members':False,
            'old_data_deleted':False,'field_executed':False,'models_or_embeddings_called':0,
            'not_certified':['field permissions/capacity','Dataiku JDBC end-to-end','full data ingestion',
                             'Gold runtime consumer activation','approved ontology ingestion','embedding'],
            'reused_gold_definitions':['READ_COLUMNS','mapped_source','mapped_query'],
            'corrected_before_delivery':'Legacy UTF-8 canonical hash encoding restored; real SQLite projection test added.',
            'attachments':attachments}
put(HERE/'VALIDATION.json',validation)
print(json.dumps({'status':validation['status'],'attachments':attachments,'vendor_files':len(vendor)},ensure_ascii=False))
