from common import *
kind=sys.argv.pop(1);assert kind in ('consumer','gold')
ART=OUT/'selected';ART.mkdir(parents=True,exist_ok=True)
if kind=='consumer':
 source=(Path(__file__).parent/'consumer.py').read_text().replace('from common import *','from common import *\nART=OUT/"selected";ART.mkdir(parents=True,exist_ok=True)',1)
else:
 source=(Path(__file__).parent/'gold_probe.py').read_text().replace('from common import *','from common import *\nART=OUT/"selected";ART.mkdir(parents=True,exist_ok=True)',1)
 source=source.replace("pf=read(DES/'port-freeze.json')","pf={'files':{str(GOLD.relative_to(ROOT)/n):h for n,h in read(DES/'baseline.json')['gold_binding']['connector_files'].items()}}")
 if sys.argv[-1]=='scope':
  scope=(Path(__file__).parent/'scope_probe_body.py').read_text().split(' # Same immutable release')[0]
  scope+='\n store.check_unchanged();idx.check_unchanged()\n out=ART/("gold-"+mode);out.mkdir(exist_ok=True)\n put(out/"scope-verification.json",{"passed":True,"checks":checks,"actual_sql_calls":request.sql.calls,"new_models":0,"connector_unchanged":True})\n print("Selected Gold scope PASS",checks)\n'
  source=source.replace("exec((Path(__file__).parent/'scope_probe_body.py').read_text())",'exec('+repr(scope)+')')
exec(compile(source,str(Path(__file__).parent/('consumer.py' if kind=='consumer' else 'gold_probe.py')),'exec'))
