from common import *
import re
f=read(DES/'freeze.json');C=ROOT/f['code_root']
contracts=read(ART/'contracts-r2-local/result.json');native=read(ART/'native-r2-local/result.json');working=read(ART/'working-native/result.json')
for r in (contracts,native,working):assert r['failed']==0 and r['code_unchanged'] and r['active_unchanged']
assert (contracts['passed'],native['passed'],working['passed'])==(329,8,1)
assert all(sha(ROOT/n)==sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
integration=read(ART/'working-integration.json');assert integration['changed_files']==38
archives=read(ART/'runtime-archives.json');assert archives['all_restore_hashes_verified']
reconciliation={'initial_contracts':bind(ART/'contracts-r1/result.json'),
 'initial_native':bind(ART/'native-r1-local/result.json'),
 'native_failure':'Two fixture KeyErrors: the older synthetic approved plan contained only a cost condition, so there was no computed missing input. Fixed fixture to choose refs only when offered and added a separately approved synthetic missing-approval condition for a dedicated native test. No product inference or invented missing fact.',
 'environment_stops':[bind(ART/n/'environment-stop.json') for n in ('native-r1','contracts-r2')],
 'environment_reason':'Independent minimal FastAPI TestClient also stalled under sandbox in anyio start_blocking_portal (12s timeout). Stopped only owned runners and preserved their partial runtimes. Local timeout-bounded mock tests outside sandbox completed.',
 'r2_product_followup':'Keep bound execution catalog server-side; omit obsolete application role/link options on new model wire. Retain all current inputs/results, original text and explicit gap options. Absent RULE baseline stays UNKNOWN; no computed gap option for RULE fields. Empty expression plans do not enable the new contract.',
 'preserved_results':[bind(p) for p in sorted(ART.glob('*/result.json'))],
 'archives':bind(ART/'runtime-archives.json'),'overlap':'Earlier rounds and working smoke overlap final tests; not independent model quality samples.'}
put(ART/'verification-reconciliation.json',reconciliation)
result={'status':'TECHNICAL_PASS','candidate_revision':f['candidate_revision'],'candidate_files':528,
 'changed_files':38,'product_files':7,'pins':31,'new_files':1,'contract_passed':329,'new_contracts':46,'legacy_contracts':283,
 'native_passed':8,'working_native_passed':1,'working_check_overlaps_candidate':True,'failed':0,
 'model_calls':0,'oracle_calls':0,'main_changed':False,'selected_main':'MAIN133','quality_certified':False,
 'artifacts':{k:bind(ART/n/'result.json') for k,n in [('contracts','contracts-r2-local'),('native','native-r2-local'),('working_native','working-native')]},
 'integration':bind(ART/'working-integration.json'),'reconciliation':bind(ART/'verification-reconciliation.json'),
 'limits':['Actual Qwen effect not tested; ADR1286 adopted claims1/3 remains the latest live result and low branch is not quality-complete.',
 'Free prose still has numeric-presence false positives for honest historical comparisons; old-threshold misuse remains rejected.',
 'Explicit computed gap refs cover registered missing FACT inputs only. Arbitrary gap repetition and nonexistent refs in free prose are not solved.',
 'Baseline requirement labels remain historical; some stale labels can still appear in limitations.',
 'No final legal effect formula inferred, approved or published. Original N1 has no typed expression and remains UNKNOWN.',
 'New context-v4/application-v4 reader required for newly saved computation receipts. Legacy application-v2/v3 readers remain supported by current code.',
 'No real Oracle/NFS/GENOS or load validation; selected MAIN133 unchanged.']}
put(ART/'verification.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '서버 계산·비교 표시와 명시적 미확인 입력 연결을 구현하고 작업 코드에 반영했다. 제품7+pin31=38파일, 신규1/삭제0이며 동결후보rev002와 작업528파일이 일치한다. 선택 MAIN133은 그대로다. 실제 Qwen 재시험·법률 품질 인증은 하지 않았다.',
 'ADR1286 실제 Qwen8호출/주장채택1of3. 저액은 gap1개에 1~24참조와 미완성25를 반복했고, 고액은 올바른 현재172.5만원 설명 속 변경 전138만원 비교 때문에 거절됐다. 규칙 변경은 참조만245만원이고 본문은 옛100만원 한도를 재사용해 정당하게 거절됐다. 기존에는 서버 계산값·비교를 다시 주장/적용 연결로 작성하도록 요구했다.',
 '[사전 기준](artifacts/design/criteria.json). 서버가 승인된 식을 다시 계산해 저장 결과와 대조하고, 현재 입력·변경 전후·미확인을 직접 표시한다. 가정 수치 TRUE를 법률 허용으로 확정하지 않는다. 원문·자유문 전체 보존, 제시된 미확인 사실 ID만 명시적으로 선택, 기존 근거/권한/조건/예산/재조회 검증을 유지한다.',
 'scenario-context-v4에 승인된 evaluation_plan과 필드 메타데이터를 결속한다. scenario-computation-v1은 원래 계산 binding으로 현재 결과 전부를 재검증하고 전후 계산표·미확인 사실·미등록 효과를 별도 저장한다. 새 application-v4 모델 출력에는 application_links/값 참조/비교문 재작성을 요구하지 않는다. 계산 계획 사본은 서버에 두고 모델에는 현재 입력·계산 결과와 computed_gap_options를 전달한다. 모델은 등록된 computed_gap_ref와 쟁점 ID를 직접 선택하며, 서버는 그 배열 위치에만 완전한 gap을 만든다. 임의 gap 연결 추정이나 문장 절단은 없다.',
 '보존1286의 canonical004/005/007과 initial-response를 읽어 새 문맥에 승인 계획을 결속한 오프라인 검사이며 과거 실모델 답변을 고쳐 통과시킨 것이 아니다. 별도 합성 모의 API로 정상/1회 보완/보완 실패/원문전용/저장/동일 요청 재조회/기준 사건 보존을 확인했다. 추가 승인 식은 합성 시험 데이터에만 만들었으며 운영 온톨로지는 변경하지 않았다.',
 '최종329계약 통과(새46+기존283), 모의 native API8통과. 작업 반영 후 새 미확인 입력 ID의 저장·재조회 API1개 재확인(앞8개와 중복). 주장0/검토미완료 답변에도 계산표가 보이고 상태는 미완료로 남는다. 원문·주장·600자 사유를 보존하고, 알 수 없는/다른 가정/중복 미확인 ID·다른 쟁점·저장 계산표 변조를 거절한다. 같은 요청 재조회에는 추가 모델 호출이 없다.',
 '최초 계약44통과, 최초 모의 API5통과/2실패를 보존했다. 실패2건은 기존 합성 계획에 승인 조건식이 없는데 시험이 미확인 입력 ID를 있다고 가정한 KeyError다. 실제로 등록된 미확인 입력만 제시하는 제품 규칙을 유지하고 시험을 수정했다. 별도 승인 미확인 합성 계획을 추가한 최종8개 API는 통과했다. 제한 환경의 TestClient 대기2건도 중단 기록/전체 runtime으로 보존했고, 독립 최소 FastAPI에서도 같은 대기를 확인한 후 로컬 모의 검사로 완료했다.',
 f'외부 모델0·Oracle0·외부 비용0. 계약{contracts["seconds"]:.3f}초/API{native["seconds"]:.3f}초/작업 API{working["seconds"]:.3f}초. 새 검색·회수율·토큰/속도 개선율 비교가 아니다. 완료·중단 시험 runtime6개를 전체 파일 해시 대조 후 무손실 압축했다: 원래{archives["original_bytes"]:,}bytes→압축{archives["archive_bytes"]:,}bytes. 과거 실패 원문은 보존되고 복원 방법은 각 runtime-archive.json에 있다.',
 '온톨로지는 등록된 금액·승인 조건의 계산과 어떤 입력이 없는지에는 직접 쓸 수 있다. 예: 저액735000원은 금액 조건 TRUE, 고액1725000원은 FALSE, 한도2450000원 변경은 TRUE이나 승인 입력은 계속 UNKNOWN이다. 관계 그래프에 연결이 있다는 이유만으로 최종 허용의 충분조건을 만들어 실행하지 않는다. N1 최종 효과식은 미등록으로 남긴다.',
 '자연어 전체의 의미 검증은 미해결이다. 정상 비교문이 현재 설명에 들어오면 기존 숫자 검사가 과차단할 수 있고, 오래된 기준 사건 요구문이 확인 범위에 나타나는 문제도 남는다. 서버가 비교표를 제공하므로 모델이 같은 비교문을 다시 작성할 필요는 줄였지만, 실제 Qwen의 반복 감소·3분기 성공은 아직 확인하지 않았다. 자유문 gap의 모든 잘못된 참조도 해결한 것이 아니다. 미확인 ID 선택 경로는 등록된 FACT 입력만 지원한다. Oracle/NFS/GENOS·부하·법률 품질 미검증이다.',
 '사용자 “더 할꺼 있나? 더 진행해봐” 지시에 따라 검증한38파일만 작업 코드에 통합했다. 전체 upstream527을 쓰기 전에 대조하고 변경 전 파일을 artifacts/working-before에 보관했다. 선택 MAIN133·Gold·원문 세대·운영 DB/DDL·Git push·메일·GENOS 배포 변경0. 새 v4 기록이 생기면 이를 읽는 코드와 함께 유지해야 한다. 기존 application-v2/v3 저장 답변은 계속 지원한다.',
 'prepare→격리 후보 수정→freeze→check.py --name <새경로>→integrate→check_working.py→finalize→adr_structure hash/status/validate/graph. 모의 API 검사는 현재 환경에서 TestClient가 동작하는 로컬 실행이 필요하다. 정확한 검사 파일/SHA/후보는 verification.json과 각 result.json, runtime은 tar -xzf runtime.tar.gz로 해당 run 폴더의 빈 runtime 경로에 복원한다. 실제 모델 재시험은 별도 ADR에서 호출 전 기준/예산을 동결한다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1289 가정 계산·비교·미확인 입력의 서버 직접 표시\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
sections=[('실행 메타','run-001/verified. MAIN133 기반 후보rev002/528파일과 동일 작업 코드. 모의 모델·격리 SQLite.'),('사용자 질문 원문','더 할꺼 있나? 더 진행해봐'),('기준답변 — 채점 전용, 제품 입력 비공개','법률 기준답변·평가 모델0. 동결 기술 기준은 design/criteria.json. 새46+기존283계약/API8 통과; 작업API1은 중복.'),('제품 입력을 구성한 원값','test_server_computation.py/test_native_computation.py와 보존1286 canonical004/005/007·initial-response. 원문/주장/긴 사유 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 변경/회수 효과 비교 없음. stage_ledger not_applicable. 기본 API에서 기존 근거·원문·권한 경로를 유지.'),('제품 모델 호출 — run·arm별 실제 원문','외부 실모델0. 생성은 명시한 모의 transport만 사용했다. 새 실행을1286의 실제 성공으로 해석하지 않는다.'),('중간 LLM 호출 — router/compiler/verifier/repair','외부0. 기존 최종 ASSESS 최초+보완1회와 실패시 원문전용 반환을 검사. 미확인 연결은 모델이 고른 ID의 결정적 변환뿐.'),('채점 호출과 반복 판정','외부 채점0. 최초 API2실패와 환경 중단2건은 verification-reconciliation.json과 무손실 runtime archive에 보존.'),('사례 최종 판정','TECHNICAL_PASS/작업38파일 반영/선택MAIN133 유지/quality_certified=false. 실제 Qwen 최종3분기 성공·법률 효과식 승인·현장 검증은 별도.')]
for p in (ADR/'실험').glob('질문-*.md'):p.write_text('# 기술 검증 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[결정·한계](../README.md) · [검증](../artifacts/verification.json) · [실행계보](manifest.json)\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((ART/'verification.json').relative_to(ROOT)),sha256=sha(ART/'verification.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_main133':True,'historical_adr1286':True},'verified':result},judge_disagreements=0,usage={'model_calls':0,'oracle_calls':0},latency={'contracts_seconds':contracts['seconds'],'native_seconds':native['seconds']},error_taxonomy=[{'type':'MOCK_MISSING_INPUT_PLAN_MISMATCH_FIXED','count':2},{'type':'SANDBOX_TESTCLIENT_STALL','count':2}]);put(ADR/'실험/manifest.json',m)
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-scenario-server-computation';report.mkdir(exist_ok=False)
(report/'수정과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
(report/'남은문제와_다음검증.txt').write_text('''현재 완료
- 작업 코드38파일 통합. 서버 계산표와 제시된 미확인 사실 ID 연결, 전체 원문/사유 보존. 계약329/API8, 통합API1 중복 확인.
- 선택 MAIN133은 그대로이며 새 실제 모델 호출0.

남은 문제와 다음 순서
1. 새 ADR에서 같은 저액/고액/규칙 세 분기의 Qwen 입력·출력·최종 채택을 검증한다. 새 전송의 질문/원문 중복, computed_gap_ref 선택, 원문/권한, 가정별 호출 예산, 전체 사유/저장/재조회 및 현재 옛값 재사용을 기록한다. 이전1286 실패를 성공으로 고쳐 쓰지 않는다.
2. 자연어에 있는 현재 적용과 과거 비교의 구분은 아직 완전하지 않다. 서버가 모든 비교표를 표시하므로 재작성 요구는 없앴지만, 올바른 비교문 과차단 자체가 해결된 것은 아니다. 자유문 의미를 추측해 옮기거나 잘라서 통과시키지 않는다.
3. 기준 사건의 요구문에138만원이 남는 표시 문제는 요구 ID와 원래 문장을 보존하면서 현재 가정과 역사적 요구를 구분하는 후속 설계가 필요하다. 이 수정에 임의 문자열 치환을 넣지 않았다.
4. gap 반복은 등록된 미확인 사실에는 ID 선택으로 피할 수 있다. 미등록 원문/예외/일반사유의 반복과 없는 번호 참조는 별도 검증 대상이다. 새 실모델에서 감소했는지는 아직 미확인이다.
5. 온톨로지 최종 효과 N1은 식이 없어 UNKNOWN이다. 금액 N2와 승인 N3의 값만으로 최종 허용을 확정할 수 없다. 적용 범위·예외·시간/의무의 원문 근거를 검토한 평가식 초안을 만들고 기존 draft→검토→승인→게시를 거쳐야 한다. 자동 승인/게시하지 않았다.
6. 새 기능은 작업 코드 단계다. 실제 모델/Oracle/NFS/GENOS 검증과 MAIN 선택 여부는 각각 별도 상태로 남긴다.
''')
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
p=ART/'manifest.json';am=read(p);am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Bound candidate, preserved failed/mock records, verified integration and lossless runtime archives',contains_raw_prompts_and_outputs=x.name=='runtime.tar.gz') for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/__pycache__/' not in str(x)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'AGENTS.md';content=p.read_text();marker='SCENARIO_SERVER_COMPUTATION_1289_20261103'
assert marker not in content
entry=f'''<!-- {marker} -->
**2026-11-03 — 가정 계산·비교·미확인 입력의 서버 직접 표시 작업 반영:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261103-scenario-server-computation/수정과_검증결과.txt) · [남은 문제](09_ARTIFACTS/AUDITS/20261103-scenario-server-computation/남은문제와_다음검증.txt) · [ADR1289](04_EXPERIMENTS/ADR/ADR-1289-scenario-server-computation/README.md). **제품7+pin31=38파일·신규1/삭제0·후보rev002/작업528일치, 선택 MAIN133 유지**. 승인 계획/현재 조건 대조 후 계산표를 주장0/검토미완료에도 직접 저장·표시, application-v4는 수치/적용연결/비교문 재작성 제거. 미확인 FACT의 명시적 computed_gap_ref+쟁점 선택만 같은 위치에 전개하며 자유문/원문/600자gap 무절단·임의연결추정0. 실행계획 사본은 서버에 보존, 기존v2/v3 reader·옛값거절·권한/근거/예산/재조회 유지. **계약329(새46+기존283)+모의API8 통과, 작업API1 중복확인**. 최초API2 fixture실패/제한환경대기2 원본·runtime6개 무손실 해시복원 보존. **실모델/Oracle0·MAIN/Gold/운영DB/DDL/Git push/메일/현장변경0**. 실제1286 주장채택1/3·저액반복/고액비교 과차단/규칙옛값재사용 실패 유지; 새Qwen효과 미검증. 자유문 비교 과차단·기준요구 옛금액표시·미등록gap 반복·N1효과식은 미해결이며 효과식 자동승인/게시0·법률품질 미인증.
<!-- /{marker} -->

'''
pos=content.index('\n')+1;p.write_text(content[:pos]+'\n'+entry+content[pos:])
print('Technical PASS;329 contracts/8 mock API;working smoke1 overlaps;38 integrated;MAIN133 unchanged')
