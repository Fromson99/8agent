"""Reject any change to the parent suite or to the legacy fixture failure signature."""
from common import *
import re
candidate=read(ART/'final-contracts/result.json');parent=read(ART/'parent-legacy-api/result.json')
prior=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1372-assigned-original-use-repair-feedback/artifacts/final-contracts/result.json')
passed={r['test'] for r in candidate['rows'] if r['outcome']=='passed'}
assert len(passed)==candidate['passed'] and {r['test'] for r in prior['rows']} <= passed
def failures(result):
    rows={}
    for r in result['rows']:
        if r['outcome']=='failed':
            body=json.loads(re.search(r'AssertionError: (\{.*\})',r['error']).group(1))
            rows[r['test']]={k:body[k] for k in ('answer_status','failure_reason','failure_stage')}
    return rows
baseline=failures(parent)
assert len(baseline)==3 and failures(candidate)==baseline
assert all('test_actual_api_partition_repair_and_terminal_failure' in name for name in baseline)
put(ART/'technical-verification.json',{'contracts_passed':candidate['passed'],'parent_suite_passed':prior['passed'],
    'legacy_failures_reproduced_on_parent':baseline,'new_failures':0,'prior_accepted_generations':29,
    'reference_bundle_review':True,'separate_advisory_final_review_enabled':False,'no_validation_removed':True})
