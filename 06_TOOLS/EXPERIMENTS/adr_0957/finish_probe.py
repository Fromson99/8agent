from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,re,sys
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0957-multiturn-structured-scope';A=D/'artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
# Reproduce the unchanged working baseline without model calls.
sys.path.insert(0,str(R/'02_BACKEND'))
from semantic_runtime.legal_agent.memory_methods import normalize
from semantic_runtime.legal_agent.corrected_memory import COMMAND
from jsonschema import validate,ValidationError
command=dict(method_id='RESEARCH_REPLAN',document_scope_mode='AUTHORIZED',target='g',knowledge_id=None,stage='PLAN',task=None,source_category='KEEP',document_ids=None,facts=None,queries=['approval'],restore_event=None,restore_fields=[],format='prose',reason='synthetic reproduction')
value=normalize(command,{'goals':[{'id':'g'}],'knowledge':[],'allowed_documents':[{'id':str(i)} for i in range(161)]})
try:validate(value,COMMAND);baseline=False
except ValidationError as exc:baseline=exc.validator=='maxItems' and len(value['document_ids'])==161
assert baseline
suites=ET.parse(A/'frozen-contracts.xml').getroot().findall('testsuite')
assert all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in suites)
n=sum(int(s.get('tests',0)) for s in suites)
live=json.loads((A/'command-results.json').read_text());assert len(live['results'])==7 and all(r['pass'] for r in live['results'])
result={'strict_success':True,'checks':{'baseline_161_failure_reproduced':baseline,'contracts_pass':True,'seven_live_commands_pass':True},
 'contracts':n,'live_calls':live['model_calls'],'baseline':{'expected_failure':'SCHEMA_MAXITEMS','authorized_documents':161},
 'limits':['Synthetic command interpretation, not legal accuracy or GENOS certification.',
 'One pre-existing unit fixture lacks session.sources and is excluded; no production check was weakened.',
 'Development harness failures and repaired fixture metadata are retained; only frozen final contracts counted.']}
save(A/'result.json',result)
p=D/'실험/manifest.json';m=json.loads(p.read_text());m['runs'][0].update(status='complete',sha256=sha(A/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','expected_failure':'SCHEMA_MAXITEMS at161'},'scoped':{'status':'complete','contracts':n,'live_commands_pass':7,'live_commands_total':7}},usage={'model_calls':live['model_calls']},latency={'seconds':live['elapsed_seconds']},judge_disagreements=0,error_taxonomy=['baseline command maxItems','development harness binding','inherited stale unit fixture'])
save(p,m)
# Keep every required section; link raw records rather than duplicating them.
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scope-multiturn-contract.md']:
 old=path.read_text();header=''
 if old.startswith('---'):
  _,front,body=old.split('---',2);header='---'+front+'---\n';old=body
 headings=[line for line in old.splitlines() if line.startswith('#')]
 paragraphs={
 '1.':'Frozen candidate scope contracts and seven synthetic live command decisions passed. MAIN remains unchanged; independent qualification is required.',
 '2.':'AUTHORIZED replan expanded 161 authorized document IDs into a maxItems160 command. The corrected question can therefore fail before retrieval. The new command carries user title/structure selectors instead.',
 '3.':'Criteria fixed before live execution: same-goal continuation, correct KEEP/REPLACE/ADD/CLEAR, no inventory, exact original/ACL/revision checks. No legal answer labels or model judge.',
 '4.':'Candidate rev-001 and the complete staged code closure share exact hashes. Model data: artifacts/command-cases.json. Search/read contracts use tiny synthetic source trees and actual indexes; this live run performs no retrieval.',
 '5.':'Qwen3.8 qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback. Exact system/user/schema/response/usage are under artifacts/model. Inputs contain synthetic names only.',
 '6.':f'Frozen final regression: {n} passed. Live scope commands: 7/7, {live["model_calls"]} physical calls. Existing fixture failure and development harness attempts are retained, not included as successes.',
 '7.':'No offline model grading or majority vote. Deterministic assertions check returned fields, actual acquired source bounds, reference witnesses, resume, state hash and publication behavior.',
 '8.':'Command probe does not retrieve legal bodies; corpus/gold recall is not applicable. Runtime search filtering is tested structurally, without claiming measured production retrieval quality.',
 '9.':'The observed command failure is reproduced, and bounded selectors avoid inventory expansion. This supports the scoped implementation in synthetic cases, not general legal-answer correctness.',
 '10.':'Limited synthetic sample, external model only. Oracle/GENOS/internal model and full production law quality are unverified. Existing pre-MAIN working fixes are bound in the staged closure.',
 '11.':'No MAIN pointer changed by this probe. Reject promotion for source/permission/hash/revision failures. A later out-of-sample qualification must bind the unchanged candidate and actual local service.',
 '12.':'Reproduce with .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0957/run_contracts.py and probe.py, using the frozen manifest and stage hashes; recorded model calls must not be overwritten.'}
 out=header+'\n'
 for h in headings:
  key=next((k for k in paragraphs if h.lstrip('# ').startswith(k)),None)
  out+=h+'\n\n'+(paragraphs[key] if key else 'Exact records and limitations: [experiment manifest](manifest.json), artifacts/result.json, artifacts/command-results.json and artifacts/model. No result was promoted to a legal ground truth.')+'\n\n'
 path.write_text(out)
# File catalog deliberately excludes mutable status metadata and the shared code tree.
rows=[]
for path in sorted(A.rglob('*')):
 if not path.is_file() or path==A/'manifest.json' or path.is_relative_to(A/'code') or path.suffix in ('.sqlite','.pyc') or 'sqlite-' in path.name:continue
 rows.append({'path':str(path.relative_to(R)),'sha256':sha(path),'bytes':path.stat().st_size,'description':'Exact probe or development record; see result for inclusion/exclusion.','contains_raw_prompts_and_outputs':path.is_relative_to(A/'model')})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0957','created_at':m['reservation']['created_at'],'files':rows})
print('probe complete',n,'contracts, 7/7 commands')
