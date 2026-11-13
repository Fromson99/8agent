"""ADR-1514 (repeat of ADR-1513, where Reka answered normally so no switch happened): live check of lawrag.research.provider_fallback.send_with_fallback (frozen before the call).
Request: the stored wire request on which Reka and Parasail wrote only newlines (ADR-1511 cmp-soundness call 3; ADR-1512 T2).
Order forced to Reka -> Near AI so the runaway happens first. Expected: Reka attempt ends as BLANK_STALL after about
60 s (stall limit, policy 00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json), then Near AI returns a complete answer that is
valid JSON for the request schema, within the 180 s per-call deadline. Then the default order (Near AI first) once.
Pass: one runaway caught and answered by the next provider (see criteria in results); inconclusive if none happens."""
import sys,json,gzip,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'02_BACKEND'))
import jsonschema
from lawrag.research.provider_fallback import load_policy,send_with_fallback
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.legal_agent import errors
ADR=next((ROOT/'04_EXPERIMENTS/ADR').glob('ADR-1514-*'));ART=ADR/'artifacts'
SRC=ROOT/'04_EXPERIMENTS/ADR/ADR-1511-compare-research-budget-qwen/artifacts/live/candidate/cmp-soundness/raw/call-003/request.json.gz'
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=1))
if sys.argv[1]=='freeze':
    assert not (ART/'freeze.json').exists()
    put(ART/'freeze.json',{'check_py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'provider_fallback_py':hashlib.sha256((ROOT/'02_BACKEND/lawrag/research/provider_fallback.py').read_bytes()).hexdigest(),
        'policy':hashlib.sha256((ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json').read_bytes()).hexdigest(),
        'request':hashlib.sha256(SRC.read_bytes()).hexdigest(),'model_calls_before_freeze':0});print('frozen');sys.exit()
fz=json.loads((ART/'freeze.json').read_text())
assert hashlib.sha256((ROOT/'02_BACKEND/lawrag/research/provider_fallback.py').read_bytes()).hexdigest()==fz['provider_fallback_py']
policy,ph=load_policy(ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_FALLBACK.json');assert ph==fz['policy']
body=json.loads(gzip.decompress(SRC.read_bytes()));body.pop('provider',None);body.pop('stream',None)
schema=body['response_format']['json_schema']['schema']
client=ExperimentClient(ROOT,ART/'client',max_calls=12,max_repairs=0)
results=[]
# Up to 3 rounds of (Reka -> Near AI) and (Parasail -> Near AI); stop as soon as one runaway was caught and answered.
for rnd in range(3):
    for first in ('Reka','Parasail'):
        name=f'r{rnd+1}-{first}-first';order=[first,'Near AI']
        pol=dict(policy,providers=[p for n in order for p in policy['providers'] if p['name']==n])
        begin=time.monotonic()
        try:
            env=send_with_fallback(client,body=body,ticket={'deadline':time.monotonic()+180,'remaining_seconds':180,'attempt_id':name},
                phase=name,error_module=errors,request_encoder=lambda b:dict(b),policy=pol,policy_sha256=ph)
            text=env['body_json']['choices'][0]['message']['content'];v=json.loads(text);jsonschema.validate(v,schema)
            results.append({'case':name,'ok':True,'seconds':round(time.monotonic()-begin,3),'provider':env['body_json']['provider'],
                            'failures':[a['failure'] for a in env['fallback_attempts']],'attempts':env['fallback_attempts']})
        except Exception as exc:
            results.append({'case':name,'ok':False,'seconds':round(time.monotonic()-begin,3),'error':type(exc).__name__+': '+str(exc)[:300],
                            'attempts':(getattr(exc,'response',None) or {}).get('fallback_attempts')})
        print(json.dumps({k:v for k,v in results[-1].items() if k!='attempts'},ensure_ascii=False),flush=True)
        if results[-1]['ok'] and results[-1]['failures'][0] is not None:break
    if results and results[-1]['ok'] and results[-1]['failures'][0] is not None:break
caught=[r for r in results if r['ok'] and r['failures'][0] in ('BLANK_STALL','NO_NONBLANK','ATTEMPT_DEADLINE')]
put(ART/'results.json',{'results':results,'physical_calls':client.calls,'switch_observed':bool(caught),
    'pass':bool(caught) and all(r['ok'] for r in results),
    'criteria':'pass = at least one runaway/no-content attempt caught and the next provider returned a schema-valid answer within the call; inconclusive if no runaway happened in 6 tries'})
print('physical',client.calls,'pass',json.loads((ART/'results.json').read_text())['pass'],'switch_observed',json.loads((ART/'results.json').read_text())['switch_observed'])
