from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0962-scoped-clear-boundary';A=D/'artifacts';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
live=json.loads((A/'command-results.json').read_text());assert len(live['results'])==1 and live['results'][0]['pass']
suites=ET.parse(A/'frozen-contracts.xml').getroot().findall('testsuite');assert all(int(x.get('failures',0))==int(x.get('errors',0))==0 for x in suites);n=sum(int(x.get('tests')) for x in suites)
consumer=json.loads((A/'consumer-candidate.json').read_text());assert consumer['status']=='PASS' and all(consumer['checks'].values())
result={'strict_success':True,'checks':{'known_clearance_regression':True,'all_contracts':True,'real_data_service_consumer':True},'contracts':n,'model_calls':live['model_calls'],'consumer':{'path':str((A/'consumer-candidate.json').relative_to(R)),'sha256':sha(A/'consumer-candidate.json')},'limits':['In-sample prompt correction; independent unchanged-code holdout required for MAIN.','Ambiguous stored coordinate refused; consumer selects a uniquely stored coordinate.','Named document plus unrestricted-clear request needs clarification; never silently global.','Stale pre-existing fixture excluded. No GENOS/internal-model/Oracle execution.']};save(A/'result.json',result)
paragraphs=[
'Known whole-document regression and120 structural contracts passed. This is a development probe; MAIN unchanged.',
'Previous qualification misread a named regulation in full as unrestricted search. The prompt distinguishes document-wide from all-documents, and the host rejects CLEAR if an authorized document name or alias appears in the current utterance.',
'No failed output was relabeled as success. ADR0960 provider429 and ADR0961 interpretation failure remain immutable evidence. Candidate scope/read/state contracts remain enforced.',
'101 candidate files bind complete executable closure. Concurrent request_repair, decision_projection and law_navigation edits were merged before frozen execution and their22 contract tests included.',
'One known regression, two physical calls through Qwen3.8 Parasail FP8 reasoning none; no fallback. Five unused cases were withheld before calls for separate qualification.',
f'All{n} deterministic contracts passed. Real-data service HEALTH, exact417 serving-file hashes, document/coordinate resolution and scoped original read passed. Consumer model calls0.',
'Development consumer fixture errors (null coordinate and incomplete hit identity) are retained. Fixes changed harness only. A stored duplicate article number correctly produced UnresolvedScope; it was not bypassed.',
'No retrieval-quality comparison, legal-answer scoring or gold recall claim. Tiny actual indexes verify filtering before pagination; real-data consumer confirms actual stored original access.',
'CLEAR guard is intentionally conservative when a named document and global removal are mixed: prior state is preserved and clarification is required. Explicit named-document expansion uses REPLACE with structure null.',
'External synthetic command behavior is not internal GENOS certification. Oracle serving compliance and general legal correctness are outside this validation.',
'MAIN remains generation96. Independent unchanged-code qualification must pass before a hash-pinned validated promotion; post-activation active binding must pass or roll back.',
'Reproduction: frozen candidate manifest, stage.json, run_contracts.py, consumer.py and probe.py. Raw model requests/responses/usage in artifacts/model; avoid repeating them in prose.'
]
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scoped-boundary-heldout.md']:
 old=path.read_text();front=''
 if old.startswith('---'):
  _,f,old=old.split('---',2);front='---'+f+'---\n'
 out=front+'\n'
 for h in old.splitlines():
  if h.startswith('#'):
   s=h.lstrip('# ');idx=next((i for i in range(12) if s.startswith(str(i+1)+'.')),None)
   out+=h+'\n\n'+(paragraphs[idx] if idx is not None else 'Exact evidence: artifacts/result.json, artifacts/command-results.json, artifacts/consumer-candidate.json and experiment manifest. This probe does not activate MAIN.')+'\n\n'
 path.write_text(out)
p=D/'실험/manifest.json';m=json.loads(p.read_text());m['runs'][0].update(status='complete',sha256=sha(A/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'ADR0961 rejected'},'guarded':{'status':'complete','contracts':n,'known_regression_pass':True}},usage={'model_calls':live['model_calls']},latency={'seconds':live['elapsed_seconds']},judge_disagreements=0,error_taxonomy=['prior global scope misinterpretation','development consumer harness repairs','concurrent working upstream update'])
for q in m['questions']:q['sha256']=sha(D/'실험'/q['file'])
save(p,m)
rows=[]
for p in sorted(A.rglob('*')):
 if p.is_file() and p.name!='manifest.json' and not p.is_relative_to(A/'code') and not any(x.startswith('runtime-') for x in p.parts) and p.suffix not in ('.sqlite','.pyc') and 'sqlite-' not in p.name:rows.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Development probe exact evidence; inherited failure records retained','contains_raw_prompts_and_outputs':p.is_relative_to(A/'model')})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0962','created_at':m['reservation']['created_at'],'files':rows})
print('Probe complete',n,'contracts; known regression passed')
