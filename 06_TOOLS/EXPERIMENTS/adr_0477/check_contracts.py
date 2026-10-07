"""Run only synthetic contracts against hash-verified, explicitly frozen code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0477-source-first-action-feedback'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0477/action-feedback'
TESTS=['05_TESTS/CONTRACTS/test_source_first_candidate.py',
       '05_TESTS/CONTRACTS/test_source_first_action_feedback.py']

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision',required=True)
    parser.add_argument('--check',required=True)
    args=parser.parse_args()
    if not args.check.replace('-','').isalnum():
        raise ValueError('invalid check label')
    manifest=json.loads((CAND/'candidate.json').read_text())
    revision=next(r for r in manifest['revisions'] if r['revision_id']==args.revision)
    for row in revision['files']:
        assert hashlib.sha256((ROOT/row['frozen_path']).read_bytes()).hexdigest()==row['snapshot_sha256']
    frozen=CAND/'revisions'/args.revision/'snapshot/02_BACKEND'
    out=ADR/'artifacts'/args.check
    out.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m','pytest','-o','pythonpath='+str(frozen)+' '+str(ROOT/'02_BACKEND')+' '+str(ROOT),
             '-p','no:cacheprovider','-q','--junitxml='+str(out/'junit.xml'),*TESTS]
    started=time.monotonic()
    with (out/'pytest.log').open('w') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    receipt={'check':args.check,'revision':args.revision,'revision_sha256':revision['revision_sha256'],
             'exit_code':result.returncode,'seconds':round(time.monotonic()-started,3),
             'external_calls':0,'quality_evaluated':False,'command':command,
             'tests':{t:hashlib.sha256((ROOT/t).read_bytes()).hexdigest() for t in TESTS}}
    (out/'result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print((out/'pytest.log').read_text())
    print(json.dumps(receipt,ensure_ascii=False))
    return result.returncode
if __name__=='__main__':
    raise SystemExit(main())


