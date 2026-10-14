from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0688-followup-structure-observability-recovery';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0688/integrated'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
# Primary categories remain the criteria fixed before development; product
# implementation was exercised only as ordinary local development tests.
regression=['05_TESTS/CONTRACTS/'+name for name in ('test_structure_first_search.py','test_law_grouped_navigation.py','test_unit_fulltext_adaptive_read.py','test_completion_boundary_adr0679.py')]
exclude='not native and not workflow and not v6_default and not bounded_exact and not insufficient_structural and not exact_structure_ask and not unread_requested and not original_body_and_expansion and not cross_unit_scope and not selected_scopes_drive'
put(D/'execution-plan.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),
 'primary':['06_TOOLS/EXPERIMENTS/adr_0688/test_required_contracts.py'],
 'existing':['05_TESTS/CONTRACTS/test_followup_structure_lookup.py'],
 'regression':regression,'regression_expression':exclude,
 'expected_counts':{'new':18,'followup':27,'regression':61},
 'exclusion_reason':'Historical maintained 61-case suite from preceding audit: remaining 18 old native/completion fixture cases have unrelated workspace-receipt or predating-coordinate fixture faults. No new case is excluded.',
 'role':'Functional audit controls production integration; four synthetic model probes are supplemental in-sample, not legal quality certification.',
 'baseline_receipt':str((D/'baseline-snapshot-receipt.json').relative_to(R))})
for q in read(A/'실험/manifest.json')['questions']:
 p=A/'실험'/q['file']
 p.write_text(f'''# 사례 {q['number']:03d} — {q['case_id']}

## 1. 실행 메타
ADR-0688 / run-001 / baseline, integrated. 실행 시각·원상태 exact는 해시 고정 실행 로그와 XML에 기록한다.

## 2. 제품 요청
구조 탐색의 기능 계약 감사. 별도 실제 법률 답변 질의를 평가하지 않는다. 합성 제품 질의4개는 ../artifacts/design/criteria.json의 model_probe.cases에 고정했다.

## 3. 기준답변
해당 없음. 법률 정답·gold·judge 호출이 없다. 실행 전 고정한 기능 기준은 ../artifacts/design/criteria.json이다.

## 4. 제품 입력의 원값
원문·권한·검색 데이터는 합성 fixture의 소스 생성 코드에 고정하며 공유 fixture/code hash는 freeze.json에 기록한다. 색인 변경·회수 품질 평가가 없으므로 retrieval recall 원장은 해당 없다. 실제 탐색 행동 목록과 전달 범위는 probe 각 turn의 offered.json과 result.json에 기록한다.

## 5. 제품 모델 호출
기능 계약은 외부 모델 호출 없음. 보조 합성 질의4개×2 arm만 Qwen3.8 / Parasail FP8 / reasoning none / fallback false로 최대3호출씩 실행한다. 실제 system/user/schema/원응답·구조화 출력·usage·지연의 원본 경로는 artifacts/run-001/probe이며 반복 본문을 보고서에 복사하지 않는다.

## 6. 중간 LLM 호출
[] — router/compiler/judge/repair 별도 호출 없음.

## 7. 채점 호출
[] — 법률 의미 채점과 다수결 없음. 계약 검사는 실제 도구 결과와 상태·권한·원문 범위를 대조한다.

## 8. 최종 판정
측정 전 결과 미기록. 동결 코드로 실행한 XML·result.json에 실제 성공/실패와 원인을 보존한다. 이 문서는 합성 감사의 범위 설명이며 실제 현장 질문을 보관하거나 모델에 반출한 기록이 아니다.
''')
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/COMMANDS/adr_candidate.py','freeze',str(C)],cwd=R,check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
shared=list((R/'05_TESTS').rglob('*.py'))+list((R/'02_BACKEND/lawrag/pipeline').rglob('*.py'))+list((R/'02_BACKEND/lawrag/core').rglob('*.py'))+list(Path(__file__).parent.glob('*.py'))
shared += [R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',D/'criteria.json',D/'execution-plan.json']
files={str(p.relative_to(R)):sha(p) for p in sorted(set(shared))}
f={'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),
 'candidate_manifest':str((C/'candidate.json').relative_to(R)),'candidate_manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'serving_files':{r['target_path']:sha(code/r['target_path']) for r in cm['files']},'shared_files':files,
 'data_unchanged':True,'baseline_snapshot_receipt_sha256':sha(D/'baseline-snapshot-receipt.json')}
put(D/'freeze.json',f)
m=read(A/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,
 candidates=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],
 'manifest_path':f['candidate_manifest'],'manifest_sha256':f['candidate_manifest_sha256'],'revision_id':f['revision_id'],
 'revision_sha256':f['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0688/run_contracts.py',
 'runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0688/run_contracts.py')}])
for q in m['questions']:q['sha256']=sha(A/'실험'/q['file'])
put(A/'실험/manifest.json',m)
print('Frozen',len(f['serving_files']),'serving files and',len(files),'shared fixture/tool files; model calls not started.')
