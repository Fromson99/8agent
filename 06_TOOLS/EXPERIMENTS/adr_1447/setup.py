"""Freeze the MAIN release code, the reused public test corpus, authorization and criteria before any model call (ADR-1447)."""
from common import *
import importlib, shutil, sqlite3
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(parents=True, exist_ok=True)
assert not (DES / 'freeze.json').exists(), 'already frozen'
REQUEST = '2'  # 선택 2: MAIN 반영 → 반영된 MAIN 코드로 실제 문서 전체 실행 → 성공하면 삼성메일
rel = lambda path: str(Path(path).relative_to(ROOT))

# 1. Candidate = the selected MAIN release that carries 문서 대사, every release file pinned (byte-identical copy).
pointer = read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer['release_id'] == RELEASE_ID, 'selected MAIN is not the 문서 대사 release: ' + pointer['release_id']
release = read(ROOT / pointer['manifest_path'])
MAIN = (ROOT / pointer['manifest_path']).parent / 'code'
files = dict(release['files'])
assert all(sha(MAIN / n) == h for n, h in files.items()), 'release code differs from its manifest'
put(DES / 'baseline.json', {'pointer': pointer, 'release_manifest_sha256': sha(ROOT / pointer['manifest_path'])})
present = [n for n in files if (ROOT / n).is_file() and not (ROOT / n).is_symlink()]
absent = [n for n in files if n not in present]
manifest = read(ADR / '실험/manifest.json')
path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1447/maindoc'
if not (path / 'candidate.json').exists():
    path = ac.snapshot(ADR, 'maindoc', present, experiment_id=manifest['experiment_id'], arm_id='maindoc', run_ids=['run-001'])
    for n in present:
        if sha(path / 'snapshot' / n) != files[n]:
            shutil.copyfile(MAIN / n, path / 'snapshot' / n)
    for n in absent:
        target = path / 'snapshot' / n; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MAIN / n, target)
        ac.register_file(path, n, upstream_state='absent')
    ac.freeze(path)
assert not ac.validate(path), ac.validate(path)
revision = read(path / 'candidate.json')['revisions'][-1]
C = path / 'revisions' / revision['revision_id'] / 'snapshot'
assert all(sha(C / n) == h for n, h in files.items())
pin = {'manifest_path': rel(path / 'candidate.json'), 'manifest_sha256': sha(path / 'candidate.json'),
       'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256']}
put(DES / 'candidate.json', {'code_root': rel(C), 'files': files, 'new_files': absent, 'pin': pin,
                             'release': {'release_id': pointer['release_id'], 'generation': pointer['generation'],
                                         'manifest_path': pointer['manifest_path'], 'manifest_sha256': sha(ROOT / pointer['manifest_path'])},
                             'offline_evidence': '09_ARTIFACTS/AUDITS/20261107-document-compare-main172/'})
shutil.copyfile(C / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json', DES / 'provider-policy.json')
assert read(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES / 'provider-policy.json')

# 2. Transport modules pinned to immutable copies (same list as ADR-1424/1429/1435).
pins = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    target = ART / 'transport' / name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target); pins['files'][name] = sha(target)
put(ART / 'transport/transport-pins.json', pins)

# 3. The ADR-1440 test corpus, reused by hash (not rebuilt).
live = read(PARENT / 'design/comparison-source.json')
for file, expected in live['files'].items():
    assert sha(ROOT / file) == expected, 'reused corpus file changed: ' + file
live['reused_from'] = 'ADR-1440'
put(DES / 'comparison-source.json', live)
put(DES / 'scripted-source.json', read(PARENT / 'design/scripted-source.json'))
case = {'id': CASE, 'question': '문서 대사: 금융투자회사의 리스크관리 모범규준 문서 전체를 외규와 대사해 주세요.',
        'document_ids': sorted([INTERNAL, *EXTERNAL]), 'public_documents_only': True}
put(DES / 'case.json', case)
put(DES / 'scripted-case.json', {'id': 'scripted-wiring', 'question': '문서 대사: 모의내규 전체를 대사해 주세요.',
                                 'document_ids': ['inside', 'outside'], 'synthetic': True})
put(DES / 'authorization.json', {'user_instruction': REQUEST, 'workflow_id': 'risk_team_document_compare_workflow', 'question': case['question'],
                                 'documents': [{k: r[k] for k in ('document_id', 'name', 'category')} for r in live['documents']],
                                 'generation_id': live['source_manifest']['generation_id'], 'store_sha256': live['source_manifest']['store_sha256'],
                                 'scope': 'Five documents of the existing public grant only (copied text, no internal 내규 original). '
                                          'The public guideline plays the internal role for this test.'})
