"""Same failing tests against the parent runtime; no model or frozen source edits."""
from common import *
import sys
s=read(ART/'stage.json');T=ROOT/s['roots']['candidate'];parent=read(ROOT/s['parent']/'artifacts/stage.json');C=ROOT/parent['roots']['candidate']
failures=read(ART/'qualification.json')['failures'];tests=[]
for f in failures:
 module=f['test']['classname'].rsplit('.',1)[-1]
 tests.append(str(T/'05_TESTS/CONTRACTS'/(module+'.py'))+'::'+f['test']['name'])
sys.argv=[__file__,'-q','--junitxml='+str(ART/'baseline-regressions.xml'),*tests]
source=Path(__file__).with_name('run_contracts.py').read_text()
source=source.replace("C=ROOT/read(ART/'stage.json')['roots'][arm]",'C='+repr(str(C))+";C=Path(C);T=Path("+repr(str(T))+")")
source=source.replace("str(C/'05_TESTS/CONTRACTS')","str(T/'05_TESTS/CONTRACTS')")
source=source.replace("==ROOT:kw['contracts_root']=C","in (ROOT,T):kw['contracts_root']=C")
exec(compile(source,__file__,'exec'))
