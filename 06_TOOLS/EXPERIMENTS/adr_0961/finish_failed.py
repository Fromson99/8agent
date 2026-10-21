from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0961-scoped-consumer-qualification';A=D/'artifacts';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
result={'strict_success':False,'checks':{'five_live_commands_pass':False,'four_api_consumers_pass':True},'live':{'pass':4,'total':5,'physical_calls':10},'failure':'q3 whole named document was incorrectly interpreted as CLEAR, which would release document scope. Promotion rejected.','api':'Four API variants pass with corrected scripted transport; earlier failures preserved.','decision':'Follow-up prompt distinction plus host guard for named document in a CLEAR quote; no MAIN change.'}
save(A/'result.json',result)
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scoped-consumer-heldout.md']:
 old=path.read_text();header=''
 if old.startswith('---'):
  _,front,body=old.split('---',2);header='---'+front+'---\n';old=body
 path.write_text(header+'\n'+''.join(h+'\n\nQualification rejected: four of five unseen commands passed; q3 incorrectly cleared the named-document limit when only its chapter limit should be removed. Four API cases pass after fixing the scripted transport. Exact outputs, hashes and earlier failures remain under artifacts. No MAIN activation. Follow-up must prevent named-document CLEAR and distinguish structure-only removal. No legal quality or GENOS claim.\n\n' for h in old.splitlines() if h.startswith('#')))
p=D/'실험/manifest.json';m=json.loads(p.read_text());m['runs'][0].update(status='complete',sha256=sha(A/'result.json'));m['decision_eligible']=False;m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'ADR0960'},'qualified':{'status':'complete','strict_success':False}},usage={'model_calls':10},latency={},judge_disagreements=0,error_taxonomy=['incorrect named-document whole-scope CLEAR','scripted harness issues repaired'])
for q in m['questions']:q['sha256']=sha(D/'실험'/q['file'])
save(p,m)
rows=[]
for p in sorted(A.rglob('*')):
 if p.is_file() and p.name!='manifest.json' and not any(s.startswith('runtime-') for s in p.parts) and p.suffix not in ('.sqlite','.pyc') and 'sqlite-' not in p.name:rows.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Failed qualification evidence, no promotion','contains_raw_prompts_and_outputs':p.is_relative_to(A/'model')})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0961','created_at':m['reservation']['created_at'],'files':rows})
