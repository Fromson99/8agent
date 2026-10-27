"""Report complete navigation windows; preserve the older failed service run."""
from common import *
from native_transport import checked
from collections import defaultdict

run=ADR/'artifacts/run-002';out=run/'optimized'
inventory=read(checked(read(DESIGN/'secondary-replay.json')['input_inventory']))
reference=inventory['completed_baseline_windows']
baseline=read(checked(reference['result']));actual=read(out/'result.json')
frames=[read(p) for p in sorted(out.glob('view-*.json'))]
old_frames=[read(checked(item)) for item in reference['views']]
transport=read(out/'transport-checks.json')
checks={
    'candidate_completed':actual['completed'] is True,
    'original_baseline_service_failure_preserved':baseline['completed'] is False,
    'baseline_35_complete_exact_windows':len(old_frames)==35 and all(r['exact'] for r in old_frames),
    'candidate_35_complete_exact_windows':len(frames)==35 and all(r['exact'] for r in frames),
    'frames_match_baseline_and_completed_original':len(frames)==35 and all(a['hashes']==b['hashes']==inventory['frames'][i]['hashes'] for i,(a,b) in enumerate(zip(frames,old_frames))),
    'responses38_unmodified':actual['recorded_responses_used']==38 and len(transport)==38 and actual['literal_response_rewrite'] is False,
    'protected_requests_exact':all(r['protected_request_exact'] and r['schema_exact'] and r['system_exact'] for r in transport),
    'compose_id_verified_against_both_journals':transport[-1].get('domain_choice_proof',{}).get('journal_bound') is True,
    'final_answer_exact_to_completed_original':actual.get('answer_exact') is True,
    'final_answer_identity_bound':actual.get('answer_identity_bound_to_native_journal') is True,
    'external_model_calls_zero':actual['external_model_calls']==0,
    'candidate_view_time_reduced':actual['view_seconds']<reference['view_seconds'],
    'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DESIGN/'baseline.json')['pointer_sha256'],
    'frozen_files_unchanged':all(sha(ROOT/p)==h for p,h in read(DESIGN/'freeze.json')['files'].items())}
function_totals={}
for arm,path in [('prior_baseline_windows',checked(reference['spans'])),('optimized',out/'spans.json')]:
    labels=defaultdict(lambda:{'calls':0,'seconds':0.0,'cpu_seconds':0.0})
    for row in read(path):
        value=labels[row['function']];value['calls']+=1
        value['seconds']+=row['seconds'];value['cpu_seconds']+=row['cpu_seconds']
    function_totals[arm]=dict(labels)
b=reference['view_seconds'];a=actual['view_seconds']
result={'schema_version':'adr1078-bound-replay-result-v1','strict_success':all(checks.values()),'checks':checks,
    'known_in_sample':True,'primary_quality_evidence':False,'freeze':bound(DESIGN/'freeze.json'),
    'baseline_reference':reference['result'],'optimized':bound(out/'result.json'),
    'timing':{'view_seconds':{'baseline':b,'optimized':a,'reduction_percent':100*(1-a/b)},
        'optimized_request_seconds':actual['request_seconds'],'optimized_offline_transport_seconds':actual['offline_transport_seconds'],
        'optimized_application_prepare_seconds':actual['application_prepare_seconds']},
    'inclusive_functions':function_totals,'new_model_calls':0,'new_tokens':0,'new_cost_usd':0,
    'unchanged_recorded_responses_used':38,'exact_navigation_windows':35,'final_answer_reference':inventory['response'],
    'scope':'Prior baseline completed35 exact navigation windows but failed later at final compose generated-ID comparison. Its failed outcome is preserved and no full-request improvement is calculated. Current complete candidate is checked against original1075 completed answer. Only view windows with identical wrappers are compared; different runtime/cache warmth and single sample limit causal/generalization claims. No GENOS or legal quality certification.'}
put(run/'result.json',result)
print(__import__('json').dumps({'strict_success':result['strict_success'],'checks':checks,'timing':result['timing']},ensure_ascii=False))
raise SystemExit(0 if result['strict_success'] else 1)
