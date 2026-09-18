"""Validate design artifacts only; does not run or evaluate the proposed RAG."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
schema=json.loads((ROOT/'contracts.schema.json').read_text())
Draft202012Validator.check_schema(schema)
examples=json.loads((ROOT/'contract-examples.json').read_text())
checks=[]
for expected,key in [(True,'valid'),(False,'invalid')]:
 for item in examples[key]:
  target={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+item['definition']}
  errors=list(Draft202012Validator(target).iter_errors(item['value']))
  accepted=not errors
  checks.append({'name':item['name'],'definition':item['definition'],'expected':'accept' if expected else 'reject','actual':'accept' if accepted else 'reject','passed':accepted==expected})
# Cross-field checks available in synthetic records; real delivery/ACL/source checks remain runtime work.
semantic=[]
for item in examples['valid']:
 v=item['value'];d=item['definition'];passed=True
 if d=='ReadReceipt':passed=all(x['end_char']>x['start_char'] for x in v['extents'])
 elif d=='ToolResultEnvelope' and v['total_kind']=='EXACT':passed=len(v['items'])<=v['total']
 elif d=='ToolCall' and v['tool']=='JUDGE':passed=v['issue_id']==v['args']['issue_id']
 else:continue
 semantic.append({'name':item['name'],'passed':passed})
text=(ROOT/'DESIGN.md').read_text()
missing=[];checked=0
for href in re.findall(r'\]\(([^)]+)\)',text):
 if href.startswith(('https://','http://','#')):continue
 target=href.split('#',1)[0]
 if target=='validation.json':continue
 path=Path(target) if target.startswith('/') else ROOT/target
 checked+=1
 if not path.exists():missing.append(href)
fences=sum(line.startswith('```') for line in text.splitlines())
# Equation dimensional/round-trip sanity with unitless synthetic inputs, not forecasts.
Q=1000;delta=.01;build=60;months=6;ops=2
net=Q*delta-build/months-ops
break_even=(build/months+ops)/delta
formula={'status':'SYNTHETIC_ARITHMETIC_ONLY_NOT_FORECAST','monthly_net_example':net,'break_even_example':break_even,'zero_at_break_even':abs(break_even*delta-build/months-ops)<1e-9}
inspection=json.loads((ROOT/'inspection.json').read_text())
repo=Path('/home/jin/8-AGENT');active=repo/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
root_check={'active_pointer_unchanged':sha(active)==inspection['active_pointer_sha256'],'release_manifest_verified_at_inspection':inspection['release_manifest_hash_ok'],'release_code_files_verified_at_inspection':all(inspection['release_files_verified'].values()),'source_store_verified_at_inspection':inspection['source_store_hash_ok']}
report={'validated_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Design JSON/links/arithmetic validation only. No product tests, model calls, performance evaluation, independent review or deployment.','schema_valid':True,'example_results':checks,'synthetic_cross_field_checks':semantic,'local_links_checked':checked,'missing_local_links':missing,'code_fences_paired':fences%2==0,'formula_sanity':formula,'source_binding_checks':root_check,'artifacts':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in ROOT.iterdir() if p.is_file() and p.name!='validation.json'}}
report['passed']=all(x['passed'] for x in checks+semantic) and not missing and fences%2==0 and formula['zero_at_break_even'] and all(root_check.values())
(ROOT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['passed','schema_valid','local_links_checked','missing_local_links','code_fences_paired','source_binding_checks']},ensure_ascii=False,indent=2))
print('Valid examples:',len(examples['valid']),'Invalid examples:',len(examples['invalid']))
if not report['passed']:raise SystemExit(1)
