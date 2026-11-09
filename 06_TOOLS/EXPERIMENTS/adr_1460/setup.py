"""Freeze the fix candidate (stage r3), the reused public test corpus, authorization and criteria before any model call (ADR-1460)."""
from common import *
import shutil
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(parents=True, exist_ok=True)
assert not (DES / 'freeze.json').exists(), 'already frozen'
REQUEST = '실험해봐 우리 기본 rag셋팅은 오라클 + vector이긴한데 우리 없는 조문이 있을수 있으니까 그건 sql로 해도 무방함'
rel = lambda path: str(Path(path).relative_to(ROOT))

# 1. Candidate = stage r3: the MAIN178 release files, 38 of them replaced (6 product + 32 derived pins), byte for byte.
release_path = ROOT / '08_DEPLOYMENT/RELEASES' / BASE_RELEASE_ID / 'release.json'
release = read(release_path)
files = {n: sha(STAGE / n) for n in release['files']}
assert {str(p.relative_to(STAGE)) for p in STAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts} == set(files)
changed = sorted(n for n in files if files[n] != release['files'][n])
assert len(changed) == 38, len(changed)
product = ['02_BACKEND/workflow/risk_team_document_compare_workflow/flow.py',
           '02_BACKEND/workflow/risk_team_document_compare_workflow/compare_unit.py',
           '02_BACKEND/workflow/risk_team_document_compare_workflow/manifest.json',
           '02_BACKEND/semantic_runtime/workflow_rag.py',
           '02_BACKEND/semantic_runtime/legal_agent/workflow_execution.py',
           '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py']
assert set(product) <= set(changed)
put(DES / 'baseline.json', {'base_release_id': BASE_RELEASE_ID, 'base_release_manifest_sha256': sha(release_path),
                            'stage': rel(STAGE), 'changed_files': changed, 'product_files': product,
                            'stage_verification': '09_ARTIFACTS/AUDITS/20261108-document-compare-external-fix/regression-compare.json',
                            'reference_run': rel(BASELINE_ADR)})
present = [n for n in files if (ROOT / n).is_file() and not (ROOT / n).is_symlink()]
absent = [n for n in files if n not in present]
manifest = read(ADR / '실험/manifest.json')
path = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1460/extfix'
if not (path / 'candidate.json').exists():
    path = ac.snapshot(ADR, 'extfix', present, experiment_id=manifest['experiment_id'], arm_id='extfix', run_ids=['run-001'])
    for n in present:
        if sha(path / 'snapshot' / n) != files[n]:
            shutil.copyfile(STAGE / n, path / 'snapshot' / n)
    for n in absent:
        target = path / 'snapshot' / n; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STAGE / n, target)
        ac.register_file(path, n, upstream_state='absent')
    ac.freeze(path)
assert not ac.validate(path), ac.validate(path)
revision = read(path / 'candidate.json')['revisions'][-1]
C = path / 'revisions' / revision['revision_id'] / 'snapshot'
assert all(sha(C / n) == h for n, h in files.items())
pin = {'manifest_path': rel(path / 'candidate.json'), 'manifest_sha256': sha(path / 'candidate.json'),
       'revision_id': revision['revision_id'], 'revision_sha256': revision['revision_sha256']}
put(DES / 'candidate.json', {'code_root': rel(C), 'files': files, 'new_files': absent, 'pin': pin,
                             'base_release': {'release_id': BASE_RELEASE_ID, 'manifest_sha256': sha(release_path)},
                             'offline_evidence': '09_ARTIFACTS/AUDITS/20261108-document-compare-external-fix/'})
