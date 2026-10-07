"""Mechanically seal local test artifacts; never edits application code."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0477-source-first-action-feedback'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0477/action-feedback'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_text())
def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def summary(path):
    root=ET.parse(path).getroot()
    cases=list(root.iter('testcase'))
    failed=[c.attrib['classname']+'::'+c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
    skipped=sum(c.find('skipped') is not None for c in cases)
    return {'tests':len(cases),'passed':len(cases)-len(failed)-skipped,'failed':len(failed),'skipped':skipped,'failed_ids':failed}
def main():
    manifest=read(ADR/'실험/manifest.json')
    candidate=read(CAND/'candidate.json')
    revision=next(r for r in candidate['revisions'] if r['revision_id']=='rev-002')
    for f in revision['files']:
        assert sha(ROOT/f['frozen_path'])==f['snapshot_sha256']
    primary=summary(ADR/'artifacts/check-003/junit.xml')
    regression=summary(ADR/'artifacts/regression-junit.xml')
    parent=summary(ADR/'artifacts/parent-regression-junit.xml')
    assert primary['passed']==33 and primary['failed']==0
    assert regression['failed_ids']==parent['failed_ids']
    working=ROOT/'02_BACKEND/semantic_runtime/legal_agent/gateway.py'
    assert sha(working)=='878c22965998b693e486cb4f262685b1d72e82b410a63cc3d11a52823b2a407a'
    result={'primary_contracts':primary,'candidate_regression':regression,'parent_regression':parent,
            'new_regression_failures':sorted(set(regression['failed_ids'])-set(parent['failed_ids'])),
            'external_calls':0,'quality_evaluated':False,'production_route_changed':False,
            'external_policy':{'isolated_candidate_guard_removed':True,
                              'working_gateway_guard_removed':False,'working_gateway_sha256':sha(working),
                              'status':'blocked_by_execution_security_review',
                              'reason':'Permanent external-send permission beyond a single Qwen run requires explicit scope approval; no bypass attempted.'},
            'first_check_harness_errors':['test used tool_reserved instead of tool_used',
                                          'result writer used sha256 instead of revision_sha256'],
            'revision_id':'rev-002','revision_sha256':revision['revision_sha256']}
    write(ADR/'artifacts/result.json',result)
    frozen_tests=ADR/'artifacts/frozen-action-feedback-tests.py'
    shutil.copyfile(ROOT/'05_TESTS/CONTRACTS/test_source_first_action_feedback.py',frozen_tests)
    manifest['dataset'].update(frozen_source=str(frozen_tests.relative_to(ROOT)),sha256=sha(frozen_tests))
    manifest['design']['code_isolation']['candidates']=[{
        'candidate_id':'action-feedback','experiment_id':manifest['experiment_id'],'arm_id':'action-feedback',
        'run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),
        'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':'rev-002','revision_sha256':revision['revision_sha256'],
        'runner_path':'06_TOOLS/EXPERIMENTS/adr_0477/check_contracts.py',
        'runner_sha256':sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_0477/check_contracts.py')}]
    manifest['design']['arms'][0]['changes']='Unchanged parent frozen rev-001; common synthetic regression tests only, no model replay'
    manifest['runs'][0].update(status='complete',arm_ids=['baseline','action-feedback'],
        artifact_path=str((ADR/'artifacts/result.json').relative_to(ROOT)),sha256=sha(ADR/'artifacts/result.json'))
    manifest['results'].update(status='complete',
        by_arm={'baseline':{'executed':True,'synthetic_regression':parent},
                'action-feedback':result},
        comparisons=[{'metric':'common synthetic regression failed IDs','same_as_parent':True,'new_failures':0}],
        usage={'physical_external_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},
        latency={'local_check_003_seconds':read(ADR/'artifacts/check-003/result.json')['seconds']})
    write(ADR/'실험/manifest.json',manifest)
    rows=[]
    paths=[ADR/'PLAN.md',*sorted((ADR/'artifacts').rglob('*'))]
    for path in paths:
        if not path.is_file() or path==ADR/'artifacts/manifest.json':
            continue
        rows.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size,
                     'description':'Synthetic contract/audit artifact; no live model outputs',
                     'contains_raw_prompts_and_outputs':False})
    write(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0477',
         'created_at':manifest['reservation']['created_at'],'files':rows})
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    main()

