"""Recheck existing workspace contracts on byte-identical current product code."""
from common import *
import runpy
F=read(DES/'freeze.json');assert all(sha(ROOT/n)==h for n,h in F['files'].items())
tests=['05_TESTS/CONTRACTS/'+n for n in ('test_wiki_workspace.py','test_domain_profile_workflow.py','test_wiki_workspace_native.py','test_domain_profile_native.py','test_domain_profile_ui.py')]
tests+=['08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/test_mapping.py']
runner=ROOT/'06_TOOLS/maintenance/check_wiki_workspace.py'
before={n:sha(ROOT/n) for n in tests}
sys.argv=[str(runner),'--adapt-legacy','--output',str(ART/'workspace-check.json'),*tests]
code=0
try:runpy.run_path(str(runner),run_name='__main__')
except SystemExit as e:code=int(e.code or 0)
checks={'working_candidate518_equal':all(sha(ROOT/n)==h for n,h in F['files'].items()),
 'tests_unchanged':all(sha(ROOT/n)==h for n,h in before.items()),
 'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==F['pointer_sha256']}
put(ART/'workspace-code-binding.json',{'checks':checks,'test_files':before,'runner':bind(runner),'legacy_adapter':'Synthetic model fixtures only; no product validator relaxed'})
assert all(checks.values())
raise SystemExit(code)
