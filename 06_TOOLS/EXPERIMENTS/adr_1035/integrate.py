"""Selective verified working-code integration; no selected release mutation."""
from common import *
import re, shutil, tarfile
s=read(ART/'stage.json'); c=ROOT/s['root']; f=read(ART/'design-freeze.json')['files']['candidate']
assert not (ART/'working-integration.json').exists()
assert all(sha(c/n)==h for n,h in f.items())
assert all(sha(ROOT/n)==h for n,h in s['working_before'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
assert (ART/'guard-result.json').exists()
logs=['contracts-rev001.log','regression-rev001.log','baseline-main50.log']
target=(ART/logs[0]).read_text(); assert '60 passed' in target and 'FAILURES' not in target and 'ERRORS' not in target
comparison=read(ART/'regression-baseline-comparison.json')
assert comparison['same_failed_tests'] and len(comparison['failed_tests'])==6
for name in logs[1:]:
    log=(ART/name).read_text()
    assert [x.split('/snapshot/')[-1] for x in re.findall(r'^FAILED (.+)$',log,re.M)]==comparison['failed_tests']
assert '95 passed' in (ART/logs[1]).read_text()
o=read(ART/'observations.json')['by_arm']['candidate']; j=read(ART/'judgment-review.json')
assert o['source_checks']['mismatches']==o['source_checks']['scope_violations']==0
assert j['prior_commit_mismatches']==j['input_continuity_violations']==0
changed=[n for n,h in f.items() if s['working_before'].get(n)!=h]
for n in changed:
    assert (sha(ROOT/n) if (ROOT/n).exists() else None)==s['working_before'].get(n),n
save(ART/'integration-decision.json',{'authority':'User requested fix and experiment; predeclared selective integration of verified deterministic fixes into working code.',
    'verified_logs':{n:sha(ART/n) for n in logs},'candidate_tests':{'passed':155,'failed':6,'same_parent_failures':6},
    'live_observations_sha256':sha(ART/'observations.json'),'judgment_audit_sha256':sha(ART/'judgment-review.json'),
    'semantic_quality_certified':False,'revision':read(ADR/'실험/manifest.json')['design']['code_isolation']['candidates'][0]['revision_id'],
    'before':{n:s['working_before'].get(n) for n in changed},'after':{n:f[n] for n in changed}})
with tarfile.open(ART/'working-before.tar.gz','w:gz') as archive:
    for n in changed:
        if (ROOT/n).is_file():archive.add(ROOT/n,arcname=n)
for n in changed:
    (ROOT/n).parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(c/n,ROOT/n)
assert all(sha(ROOT/n)==h for n,h in f.items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'files':changed,'sha256':{n:f[n] for n in changed},'all_513_files_match_candidate':True,
    'MAIN102_pointer_unchanged':True,'GENOS_changed':False,'backup_sha256':sha(ART/'working-before.tar.gz'),
    'rollback':'Verify current listed files match after-hashes, restore preexisting files from working-before.tar.gz, remove only unchanged new files with before=null. Do not change selected MAIN pointer.'})
print('Integrated',len(changed),'files; selected MAIN unchanged')