criteria = {
    'request': REQUEST,
    'question': 'MAIN에 반영한 문서 대사(좁힌 검색 재검사 수정 포함)가 반영된 MAIN 코드 그대로 실제 Qwen3.8로 공개 모범규준(약 20쪽) 문서 전체를 끝내는가',
    'primary_metric': 'One real document comparison: share of reading groups finished and of comparison units with a substantive verdict',
    'required': ['HTTP 200 workflow-result-v1 for risk_team_document_compare_workflow; the stated document is selected without asking',
                 'Every reading group of the document ends done or held with a recorded reason (none left pending)',
                 'Every row of a done group is placed exactly once (unit / not target / hold), checked from the saved placements',
                 'Every unit verdict other than DEFERRED/EXTERNAL_NOT_FOUND cites an internal and an external original (server checked)',
                 'UNKNOWN 0; the same request again adds 0 model calls; frozen candidate/transport/corpus hashes unchanged'],
    'secondary': ['Groups, units, verdict counts, not-target and held rows',
                  'Physical requests per stage (group read / external child / unit compare), tokens, reported cost, wall seconds',
                  'Units whose external child read a named external rule first; external child status counts',
                  'Operator reading of a sample of units against the originals (descriptive, no evaluator call)'],
    'not_measured': 'Legal quality, real internal documents, repeat stability, GENOS internal model and Oracle path are not measured. '
                    'One request, in-sample; a public guideline stands in for an internal rule.',
    'stop': 'One request. No request time or call limit (user direction). An unknown provider outcome stops the run with the finished groups saved '
            '(user choice 가); it is not re-sent. A continuation ("계속") is a separate run (run-002+) started only after the user decides.',
    'limits': {'physical_total': None, 'per_physical_seconds': 180, 'reported_cost_usd': None, 'request_seconds': None,
               'ram_start_gib': 5, 'wait_seconds': 5400,
               'start_gate': 'waits only for another experiment live.py',
               'guard': 'resource_guard.py (= ADR-1443 = ADR-1440 run-003): start needs 5GiB available; during the run low available RAM (<3GiB) pauses sending '
                        'before a physical call instead of killing the process; worker RSS 5GiB, worker swap growth 128MiB, free disk 20GiB stop it. Host swap growth recorded only.'},
    'quality_certified': False, 'in_sample': True}
put(DES / 'criteria.json', criteria)

manifest['lineage']['hypothesis_delta'] = criteria['question']
manifest['design'].update(hypothesis=criteria['question'] + ' — 예상: 모든 묶음이 끝나고 대부분의 단위에 양쪽 원문 인용 판정이 나온다.',
                          primary_metric=criteria['primary_metric'], success_criteria=criteria['required'],
                          failure_criteria=[criteria['stop'], 'HTTP 500 or a workflow failure', 'A reading group left pending at the end',
                                            'Any source/ACL/hash mismatch reported by the product'],
                          criteria_frozen_before_run=True,
                          criteria_freeze_evidence={'path': rel(DES / 'criteria.json'), 'sha256': sha(DES / 'criteria.json')})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[
    {**pin, 'candidate_id': 'maindoc', 'experiment_id': manifest['experiment_id'], 'arm_id': 'maindoc', 'run_ids': ['run-001'],
     'runner_path': rel(TOOLS / 'live.py'), 'runner_sha256': sha(TOOLS / 'live.py')}])
for arm in manifest['design']['arms']:
    if arm['id'] == 'baseline':
        arm.update(changes='ADR-1443 docsearch arm; reference only, its real result is ADR-1443 (12/32 groups, HTTP 500 at the narrowed-scope re-check)', controls='Same corpus and question')
    else:
        arm.update(changes='The selected MAIN release that carries 문서 대사: ADR-1443 candidate merged onto the selected MAIN, plus the read-export '
                           're-check against the narrowed search scope of that call (cause of ADR-1443 HTTP 500)',
                   controls='Selected profile-unified-v6 unchanged (supervisor enforce), Qwen3.8 policy, five public-grant documents')
manifest['runs'][0].update(arm_ids=['maindoc'], selection_rule='One predeclared document comparison request; ' + criteria['stop'],
                           artifact_path=rel(ART / 'run-001/result.json'))
manifest['dataset'].update(name='ADR-1440 test corpus (also used by ADR-1443) reused by hash: five public-grant documents (guideline as internal)', version=live['source_manifest']['generation_id'],
                           frozen_source=rel(DES / 'comparison-source.json'), sha256=sha(DES / 'comparison-source.json'),
                           legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
reason = 'Retrieval inside the workflow children is product behaviour; this probe records groups, units and originals, not recall. No gold coordinates.'
manifest['retrieval_accounting'].update(not_applicable_reason=reason)
manifest['retrieval_accounting']['stage_ledger'].update(not_applicable_reason=reason)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')

put(ART / 'preparation-issues.json', [])
frozen = [*sorted(TOOLS.glob('*.py')), *(DES / n for n in ('candidate.json', 'provider-policy.json', 'comparison-source.json', 'scripted-source.json',
                                                         'case.json', 'scripted-case.json', 'authorization.json', 'criteria.json')),
          ART / 'transport/transport-pins.json', ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json']
put(DES / 'freeze.json', {'files': {rel(p): sha(p) for p in frozen if p.name not in ('finalize.py', 'publish.py')}, 'model_calls_before_freeze': 0})
print('frozen: candidate', len(files), 'files (', len(absent), 'new ); corpus', [(r['name'], r['category'], r['blocks'], r['chars']) for r in live['documents']])
