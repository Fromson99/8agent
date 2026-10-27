"""Freeze tested bytes and record this synthetic-only repair continuation."""
from pathlib import Path
import json
import hashlib
import sys

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1055-judgment-link-delta-repair'; ART=ADR/'artifacts'
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1055/delta-repair-r1'
SUMMARY='contracts-api-final-v2'
def read(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def files(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}

tested=read(ART/(SUMMARY+'-summary.json'))
assert tested['status']==0 and tested['failed']==0 and not tested['production_import_leaks'] and not tested['candidate_changed_during_tests']
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
if sys.argv[1]=='freeze':
    assert tested['files']==files(CAND/'snapshot')
    assert not read(CAND/'candidate.json')['revisions'],'never replace a frozen revision'
    c.freeze(CAND);assert not c.validate(CAND)
    manifest=read(CAND/'candidate.json');revision=manifest['revisions'][-1]
    m=read(ADR/'실험/manifest.json')
    m['design']['code_isolation']['candidates']=[{
        'candidate_id':manifest['candidate_id'],'arm_id':'delta-repair','experiment_id':m['experiment_id'],
        'run_ids':['run-001'],'manifest_path':rel(CAND/'candidate.json'),'manifest_sha256':sha(CAND/'candidate.json'),
        'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
        'runner_path':rel(Path(__file__).parent/'validate_candidate.py'),
        'runner_sha256':sha(Path(__file__).parent/'validate_candidate.py')}]
    save(ADR/'실험/manifest.json',m)
    save(ART/'tested-freeze.json',{'candidate':rel(CAND),'revision':revision['revision_id'],
        'revision_sha256':revision['revision_sha256'],'files':len(tested['files']),
        'test_summary':rel(ART/(SUMMARY+'-summary.json')),'sha256':sha(ART/(SUMMARY+'-summary.json')),
        'exact_tested_files':True,'external_model_calls':0})
    print('Frozen',len(tested['files']),'files;',tested['passed'],'contracts passed')
    sys.exit(0)

assert sys.argv[1]=='record'
frozen=CAND/'revisions/rev-001/snapshot'
repeat=read(ART/'frozen-api-summary.json')
assert repeat['status']==0 and not repeat['failed'] and not repeat['production_import_leaks'] and not repeat['candidate_changed_during_tests']
assert tested['files']==repeat['files']==files(frozen)
preserved=read(ART/'preservation.json')
assert all(sha(ROOT/n)==h for n,h in preserved['files'].items())
source=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1054/step-state-r1/revisions/rev-001/snapshot'
assert all(sha(source/n)==h for n,h in preserved['inherited_files'].items())
changed=[n for n,h in tested['files'].items() if preserved['inherited_files'].get(n)!=h]
wire=read(ART/(SUMMARY+'-repair-wire-sizes.json'))
for row in wire:row['byte_reduction_vs_initial_full_pct']=round(100*(1-row['partial_repair_request_bytes']/row['initial_full_request_bytes']),2)
result={'status':'complete','scope':'synthetic contracts; no live quality evaluation','contract_passed':tested['passed'],
    'contract_failed':0,'frozen_api_passed':repeat['passed'],'files':len(tested['files']),
    'exact_frozen_repeat':True,'runtime_import_leaks':0,'model_calls':0,'real_source_database_opened':False,
    'main_unchanged':True,'running_1054_frozen_code_and_design_preserved':True,
    'core_claims_and_originals_revalidated':True,'repair_limit':1,'changed_files':changed,
    'wire_bytes_synthetic':wire,'test_summary':rel(ART/(SUMMARY+'-summary.json')),
    'frozen_summary':rel(ART/'frozen-api-summary.json'),
    'limitations':['No measured Qwen repair success rate, provider tokens or latency',
        'Only fully parsed judgment-link consistency errors use the patch; other errors retain existing full repair/failure paths',
        'Incomplete link review cannot close earlier needs/conflicts or become a fully reviewed answer',
        'No live1054 hot replacement or MAIN/GENOS promotion'],
    'development_failures_retained':['Initial missing-need display chose generic reason instead of need text',
        'v5 fixture used old expanded condition wire',
        'Partial source header initially lacked evidence_refs; native acquired-span guard rejected it before model delivery',
        'Private failure diagnostics in a display receipt were stripped on public serialization; moved to existing failure journal, retaining diagnostic hash and affected IDs in receipt']}
save(ART/'result.json',result)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'),executed_arm_ids=['delta-repair'])
m['results']={'status':'complete','by_arm':{
    'baseline':{'status':'complete','correct':None,'total':0,'accuracy':None,'reason':'Immutable implementation reference only; not a paired quality arm'},
    'delta-repair':{'status':'complete','correct':None,'total':0,'accuracy':None,'contract_passed':tested['passed'],'contract_failed':0}},
    'comparisons':[],'judge_disagreements':None,'usage':{'physical_calls':0,'input_tokens':0,'output_tokens':0},
    'latency':{'model_latency':None},'error_taxonomy':result['development_failures_retained']}
save(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
body=f'''
# ADR-1055: 판단 연결 누락의 부분 보완

## 1. 결정 요약
사용자 요청에 따라 전체 평가 재작성 대신 오류가 있는 판단 행만 기존 수정1회 안에서 보완한다. 격리 후보와 합성 검증이며 MAIN·GENOS·진행 중1054에는 반영하지 않았다. Proposed, in_sample=true, decision_eligible=false다.

## 2. 문제와 변경 전 구조
1054 최초 관찰에서는 USE 판단의 빈 claim_refs 또는 주장과 원문의 연결 불일치가 전체 평가 재작성과422로 이어졌다. 실제 주장 검증보다 보조 검토 검사가 먼저였고 modern 분기에 제한 답변 복구가 없었다. 관찰한 첫 사례를 전체 미완료 원인으로 일반화하지 않는다.

## 3. 가설과 사전 판정 기준
구현 전 [기준](artifacts/implementation-plan.json)을 동결했다. 오류 행만 수정하고 원문·주장·권한·상태·최종 발행 검사를 유지한다. 스키마나 근거 검증 면제, 추가 재시도, 미확인 삭제는 실패다.

## 4. 실험 설계
완료1052/overview를 계보 기준으로 삼고 진행 중1054는 동결 구현 의존 관계다. 작은 합성 계약/API만 순차 검사한다. 실제 법령 말뭉치·제품 모델·judge 호출은0회다. 111셀의 대체 실험이 아니다.

## 5. 데이터·모델·재현성
{len(tested['files'])}파일 rev-001과 엔진 pin으로 결속한다. 후보의 외부 정책 파일은1054 바이트를 상속한 미사용 설정이다. 이 후보에서 실제 외부 호출을 하려면 새 실행 ADR의 정책·grant 결속과 조건 동결이 필요하다. 원문·기준답변·승인31묶음은 변경하지 않았다.

## 6. 결과
최종 계약/API {tested['passed']}개 통과, 동결 경로 API {repeat['passed']}개 재검사 통과. 런타임 import 누출0, 검사 중 코드 변경0. [결과](artifacts/result.json), [검사](artifacts/{SUMMARY}-summary.json), [동결](artifacts/tested-freeze.json).

## 7. 사례별 오류 분석
빈 연결·잘못된 주장 연결·원문 공유 불일치는 ID/필드 경로로 분류한다. 독립 오류를 한 번에 모아 해당 판단과 연결 가능한 주장·그 원문만 보낸다. 서버가 합친 뒤 전체 계약을 재검증한다. 보완 실패는 REJECTED로 보존하며 검증된 주장만 제한 답변에 쓰고 검토 미완료를 표시한다. 다른 스키마 오류·권한·해시·상태·근거 오류는 통과시키지 않는다. 개발 중 발견한 누락된 원문 헤더와 공개 표시 진단 불일치도 실패 기록을 보존하고 수정했다.

## 8. 비용·지연·회수 규모
보완 출력은 대상 판단 행뿐이다. 합성 API에서 실제 gateway 요청 JSON 크기는 [기록](artifacts/{SUMMARY}-repair-wire-sizes.json)에 있다. 최초 전체 평가 요청과의 바이트 비교이며 제공자 토큰·지연·정확도 효과가 아니다. 기존 전체 재작성에는 거절된 전체 평가도 추가되므로 이 비교가 기존 재시도 비용의 정확한 측정은 아니다. 회수 정책은 변경하지 않았다.

## 9. 해석
짧은 부분 보완을 실제 API·저장·재사용까지 연결했다. 모델이 빠진 연결을 실제로 얼마나 잘 고치는지는 실모델 검증이 남아 있다. 연결할 주장이 없으면 모델의 명시적 NOT_USED/UNRESOLVED가 필요하며 서버가 법적 중요도를 추정하지 않는다.

## 10. 한계와 일반화 가능 범위
필수 필드 자체가 없거나 JSON이 깨진 경우 등 모든 오류를 부분 보완하는 공통 엔진은 아니다. 현재 대상은 유효하게 수신한 평가의 판단–주장 연결 오류다. 다른 오류는 기존 전체 수정/중단 경로를 유지한다. 검증된 인용은 법률 의미 정답 인증이 아니다.

## 11. 운영 결정·롤백 조건
진행 중1054와 MAIN103의 포인터·코드·정책을 보존했다. 미승격 후보이므로 운영 롤백은 필요 없다. 후속 실험은 이 revision을 명시 결속하며 실패한 이전 결과를 덮어쓰지 않는다. 전역 계보 검사에 기존 타 ADR 오류가 있으면 별도 로그에 남기며 전역 통과로 보고하지 않는다.

## 12. 재현 명령
`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1055/validate_candidate.py {rel(frozen)} repeat test_judgment_link_repair_adr1055.py test_read_judgment.py test_read_judgment_api.py`

`.venv/bin/python -B 06_TOOLS/run_tool.py adr_structure.py validate --path {rel(ADR)} --final`
'''
(ADR/'README.md').write_text('---'+front+'---\n'+body)
(ADR/'실험/README.md').write_text('# 합성 검증 인덱스\n\n질문별 법률 채점은 수행하지 않았다. 기존 실제 실패 유형을 모사한 계약/API 검사이며 정답률 비교가 아니다.\n\n[기준](../artifacts/implementation-plan.json) · [결과](../artifacts/result.json) · [실제 API import](../artifacts/'+SUMMARY+'-imports.json)\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';line='\n- [ADR-1055: 판단 연결 누락의 부분 보완](ADR-1055-judgment-link-delta-repair/README.md) — 합성 계약/API 검증;1054·MAIN 보존.\n'
if 'ADR-1055-judgment-link-delta-repair' not in index.read_text():index.write_text(index.read_text()+line)
print(json.dumps({k:result[k] for k in ('contract_passed','frozen_api_passed','files','model_calls','main_unchanged')},ensure_ascii=False))
