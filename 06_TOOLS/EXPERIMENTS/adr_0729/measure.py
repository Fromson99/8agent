from pathlib import Path
import sys,json,tarfile,hashlib
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0729/compact';cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];C=B/'revisions'/rev['revision_id']/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0729-compact-branch-choice-contract';O=A/'artifacts/run-001';O.mkdir(exist_ok=True)
for x in rev['files']:assert hashlib.sha256((R/x['frozen_path']).read_bytes()).hexdigest()==x['snapshot_sha256']
sys.path.insert(0,str(C/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent.wire_schema import factor_schema, compact_branch_choices
from semantic_runtime.legal_agent.gateway import compact_wire_view
size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')))
def expand(v,defs):
 if isinstance(v,list):return [expand(x,defs) for x in v]
 if isinstance(v,dict):
  if set(v)=={'$ref'}:return expand(defs[v['$ref'].split('/')[-1]],defs)
  return {k:expand(x,defs) for k,x in v.items() if k!='$defs'}
 return v
rows=[]
with tarfile.open(R/'04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification/artifacts/run-001/raw.tar.gz') as t:
 for name in t.getnames():
  if not(name.startswith('integrated/H02/provider/call-') and name.endswith('request.json')):continue
  o=json.load(t.extractfile(name));schema=o['response_format']['json_schema']['schema'];projected=compact_branch_choices(schema);factored=factor_schema(projected);assert expand(factored,factored.get('$defs',{}))==projected
  v=json.loads(o['messages'][1]['content'])['view'];after=v
  if v['source_stage'].startswith('source-law-navigation') or v['source_stage'].startswith('memory-assess'):
   # Replay projection over the recorded wire copy. Resolve old TEXT references first.
   texts={s['text_id']:s['text'] for s in v.get('sources',[]) if 'text_id' in s}
   def restore(x):
    if isinstance(x,list):return [restore(y) for y in x]
    if isinstance(x,dict):
     d={k:restore(y) for k,y in x.items() if k not in ('text_id','text_ref')}
     if 'text_ref' in x:
      r=x['text_ref'];d['text']=texts[r['id']][r['start']:r['end']]
     return d
    return x
   initial=restore(v);initial['input_projection']='compact-selection-source-v2';after=compact_wire_view(initial,v.get('phase','investigate'))
   assert [(x['source_id'],x.get('text')) for x in initial.get('sources',[])]==[(x['source_id'],x.get('text')) for x in after.get('sources',[])]
  rows.append({'phase':v['source_stage'],'schema_before':size(schema),'schema_after':size(projected),'transport_schema_after':size(factored),'view_before':size(v),'view_after':size(after),'projected_schema_expansion_exact':True})
result={'mode':'recorded-input-only','model_calls':0,'rows':rows,'schema_before':sum(x['schema_before'] for x in rows),'schema_after':sum(x['schema_after'] for x in rows),'view_before':sum(x['view_before'] for x in rows),'view_after':sum(x['view_after'] for x in rows),'token_claim':False,'note':'Separate deterministic representation ablation; new question routing/reading effects require fresh full API qualification'}
(O/'representation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
