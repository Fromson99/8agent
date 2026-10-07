"""Snapshot authorised native journals and freeze the offline builder holdout."""
import json
import sqlite3
import subprocess
from harness import R,A,C,candidate,write,sha

def main():
    runtime=A/'artifacts/log-snapshot/runtime';rows=[]
    with candidate(snapshot=True):
        from lawrag.core.action_memory import episode_from_journal
        from lawrag.pipeline.action_memory import PublicModel
        model=PublicModel(R,A/'artifacts/model-readiness')
        chosen=[];private=[]
        for p in sorted((R/'90_RUNTIME/semantic/legal-agent/runs').glob('*/*/journal.sqlite')):
            e=episode_from_journal(p)
            if e:
                (chosen if model.eligible(e) else private).append(p)
        assert len(chosen)==4
        for p in chosen+private[:1]:
            dest=runtime/'legal-agent/runs'/p.parent.parent.name/p.parent.name/p.name;dest.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(dest) as target:source.backup(target)
            rows.append({'path':str(dest.relative_to(R)),'sha256':sha(dest),'original_path':str(p.relative_to(R)),
                         'original_sha256':sha(p),'eligible':p in chosen})
    write(A/'artifacts/log-snapshot/sources.json',{'model_calls':0,'eligible':4,'waiting_auth_fixture':1,'files':rows})
    subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C.relative_to(R))],check=True)
    cm=json.loads((C/'candidate.json').read_text());rev=cm['revisions'][-1];m=json.loads((A/'실험/manifest.json').read_text())
    m['design']['success_criteria']['schema']='Exact closed output schema is visible in the same existing model call; no classifier or repair; structured decoding alone proved insufficient in independent native API audit.'
    m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],
        'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],
        'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0573/run.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0573/run.py')}]
    m['dataset'].update(frozen_source=str((A/'artifacts/log-snapshot/sources.json').relative_to(R)),sha256=sha(A/'artifacts/log-snapshot/sources.json'))
    files=[R/r['path'] for r in rows]+list((R/'06_TOOLS/EXPERIMENTS/adr_0573').glob('*.py'))+[C/'candidate.json']+[R/f['frozen_path'] for f in rev['files']]
    files += [R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',R/'02_BACKEND/semantic_runtime/legal_agent/local_gemma.py']
    m['design']['frozen_inputs']={str(p.relative_to(R)):sha(p) for p in files}
    write(A/'실험/manifest.json',m)
    print('Four authorised real journals plus one unauthorised control, isolated deadline/schema builder frozen')

if __name__=='__main__':main()
