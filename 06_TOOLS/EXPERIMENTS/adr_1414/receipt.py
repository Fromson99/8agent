"""Read-only reconciliation of completed ADR1412 evidence; never call a model."""
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/home/jin/8-AGENT')
OLD = ROOT/'04_EXPERIMENTS/ADR/ADR-1412-main152-integration-r5-qwen'
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1414-main152-integration-record-receipt'
ART = ADR/'artifacts'

def read(p):
    p = Path(p)
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as f:
        v = json.load(f)
    if isinstance(v, dict) and set(v) == {'raw_json'}:
        return read(ROOT/v['raw_json']['path'])
    return v

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def put(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')

def ref(p):
    return {'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'bytes': p.stat().st_size}

if sys.argv[1] == 'freeze':
    assert not (ART/'criteria.json').exists()
    criteria = {
        'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'purpose': '기존 결과를 알고 수행하는 기록 감사. 새 성능 시험이나 재채점이 아님.',
        'checks': ['30개 기존 응답과 직접판정 해시 일치', '기존 23통과/7실패 판정 보존',
                   '150개 실제 물리 호출의 정상/비용 집계 일치', '모든 실행 binding MAIN152',
                   '7개 실패의 저장된 표시계약 오류와 원응답 해시 일치',
                   '30개 중복요청 추가호출0/같은답변', '기존 원문/ACL/wire 감사 불일치0/예산일치',
                   '마지막 응답 뒤 MAIN153 전환', '기존 MAIN152 532파일 해시 일치',
                   '완료된 상세원장 해시 일치', '기존 메타 검증실패 기록 보존',
                   '기존 입력파일을 감사 중 변경하지 않음'],
        'failure': '필수 확인 하나라도 불일치하면 감사 실패. 기존 실패 7개를 통과로 바꾸지 않음.',
        'new_model_calls': 0, 'new_grades': 0, 'product_changes': 0,
    }
    put(ART/'criteria.json', criteria)
    m = read(ADR/'실험/manifest.json')
    m['in_sample'] = True
    m['lineage'].update(root_ref='ADR-1414-experiment-v1/receipt',
                        root_refs=['ADR-1414-experiment-v1/receipt'],
                        hypothesis_delta='기존 응답 및 직접판정 불변의 메타데이터 감사')
    m['design'].update(hypothesis='기록 실패와 제품 응답 실패를 분리하여 기존 실제 결과를 정확히 결속할 수 있다.',
                       primary_metric='사전 고정한 기록 일치 검사 전부 통과',
                       success_criteria=criteria['checks'], failure_criteria=criteria['failure'],
                       criteria_frozen_before_run=True,
                       arms=[{'id':'receipt','role':'candidate','derived_from':[],
                              'changes':'별도 기록 영수증만 생성','controls':'기존 제품·응답·직접판정·원장 불변'}])
    reason = '기존 파일 해시와 집계만 검사하는 메타데이터 감사. 새 회수·제품 구현·모델 실행 없음.'
    m['design']['code_isolation']['reason'] = reason
    m['runs'][0].update(arm_ids=['receipt'], selection_rule='ADR1412의 저장된30개 질문 전부, 표본 제외 없음')
    m['llm_policy']['llm_calls'] = []
    m['dataset'] = {'name':'ADR1412 saved evidence', 'version':'20261105-original',
                    'frozen_source':str((ART/'criteria.json').relative_to(ROOT)),
                    'sha256':sha(ART/'criteria.json'), 'legal_version_checked':False,
                    'reference_version_checked':True,
                    'note':'기존 등록 원문 검토 결과를 승계하며 법령 최신성 재검증은 하지 않음.'}
    m['retrieval_accounting']['not_applicable_reason'] = reason
    m['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = reason
    put(ADR/'실험/manifest.json', m)
    print('Criteria frozen for metadata-only audit')
    sys.exit(0)

assert sys.argv[1] == 'run'
assert (ART/'criteria.json').exists() and not (ART/'audit-result.json').exists()
inputs = {}
def track(p):
    p = Path(p)
    inputs[str(p)] = ref(p)
    return read(p)

result = track(OLD/'artifacts/result.json')
reviews = track(OLD/'artifacts/direct-review.json')
audit = track(OLD/'artifacts/source-wire-audit.json')
diagnosis = track(OLD/'artifacts/failure-diagnosis.json')
baseline = track(OLD/'artifacts/design/baseline.json')
change = track(OLD/'artifacts/post-run-main-change.json')
old_manifest = track(OLD/'실험/manifest.json')
rows = result['rows']
assert len(rows) == len(reviews) == len({r['case_id'] for r in rows}) == 30
assert sum(r['semantic_pass'] for r in rows) == 23
assert all(r['direct_review'] == reviews[r['case_id']] for r in rows)
calls = []
last_response = 0
raw_refs = 0
for row in rows:
    cid = row['case_id']
    folder = OLD/'artifacts/public-live'/(cid+'-selected')
    p = ROOT/row['response_path']
    assert sha(p) == row['response_sha256'] == reviews[cid]['response_sha256']
    inputs[str(p)] = ref(p)
    last_response = max(last_response, p.stat().st_mtime)
    assert track(folder/'binding.json')['selected_pointer'] == baseline['pointer']
    calls.extend(track(folder/'calls.json'))
    duplicate = track(folder/'turn-1/duplicate.json')
    assert duplicate['same_answer'] and duplicate['extra_model_calls'] == 0
    for p in sorted((folder/'raw').glob('call-*/*.ref.json')):
        inputs[str(p)] = ref(p)
        pointer = json.loads(p.read_text())['raw_json']
        target = ROOT/pointer['path']
        assert sha(target) == pointer['stored_sha256']
        inputs[str(target)] = ref(target)
        raw_refs += 1
assert len(calls) == 150 and all(c['status']=='responded' and c['http_status']==200 for c in calls)
assert abs(sum(c['usage']['cost'] for c in calls)-result['reported_cost_usd']) < 1e-9
failed = {r['case_id'] for r in rows if not r['semantic_pass']}
assert failed == set(result['presentation_name_rejection_cases'])
assert failed == {c['case_id'] for c in diagnosis['cases']}
for item in diagnosis['cases']:
    assert any(e['error']=='Source details belong in source cards' for e in item['saved_errors'])
    assert reviews[item['case_id']]['raw_model_expected_content']
    for response in item['model_final_outputs']:
        p = ROOT/response['path']
        assert sha(p) == response['sha256']
        inputs[str(p)] = ref(p)
assert len(audit['cells']) == 30
assert all(c['budget_matches'] and not any(c[k] for k in ('source_mismatches','acl_violations','wire_mismatches')) for c in audit['cells'])
assert sum(c['source_checks'] for c in audit['cells']) == 159
assert sum(c['delivered_checks'] for c in audit['cells']) == 144
assert dt.datetime.fromtimestamp(last_response,dt.timezone.utc) < dt.datetime.fromisoformat(change['observed_pointer']['activated_at'])
release = baseline['release']
assert len(release['files']) == 532
assert all(sha(ROOT/release['code_root']/p)==h for p,h in release['files'].items())
ledger = old_manifest['retrieval_accounting']['stage_ledger']
p = ROOT/ledger['artifact_path']
assert sha(p) == ledger['sha256']
inputs[str(p)] = ref(p)
assert 'ERROR:' in (ART/'prior-final-validation.log').read_text()
assert old_manifest['reservation']['status']=='completed' and old_manifest['results']['status']=='not_run'
active = read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
active_release = read(ROOT/active['manifest_path'])
guard = ROOT/active_release['code_root']/'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py'
guard_present = "raise ProposalError('Source details belong in source cards')" in guard.read_text()
assert all(sha(Path(p)) == v['sha256'] for p,v in inputs.items())
put(ART/'input-file-hashes.json', {'files':list(inputs.values()), 'all_unchanged_after_audit':True})
receipt = {'state':'PASS_METADATA_AUDIT', 'source_adr':'ADR-1412', 'preserved_product_result':'23 pass / 7 fail',
           'checks_passed':len(read(ART/'criteria.json')['checks']), 'saved_question_responses':30,
           'saved_physical_calls':150, 'raw_reference_hash_checks':raw_refs,
           'saved_MAIN':152, 'saved_serving_files_verified':532,
           'active_MAIN_observed':active['generation'], 'active_name_rejection_present':guard_present,
           'last_response_utc':dt.datetime.fromtimestamp(last_response,dt.timezone.utc).isoformat(),
           'subsequent_cutover_utc':change['observed_pointer']['activated_at'],
           'old_final_metadata_validation':'failed; original immutable record retained',
           'ledger_check':'exact saved gzip SHA only; no new ledger reconstruction',
           'source_check':'existing source/wire audit preserved; no new DB or legal-version verification',
           'new_model_calls':0,'new_judge_calls':0,'new_grades':0,'product_changes':0,
           'input_hash_index':ref(ART/'input-file-hashes.json')}
put(ART/'audit-result.json',receipt)
corrected = dict(result, state='COMPLETED_WITH_FAILURES',
                 recorded_state_before_receipt=result['state'],
                 record_receipt='ADR-1414', active_main_at_receipt=active['generation'],
                 main_changed_by_this_experiment=False, old_metadata_final_validation_passed=False)
put(ART/'corrected-result.json',corrected)
report = '''MAIN152 통합테스트 R5 결과

서로 다른 답변 질문30개를 실제 실행: 기대답변·출처 일치23개, 실패7개.
7개 모두 원응답은 기대내용과 맞지만 본문에 법률명이 포함되어 서버의
“Source details belong in source cards” 검사로 사용자 답변 전체가 거절됐다.
원문카드 중복을 줄이기 위한 문체 지침을 강제 실패 조건으로 구현한 문제다.
법률명이 답변 내용을 더 명확히 해도 이 조건은 단순 문자열 포함만으로 거절한다.
근거가 확인된 법률명·조문 표기를 허용하는 수정이 필요하며, 이번에는 제품을 바꾸지 않았다.

30개 결과를 통테 답변50행에 매핑: 39행 통과/11행 실패. 중복행은 추가 시험이 아니다.
화면·출처열기10항목은 미실행. 온톨로지 기본OFF, 로컬 실제 root service, Qwen3.8.
모델150회 모두 정상응답, UNKNOWN0. 보고비용 $0.1866168.
질문별 중앙값46.274초, p95 86.386초, 최대111.897초.
원문159/전달144 검사, 원문·권한·wire 불일치0, 호출예산일치.
동일 요청 재조회30개 모두 같은답변/추가모델0.
등록된 조항 질문의 단일 실행 결과이며 일반 법률 품질·최신성·GENOS 현장 인증은 아니다.

실행은 전부 MAIN152: 마지막 저장 응답 UTC10:53:37.563. 이후 별도 작업에서 UTC10:57:02 MAIN153 전환.
감사 시 MAIN153에도 법률명 차단이 남아 있음을 확인. MAIN153의 새 실모델 결과는 아니다.

기록 정정: 상세원장 생성과 결과 집계가 겹쳐 완료 메타가 덮였고, 이후 메인 변경으로
최종 집계가 중단됐는데도 완료 처리한 기록 오류가 있었다. 원 ADR1412 최종 메타 검증은 실패다.
완료된 원본을 덮지 않고 ADR1414에서 기존 응답·직접판정·호출·원장의 해시와 집계를 확인했다.
이 정정에서 질문 재실행·재채점·추가 모델·제품 변경은 없다.

질문별 실제 답변과 판정: corrected-result.json
기존 60행 표: ../../ADR-1412-main152-integration-r5-qwen/artifacts/통합테스트_60행_결과.csv
실패 원응답/저장 오류: ../../ADR-1412-main152-integration-r5-qwen/artifacts/failure-diagnosis.json
'''
(ART/'통합테스트_확정결과.txt').write_text(report)
m = read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',artifact_path=str((ART/'audit-result.json').relative_to(ROOT)),sha256=sha(ART/'audit-result.json'))
m['results'].update(status='complete',by_arm={'receipt':receipt},comparisons=[],judge_disagreements=0,
                    usage={'new_model_calls':0,'new_grades':0},latency={'not_applicable':'offline metadata only'},
                    error_taxonomy=['Original ADR1412 final metadata invalid; preserved separately',
                                    'Original product presentation rejection: 7 of 30'])
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted').replace('in_sample: false','in_sample: true')
headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[report,'원 ADR1412의 결과 기록과 상세원장 쓰기가 겹쳤다. 뒤늦은 메인전환과 완료처리로 기존 최종 메타 검증이 실패했다. 기존 이력을 보존한다.',
       '기존 결과를 알고 하는 기록 감사다. criteria.json의12가지 기록 일치 조건을 실행 전에 고정했다.',
       '단일 receipt arm. 기존30개 응답과150개 실제 호출 전수. 새 제품 변경·모델·판정 없음.',
       'input-file-hashes.json에 원본 경로/바이트/SHA. 기준판정은 기존 direct-review.json, 모델은 호출하지 않음.',
       json.dumps(receipt,ensure_ascii=False,indent=2),
       '7개 원응답의 법률명 표기 때문에 표시계약 거절. 기록 오류는 별개이며 prior-final-validation.log 보존.',
       '이번 감사 모델0·비용0. 기존 시험 비용/지연은 확정결과에 기재. 기존 회수 원장은 해시만 확인했다.',
       '실제 응답과 기존 판정23/7을 보존했음을 확인. 원 ADR 메타 검증이 통과한 것으로 바꾸지 않는다.',
       '이미 결과를 아는 인샘플 감사. 새 정확도 평가·법률 최신성·MAIN153 실모델 검증 아님.',
       '제품/MAIN/DB 변경 없음. 재실행하거나 완료 원본을 덮지 않음.',
       '기존 실행 원본은 ADR1412. 새 질문 실행은 새 ADR 필요. 이 감사의 코드: 06_TOOLS/EXPERIMENTS/adr_1414/receipt.py (freeze 후 run). 완료 원본 재실행 금지.']
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN152 통합테스트 기록 영수증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(headings,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기존 결과 기록 감사\n\n질문 재실행/재채점 없음. 기존30개 응답·직접판정·150호출을 결속했다.\n\n[결과](../artifacts/통합테스트_확정결과.txt) · [감사](../artifacts/audit-result.json) · [기존 질문](../../ADR-1412-main152-integration-r5-qwen/실험/README.md)\n')
files=[p for p in ART.iterdir() if p.is_file() and p.name!='manifest.json']+[Path(__file__).resolve()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1414',
                        'files':[dict(ref(p),description='Read-only reconciliation evidence',contains_raw_prompts_and_outputs=False) for p in sorted(files)]})
print(json.dumps(receipt,ensure_ascii=False,indent=2))
