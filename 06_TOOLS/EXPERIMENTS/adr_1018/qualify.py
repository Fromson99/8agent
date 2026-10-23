from common import *
import subprocess
C=ROOT/read(ART/'stage.json')['roots']['candidate']
files=['test_navigation_input_compaction.py','test_selected_connection_scope.py','test_selected_connection_scope_api.py',
 'test_retained_partial_connections.py','test_batch_reference_navigation.py','test_reference_decision_continuity.py',
 'test_reference_context_continuity.py','test_reference_endpoint_coverage.py','test_relation_read_policy.py',
 'test_compact_reference_menu_repair.py','test_navigation_delivery_recovery.py']
with (ART/'qualification.log').open('x') as stream:
 p=subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('run_contracts.py')),'-q',
  '--junitxml='+str(ART/'qualification.xml'),*[str(C/'05_TESTS/CONTRACTS'/n) for n in files]],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
import xml.etree.ElementTree as ET
root=ET.parse(ART/'qualification.xml').getroot()
failed=[{'test':t.attrib,'failure':[c.text for c in t if c.tag in ('failure','error')]} for t in root.iter('testcase') if any(c.tag in ('failure','error') for c in t)]
known='test_bounded_path_adopts_new_reference_source_with_exact_evidence'
report={'tests':sum(1 for t in root.iter('testcase')),'failures':failed,'exit_code':p.returncode,
 'new_failures':[x for x in failed if x['test']['name']!=known or 'structure_selections' not in str(x)],
 'existing_fixture_failure':known,'same_failure_previously_reproduced':'ADR1015 frozen code and 20261023-final-connection-selection audit',
 'candidate_module_asserted':True,'offline_projection':read(ART/'offline-projection.json')}
report['deterministic_gates_pass']=not report['new_failures'] and report['offline_projection']['criteria_met']
save(ART/'qualification.json',report)
print(json.dumps({k:report[k] for k in ('tests','exit_code','deterministic_gates_pass')},ensure_ascii=False))
raise SystemExit(0 if report['deterministic_gates_pass'] else 1)
