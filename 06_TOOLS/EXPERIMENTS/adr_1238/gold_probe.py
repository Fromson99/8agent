from common import *
import importlib.util,shutil,logging,time
logging.disable(logging.CRITICAL)
mode=sys.argv[1];action=sys.argv[2];assert mode in ('candidate','active') and action in ('source-vector','ontology','binding')
f=read(DES/'freeze.json');pf=read(DES/'port-freeze.json')
if mode=='candidate':
 T=ART/'test-runtime'/('gold-port-'+action+'-'+str(time.time_ns()));T.mkdir(parents=True)
 for n,h in pf['files'].items():
  src=ROOT/pf['code_root']/n;assert sha(src)==h;shutil.copy2(src,T/Path(n).name)
 for n in ('ACTIVE_MAPPING.json','mapping_local_vctr_current.json','ontology_settings.json'):
  assert sha(GOLD/n)==read(DES/'baseline.json')['gold_files'][str((GOLD/n).relative_to(ROOT))];shutil.copy2(GOLD/n,T/n)
 b=read(DES/'baseline.json')['gold_binding'];b.update(schema_version='selected-main-gold-port-v2',engine_root=f['code_root'],engine_files=f['files'],engine_release_id='synthetic-qualified-candidate',data_path=read(DES/'baseline.json')['manifest']['data_path'],connector_files={Path(n).name:h for n,h in pf['files'].items()})
 manifest={'code_root':b['engine_root'],'files':b['engine_files'],'data_path':b['data_path']};put(T/'synthetic-manifest.json',manifest)
 b['engine_manifest_sha256']=sha(T/'synthetic-manifest.json');put(T/'binding.json',b)
 put(T/'synthetic-active.json',{'deployment_basis':'VALIDATED_ADR_PROMOTION','release_id':b['engine_release_id'],'release_manifest_sha256':b['engine_manifest_sha256'],'manifest_path':str((T/'synthetic-manifest.json').relative_to(ROOT))})
else:T=GOLD
spec=importlib.util.spec_from_file_location('connect',T/'connect.py');connect=importlib.util.module_from_spec(spec);sys.modules['connect']=connect;spec.loader.exec_module(connect)
connect.ROOT=ROOT;connect.ACTIVE_POINTER=T/'synthetic-active.json' if mode=='candidate' else ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
if action=='binding':
 assert mode=='candidate'
 before=read(connect.ACTIVE_POINTER);checks=[]
 for key,value in [('release_id','stale'),('deployment_basis','UNQUALIFIED'),('release_manifest_sha256','0'*64)]:
  connect.ACTIVE_POINTER.write_text(json.dumps({**before,key:value}))
  try:connect.engine_binding()
  except RuntimeError:checks.append(key)
  else:raise AssertionError(key)
 connect.ACTIVE_POINTER.write_text(json.dumps(before))
 binding=connect.engine_binding();runtime,_=connect.load_runtime()
 import semantic_runtime
 assert Path(semantic_runtime.__file__).resolve()==ROOT/f['code_root']/'02_BACKEND/semantic_runtime/__init__.py'
 try:connect.load_runtime()
 except RuntimeError:checks.append('dirty_process')
 else:raise AssertionError('dirty process')
 assert not hasattr(connect,'install_runtime_patches')
 checks.extend(['selected_code_root','no_runtime_patches'])
 put(ART/'gold-binding-candidate.json',{'passed':True,'checks':checks,'synthetic_pointer_only':True,'external_model_calls':0})
 print('Gold binding',len(checks),'PASS');raise SystemExit()
# Reuse read-only verification functions without writing their historical records.
spec=importlib.util.spec_from_file_location('gold_readonly_checks_1238',ROOT/'06_TOOLS/maintenance/verify_gold_vctr_sctn_rename.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.OUT=ART/('gold-'+mode);module.OUT.mkdir(exist_ok=True)
if action=='source-vector':module.source_vector()
else:module.ontology()
import semantic_runtime
engine=ROOT/f['code_root'] if mode=='candidate' else ROOT/read(ROOT/read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['manifest_path'])['code_root']
assert Path(semantic_runtime.__file__).resolve()==engine/'02_BACKEND/semantic_runtime/__init__.py'
put(module.OUT/(action+'-engine.json'),{'engine':str(engine.relative_to(ROOT)),'files_exact':all(sha(engine/n)==h for n,h in f['files'].items()),'connector_exact':all(sha(T/Path(n).name)==h for n,h in pf['files'].items()),'runtime_patches':False,'model_calls':0})
