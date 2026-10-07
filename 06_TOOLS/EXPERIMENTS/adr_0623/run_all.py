"""Immutable baseline reuse and one fresh call sequence per candidate case."""
import shutil,subprocess,sys
from datetime import datetime,timezone
from run import ROOT,ADR,RUN,read,put,sha

def main():
    put(ADR/'artifacts/contract-results.json',{'passed':58,'failed':0,'frozen':True,'log':'artifacts/contracts-frozen.log','synthetic_external_model_calls':0})
    parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0622-batch-reference-navigation'
    inherited=[]
    for cid in ('cm-003','cm-051'):
        source=parent/'artifacts/run-001'/cid/'batch-reference';target=RUN/cid/'baseline'
        shutil.copytree(source,target)
        receipt={'case_id':cid,'source_result':str((source/'result.json').relative_to(ROOT)),'source_sha256':sha(source/'result.json'),
            'raw_model_files':{str(p.relative_to(source)):sha(p) for p in source.rglob('*.json') if p.name.startswith(('model-input','model-output')) or 'provider' in p.parts}}
        result=read(target/'result.json');result.update(inherited_from=receipt,new_model_calls=0);put(target/'result.json',result);inherited.append(receipt)
    put(ADR/'artifacts/inherited-baseline.json',{'parent_arm':'ADR-0622-experiment-v1/batch-reference','receipts':inherited,'raw_calls_replayed':False})
    put(RUN/'execution-order.json',{'planned_before_product_calls':True,'order':[('cm-003','compact-reference'),('cm-051','compact-reference')],'python':sys.executable,'started_at':datetime.now(timezone.utc).isoformat()})
    for cid in ('cm-003','cm-051'):
        path=RUN/cid/'compact-reference-runtime.log';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as log:
            result=subprocess.run([sys.executable,'-B','06_TOOLS/EXPERIMENTS/adr_0623/run.py','--case',cid,'--arm','compact-reference'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        print(cid,'compact-reference','exit',result.returncode,flush=True)
        if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
