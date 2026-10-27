"""Read-only inventory and prospective secondary contract, before any replay."""
from common import *
import sqlite3
from native_transport import digest

source = ROOT/'04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001'
case = source/'fsc-hard-005'
original = read(case/'result.json')
assert original['http_status'] == 200 and original['model_calls'] == 38 and not original['fatal']
journal = ROOT/original['journal_paths'][0]
assert not Path(str(journal)+'-wal').exists() or Path(str(journal)+'-wal').stat().st_size == 0
db = sqlite3.connect(journal.as_uri()+'?mode=ro&immutable=1')
try:
    rows = db.execute("SELECT payload_json,payload_hash FROM entity_version WHERE kind='case_stage' AND entity_id='case:SELECT'").fetchall()
    assert len(rows) == 1
    state = __import__('json').loads(rows[0][0])
    assert digest(state) == rows[0][1]
    all_frames = state['investigation_state']['action_chain']['frames'].values()
    frames = sorted((f for f in all_frames if f['kind']=='NAVIGATION'), key=lambda f:f['number'])
    assert len(frames) == 35 and [f['number'] for f in frames] == list(range(1,36))
    frame_inventory = [{'number':f['number'], 'kind':f['kind'],
        'hashes': {k:digest(f[k]) for k in ('data','actions','location')}} for f in frames]
finally:
    db.close()
calls = []
for n in range(1,39):
    directories = list((case/'raw').glob(f'call-{n:03d}-*'))
    assert len(directories) == 1
    calls.append({'ordinal':n,'wire':bound(case/'wire'/f'{n:03d}.json.gz'),
                  'response':bound(directories[0]/'response.json')})
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse/artifacts/run-002/baseline'
previous=read(prior/'result.json')
assert previous['completed'] is False and previous['view_count']==35 and previous['recorded_responses_used']==37
old_views=[read(prior/f'view-{n:03d}.json') for n in range(1,36)]
assert all(row['exact'] and row['hashes']==frame_inventory[n]['hashes'] for n,row in enumerate(old_views))
assert sum(row['seconds'] for row in old_views)==previous['view_seconds']
inventory = {'source_result':bound(case/'result.json'),'source_binding':bound(source/'binding.json'),
    'original_journal':bound(journal),'request':bound(case/'request.json'),
    'response':bound(case/'response.json'),'calls':calls,'frames':frame_inventory,
    'completed_baseline_windows':{'result':bound(prior/'result.json'),'spans':bound(prior/'spans.json'),
        'views':[bound(prior/f'view-{n:03d}.json') for n in range(1,36)],
        'source_service_completed':False,'navigation_windows_completed':35,
        'view_seconds':previous['view_seconds'],'failure_after_navigation':'Generated domain_choice ID mismatch in final compose; no successful baseline final-answer or full-request latency claim.'}}
put(DESIGN/'secondary-inputs.json',inventory)
put(DESIGN/'secondary-replay.json',{
    'schema_version':'adr1081-bound-native-secondary-v1',
    'input_inventory':bound(DESIGN/'secondary-inputs.json'),
    'known_in_sample':True,'primary_criteria_unchanged':True,
    'runs':{'run-002':['optimized']},'execution':'One fresh optimized worker. Reuse only the35 completed, exact navigation windows from1076 failed baseline; original1075 remains the completed final-answer reference.',
    'expected_responses':38,'expected_views':35,'external_model_calls':0,
    'response_rewrite':False,'request_identity_substitution':False,'network_allowed':False,
    'comparison_exemptions':['Only generated UUID /messages/1/content/view/view_id is omitted in comparison copies; stable aliases remain exact except the separately verified call36 V-role mapping.',
        'Final answer comparison copy omits only id and query_id after checking answer:id=answer:+native run_id and answer.query_id=native query.id, with both response identities checked against the new journal. Remaining answer fields are exact.',
        'Only call38 memory-compose /view/domain_choice/choice_id: prove each actual ID from its own native journal run_id, COMPOSE stage, created_seq and choice; require byte-exact choice_json, offer_json and event sequence before omitting this one ID in comparison copies. D1 aliases and all content remain protected.',
        'Only call36 source-law-navigation-35: reconstruct both native NavigationReferences maps from hash-bound canonical model_view and NUMBERED_REFERENCES receipts; canonical view content must match except native view UUID and separately journal-bound SELECT domain-choice ID. The same canonical preview ID must map bijectively with the current-view role across exactly V1/V2. Normalize these aliases in comparison copies of user payload/schema only. Never mutate requests/responses; refuse if unchanged recorded response refers to any changed alias, and validate it against current schema.'],
    'required':['All38 protected requests, phase/order and system prompts match historical input; schemas are exact except the explicitly verified call36 V role renumbering. Actual raw-wire and raw-schema differences are recorded.',
        'All35 original navigation frame data, actions and location hashes match.',
        'Final answer content matches the original except separately native-journal-bound generated id/query_id; native run COMPLETED and publication PUBLISHED.',
        'Frozen files and original source artifacts remain unchanged.',
        'Candidate total Investigation.view time is below baseline; report per-view, startup, request and offline transport separately.'],
    'failure':'Stop on integrity/resource/unexpected schema or source/semantic mismatch, invalid native alias/domain proof, a response using a changed alias, or native contract failure. Preserve failed runs and never rewrite recorded responses or rerun the existing reservation.',
    'timing':'Same view/function wrappers as frozen1076, verified by AST; native domain/alias journal guards at calls36 and38, outside all view timers. Inclusive perf_counter wall/process CPU. Nested timers not additive. Frame hashing/writes outside view. Different run times and filesystem cache warmth are limitations. Only completed view-window speed comparison, no failed-baseline full-response speed comparison or p95.',
    'limits':{'rss_bytes':4*1024**3,'address_space_bytes':6*1024**3,'available_memory_bytes':3*1024**3,'disk_free_bytes':20*1024**3,'swap_growth_bytes':512*1024**2,'seconds':1800},
    'runtime':'Same frozen service.application/service API, pinned profile and dataset. Only harness binding selection points to frozen arm; active MAIN pointer is never edited.',
    'qualification_boundary':'Known trace is supplemental in-sample mechanics/performance, not unseen legal quality, GENOS throughput or model speed.'})
print('Frozen input inventory: 38 responses, 35 native frames; no product execution')
