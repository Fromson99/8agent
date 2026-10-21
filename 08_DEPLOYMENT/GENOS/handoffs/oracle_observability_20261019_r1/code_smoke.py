import asyncio, importlib.util, json, os, sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(root),str(root/'02_BACKEND'),str(root/'08_DEPLOYMENT/GENOS')]
os.environ.update(GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',GENOS_SYSTEM_LOG_ENABLED='0')
files=['service.py','02_BACKEND/semantic_runtime/oracle_dp.py','02_BACKEND/semantic_runtime/oracle_dp_io.py','02_BACKEND/semantic_runtime/preparation_progress.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
for name in files:compile((root/name).read_bytes(),name,'exec')
import service
assert Path(service.__file__).resolve()==root/'service.py'
def forbidden():raise AssertionError('Control reached AD storage')
service._ad_control=forbidden
result=asyncio.run(service.service({}, {'API_TYPE':'WARMUP_STATUS','request_id':'installation-smoke'}))
assert result['body']['state']=='NOT_STARTED'
spec=importlib.util.spec_from_file_location('installed_workflow',root/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
w._post_code_serving=lambda payload:{'state':'RUNNING','worker_id':'mock','progress':{'phase':'source.download','rows_done':10,'rows_total':20,'elapsed_seconds':5,'last_progress_age_seconds':1}}
response=asyncio.run(w.run({'question':'WARMUP_STATUS','request_id':'installation-workflow'}))
assert '10/20' in response['text']
print(json.dumps({'status':'PASS','root':str(root),'python':sys.version,'compiled':len(files),'service_control':'PASS','workflow_progress':'PASS'}))
