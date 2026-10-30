"""One new correction against an immutable previously delivered public screen."""
from common import *
import sys,gzip,copy,time,traceback
f=read(DES/'freeze.json');C=ROOT/f['code_root'];OUT=ART/'run-002';OUT.mkdir(exist_ok=True)
assert all(read(ART/('check-'+n+'.json'))['status']==0 for n in ('primary','support','modes'))
for n,h in f['files'].items():assert sha(C/n)==h
for n,h in f['scripts'].items():assert sha(ROOT/n)==h
inputs=read(DES/'final-probe-inputs.json')
for n,h in inputs.items():assert sha(ROOT/n)==h
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.legal_agent import read_judgment_final as fj,output_contract as oc
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.minimal_output import Projection
from lawrag.research.experiment_client import ExperimentClient
BASE=ROOT/'04_EXPERIMENTS/ADR/ADR-1120-full-alternative-native-check/artifacts/run-002/fsc-hard-005'
def gz(p):return json.load(gzip.open(p,'rt'))
c=gz(BASE/'canonical/015.json.gz');rejected=gz(BASE/'canonical/014-output.json.gz');body=gz(BASE/'wire/015.json.gz');refs=NavigationReferences(c['view']);projection=Projection(refs.schema(c['schema']));assert projection.wire==body['response_format']['json_schema']['schema']
try:fj.validate_review(rejected,c['view']['read_judgments'],c['view']['evidence_options'])
except oc.OutputContractError as exc:feedback={'errors':str(exc),'validation':oc.diagnostics(exc)}
else:raise AssertionError('preserved failure no longer fails')
feedback=refs.view({'repair_feedback':feedback})['repair_feedback'];original=copy.deepcopy(body);view=json.loads(body['messages'][1]['content']);oldfeedback=copy.deepcopy(view['view']['repair_feedback']);view['view']['repair_feedback'].update(feedback);body['messages'][1]['content']=json.dumps(view,ensure_ascii=False,separators=(',',':'))
compare=copy.deepcopy(view);compare['view']['repair_feedback']=oldfeedback;assert compare==json.loads(original['messages'][1]['content']);assert all(body[k]==original[k] for k in body if k!='messages');assert body['messages'][0]==original['messages'][0]
put(OUT/'probe-binding.json',{'source_screen':str((BASE/'canonical/015.json.gz').relative_to(ROOT)),'only_changed_fields':['view.repair_feedback.errors','view.repair_feedback.validation'],'full_native_run':False,'prior_model_calls_replayed':0,'new_model_call_limit':1,'candidate':f['binding'],'source_question_in_sample':True})
client=ExperimentClient(ROOT,OUT/'raw',max_calls=1,max_output_tokens=None,max_repairs=0);start=time.monotonic();r={'completed':False,'full_native_run':False,'quality_certified':False}
try:
 raw=client.chat_completions(body,phase='final-judgment-correction',timeout_seconds=180);value=oc.strict_json(raw['body_json']['choices'][0]['message']['content']);expanded=projection.expand(value);decoded=refs.decode(expanded,refs.schema(c['schema']));put(OUT/'decoded.json',decoded);fj.validate_review(decoded,c['view']['read_judgments'],c['view']['evidence_options']);r.update(completed=True,claims=len(decoded['claims']),judgments=len(decoded[fj.FIELD]['judgments']),dispositions=[x['disposition'] for x in decoded[fj.FIELD]['judgments']])
except Exception as exc:r.update(error_type=type(exc).__name__,error=str(exc));(OUT/'error.txt').write_text(traceback.format_exc())
finally:r.update(new_model_calls=client.calls,usage=client.usage,elapsed_seconds=time.monotonic()-start);put(OUT/'result.json',r);print({k:v for k,v in r.items() if k!='usage'})