shutil.copyfile(C / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json', DES / 'provider-policy.json')
assert read(ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json') == read(DES / 'provider-policy.json')

# 2. Transport modules pinned to immutable copies (same list as ADR-1424/1447).
pins = read(ROOT / '04_EXPERIMENTS/ADR/ADR-1424-main161-cm51-financial-qwen/artifacts/transport/transport-pins.json')
for name in pins['files']:
    target = ART / 'transport' / name; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target); pins['files'][name] = sha(target)
put(ART / 'transport/transport-pins.json', pins)

# 3. The ADR-1440 test corpus (also ADR-1443/1447), reused by hash: local SQLite store, keyword first search (user: SQL is fine).
live = read(PARENT / 'design/comparison-source.json')
for file, expected in live['files'].items():
    assert sha(ROOT / file) == expected, 'reused corpus file changed: ' + file
live['reused_from'] = 'ADR-1440'
put(DES / 'comparison-source.json', live)
put(DES / 'scripted-source.json', read(PARENT / 'design/scripted-source.json'))
reference = read(BASELINE_ADR / 'artifacts/design/case.json')
case = {'id': CASE, 'question': reference['question'], 'document_ids': sorted([INTERNAL, *EXTERNAL]), 'public_documents_only': True}
assert case == reference, 'question or documents differ from ADR-1447'
put(DES / 'case.json', case)
put(DES / 'scripted-case.json', {'id': 'scripted-wiring', 'question': '문서 대사: 모의내규 전체를 대사해 주세요.',
                                 'document_ids': ['inside', 'outside'], 'synthetic': True})
put(DES / 'authorization.json', {'user_instruction': REQUEST, 'workflow_id': 'risk_team_document_compare_workflow', 'question': case['question'],
                                 'documents': [{k: r[k] for k in ('document_id', 'name', 'category')} for r in live['documents']],
                                 'generation_id': live['source_manifest']['generation_id'], 'store_sha256': live['source_manifest']['store_sha256'],
                                 'scope': 'Five documents of the existing public grant only (copied text, no internal 내규 original). '
                                          'The public guideline plays the internal role. Local SQLite store, keyword first search '
                                          '(the default Oracle + vector setting is not used; the user allowed SQL for this test).'})
criteria = {
    'request': REQUEST,
    'question': '외규 조사 수정(번호 뺀 검색어, 질문 속 내규 원문의 정의 자동 확보 끄기, 외규 조 전체 비교, 묶음 안 공유)으로 '
                '같은 공개 모범규준 문서 대사의 판정 보류 비율이 ADR-1447보다 줄어드는가',
    'primary_metric': 'Share of comparison units with an open verdict (DEFERRED or EXTERNAL_NOT_FOUND) in the reading groups finished '
                      'by both this experiment and ADR-1447 (same group_id; ADR-1447 state after its run-002, 22 groups, 122/135 open)',
    'required': ['HTTP 200 workflow-result-v1 for risk_team_document_compare_workflow; the stated document is selected without asking',
                 'Primary: open share on the shared groups <= 0.70 and more substantive verdicts there than ADR-1447',
                 'Every unit verdict other than DEFERRED/EXTERNAL_NOT_FOUND cites an internal and an external original (checked from saved state)',
                 'Document-compare children acquire no automatic question definitions (SYSTEM_DEFINITION targets 0 in every child)',
                 'No run stops because a comparison input exceeded the context bound',
                 'The same request again adds 0 model calls; frozen candidate/transport/corpus hashes unchanged'],
    'secondary': ['Groups finished, units, verdict counts overall and on shared groups; units whose comparison cited a nearby_unit article',
                  'Child reads of external articles whose number equals the unit internal number (number chasing)',
                  'Whole-article widening (articles read whole / kept as read), comparison input sizes',
                  'Physical requests per stage, tokens, reported cost, wall seconds, unknown outcomes',
                  'Operator reading of a sample of units against the originals (descriptive, no evaluator call)'],
    'not_measured': 'Legal correctness of verdicts, real internal documents, repeat stability, GENOS internal model, Oracle + vector path. '
                    'One document, in-sample (the fix was designed from ADR-1447 records); a public guideline stands in for an internal rule. '
                    'Unit boundaries are re-decided by the model in each run, so units are compared per reading group, not one to one.',
    'stop': 'run-001 is one request. If it stops on an unknown provider outcome (the product never re-sends it), the experimenter sends '
            '"문서 대사: 계속" in the same session as run-002, and once more as run-003 at most; then stops regardless. '
            'HTTP 500 or a workflow failure stops without continuation.',
    'limits': {'physical_total': None, 'per_physical_seconds': 180, 'reported_cost_usd': None, 'request_seconds': None,
               'ram_start_gib': 5, 'wait_seconds': 5400, 'continuations': 2,
               'start_gate': 'waits only for another experiment live.py',
               'guard': 'resource_guard.py (= ADR-1447): start needs 5GiB available; low available RAM (<3GiB) pauses sending before a physical call; '
                        'worker RSS 5GiB, worker swap growth 128MiB, free disk 20GiB stop it. Host swap growth recorded only.'},
    'quality_certified': False, 'in_sample': True}
put(DES / 'criteria.json', criteria)

manifest['lineage']['hypothesis_delta'] = criteria['question']
manifest['design'].update(hypothesis=criteria['question'] + ' — 예상: 같은 묶음의 판정 보류 비율이 90%에서 70% 이하로 줄고, 정의·부칙 조각과 같은 번호 조문 읽기가 줄어든다.',
                          primary_metric=criteria['primary_metric'], success_criteria=criteria['required'],
                          failure_criteria=['Open share on the shared groups > 0.70', 'HTTP 500 or a workflow failure',
                                            'A comparison-input bound stop', 'Any source/ACL/hash mismatch reported by the product'],
                          criteria_frozen_before_run=True,
                          criteria_freeze_evidence={'path': rel(DES / 'criteria.json'), 'sha256': sha(DES / 'criteria.json')})
manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[
    {**pin, 'candidate_id': 'extfix', 'experiment_id': manifest['experiment_id'], 'arm_id': 'extfix', 'run_ids': ['run-001'],
     'runner_path': rel(TOOLS / 'live.py'), 'runner_sha256': sha(TOOLS / 'live.py')}])
