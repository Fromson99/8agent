"""Post-execution reporting only; never changes replay inputs or criteria."""
from common import *
from collections import defaultdict

run=ADR/'artifacts/run-002'
arms={name:read(run/name/'result.json') for name in ('baseline','optimized')}
checks={}
for name,result in arms.items():
    transport=read(run/name/'transport-checks.json')
    frames=[read(p) for p in sorted((run/name).glob('view-*.json'))]
    checks.update({name+'_completed':result['completed'] is True,
        name+'_38_responses':result['recorded_responses_used']==38 and len(transport)==38,
        name+'_35_frames':result['view_count']==35 and len(frames)==35 and all(r['exact'] for r in frames),
        name+'_protected_requests_exact':all(r['protected_request_exact'] and r['schema_exact'] and r['system_exact'] for r in transport),
        name+'_answer_content_exact':result.get('answer_exact') is True,
        name+'_answer_identity_bound':result.get('answer_identity_bound_to_native_journal') is True,
        name+'_external_model_calls_zero':result['external_model_calls']==0})
checks['candidate_view_time_reduced']=arms['optimized']['view_seconds']<arms['baseline']['view_seconds']
checks['active_pointer_unchanged']=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DESIGN/'baseline.json')['pointer_sha256']
checks['frozen_files_unchanged']=all(sha(ROOT/p)==h for p,h in read(DESIGN/'freeze.json')['files'].items())
spans={}
for arm in arms:
    labels=defaultdict(lambda:{'calls':0,'seconds':0.0,'cpu_seconds':0.0})
    for row in read(run/arm/'spans.json'):
        value=labels[row['function']];value['calls']+=1
        value['seconds']+=row['seconds'];value['cpu_seconds']+=row['cpu_seconds']
    spans[arm]=dict(labels)
timing={}
for key in ('view_seconds','request_seconds','request_cpu_seconds','offline_transport_seconds','application_prepare_seconds'):
    b,a=(arms[name][key] for name in ('baseline','optimized'))
    timing[key]={'baseline':b,'optimized':a,'reduction_percent':100*(1-a/b) if b else None}
result={'schema_version':'adr1076-native-replay-result-v1','strict_success':all(checks.values()),'checks':checks,
    'known_in_sample':True,'source_experiment':'ADR1075/observed','primary_quality_evidence':False,
    'freeze':bound(DESIGN/'freeze.json'),'secondary_contract':bound(DESIGN/'secondary-replay.json'),
    'arms':{k:bound(run/k/'result.json') for k in arms},'timing':timing,'inclusive_functions':spans,
    'new_model_calls':0,'new_tokens':0,'new_cost_usd':0,'historical_model_outputs_used_per_arm':38,
    'exact_navigation_frames_per_arm':35,'response_rewritten':False,'GENOS_measured':False,
    'scope':'Paired reconstruction of known MAIN104 trace, identical coarse instrumentation. View hashing/file writes excluded from view. Request includes offline harness overhead; model-free reconstruction time, not a new live answer latency. Nested function spans are not additive. Separate startup; no p95 or legal accuracy claim.'}
put(run/'result.json',result)
print(__import__('json').dumps({'strict_success':result['strict_success'],'timing':timing,'checks':checks},ensure_ascii=False))
raise SystemExit(0 if result['strict_success'] else 1)
