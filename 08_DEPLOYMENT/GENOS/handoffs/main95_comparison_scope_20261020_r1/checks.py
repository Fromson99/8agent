from pathlib import Path
import json,os,runpy,sys
H=Path(__file__).resolve().parent;R=H.parents[3];C=H/'test-code'
os.environ['TASK_TEST_CODE_ROOT']=str(C)
sys.path.insert(0,str(H))
sys.argv=['installed_contract_runner.py',str(C),'-p','display_fixture','--junitxml='+str(H/'CONTRACT_TESTS_01.xml'),*json.loads((H/'TEST_SELECTION.json').read_text())]
runpy.run_path(str(H/'installed_contract_runner.py'),run_name='__main__')
