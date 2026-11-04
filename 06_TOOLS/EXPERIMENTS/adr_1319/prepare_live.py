from common import *
import shutil,ast
C=ROOT/read(DES/'candidate-repaired.json')['code_root']
grant=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');allowed=sorted(grant['public_document_ids'])
cases=[{'id':'repeat','arms':['repaired'],'document_ids':allowed,'steps':[
 {'number':1,'question':'상법상 정기주주총회는 언제 소집해야 하나요?','mode':'외규'},
 {'number':2,'question':'상법상 정기주주총회는 언제 소집해야 하나요?','mode':'외규'},
 {'number':3,'question':'그럼 임시총회는 언제 소집하나요?','mode':'외규'},
 {'number':4,'question':'상법 제369조의 의결권 원칙을 알려줘.','mode':'외규'}]}]
put(DES/'live-cases.json',cases)
put(DES/'authorization.json',{'user_request':read(DES/'criteria.json')['user_authorization'],'prior_explicit_authorization':grant['workflow_authorization']['authorization_text'],'public_document_ids':allowed,'cases_sha256':sha(DES/'live-cases.json'),'grant_path':'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','grant_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'internal_relabeling':False,'quality_certified':False})
put(DES/'source-scope.json',{'public':allowed,'internal':[]})
old=ROOT/'06_TOOLS/EXPERIMENTS/adr_1318';s=(old/'live_public.py').read_text().replace('R2 exact questions via selected','Frozen public multi-turn questions via candidate').replace('adr1318','adr1319').replace('ADR1318-native-main135','ADR1319-main138-repaired')
s=s.replace("assert arm=='selected-main'","assert arm=='repaired'").replace("DES/'cases.json'","DES/'live-cases.json'").replace("DES/'candidate-public.json'","DES/'candidate-repaired.json'")
s=s.replace("sha(C/n)==sha(selected_code/n)==h","sha(C/n)==h").replace("nearai-only.json","provider-policy.json")
s=s.replace("assert len(t.provider_policy['providers'])==1","assert len(t.provider_policy['providers'])==2")
s=s.replace("'effective_provider_switches':0,'product_code_unchanged':True","'max_provider_switches':t.provider_policy['max_provider_switches'],'frozen_candidate':True")
s=s.replace("if total>=500:","if total>=160:").replace('Global experiment500','Global experiment160')
s=s.replace("payload['provider']==route({'tag':'near-ai/fp8','name':'Near AI'})", "payload['provider'] in [route(p) for p in t.provider_policy['providers']]")
s=s.replace("'selected_equivalent':True", "'selected_equivalent':False,'frozen_candidate':True")
s=s.replace("'product_state_rewritten':False", "'product_state_rewritten':False")
(Path(__file__).parent/'live_public.py').write_text(s);ast.parse(s)
oldart=ROOT/'04_EXPERIMENTS/ADR/ADR-1318-integration-search-r2-answer-check/artifacts'
shutil.copytree(oldart/'transport',ART/'transport')
s=(old/'audit.py').read_text().replace("candidate-public.json","candidate-repaired.json")
(Path(__file__).parent/'audit.py').write_text(s)
paths=[*Path(__file__).parent.glob('*.py'),*(ART/'transport').rglob('*.py'),DES/'criteria.json',DES/'live-cases.json',DES/'authorization.json',DES/'provider-policy.json',DES/'candidate-repaired.json']
put(DES/'freeze-public.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'before_model_calls':True})
print('Frozen public4turns; ParasailFP8 primary known429-only NearAI; no private source')
