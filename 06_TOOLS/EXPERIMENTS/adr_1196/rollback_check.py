"""Verify previous release can read stored preserved compositions after rollback."""
from common import *
import subprocess,gzip,os
b=read(DES/'baseline.json');f=read(DES/'freeze-rev-002.json');mode=sys.argv[1] if len(sys.argv)>1 else 'write'
C=ROOT/(b['manifest']['code_root'] if mode=='read' else f['code_root'])
os.environ['WORKFLOW_TEST_CODE_ROOT']=str(C)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'05_TESTS/CONTRACTS'),str(ROOT/'05_TESTS'),str(Path(__file__).parent)]
import lawrag,importlib
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
for name in ('pipeline','core'):
 pkg=importlib.import_module('lawrag.'+name);pkg.__path__.append(str(ROOT/'02_BACKEND/lawrag'/name))
from semantic_runtime.legal_agent import completion_contracts as cc
if mode=='write':
 from semantic_runtime.legal_agent import narrative_answer as n
 from test_preservation import sample
 rows=[]
 for layout in ('paragraphs','bullets','table'):
  for mode in ('ALL','ANY','UNKNOWN','prose'):
   a=sample(mode if mode!='prose' else 'ALL',pure=mode=='prose');out=cc.compose(a,n.preserved_plan(a,layout));cc.verify_composition(a,out)
   rows.append({'assessment':a,'answer':out,'layout':layout,'mode':mode})
 write_raw_json(ART/'rollback-compositions.json',rows)
 subprocess.run([str(ROOT/'.venv/bin/python'),__file__,'read'],check=True,cwd=ROOT)
else:
 rows=json.loads(gzip.decompress((ART/'rollback-compositions.json.gz').read_bytes()))
 for row in rows:cc.verify_composition(row['assessment'],row['answer'])
 assert Path(cc.__file__).is_relative_to(C)
 put(ART/'rollback-compatibility.json',{'passed':True,'cases':len(rows),'baseline_release':b['active']['release_id'],'old_consumer':str(Path(cc.__file__).relative_to(ROOT)),'new_composition_version':'accepted-content-v1','external_model_calls':0})
 print('Old release verifies',len(rows),'new preserved compositions exactly')
