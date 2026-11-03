from common import *
import os,shutil
P=ROOT/read(OUT/'ui-package.json')['path'];binding=read(P/'package-binding.json')
assert all(sha(P/n)==h for n,h in binding['files'].items())
sys.path.insert(0,str(ROOT/'90_RUNTIME/streamlit-knowledge-design/python'))
from streamlit.testing.v1 import AppTest
os.environ.pop('GENOS_ONTOLOGY_CODE_ROOT',None)
os.environ.pop('GENOS_RAG_ONTOLOGY_CONFIG',None)
os.environ.pop('GENOS_ONTOLOGY_HOST_FACTORY',None)
os.environ['ONTOLOGY_DASHBOARD_DEMO']='1'
app=AppTest.from_file(str(P/'streamlit_app.py'),default_timeout=20).run()
checks={'entry_loads':not app.exception and not app.error,
 'explicit_demo_label':any('체험용 예시' in str(c.value) for c in app.caption)}
import semantic_runtime
checks['backend_origin']=Path(semantic_runtime.__file__).resolve()==P/'code/02_BACKEND/semantic_runtime/__init__.py'
os.environ['GENOS_ONTOLOGY_CODE_ROOT']=str(ROOT/'08_DEPLOYMENT/RELEASES/scenario-cumulative-20261102-r1/code')
wrong=AppTest.from_file(str(P/'streamlit_app.py'),default_timeout=20).run()
checks['mixed_backend_rejected']=bool(wrong.exception) and 'root mismatch' in str(wrong.exception[0].value)
os.environ.pop('GENOS_ONTOLOGY_CODE_ROOT',None)
copy=ART/'ui-tamper-copy';shutil.copytree(P,copy)
(copy/'ontology_console.py').write_text((copy/'ontology_console.py').read_text()+'\n# synthetic tamper\n')
tampered=AppTest.from_file(str(copy/'streamlit_app.py'),default_timeout=20).run()
checks['changed_ui_rejected']=bool(tampered.exception) and 'package changed' in str(tampered.exception[0].value)
checks['original_package_unchanged']=all(sha(P/n)==h for n,h in binding['files'].items())
put(OUT/'ui-package-check.json',{'passed':all(checks.values()),'checks':checks,'model_calls':0,'field_deployed':False})
assert all(checks.values()),checks
print('UI package',len(checks),'checks PASS')
