"""Preserve completed ADR0624 baseline; run the exact-anchor candidate once."""
from datetime import datetime,timezone
import re
import shutil
import subprocess
import sys
from run import ROOT,ADR,RUN,read,put,sha

def main():
    log=ADR/'artifacts/contracts-frozen.log';text=log.read_text()
    assert not re.search(r'\d+ failed',text)
    passed=int(re.search(r'(\d+) passed',text).group(1))
    put(ADR/'artifacts/contract-results.json',{'passed':passed,'failed':0,'frozen':True,
        'log':str(log.relative_to(ROOT)),'log_sha256':sha(log),'deselected':1,
        'synthetic_external_model_calls':0})
    source=ROOT/'04_EXPERIMENTS/ADR/ADR-0624-required-unit-delegation-read/artifacts/run-001/cm-003/required-unit-closure'
    target=RUN/'cm-003/baseline';target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,target)
    receipt={'source_result':str((source/'result.json').relative_to(ROOT)),
        'sha256':sha(source/'result.json'),'new_model_calls':0,
        'raw_files':{str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()}}
    put(ADR/'artifacts/inherited-baseline.json',receipt)
    result=read(target/'result.json');result.update(arm='baseline',inherited_from=receipt,new_model_calls=0)
    put(target/'result.json',result)
    put(RUN/'execution-order.json',{'planned_before_product_calls':True,
        'order':[['cm-003','exact-anchor']],'baseline_replayed':False,
        'python':sys.executable,'started_at':datetime.now(timezone.utc).isoformat(),'repetitions':1})
    output=RUN/'cm-003/exact-anchor-runtime.log'
    with output.open('x') as stream:
        result=subprocess.run([sys.executable,'-B','06_TOOLS/EXPERIMENTS/adr_0625/run.py',
            '--case','cm-003','--arm','exact-anchor'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    print('cm-003 exact-anchor exit',result.returncode,flush=True)
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':main()
