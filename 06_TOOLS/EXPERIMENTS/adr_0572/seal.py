"""Audit completed local results, preserve immutable lineage, and close reservation."""
from pathlib import Path
import hashlib
import json
import runpy
import subprocess

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0572-native-memory-frozen-revalidation'
read = lambda p:json.loads(p.read_text())
sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')
def tool(args, *, log=None, allow_failure=False):
    r = subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),*args],cwd=R,text=True,capture_output=True)
    if log is not None: log.write_text(r.stdout+r.stderr)
    if r.returncode and not allow_failure: raise RuntimeError(r.stdout+r.stderr)
    return r


def artifacts():
    paths = list((A/'artifacts').rglob('*')) + list((R/'06_TOOLS/EXPERIMENTS/adr_0572').glob('*.py'))
    for arm in ['integrated']:
        c = R/('02_BACKEND/lawrag/research/candidates/adr_0571/'+arm)
        paths += [c/'candidate.json'] + list((c/'revisions/rev-001').rglob('*'))
    files = []
    for p in sorted(set(paths)):
        if p.is_file() and p!=A/'artifacts/manifest.json':
            files.append({'path':str(p.relative_to(R)), 'bytes':p.stat().st_size, 'sha256':sha(p),
                'description':'Frozen synthetic input/code, exact call/journal, or offline audit',
                'contains_raw_prompts_and_outputs':'calls' in p.parts})
    write(A/'artifacts/manifest.json', {'schema_version':'adr-artifacts-v1','adr_id':'ADR-0572','files':files})
    return len(files)


def main():
    assert read(A/'artifacts/run-001/result.json')['status']=='complete'
    runpy.run_path(str(R/'06_TOOLS/EXPERIMENTS/adr_0572/run.py'))['verify']()
    tool(['adr_candidate.py','validate','02_BACKEND/lawrag/research/candidates/adr_0571/integrated'],log=A/'artifacts/upstream-candidate-validation.log')
    baseline = read(R/'04_EXPERIMENTS/ADR/ADR-0568-action-concepts-presql/artifacts/baseline-release-check.json')
    checks = {'active_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['active_pointer_sha256'],
        'native_modules_unchanged':{v['path']:sha(R/v['path'])==v['working_sha256'] for v in baseline['modules']}}
    assert checks['active_pointer_unchanged'] and all(checks['native_modules_unchanged'].values())
    write(A/'artifacts/postrun-code-check.json', checks)
    m = read(A/'실험/manifest.json')
    tool(['adr_structure.py','hash','--path',str(A.relative_to(R))],log=A/'artifacts/hash-check.log')
    note = 'Early stopped after native constrained JSON generation repeated whitespace to token limits; H01 both published unresolved zero-claim answers. All raw requests/responses retained; remaining cases/generation not executed, no valid performance estimate. MAIN unchanged.'
    if m['reservation']['status']!='completed': tool(['adr_structure.py','status','--path',str(A.relative_to(R)),'--status','completed','--owner','codex',
        '--session-id','01a0ecf8-3e9d-71a0-b743-b35ad26b1ed6','--note',note],log=A/'artifacts/completion-status.log')
    graph_result = tool(['adr_structure.py','graph','--adr-root','04_EXPERIMENTS/ADR'],
        log=A/'artifacts/graph-check.log',allow_failure=True)
    errors = read(R/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json')['validation_errors']
    prior = read(R/'04_EXPERIMENTS/ADR/ADR-0569-compact-plan-smallpool/artifacts/local-lineage-audit.json')['preexisting_errors']
    fresh = [e for e in errors if e not in prior]
    parents = [{'ref':p['experiment_id']+'/'+p['arm_id'],'expected_sha256':p['manifest_sha256'],
        'actual_sha256':sha(R/p['manifest_path']),'match':sha(R/p['manifest_path'])==p['manifest_sha256']} for p in m['lineage']['parents']]
    lineage = {'global_graph_passed':graph_result.returncode==0,'preexisting_errors':errors,'new_scope_errors':fresh,
        'parent_receipts':parents,'new_scope_lineage_passed':not fresh and all(p['match'] for p in parents)}
    assert lineage['new_scope_lineage_passed']
    write(A/'artifacts/local-lineage-audit.json',lineage)
    count = artifacts()
    tool(['adr_structure.py','validate','--path',str(A.relative_to(R)),'--final'],log=A/'artifacts/final-validation.log')
    receipt = {'final_validation':'passed','candidate_validation':'passed','new_scope_lineage':'passed',
        'global_preexisting_graph_errors':len(errors),'artifact_count_before_final_receipts':count,'main_changed':False}
    write(A/'artifacts/final-validation-receipt.json',receipt)
    count = artifacts()
    for file in read(A/'artifacts/manifest.json')['files']:
        assert sha(R/file['path'])==file['sha256']
    tool(['adr_structure.py','validate','--path',str(A.relative_to(R)),'--final'])
    print(json.dumps({'validation':receipt,'artifact_hashes_verified':count,'reservation':'completed'},ensure_ascii=False))


if __name__=='__main__':main()
