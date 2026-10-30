from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1095-ontology-assess-wire'
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1095/direct-r1';S=C/'snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cm=json.loads((C/'candidate.json').read_text());known={r['target_path'] for r in cm['files']}
new=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('ontology_assessment.py','ontology_io.py','ontology_input.py','compact_model_input.py','read_candidate_pages.py')]
for n in new:
 if n not in known:ac.register_file(C,n,upstream_state='absent')
p=S/'00_SYSTEM/PIPELINE.json';pipeline=json.loads(p.read_text())
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=json.loads(ep.read_text())
 if '02_BACKEND/semantic_runtime/legal_agent/ontology_context.py' not in engine['files']:continue
 for n in new:engine['files'][n]=sha(S/n)
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(p,pipeline);ac.freeze(C)
assert not ac.validate(C),ac.validate(C)
cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1]
binding={'candidate_id':C.name,'experiment_id':'ADR-1095-experiment-v1','arm_id':'direct','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_1095/check.py','runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1095/check.py')}
code=C/'revisions'/rev['revision_id']/'snapshot'
put(ADR/'artifacts/freeze.json',{'code_root':str(code.relative_to(ROOT)),'binding':binding,'tests_sha256':{n:sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1095'/n) for n in ('test_direct.py',)}})
m=json.loads((ADR/'실험/manifest.json').read_text());m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding])
m['runs'][0].update(selection_rule='Frozen ontology compiler/context/review/API regressions and new targeted batch/index/input/cache contracts',artifact_path=str((ADR/'artifacts/check.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
print(code)
