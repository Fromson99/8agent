import runpy,sys
from pathlib import Path
sys.argv=[sys.argv[0],str(Path(__file__).resolve().parent)]
runpy.run_path(str(Path(__file__).resolve().parents[1]/'adr_1388'/'finish_record.py'),run_name='__main__')
