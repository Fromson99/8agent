"""Reproducible development regression selection; no quality qualification."""
from pathlib import Path
import json,subprocess,sys,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0776/recovery'
v=json.loads((C/'candidate.json').read_text());rev=v['revisions'][-1]['revision_id']
code=C/'revisions'/rev/'snapshot';out=R/v['adr_path']/'artifacts/development'
label=sys.argv[1];keys=('output_contract','wire_repair','genos_wire','law_navigation','request_repair',
 'completion','batch_reference_navigation','compact_reference','reference_resolution','ad_language','ad_model',
 'unified_legal_agent','unified_memory_recovery','memory_adapters','memory_runtime','gap_action','narrative',
 'answer_stream','model_stream','model_contract','input_metrics','numbered','navigation_input','failure_recovery',
 'legal_agent_tools','legal_agent_tiers','legal_agent_v2','legal_agent_v3','legal_agent_v4','legal_agent_v5')
tests=[p for p in sorted((code/'05_TESTS/CONTRACTS').glob('test_*.py'))
    if any(k in p.name for k in keys) and 'handoff' not in p.name]
tests += [p for p in sorted((code/'05_TESTS/REGRESSION/core').glob('test_*.py'))
    if any(k in p.name for k in ('recipe','output_contract','genos_response_completion'))
    and p.name not in ('test_recipe_visual_loop_contract.py','test_recipe_explicit_parent_contract.py')]
args=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/EXPERIMENTS/adr_0776/run_tests.py'),str(code),
      *map(str,tests),'--junitxml='+str(out/(label+'.xml')),*sys.argv[2:]]
(out/(label+'-selection.json')).write_text(json.dumps({'code':str(code.relative_to(R)),
    'tests':[str(p.relative_to(code)) for p in tests]},indent=2)+'\n')
with (out/(label+'.log')).open('w') as log:
    result=subprocess.run(args,cwd=R,stdout=log,stderr=subprocess.STDOUT)
if (out/(label+'.xml')).exists():
    root=E.parse(out/(label+'.xml'))
    print([n.attrib for n in root.iter('testsuite')])
    for case in root.iter('testcase'):
        for tag in ('failure','error'):
            failure=case.find(tag)
            if failure is not None:print(case.get('name'),failure.get('message','')[:220])
raise SystemExit(result.returncode)
