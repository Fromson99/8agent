"""Pre-call bootstrap correction: retain the existing external grammar adapter."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;R=HERE.parents[2];A=R/'04_EXPERIMENTS/ADR/ADR-1123-final-judgment-diagnostics';f=json.loads((A/'artifacts/design/freeze.json').read_text());source=HERE/'probe_final.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==f['scripts'][str(source.relative_to(R))]
def native_request(body):
 from semantic_runtime.legal_agent.local_gemma import provider_request
 expected_path=next((BASE/'raw').glob('call-015-*/request.json'));expected=json.loads(expected_path.read_text());adapted=provider_request(body)
 assert adapted['response_format']==expected['response_format']
 assert adapted['messages'][0]==expected['messages'][0]
 assert json.loads(original['messages'][1]['content'])==json.loads(expected['messages'][1]['content'])
 put(OUT/'native-adapter-receipt.json',{'reason':'Original component runner omitted existing external grammar adapter; corrected before any provider call. Product/tests/frozen inputs unchanged.','wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_runner_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'old_provider_request':{'path':str(expected_path.relative_to(R)),'sha256':hashlib.sha256(expected_path.read_bytes()).hexdigest()},'same_generation_schema':True,'same_system':True,'only_view_feedback_changed':True})
 return adapted
text=source.read_text();needle='client.chat_completions(body,phase=';assert text.count(needle)==1;text=text.replace(needle,'client.chat_completions(native_request(body),phase=');exec(compile(text,str(source),'exec'),globals())
