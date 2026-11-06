"""Import the real maintained Gold connector without connecting to Oracle."""
from common import *
OUT=ART/"main"
GOLD=ROOT/"08_DEPLOYMENT/LOCAL/gold_connection_engine_r12"
RELEASE="reason-decision-review-20261105-r1"

from resource_guard import Guard
resource_dir=ART/'gold-entry-resource';resource_dir.mkdir(exist_ok=False)
guard=Guard(resource_dir);guard.start()
import importlib.util
spec=importlib.util.spec_from_file_location('selected_gold_main147',GOLD/'connect.py')
gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
runtime,binding=gold.load_runtime()
import semantic_runtime
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/active['manifest_path']);b={**{'release':read(DES/'baseline.json')['release']},**{'gold_binding':read(OUT/'gold-before.json')['binding'],'gold_files':read(OUT/'gold-before.json')['files']}}
checks={'same_main147':active['generation']==147 and binding['engine_release_id']==RELEASE,
 'selected_runtime_origin':Path(semantic_runtime.__file__).resolve()==ROOT/r['code_root']/'02_BACKEND/semantic_runtime/__init__.py',
 'same_engine_files':binding['engine_files']==r['files'],'same_engine_manifest':binding['engine_manifest_sha256']==sha(ROOT/active['manifest_path']),
 'original_query_release':binding['query_release_id']==b['gold_binding']['query_release_id'],
 'original_data_path':binding['data_path']==b['gold_binding']['data_path'],
 'explicit_user_authorization':binding['main_authorization']['authorization_sha256']==r['authorization_sha256'],
 'physical_mapping_unchanged':sha(GOLD/'ACTIVE_MAPPING.json')==b['gold_files'][str((GOLD/'ACTIVE_MAPPING.json').relative_to(ROOT))],
 'ontology_settings_unchanged':sha(GOLD/'ontology_settings.json')==b['gold_files'][str((GOLD/'ontology_settings.json').relative_to(ROOT))]}
put(OUT/'gold-entry.json',{'passed':all(checks.values()),'checks':checks,'oracle_calls':0,'model_calls':0,'engine_binding_only':True})
assert all(checks.values()),checks
print('Gold actual MAIN147 import',len(checks),'checks PASS; no DB access')

guard.done.set();guard.thread.join(timeout=3);put(resource_dir/'resource-final.json',guard.check())
