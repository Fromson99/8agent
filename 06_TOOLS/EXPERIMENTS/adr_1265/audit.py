"""Read-only final delivery audit. No model/DB/test execution."""
from pathlib import Path
import ast,hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[3];a=ROOT/'04_EXPERIMENTS/ADR/ADR-1265-dataiku-queued-kure-handoff-audit';o=ROOT/'04_EXPERIMENTS/ADR/ADR-1264-dataiku-queued-verify-kure';d=ROOT/'08_DEPLOYMENT/DATAIKU/existing_nfs_queued_kure_20261031_r12'
s=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1264/queued/revisions/rev-004/snapshot/08_DEPLOYMENT/DATAIKU/existing_nfs_resume_only_20261030_r10/candidate'
checks=[]
for f in json.loads((a/'artifacts/design.json').read_text())['files']:assert hashlib.sha256((ROOT/f['path']).read_bytes()).hexdigest()==f['sha256']
checks.append('input_evidence_unchanged_including_closed1264')
cell=(d/'DATAIKU_QUEUE_AFTER_R11_R12.txt').read_text();tree=ast.parse(cell,feature_version=(3,10));constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id.startswith('PACKAGE_')}
zpath=d/constants['PACKAGE_NAME'];assert zpath.stat().st_size==constants['PACKAGE_BYTES'];assert hashlib.sha256(zpath.read_bytes()).hexdigest()==constants['PACKAGE_SHA256']
pins=json.loads((s/'PACKAGE_FILES.json').read_text());py=0
with zipfile.ZipFile(zpath) as z:
 assert set(z.namelist())==set(pins)|{'PACKAGE_FILES.json'} and len(z.namelist())==len(set(z.namelist()))
 for rel in z.namelist():
  raw=z.read(rel);assert raw==(s/rel).read_bytes();assert Path(rel).suffix not in ('.zip','.js','.jsx','.mjs','.cjs')
  if rel in pins:assert hashlib.sha256(raw).hexdigest()==pins[rel]
  if rel.endswith('.py'):ast.parse(raw,feature_version=(3,10));py+=1
checks.append('ZIP89_exact_frozen_rev004_members_and_Python310_syntax');checks.append('TXT_exact_ZIP_size_SHA_pins')
n=json.loads((o/'artifacts/run-005/results.json').read_text());assert n['status']=='PASS' and len(n['checks'])==15 and n['model_calls']==0 and n['isolated_schema_removed']
for table,plans in n['physical_batch_plans'].items():
 for plan in plans:assert any(row[1:3]==['INDEX','UNIQUE SCAN'] for row in plan)
checks.append('existing_native15_and_actual_unique_PK_plans')
log=(o/'artifacts/run-006/integration.log').read_text();assert 'R12_DELIVERED_INTEGRATION_PASS' in log and log.count('R12_REJECTED ')==7
checks.append('existing_final_delivered_one_pytest_seven_damages')
assert hashlib.sha256((ROOT/'08_DEPLOYMENT/DATAIKU/existing_nfs_set_bulk_20261031_r11/DATAIKU_EXISTING_NFS_CLIENT_20261031_R11.zip').read_bytes()).hexdigest()=='dfc0c769fc1b20093fd3c5549a750ca6557ddcb65d4d0f1b380d75cb43b9f21c'
checks.append('R11_delivery_unchanged')
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'));from experiment_json import write_summary
result={'status':'PASS','audit_checks':checks,'source_native_checks_observed':15,'source_delivery_pytest_observed':1,'source_damage_cases':7,'new_test_or_model_calls':0,'field_executed':False,'MAIN_changed':False,'revision':'rev-004','ZIP_sha256':constants['PACKAGE_SHA256'],'ZIP_bytes':constants['PACKAGE_BYTES'],'ZIP_members':len(pins)+1,'python_files':py,'administrative_correction':'Separate audit; closed ADR1264 preserved as-is, not represented as finalized metadata'}
write_summary(a/'artifacts/result.json',result);write_summary(d/'VALIDATION_FINAL.json',result)
print(json.dumps(result,ensure_ascii=False))
