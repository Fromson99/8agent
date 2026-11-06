from common import *
import ast
import importlib.util
import shutil
x=read(DES/'candidate-repaired.json');C=ROOT/x['code_root'];files=x['selected_files']
base=read(ART/'working-before.json');products=read(DES/'candidate-path.json')['product_files']
current={n:sha(ROOT/n) for n in files}
assert all(current[n]==base[n] for n in products)
stage=ART/'native-rebase';stage.mkdir(exist_ok=False)
for n in files:
 p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
for n in products:
 if not n.endswith('oracle_query_plans.py'):shutil.copyfile(C/n,stage/n)
spec=importlib.util.spec_from_file_location('prepare1396',ROOT/'06_TOOLS/maintenance/prepare_oracle_queries.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=m.source_queries;m.ROOT=stage;m.source_queries=lambda:original(stage)
sys.argv=['prepare1396'];m.main()
def plans(p):return next(ast.literal_eval(node.value) for node in ast.parse(p.read_text()).body if isinstance(node,ast.Assign) and any(getattr(t,'id','')=='PLANS' for t in node.targets))
clean=lambda d:{k:{f:v for f,v in p.items() if f!='sources'} for k,p in d.items()}
assert clean(plans(C/products[-1]))==clean(plans(stage/products[-1]))==clean(plans(ROOT/products[-1]))
assert all(sha(ROOT/n)==h for n,h in current.items())
put(ART/'native-rebase.json',{'before':current,'stage':str(stage.relative_to(ROOT)),'plan_count':len(plans(stage/products[-1])),'all_executable_plans_identical':True})
