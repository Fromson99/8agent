from common import *
import os,runpy
os.environ['R7_TEST_PACKAGE']=str(ROOT/read(ART/'loader-final-candidate.json')['package'])
sys.argv=['check.py','--name','loader-rowid-final','06_TOOLS/EXPERIMENTS/adr_1308/test_followup.py']
runpy.run_path(str(Path(__file__).parent/'check.py'),run_name='__main__')
