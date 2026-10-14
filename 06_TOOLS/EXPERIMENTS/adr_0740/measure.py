from pathlib import Path
import sys,json,tarfile,hashlib
from copy import deepcopy
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0740/integrated';cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];C=B/'revisions'/rev['revision_id']/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0740-completed-search-native-page';O=A/'artifacts/run-001';O.mkdir(exist_ok=True)
for x in rev['files']:assert hashlib.sha256((R/x['frozen_path']).read_bytes()).hexdigest()==x['snapshot_sha256']
sys.path.insert(0,str(C/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent.navigation_input import NavigationReferences,compact_cards,expand_cards,AUDIT_FIELDS
size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
def strip(v):
 if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k not in AUDIT_FIELDS}
 if isinstance(v,list):return [strip(x) for x in v]
 return v
rows=[]
for number,arm in [(728,'integrated'),(730,'compact')]:
 parent=next((R/'04_EXPERIMENTS/ADR').glob(f'ADR-{number:04}-*'))
 with tarfile.open(parent/'artifacts/run-001/raw.tar.gz') as t:
  for name in t.getnames():
   if not(name.startswith(arm+'/') and '/provider/call-' in name and name.endswith('request.json')):continue
   o=json.load(t.extractfile(name));message=json.loads(o['messages'][1]['content']);v=message['view'];phase=v.get('source_stage','')
   codec=NavigationReferences(v)
   after=compact_cards(codec.view(v)) if phase.startswith(('source-law-navigation','memory-assess')) else v
   restored=codec.restore(expand_cards(after)) if after is not v else v
   assert restored==strip(v) if after is not v else restored==v,(number,name)
   if after is not v:
    schema=o['response_format']['json_schema']['schema']
    # Every enum/const round trips with the same frozen view's vocabulary.
    alias_schema=codec.schema(schema)
    reverse=NavigationReferences({});reverse.forward=codec.reverse
    assert reverse.schema(alias_schema)==schema
   rows.append({'parent_adr':number,'request_path':name,'phase':phase,'view_before':size(v),'view_after':size(after),'exact_reconstruction_excluding_audit_hashes':True})
before=sum(r['view_before'] for r in rows);after=sum(r['view_after'] for r in rows)
result={'mode':'recorded-input-only','model_calls':0,'rows':rows,'view_before':before,'view_after':after,'reduction':1-after/before,'threshold':.2,'passed':after<=before*.8,'token_claim':False,'omitted_audit_fields':sorted(AUDIT_FIELDS),'all_source_text_and_action_values_preserved':True}
(O/'representation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
