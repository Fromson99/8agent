from common import *
s = read(ART/'stage.json'); i = read(ART/'working-integration.json')
C = ROOT/s['roots']['candidate']
checks = {n: sha(ROOT/n) == v['after'] == sha(C/n) for n,v in i['changed_files'].items()}
mismatches = []; count = 0
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
    for n,h in read(p).get('files',{}).items():
        count += 1
        if sha(ROOT/n) != h: mismatches.append({'manifest':str(p.relative_to(ROOT)), 'file':n})
pipeline = all(sha(ROOT/e['manifest']) == e['sha256'] for e in read(ROOT/'00_SYSTEM/PIPELINE.json')['engines'].values())
profile = '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'
r = {'changed_files_match_frozen':checks, 'engine_file_pins_checked':count,
     'engine_mismatches':mismatches, 'pipeline_manifest_pins_match':pipeline,
     'working_answer_progress_control':read(ROOT/profile)['candidate_navigation'].get('answer_progress_control',False),
     'candidate_answer_progress_control':read(C/profile)['candidate_navigation'].get('answer_progress_control',False),
     'working_profile_unchanged':sha(ROOT/profile) == s['working_before'][profile],
     'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == s['pointer_sha256']}
save(ART/'working-final-check.json',r)
print(json.dumps(r,ensure_ascii=False))
assert all(checks.values()) and not mismatches and pipeline
assert not r['working_answer_progress_control'] and r['working_profile_unchanged'] and r['main_unchanged']
