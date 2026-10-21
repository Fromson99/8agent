"""Inspect recorded schema/response boundaries without model calls or product writes."""
import gzip, json, sys
from pathlib import Path
from jsonschema import Draft202012Validator
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0855-fulltext-schema-live-audit-v2'
f=json.loads((A/'artifacts/design/frozen.json').read_text());sys.dont_write_bytecode=True;sys.path.insert(0,str(R/f['release']['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.minimal_output import Projection
readgz=lambda p:json.load(gzip.open(p,'rt',encoding='utf8'))
rows=[]
for case in f['cases']:
 D=A/'artifacts'/case['run_id']
 if not (D/'generations.json').exists():continue
 for generation in json.loads((D/'generations.json').read_text()):
  if generation.get('accepted') is not False:continue
  i=generation['number'];saved=readgz(D/'canonical'/f'{i:03d}.json.gz');view=saved['view'];schema=saved['schema']
  if view.get('input_projection')=='compact-selection-source-v3':schema=NavigationReferences(view).schema(schema)
  projection=Projection(schema)
  for call in json.loads((D/'calls.json').read_text()):
   if call['canonical_generation']!=i or call.get('http_status')!=200:continue
   rawfile=next((D/'provider').glob(f"call-{call['call']:03d}-*/response.json"));response=json.loads(rawfile.read_text());raw=json.loads(response['choices'][0]['message']['content'])
   wire=readgz(D/'wire'/f"{call['call']:03d}-before-provider.json.gz")['response_format']['json_schema']['schema']
   row={'run':case['run_id'],'call':call['call'],'stage':generation['stage'],'wire_matches_selected_projection':wire==projection.wire,'raw_matches_wire_schema':Draft202012Validator(wire).is_valid(raw),'next_action':raw.get('next_action'),'raw_keys':list(raw),'wire_required':wire.get('required'),'canonical_required':schema.get('required'),'wire_schema_bytes':call['schema_bytes'],'canonical_schema_bytes':generation['canonical_schema_bytes'],'observed_rejection':generation.get('error')}
   try:projection.expand(raw);row['reproduced_reconstruction_error']=None
   except Exception as e:row['reproduced_reconstruction_error']=str(e)
   rows.append(row)
(A/'artifacts/boundary-audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False,indent=2))
