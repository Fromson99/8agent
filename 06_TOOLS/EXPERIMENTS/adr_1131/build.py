from common import *
import sys,time
sys.dont_write_bytecode=True;f=read(ART/'freeze.json');code=ROOT/f['code_root'];sys.path.insert(0,str(code/'02_BACKEND'))
for n,h in f['files'].items():assert sha(code/n)==h,n
for n,h in f['inputs'].items():assert sha(ROOT/n)==h,n
from semantic_runtime.legal_agent.ontology_scenarios import compile_package
out=ART/'package.json';assert not out.exists(),'Completed compilation is immutable'
t=time.monotonic();package=compile_package(read(ART/'recipe.json'),read(ART/'build-input.json')['originals']);put(out,package)
put(ART/'build-result.json',{'status':'complete','paths':len(package['paths']),'components':len(read(ART/'recipe.json')['components']),'seconds':time.monotonic()-t,'package_sha256':sha(out),'new_model_calls':0,'compiled_before_questions':True,'authoring':package['authoring']})
(ART/'사전조립_시나리오.txt').write_text('연구용 원문 기반 사전 조립 결과 / 운영 승인·사건 적용 확정 아님\n\n'+'\n\n'+'\n\n'.join(p['id']+'\n'+p['body'] for p in package['paths'])+'\n')
print('COMPILED',len(package['paths']),'paths, model calls0')
