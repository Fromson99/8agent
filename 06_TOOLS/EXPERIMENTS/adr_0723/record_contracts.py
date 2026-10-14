from pathlib import Path
import json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete';D=A/'artifacts';C=R/'02_BACKEND/lawrag/research/candidates/adr_0723/integrated'
rev=json.loads((C/'candidate.json').read_text())['revisions'][-1]['revision_id']
def cases(p):
 ts=list(E.parse(p).iter('testcase'));return {'tests':len(ts),'failed':sorted(t.get('name') for t in ts if t.find('failure') is not None or t.find('error') is not None)}
base=cases(R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration/artifacts/contracts/baseline/all.xml');new=cases(D/'contracts'/rev/'new.xml');full=cases(D/'contracts'/rev/'all.xml')
v={'new_contracts':new,'candidate_all':full,'baseline_all':base,'new_regressions':sorted(set(full['failed'])-set(base['failed'])),'all_new_contracts_pass':not new['failed'],'candidate_revision':rev,'known_failures_not_passed':True}
(D/'contract-result.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v));assert not v['new_regressions'] and v['all_new_contracts_pass'] and new['tests']==34
