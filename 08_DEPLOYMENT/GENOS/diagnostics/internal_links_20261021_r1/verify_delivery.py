import ast,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=Path('/home/jin/8-AGENT')
spec=importlib.util.spec_from_file_location('test_audit',P/'test_audit.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
base=Path(tempfile.mkdtemp(prefix='internal-link-delivery-'));env={k:v for k,v in os.environ.items() if k not in ('DP','GENOS_GENERATION')};env['PATH']=str(ROOT/'.venv/bin')+':'+env['PATH']
files=['audit_internal_links.py','RUN_INTERNAL_LINK_AUDIT.txt','GUIDE_UTF8.txt','PACKAGE_MANIFEST.json'];z=P/'GENOS_INTERNAL_LINK_AUDIT_20261021_R1.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as out:
 for name in files:out.write(P/name,name)
with zipfile.ZipFile(z) as archive:
 assert archive.namelist()==files and not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in archive.namelist());archive.extractall(base/'GENOS_INTERNAL_LINK_AUDIT_20261021_R1')
package=base/'GENOS_INTERNAL_LINK_AUDIT_20261021_R1';g=t.fixture(base/'generation',True);dev=base/'DEV';(dev/'00_SYSTEM').mkdir(parents=True)
config={'schema_version':'genos-serving-paths-v1','selection':'operator-fixed','generation':str(g),'generation_manifest_sha256':t.sha(g/'manifest.json')};(dev/'00_SYSTEM/GENOS_SERVING_PATHS.json').write_text(json.dumps(config))
commands=[]
def run(args,rc):
 r=subprocess.run(args,cwd=base,env=env,capture_output=True,text=True);commands.append({'command':[str(a).replace(str(base),'$TEST') for a in args],'expected_exit':rc,'actual_exit':r.returncode});assert r.returncode==rc,r.stdout+r.stderr;return r
script=str(package/'RUN_INTERNAL_LINK_AUDIT.txt')
run(['bash','-n',script],0);run(['bash',script,'check'],0)
run(['bash',script,'run','--code-root',str(dev),'--output',str(base/'report')],1)
with zipfile.ZipFile(base/'report.zip') as archive:
 assert 'index.html' in archive.namelist() and all(not n.endswith(('.js','.jsx','.cjs','.mjs')) for n in archive.namelist())
run(['bash',script,'run','--code-root',str(dev),'--output',str(base/'report')],2)
run(['bash',script,'run','--code-root',str(dev),'--document-contains','표현 없는 내규','--output',str(base/'zero')],0)
summary=json.loads((base/'zero/summary.json').read_text());assert summary['rows']==0 and summary['status']=='CHECKS_COMPLETED'
run(['bash',script,'run','--code-root',str(dev),'--generation',str(base/'wrong'),'--output',str(base/'mismatch')],2)
run(['bash',script,'run','--code-root',str(dev),'--max-seconds','0','--output',str(base/'budget')],2)
assert json.loads((base/'budget/summary.json').read_text())['status']=='INCOMPLETE'
run(['bash',script,'run','--code-root',str(dev),'--team','none','--output',str(base/'scope')],2)
run(['bash',script,'run','--code-root',str(dev),'--output',str(g/'overlap')],2);assert not (g/'overlap').exists()
(package/'audit_internal_links.py').write_text((package/'audit_internal_links.py').read_text()+'\n# tamper\n')
run(['bash',script,'check'],1)
assert len(list((base/'internal-link-audit-logs').glob('run-*/exit.json')))==9
ast.parse((P/'audit_internal_links.py').read_text(),feature_version=(3,11))
result={'status':'PASS','final_zip_sha256':t.sha(z),'final_zip_bytes':z.stat().st_size,'zip_members':files,'shell_commands':commands,'python311_parse':'PASS','original_data':'synthetic only','runtime_product_changes':False}
(P/'DELIVERY_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));shutil.rmtree(base)
