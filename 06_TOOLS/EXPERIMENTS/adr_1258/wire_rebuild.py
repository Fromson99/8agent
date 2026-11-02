"""Rebuild actual user message projections from captured canonical views; offline only."""
from pathlib import Path
import json,gzip,sys,copy,types
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live';O=A/'artifacts/run-001';P=O/'live/gold-369';D=A/'artifacts/design'
def read(p):
 with gzip.open(p,'rt') if str(p).endswith('.gz') else p.open() as z:return json.load(z)
C=R/read(D/'before.json')['binding']['engine_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent.gateway import ModelGateway
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.minimal_output import prepare_request
profile=read(P/'binding.json')['profile'];rows=[];canons=[p for p in sorted((P/'canonical').glob('*.json.gz')) if '-output' not in p.name];calls=read(P/'calls.json');assert len(canons)==len(calls)==7
for index,p in enumerate(canons,1):
 v=read(p);wire=read(P/'raw'/f'{index:03d}'/'request.json.gz');gateway=ModelGateway.__new__(ModelGateway);gateway.profile=profile;gateway.compact=profile.get('schema_version')=='system-harness-profile-v5';gateway.domain={};gateway.system='';gateway.prompts={v['phase']:''};gateway.transport=types.SimpleNamespace(binding=profile['model_binding']);gateway.protocol=types.SimpleNamespace(schema=lambda name:copy.deepcopy(v['schema']))
 request=gateway.request(v['phase'],copy.deepcopy(v['view']),wire['response_format']['json_schema']['name']);request,_=prepare_request(request,gateway._generation_schema,partial_contract=False);expected=provider_request(request)
 a=[m['content'] for m in expected['messages'] if m['role']=='user'];b=[m['content'] for m in wire['messages'] if m['role']=='user'];same=a==b;rows.append({'number':index,'stage':v['view'].get('source_stage',v['phase']),'user_message_exact':same,'schema_exact_after_projection':expected['response_format']['json_schema']['schema']==wire['response_format']['json_schema']['schema']})
all_exact=all(v['user_message_exact'] for v in rows)
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(O/'wire-rebuild.json',{'new_models':0,'database_writes':0,'request_count':len(rows),'checks':rows,'all_user_messages_exact':all_exact,'verified_user_messages':sum(v['user_message_exact'] for v in rows),'status':'complete' if all_exact else 'partial_reconstruction','initial_request_question_preserved':read(D/'cases.json')[0]['request']['json']['question'] in read(P/'raw/001/request.json.gz')['messages'][-1]['content'],'unresolved_reconstruction':'Simple default gateway rebuild differs for initial bounded entry only; source-navigation/final/repair user messages and schemas six exact. Full first-request equivalence not claimed; raw original retained.','all_schema_projections_exact':all(v['schema_exact_after_projection'] for v in rows),'boundary':'Actual research archived user-message bytes rebuilt from captured canonical view using frozen selected gateway. Source text/ACL verified separately. Custom system prompt/entire authenticated payload not independently reconstructed; product NFS diagnostics remain UNCONFIGURED.'});print('User message exact',len(rows),'schema exact',sum(v['schema_exact_after_projection'] for v in rows))
