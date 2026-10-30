from common import *
import subprocess,time
T=Path(__file__).parent
def run(name,*args):
 with (ART/(name+('-'+'-'.join(args) if args else '')+'.log')).open('x') as log:
  p=subprocess.run([sys.executable,'-u',str(T/(name+'.py')),*args],stdout=log,stderr=subprocess.STDOUT)
 print(name,args,'exit',p.returncode,flush=True);return p.returncode
assert read(ART/'technical-final.json')['failed']==0
assert run('stage')==0
assert run('working')==0
assert run('working_check')==0
assert run('same_serving')==0
for mode in ('main112','candidate'):run('regression',mode)
tag=read(DES/'freeze.json')['execution_id'];p=read(ART/('regression-main112-'+tag+'.json'));c=read(ART/('regression-candidate-'+tag+'.json'))
P={r['test']:r['status'] for r in p['rows']};C={r['test']:r['status'] for r in c['rows']}
result={'baseline':{'passed':p['passed'],'failed':p['failed']},'candidate':{'passed':c['passed'],'failed':c['failed']},'same_tests':P.keys()==C.keys(),'new_regressions':[n for n in C if C[n]!='passed' and P.get(n)=='passed'],'improved':[n for n in C if C[n]=='passed' and P.get(n)!='passed'],'status_differences':[n for n in C if C[n]!=P.get(n)],'import_leaks':{'baseline':p['import_leaks'],'candidate':c['import_leaks']},'new_model_calls':0}
put(ART/'regression-comparison.json',result)
assert result['same_tests'] and not result['new_regressions'] and not p['import_leaks'] and not c['import_leaks'],result
print('INTEGRATION_CHECKS_PASSED',result,flush=True)
