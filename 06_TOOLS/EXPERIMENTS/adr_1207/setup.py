from common import *
import shutil
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1206-domain-profile-real-records'
pf=read(parent/'artifacts/design/freeze.json');C=ROOT/pf['code_root'];m=read(ADR/'실험/manifest.json')
for name in ('baseline.json','cases.json','originals.json'):put(DES/name,read(parent/'artifacts/design'/name)) if name=='baseline.json' else raw(DES/name,read(parent/'artifacts/design'/name))
criteria=read(parent/'artifacts/design/criteria.json')
criteria.update(hypothesis='A compact, exactly expandable schema described in the prompt with JSON-object transport may avoid strict-grammar provider failure while unchanged original validators still enforce all original contracts.',changes='Only research transport: repeated schema subtrees factored into local $defs, full equivalent schema in system prompt, response_format=json_object; original output validation/semantics/model/data/source/budgets unchanged.',stop_rule='One fixed follow-up, no more transport or prompt variants in this user-requested demonstration after results.')
put(DES/'criteria.json',criteria);put(ART/'evaluation-only/expectations.json',read(parent/'artifacts/evaluation-only/expectations.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Real provider completion and original server contract acceptance, then original two-stage authoring demonstration',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'portable','role':'candidate','derived_from':['ADR-1206-experiment-v1/profile'],'changes':criteria['changes'],'controls':'Exact parent483files/data/profile/glossary/model/budget; no added gold or legal hint'}])
m['runs'][0].update(arm_ids=['portable'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
pm=read(parent/'실험/manifest.json');m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting']
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ac.snapshot(ADR,'portable',list(pf['files']),experiment_id=m['experiment_id'],arm_id='portable',run_ids=['run-001'])
for n,h in pf['files'].items():
 assert sha(C/n)==h
 shutil.copyfile(C/n,candidate/'snapshot'/n)
helper='02_BACKEND/semantic_runtime/ontology_work/portable_transport.py'
code='''"""Experimental wire projection; original validators remain authoritative."""
from collections import Counter
import hashlib,json

def compact(schema):
    counts=Counter();values={}
    def collect(value):
        if isinstance(value,dict):
            key=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if len(key)>100 and (isinstance(value.get('type'),str) or 'anyOf' in value):
                counts[key]+=1;values[key]=value
            for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    collect(schema)
    names={key:'s'+hashlib.sha256(key.encode()).hexdigest()[:16] for key,n in counts.items() if n>1}
    def pack(value,own=None):
        if isinstance(value,dict):
            key=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            if key in names and key!=own:return {'$ref':'#/$defs/'+names[key]}
            return {k:pack(v) for k,v in value.items()}
        if isinstance(value,list):return [pack(v) for v in value]
        return value
    result=pack(schema);result['$defs']={names[k]:pack(values[k],k) for k in sorted(names)}
    def expand(value):
        if isinstance(value,dict):
            if set(value)=={'$ref'}:return expand(result['$defs'][value['$ref'].split('/')[-1]])
            return {k:expand(v) for k,v in value.items() if k!='$defs'}
        if isinstance(value,list):return [expand(v) for v in value]
        return value
    if expand(result)!=schema:raise ValueError('schema projection changed semantics')
    return result

def request(model,prompt,context,schema):
    contract=compact(schema)
    instruction='\\n\\n출력은 아래 JSON Schema를 충족하는 JSON 객체 하나만 작성한다. $defs/$ref는 반복되는 같은 계약의 정의다. 설명·코드블록은 쓰지 않는다.\\n'
    return {'model':model,'messages':[{'role':'system','content':prompt+instruction+json.dumps(contract,ensure_ascii=False,separators=(',',':'))},{'role':'user','content':json.dumps(context,ensure_ascii=False)}],'temperature':0,'response_format':{'type':'json_object'}}
'''
p=candidate/'snapshot'/helper;p.write_text(code);ac.register_file(candidate,helper,upstream_state='absent');ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];code_root=candidate/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={**pf['files'],helper:sha(code_root/helper)}
put(DES/'candidate.json',{'code_root':str(code_root.relative_to(ROOT)),'files':files,'candidate_revision':binding})
# Exact expansion proves the projection preserves every schema field, not just examples.
sys.path.insert(0,str(code_root/'02_BACKEND'))
from semantic_runtime.ontology_work.profile import compile_profile
from semantic_runtime.ontology_work.portable_transport import compact,request
from jsonschema import Draft202012Validator
p=compile_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'));checks=[]
for key in ('output_schema','accumulation_schema'):
 x=p[key];c=compact(x);Draft202012Validator.check_schema(c)
 for value in ({},[],{'observations':[]},{'graph':{}},None):assert Draft202012Validator(x).is_valid(value)==Draft202012Validator(c).is_valid(value)
 checks.append({'schema':key,'original_chars':len(json.dumps(x,ensure_ascii=False,separators=(',',':'))),'compact_chars':len(json.dumps(c,ensure_ascii=False,separators=(',',':'))),'exact_expansion':True,'invalid_samples_same':5})
put(ART/'projection-checks.json',{'checks':checks,'semantic_fields_changed':0,'original_validation_preserved':True,'provider_grammar_used':False,'new_model_calls':0})
print(checks)