for arm in manifest['design']['arms']:
    if arm['id'] == 'baseline':
        arm.update(changes='ADR-1447 maindoc (MAIN173 code), reference only: its saved state after run-002 (22/32 groups) is compared, not re-run',
                   controls='Same corpus, question, documents, profile, model policy')
    else:
        arm.update(changes='Stage r3 = MAIN178 + 문서 대사 외규 조사 수정 6파일: 번호 뺀 검색어, question_definitions=false, '
                           '외규 조 전체 비교(4,000자 이하), 묶음 안 이웃 조문 공유(16,000자), JSON 크기 비교 입력 한도',
                   controls='Selected profile-unified-v6 unchanged (supervisor enforce), Qwen3.8 policy, five public-grant documents, local SQLite')
manifest['runs'][0].update(arm_ids=['extfix'], selection_rule='One predeclared document comparison request; ' + criteria['stop'],
                           artifact_path=rel(ART / 'run-001/result.json'))
manifest['dataset'].update(name='ADR-1440 test corpus (also ADR-1443/1447) reused by hash: five public-grant documents (guideline as internal)',
                           version=live['source_manifest']['generation_id'],
                           frozen_source=rel(DES / 'comparison-source.json'), sha256=sha(DES / 'comparison-source.json'),
                           legal_version_checked=False, reference_version_checked=False)
manifest['llm_policy']['llm_calls'] = [{'role': 'product', 'class': 'product', 'model': 'qwen/qwen3.8-27b', 'repeats': 1}]
reason = 'Retrieval inside the workflow children is product behaviour; this probe compares verdict outcomes per reading group, not recall. No gold coordinates.'
manifest['retrieval_accounting'].update(not_applicable_reason=reason)
manifest['retrieval_accounting']['stage_ledger'].update(not_applicable_reason=reason)
(ADR / '실험/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')

put(ART / 'preparation-issues.json', [])
frozen = [*sorted(TOOLS.glob('*.py')), *(DES / n for n in ('baseline.json', 'candidate.json', 'provider-policy.json', 'comparison-source.json',
                                                         'scripted-source.json', 'case.json', 'scripted-case.json', 'authorization.json', 'criteria.json')),
          ART / 'transport/transport-pins.json', ROOT / '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json', ROOT / '00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json']
put(DES / 'freeze.json', {'files': {rel(p): sha(p) for p in frozen if p.name not in ('analyze.py',)}, 'model_calls_before_freeze': 0})
print('frozen: candidate', len(files), 'files (', len(absent), 'new,', len(changed), 'changed vs', BASE_RELEASE_ID, '); corpus',
      [(r['name'], r['category'], r['blocks'], r['chars']) for r in live['documents']])
