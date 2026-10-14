from pathlib import Path
import importlib.util,json,hashlib
R=Path(__file__).resolve().parents[3];O=R/'08_DEPLOYMENT/GENOS/handoffs/successful_shortcut_20261013_r1';O.mkdir(exist_ok=False);P=O.with_name('ad_request_logs_20261013_r2');Q=O.with_name('ad_request_logs_20261013_r1')
s=(P/'apply_patch.py').read_text().replace('GENOS_AD_REQUEST_LOGS_20261013_R2','GENOS_SUCCESSFUL_SHORTCUT_20261013_R1').replace('ad-request-logs-r2','successful-shortcut-r1');(O/'apply_patch.py').write_text(s)
s=(Q/'build_delivery.py').read_text().replace("NAME='GENOS_AD_REQUEST_LOGS_20261013_R1'","NAME='GENOS_SUCCESSFUL_SHORTCUT_20261013_R1'").replace("PARENT=OUT.with_name('model_stream_fix_20261013_r1')","PARENT=OUT.with_name('ad_request_logs_20261013_r2')")
s=s.replace("PARENT/'build_delivery.py'","PARENT.with_name('ad_request_logs_20261013_r1')/'build_delivery.py'").replace("'/stream-fix-r1'","'/ad-logs-r2'")
s=s.replace("PARENT/'GENOS_MODEL_STREAM_FIX_20261013_R1_RUN.txt'","PARENT/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt'")
s=s.replace(".replace('model-stream-fix-r1','ad-request-logs-r1').replace('MODEL_STREAM_FIX','AD_REQUEST_LOGS')",".replace('ad-request-logs-r2','successful-shortcut-r1').replace('AD_REQUEST_LOGS','SUCCESSFUL_SHORTCUT')")
(O/'build_delivery.py').write_text(s)
spec=importlib.util.spec_from_file_location('new_handoff',O/'build_delivery.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
_,payload,_=next(b.predecessors())
names=['02_BACKEND/semantic_runtime/'+n for n in ['ad_backend.py','ad_mode.py','ad_store.py','ad_language.py']]+['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ['core_evidence_route.py','shortcut_repository.py','unified_runtime.py','successful_answer.py']]+['02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py']
for n in names:
 if n in payload:
  p=O/'preimage'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload[n])
(O/'WORKING_INTEGRATION.json').write_text(json.dumps({'files':{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names}},indent=2)+'\n')
print(O)
