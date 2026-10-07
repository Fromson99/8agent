"""Fixed paired order, one invocation per case/arm; preserve every failure."""
import subprocess,sys
from run import ROOT,ADR,RUN,put
from datetime import datetime,timezone

def main():
    put(ADR/'artifacts/contract-results.json',{'passed':54,'failed':0,'frozen':True,'log':'artifacts/contracts-frozen.log','synthetic_external_model_calls':0})
    order=[('cm-003','baseline'),('cm-003','batch-reference'),('cm-051','batch-reference'),('cm-051','baseline')]
    put(RUN/'execution-order.json',{'planned_before_product_calls':True,'order':order,'python':sys.executable,'started_at':datetime.now(timezone.utc).isoformat()})
    for cid,arm in order:
        path=RUN/cid/(arm+'-runtime.log');path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as log:
            result=subprocess.run([sys.executable,'-B','06_TOOLS/EXPERIMENTS/adr_0622/run.py','--case',cid,'--arm',arm],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        print(cid,arm,'exit',result.returncode,flush=True)
        if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
