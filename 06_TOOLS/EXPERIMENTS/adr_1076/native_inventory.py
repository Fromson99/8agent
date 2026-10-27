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
inventory = {'source_result':bound(case/'result.json'),'source_binding':bound(source/'binding.json'),
    'original_journal':bound(journal),'request':bound(case/'request.json'),
    'response':bound(case/'response.json'),'calls':calls,'frames':frame_inventory}
put(DESIGN/'secondary-inputs.json',inventory)
put(DESIGN/'secondary-replay.json',{
    'schema_version':'adr1076-literal-native-secondary-v1',
    'input_inventory':bound(DESIGN/'secondary-inputs.json'),
    'known_in_sample':True,'primary_criteria_unchanged':True,
    'runs':{'run-002':['baseline','optimized']},'execution':'Sequential fresh processes, baseline then optimized, one corpus worker at a time.',
    'expected_responses':38,'expected_views':35,'external_model_calls':0,
    'response_rewrite':False,'request_identity_substitution':False,'network_allowed':False,
    'comparison_exemptions':['Only generated UUID /messages/1/content/view/view_id is omitted in comparison copies; stable aliases V1 etc remain exact.',
        'Final answer comparison copy omits only id and query_id after checking answer:id=answer:+native run_id and answer.query_id=native query.id, with both response identities checked against the new journal. Remaining answer fields are exact.'],
    'required':['All38 protected requests, schemas, phases and system prompts match historical input before delivery.',
        'All35 original navigation frame data, actions and location hashes match.',
        'Final answer content matches the original except separately native-journal-bound generated id/query_id; native run COMPLETED and publication PUBLISHED.',
        'Frozen files and original source artifacts remain unchanged.',
        'Candidate total Investigation.view time is below baseline; report per-view, startup, request and offline transport separately.'],
    'failure':'Stop the arm on integrity, resource, unexpected request or native contract failure; preserve results. No response rewriting or automatic rerun. A failed reconstruction cannot support a speed claim.',
    'timing':'Same wrappers in both arms. Inclusive perf_counter wall/process CPU per function. Nested timers are not additive. Frame hashing and output writes outside measured view; offline transport reads/comparison separately timed.',
    'limits':{'rss_bytes':4*1024**3,'address_space_bytes':6*1024**3,'available_memory_bytes':3*1024**3,'disk_free_bytes':20*1024**3,'swap_growth_bytes':512*1024**2,'seconds':1800},
    'runtime':'Same frozen service.application/service API, pinned profile and dataset. Only harness binding selection points to frozen arm; active MAIN pointer is never edited.',
    'qualification_boundary':'Known trace is supplemental in-sample mechanics/performance, not unseen legal quality, GENOS throughput or model speed.'})
print('Frozen input inventory: 38 responses, 35 native frames; no product execution')
