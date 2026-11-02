from common import *
import re
f=read(DES/'freeze.json');C=ROOT/f['code_root']
contracts=read(ART/'final-contracts-r5/result.json');native=read(ART/'final-native-r5/result.json');working=read(ART/'working-native/result.json')
for r in (contracts,native,working):assert r['failed']==0 and r['code_unchanged'] and r['active_unchanged']
assert contracts['passed']==283 and native['passed']==working['passed']==7
assert all(sha(ROOT/n)==sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
reconciliation={
 'initial_implementation':'Candidate-only edit script stopped on an already replaced repair guard; corrected scoped guard before first freeze; product working files were untouched.',
 'scope_r2':bind(ART/'scope-contracts-r2/result.json'),
 'scope_failure':'One check showed a const-empty field remained on the generation wire under an untyped anyOf. Removed the field at the shared-review projection and restored it only for an exact validated empty-claim branch; recorded immutable paths.',
 'native_r2':bind(ART/'native-r2/result.json'),'native_r3':bind(ART/'native-r3/result.json'),
 'native_failure':'r2 six failures included conditional parent link fields and host-fixed fields; r3 four failures were the fixture treating OPEN needs/scope groups as schema-fixed-empty rows although their current schema still uses shared links. Restrict fixture omission to actual fixed-empty requirement/judgment branches. Canonical validators unchanged.',
 'native_r4':bind(ART/'native-r4/result.json'),
 'integration_admission':'An early integration command found final-native-r5 result not yet present and stopped before writing; after checks completed the same integration preflight passed and wrote only36 owned files.',
 'preserved_results':[bind(p) for p in sorted(ART.glob('*/result.json'))],
 'notes':'Rounds overlap; not independent quality samples. No external model rerun or historical artifact alteration.'}
put(ART/'verification-reconciliation.json',reconciliation)
result={'status':'TECHNICAL_PASS','candidate_revision':f['candidate_revision'],'candidate_files':527,
 'changed_files':36,'product_files':5,'pins':31,'contract_passed':283,'native_passed':7,'working_native_passed':7,
 'failed':0,'working_check_overlaps_candidate':True,'model_calls':0,'oracle_calls':0,'main_changed':False,'quality_certified':False,
 'artifacts':{k:bind(ART/n/'result.json') for k,n in [('contracts','final-contracts-r5'),('native','final-native-r5'),('working_native','working-native')]},
 'integration':bind(ART/'working-integration.json'),'reconciliation':bind(ART/'verification-reconciliation.json'),
 'limits':['New scenario application v3 and shared review v2; old v2/v1 receipts retain their old validators.',
 'Current numeric-role checks are not a proof of arbitrary natural-language or legal meaning; comparison prose remains model-owned.',
 'Recorded1284 proposal checks exercise a component only; actual Qwen final-answer success remains unverified.',
 'No new Oracle/GENOS/NFS, concurrent load or model token/latency/cost comparison.']}
put(ART/'verification.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '수정·작업 코드 반영 완료. 제품5+pin31=36파일을 변경했고 최종후보rev005와 작업527파일이 일치한다. MAIN132는 그대로다. 실제Qwen 재시험은 하지 않았으며 모델 품질 성공을 주장하지 않는다.',
 'ADR1284 실제11호출/가정0of3에서 일반 예외·승인 설명까지 가정 연결을 요구하고, 공유참조 뒤의 UNRESOLVED 빈 주장 제약이 가려졌다. 과거 비교참조를 붙이면 이전100만 원을 현재 한도로 쓰는 본문도 수치검사를 통과할 수 있었다. 질문+사실 합성문장에 같은 질문1회도 남았다.',
 '[호출 전 기준](artifacts/design/criteria.json). 가정 조건 연결의 범위 축소, 현재값 검사 유지, 상태별 빈 주장 서버 소유, 전체 원문·gap·비교문 보존, 기존 reader·원문/권한/hash/예산·발행·재조회 연결 검증. 의미 추정 보정·새 재시도 금지.',
 '가정 적용v3은 명시적으로 연결한 주장과 변경된 각 조건의 실제 적용을 검사한다. 일반 설명의 연결을 강요하지 않지만 연결되지 않은 현재 설명도 이전 금액 재사용 검사에서 빠지지 않는다. 선택 comparison_text에 비교 문장 전체를 보존하고 현재 적용 설명과 구분해 표시한다. 새 공유 검토v2는 스키마가 빈 주장 목록으로 고정한 요구/판단 행에서 claim_refs와 link_ref를 모델에게 요구하지 않으며, 검증된 해당 행 경로에만 []를 복원한다. 기존 의미 검증을 계속 수행한다.',
 '완료1284 arm의 제품527파일에서 새 후보를 격리·동결했다. 합성 규정/모의 transport의 native API·SQLite 저장·게시·재조회 검사와 실제1284 제안5개의 읽기전용 컴포넌트 검사를 사용했다. 실제 답변을 다시 생성하거나 실패 응답을 수정하지 않았다.',
 '최종계약283통과(범위 계약60+관련기존223)·모의 native API7통과. 작업 반영 후 API7재확인(중복). 현재245만 원/2,450,000원 허용, 과거비교 참조를 붙인 현재100만 원 재사용 및 연결을 빼서 숨긴 옛값 거절. 긴 질문의 문자그대로인 현재 사실: 구문/끝예외, 긴 비교문 전체,600자gap 끝부분과 같은 요청 추가모델0 보존.',
 '실제1284의 저액6/7·고액9 제안은 불필요한 SCENARIO_APPLICATION_LINK가 사라짐을 확인했다. 규칙10/11은 현재100만 원 재사용을 구체 수치 오류로 검출한다. 이는 가정검사 컴포넌트 결과이며 해당 응답의 모든 법률 의미나 전체 파이프라인 통과를 뜻하지 않는다. 초기계약1실패/API6실패/API4실패와 코드·fixture 보완 과정은 verification-reconciliation.json과 각 원결과에 보존했다.',
 f'새 외부모델0·Oracle0·외부비용0. 최종계약{contracts["seconds"]:.3f}초/native{native["seconds"]:.3f}초/작업native{working["seconds"]:.3f}초. 여러 라운드를 독립 표본으로 합산하지 않는다. 검색/회수 정책이나 성능 개선율을 측정한 작업이 아니다.',
 '모델의 설명을 잘라내거나 기존 결론을 서버가 수정하지 않는다. 서버가 이미 아는 빈 주장 목록만 상태에 맞춰 복원하며 근거·gap·이유는 유지한다. 질문은 합성 문자열을 잘라서 나누지 않고 원래 task와 facts에서 조립한다. 공유 연결의 개수 제약은 생성 스키마의 안내와 모델이 실제 보는 link_ref/정의 위치의 보완 오류로 전달한다.',
 '새 가정 생성은 application-v3/shared-review-v2, 이전 기록은 v2/v1 계약으로 읽는다. 자유문에 나타난 명시 금액·역할 검사는 모든 법률 의미를 판단하지 못한다. 비교문 자체의 자연어 의미도 자동 인증하지 않는다. 실제Qwen 개선율·최종3분기 통과, Oracle/GENOS/NFS·부하 미검증이다.',
 '사용자 수정 지시에 따라 검증한36파일만 반영했고 다른 기존 작업을 덮지 않았다. artifacts/working-before와 before/after hash를 보존했다. 선택MAIN132·Gold·DB/DDL·Git/메일·현장배포 변경0. 신규 형식이 저장된 뒤에는 신규 형식을 읽을 수 있는 코드와 함께 유지한다.',
 'check.py --name <새경로> <검사파일...> / check_working.py. 정확한 파일과 SHA는 verification.json 및 각 result.json. prepare→candidate수정→freeze→계약/native→integrate→작업native→finalize→hash/status/validate/graph. 완료 결과 덮어쓰기와 실모델 자동 재실행 금지.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1285 가정 연결 범위·비채택 검토·현재/과거 설명 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
sections=[('실행 메타','run-001/verified. 격리527파일 rev005와 동일 작업 코드. artifacts/design/freeze.json 및 verification.json.'),('사용자 질문 원문','수정해봐 — ADR1284에서 확인한 가정 연결·공유 검토·이전 한도 재사용 결함 수정.'),('기준답변 — 채점 전용, 제품 입력 비공개','법률 기준답변·평가모델0. 동결된 기술 기준은 criteria.json; 합성 계약/API 검사.'),('제품 입력을 구성한 원값','test_scope_contracts.py/test_native_shared_review.py, 보존1284 canonical5제안. 전체 원문과 이유·gap 유지.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색효과 변경 비교 없음. stage_ledger not_applicable. 원문/근거 검증은 기존 계약과 native API 경로에서 유지.'),('제품 모델 호출 — run·arm별 실제 원문','새 실제 모델 호출0. native transport는 명시한 모의 응답이다.'),('중간 LLM 호출 — router/compiler/verifier/repair','외부 호출0. API 정상·수정1회·반복실패·원문전용·재조회 경로를 모의응답으로 검사.'),('채점 호출과 반복 판정','외부 채점0. 최종 계약283/API7, 작업API7는 중복범위다. 초반 실패는 원래 결과대로 보존.'),('사례 최종 판정','TECHNICAL_PASS·MAIN132 unchanged·quality_certified=false. 실제Qwen 성공을 뜻하지 않는다.')]
for p in (ADR/'실험').glob('질문-*.md'):
 p.write_text('# 기술 검증 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[결정·한계](../README.md) · [검증](../artifacts/verification.json) · [실행계보](manifest.json)\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((ART/'verification.json').relative_to(ROOT)),sha256=sha(ART/'verification.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_adr1284':True},'verified':result},judge_disagreements=0,usage={'model_calls':0,'oracle_calls':0},latency={'contracts_seconds':contracts['seconds'],'native_seconds':native['seconds']},error_taxonomy=[{'type':'HOST_EMPTY_BRANCH_PROJECTION_REPAIRED','count':1},{'type':'NATIVE_SCHEMA_AND_FIXTURE_REPAIRED','round_failures':[6,4]}]);put(ADR/'실험/manifest.json',m)
report=ROOT/'09_ARTIFACTS/AUDITS/20261102-scenario-review-scope-fix';report.mkdir(exist_ok=False)
(report/'수정과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
p=ART/'manifest.json';am=read(p);am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Frozen design, preserved failures and exact verified working integration',contains_raw_prompts_and_outputs=False) for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Final:283 contracts+7 native; working native7;36 files integrated;MAIN132 unchanged;new real model0')
