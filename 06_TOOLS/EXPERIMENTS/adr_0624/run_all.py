"""One fresh paired CM003 sequence; never rerun completed model calls."""
from datetime import datetime, timezone
import re
import subprocess
import sys
from run import ROOT, ADR, RUN, read, put, sha


def main():
    contracts=ADR/'artifacts/contracts-frozen.log'
    text=contracts.read_text()
    assert not re.search(r'\d+ failed',text)
    passed=int(re.search(r'(\d+) passed',text).group(1))
    put(ADR/'artifacts/contract-results.json',{'passed':passed,'failed':0,'frozen':True,
        'log':str(contracts.relative_to(ROOT)),'log_sha256':sha(contracts),'deselected':1,
        'scope_exclusions':read(ADR/'실험/manifest.json')['design']['contract_scope_exclusions'],
        'synthetic_external_model_calls':0})
    order=[('cm-003','baseline'),('cm-003','required-unit-closure')]
    put(RUN/'execution-order.json',{'planned_before_product_calls':True,'order':order,
        'python':sys.executable,'started_at':datetime.now(timezone.utc).isoformat(),
        'repetitions':1,'fixed_order_limit':'No random order or repeated variability estimate'})
    for cid,arm in order:
        path=RUN/cid/(arm+'-runtime.log');path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as stream:
            result=subprocess.run([sys.executable,'-B','06_TOOLS/EXPERIMENTS/adr_0624/run.py',
                '--case',cid,'--arm',arm],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        print(cid,arm,'exit',result.returncode,flush=True)
        if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':main()
