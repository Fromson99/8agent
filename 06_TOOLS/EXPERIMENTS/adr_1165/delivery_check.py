from common import *
import tempfile,subprocess,sys,types,io,copy,zipfile
D=ROOT/'08_DEPLOYMENT/GENOS/handoffs/vector_initial_20261028_r1';P=D/'package';checks={}
with tempfile.TemporaryDirectory(prefix='vector-delivery-') as tmp:
 root=Path(tmp)/'checkout';root.mkdir();m=read(P/'CODE_MANIFEST.json')
 for n in m['preserve_existing']:
  p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/read(DES/'freeze.json')['code_root']/n).read_bytes())
 subprocess.run(['git','init','-q',str(root)],check=True);subprocess.run(['git','add','.'],cwd=root,check=True);subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],cwd=root,check=True)
 a=subprocess.run(['bash',str(D/'GENOS_VECTOR_APPLY.txt'),str(D/'VECTOR_INITIAL_CODE_20261028_R1.zip'),str(root)],capture_output=True,text=True);assert a.returncode==0,a.stderr
 checks['actual_bash_install_all458_hashes']=all(sha(root/n)==h for n,h in m['serving_files'].items())
 backups=list(Path(tmp).glob('vector-backup-*'));assert len(backups)==1 and read(backups[0]/'RECEIPT.json')['field_revision'] is None;checks['rollback_backup_receipt']=True
 tracked=root/next(iter(m['preserve_existing']));tracked.write_bytes(tracked.read_bytes()+b'\n// local edit\n')
 second=subprocess.run(['bash',str(D/'GENOS_VECTOR_APPLY.txt'),str(D/'VECTOR_INITIAL_CODE_20261028_R1.zip'),str(root)],capture_output=True,text=True);assert second.returncode!=0;checks['dirty_checkout_not_overwritten']=True
class Settings:
 type='S3'
 def __init__(self):self.params={'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':'/landing'};self.code=None
 def get_raw_params(self):return self.params
 def save(self):pass
 def set_code_env(self,**kw):pass
 def get_code(self):return self.code
 def get_flat_input_refs(self):return ['ehA8dpVm']
 def get_flat_output_refs(self):return ['out']
class Folder:
 def __init__(self,id,name):self.id=id;self.name=name;self.s=Settings()
 def get_settings(self):return self.s
 def get_download_stream(self,p):return io.BytesIO((D/p).read_bytes())
class Recipe:
 def __init__(self):self.s=Settings()
 def get_settings(self):return self.s
class Builder:
 def with_input(self,*a,**k):return self
 def with_output(self,*a,**k):return self
 def with_script(self,code):self.code=code;return self
 def create(self):r=Recipe();r.s.code=self.code;project.recipes['LEGAL_04_VECTOR_INITIAL_R1']=r;return r
class Project:
 def __init__(self):self.vars={'standard':{}};self.folders={'ehA8dpVm':Folder('ehA8dpVm','landing')};self.recipes={}
 def get_variables(self):return copy.deepcopy(self.vars)
 def set_variables(self,v):self.vars=v
 def get_managed_folder(self,id):return self.folders[id]
 def list_managed_folders(self):return [{'id':x.id,'name':x.name} for x in self.folders.values()]
 def create_managed_folder(self,name,**kw):f=Folder('out',name);self.folders['out']=f;return f
 def list_recipes(self):return [{'name':n} for n in self.recipes]
 def get_recipe(self,n):return self.recipes[n]
 def new_recipe(self,*a):return Builder()
project=Project();d=types.ModuleType('dataiku');d.Folder=lambda id:project.folders[id];d.api_client=lambda:types.SimpleNamespace(get_default_project=lambda:project);d.get_custom_variables=lambda:{'GENOS_BASE_URL':'https://example.invalid','GENOS_EMBED_SERVING_ID':'3'};sys.modules['dataiku']=d
cell=(D/'DATAIKU_VECTOR_INSTALL_RUN.txt').read_text().replace('EMBED_MODEL = "실제 임베딩 모델 ID"','EMBED_MODEL = "fixture"').replace('EMBED_REVISION = "실제 배포 가중치 버전 또는 SHA256"','EMBED_REVISION = "fixture-v1"').replace('EMBED_DIMENSIONS = 0','EMBED_DIMENSIONS = 4')
exec(compile(cell,'delivery-install','exec'),{})
assert 'LEGAL_04_VECTOR_INITIAL_R1' in project.recipes;checks['Dataiku_complete_TXT_installs_recipe']=True
exec(compile(cell,'delivery-install-again','exec'),{})
assert len(project.recipes)==1 and len(project.folders)==2;checks['idempotent_install_no_duplicates']=True
assert project.vars['standard']['LEGAL_VECTOR_PROFILE']['dimensions']==4;checks['profile_generated_from_existing_endpoint']=True
assert project.folders['out'].s.params['path']=='/LEGAL_RAG/vector_initial_20261028_r1/results';checks['Dataiku_result_S3_reuses_connection']=True
with zipfile.ZipFile(D/'VECTOR_INITIAL_CODE_20261028_R1.zip') as z:checks['no_javascript_in_archive']=not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
put(D/'VALIDATION.json',{'strict_success':all(checks.values()),'checks':checks,'physical_embedding_calls':0,'field_verified':False});print(checks)
