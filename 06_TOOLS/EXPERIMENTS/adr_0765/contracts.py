import json,subprocess,os,xml.etree.ElementTree as ET
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0765-bounded-wiki-recall'
read=lambda p:json.loads(p.read_text())
C=R/'02_BACKEND/lawrag/research/candidates/adr_0765/integrated'
cm=read(C/'candidate.json');candidate=C/'revisions'/cm['revisions'][-1]['revision_id']/'snapshot'
baseline=R/read(A/'artifacts/design/baseline.json')['manifest']['code_root']
files=[str(R/'05_TESTS/CONTRACTS'/n) for n in ('test_cm_shortcut_package.py','test_cm_common_catalogue.py','test_session_runtime_without_wiki_signing.py','test_unified_legal_agent.py','test_unified_memory_recovery.py','test_legal_agent_double_harness.py')]
files += [str(R/'06_TOOLS/EXPERIMENTS'/p) for p in ('adr_0683/test_core_routes.py','adr_0683/test_core_api.py','adr_0707/test_entry.py','adr_0707/test_title_search.py','adr_0712/test_compact_input.py')]
def run(label,code,tests):
    xml=A/'artifacts'/f'{label}.xml'
    cmd=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'),str(code),*tests,'--junitxml='+str(xml)]
    with (A/'artifacts'/f'{label}.log').open('w') as out:
        p=subprocess.run(cmd,cwd=R,stdout=out,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':str(R/'05_TESTS/CONTRACTS')+':'+str(R/'05_TESTS/REGRESSION/core')})
    if not xml.exists():raise RuntimeError('Contract bootstrap failed: '+label)
    cases=list(ET.parse(xml).iter('testcase'))
    return {'exit_code':p.returncode,'tests':len(cases),'failed':sorted(t.get('classname','')+'::'+t.get('name','') for t in cases if t.find('error') is not None or t.find('failure') is not None)}
b=run('baseline-contracts',baseline,files);print('baseline',b,flush=True)
c=run('candidate-contracts',candidate,files);print('candidate',c,flush=True)
n=run('new-contracts',candidate,[str(candidate/'05_TESTS/CONTRACTS/test_bounded_wiki_recall.py')]);print('new',n,flush=True)
new=sorted(set(c['failed'])-set(b['failed']))
result={'baseline_all':b,'candidate_all':c,'new_contracts':n,'new_regressions':new,'all_new_contracts_pass':not n['failed'],'strict_success':not new and not n['failed'],'suite_files':files}
(A/'artifacts/contract-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
raise SystemExit(0 if result['strict_success'] else 1)
