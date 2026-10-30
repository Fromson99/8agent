from common import *
import gzip
f=read(DES/'freeze.json');r=read(RUN/'result.json');p=ART/'live/cm-007';a=read(p/'audit.json');st=read(p/'investigation-state.json');goals=[g for v in st.get('investigation_supervisor',{}).values() for g in v.get('source_goals',[])];assert len(goals)==3 and all(g['status']=='ACQUIRED' for g in goals)
assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items());assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
put(ART/'live-source-completion.json',{'goals':goals,'original_span_checks':a['span_checks'],'outbound_span_checks':a['delivered_span_checks'],'source_mismatches':a['source_mismatches'],'acl_violations':a['acl_violations'],'phase_sequence':['request-entry physical1','server5actions:3READ and2LOOKUP; no source-selection model call','physical2 chooses FOLLOW_CONNECTION','physical3 sent; no completed response; local controller interrupted'], 'quality_certified':False,'complete_answer':False,'new_model_calls_during_audit':0})
report=ROOT/'09_ARTIFACTS/AUDITS/20261028-source-scope-completion/수정과_재시험결과.txt';report.parent.mkdir(parents=True,exist_ok=True)
text='''필요 조문을 목표로 올리지 않고 충분하다고 끝내는 문제 — 수정과 재시험
2026-10-28 / ADR1179 / MAIN112 유지

1. 바뀐 동작
기존에는 모델이 선언한 원문 목표만 강제했다. 이제 서버가 사용자 요구와 직접 일치하는 저장 표제를 기존 제목 색인에서 찾고, 문서·조문 좌표를 데이터에서 가져와 조사 목표로 등록한다. 특정 문서명·13조·문서 ID를 제품에 넣지 않았다.
등록은 모델의 다음 선택과 조기 최종판단 이전에 수행한다. 실제 권한, 사용자의 문서/구조 범위와 제외를 지키며, 기존 조회·읽기 도구로 집행한다. 미리보기나 다른 문서의 정의 조항, 충분하다는 이유 한 문장으로 이 목표를 제외할 수 없다. 목표 원문을 읽은 뒤 법적 적용 여부를 판단하고 답변에서 제외하는 것은 허용한다.
실제 전체 원문·좌표·span 검증을 통과해야 ACQUIRED다. 미확보·중복좌표·등록한도 초과는 제한 답변에 남긴다. 원문 확보 자체가 법률 판단의 정답을 뜻하지 않는다.

2. 일반화 범위
본문의 조 단위 저장 표제 전체가 사용자 요구에 직접 일치하는 경우를 대상으로 한다(정규화4자 이상). 기존 제목 색인을 재사용하며 별도 전체 DB 다운로드나 모델 호출을 추가하지 않는다. 다른 번호·문서명·ID, 권한/사용자범위, 부칙, 모호한 좌표, 원문 부재, 재개, 목표 초과, 잘못된 제외를 검사했다.
모든 의미상의 필요 조문·동의어·위임/예외를 자동 판정하는 해결책은 아니다. 제목이 직접 맞지 않거나 구조 좌표가 해석되지 않는 단서는 기존 탐색·원문 해석 영역에 남는다. Oracle 원격 조회는 기존 색인/점조회 인터페이스를 사용하지만 실제 GENOS/Oracle 현장 성능 시험을 한 것은 아니다.

3. 기술 검증
최종 제품 rev002465파일. 부모1178 대비 제품/설정5파일과 pin31파일 변경. 기술293조건 통과(부모263+신규30). 최종 재검사 기록은 같은 제품의290통과를 승계하고 결과 저장 경로2건·실제 문서명 fixture1건을 새 기록으로 다시 검사했다.
211개 회귀를 부모/후보 각각 실행:189통과, 기존9실패, 준비오류13으로 항목별 동일. 새 회귀0, import 누출0.
rev001 OFF설정 충돌/제한환경 대기, rev002 검사 보조함수1실패, 후속 기록파일 이름 충돌2건을 지우지 않았다. 제품 코드가 그대로인 상태에서 검사만 정정했다. 다른 작업이 작업폴더 completion_execution.py를 변경하여 rev003고정은 중단했으며, 부분 복사와 중단 사유를 보존했다. 실제 시험은 이전에 완전히 고정한 rev002와 별도 실행 영수증으로 수행했다.

4. 실제 7번
Qwen3.8 / Chutes FP8, 질문1회, 물리 호출3회=예산차감3. 2개 응답 수신, 3번째 결과 불명. 최초 모델 호출 뒤 서버가 코스닥시장 상장규정13조, 유가증권시장 상장규정13조, 유가증권시장 상장규정 시행세칙9조를 목표로 등록했다. 추가 선택 모델0회로 기존 도구의 READ3/LOOKUP2를 수행해 세 원문을 모두 확보했다.
이전 7번에서 빠진 두 시장13조는 이번 실제 실행에서 확보됐다. 원문72구간/호출입력122구간 대조, 불일치0·권한위반0. 출력상한 필드0. 모델은 이후 연결 조문 조사를 선택했다.
3번째 호출은179.751초의 단계 기한이 지나도 완료 응답을 반환하지 않았다. 5분 이상 대기 후 실험 제어 측에서 중단했고 로컬 프로세스 종료코드130과 종료를 확인했다. 전체 실행 기록은475.648초이며, 제공자가 반환한 확정 timeout/429로 기록하지 않는다. 원격 계산 종료·미응답 호출의 비용은 미확인이다. 429 확인이 없으므로 Near AI 전환이나 재요청을 하지 않았다.
최종 답변·ASSESS 완료가 없으므로 7번 전체 시험은 미통과다. 두13조의 원문 확보 성공과 답변 완성 실패를 구분한다. 기한이 지나도 통신 대기가 종료되지 않은 현상은 별도 후속 문제이며 이번 변경이 이를 해결했다고 주장하지 않는다.

5. 9번과 반영 상태
7번 미통과이므로9번 미실행. 1번 재호출0, 같은7번 자동 재실행0. 최종 답변 평가·더좋은 모델 비교0. GENOS 대리 모델을 개선 모델로 사용하지 않았다.
작업 제품 통합·MAIN 승격·선택 서비스 변경·GENOS 배포 없음. MAIN112유지. 이번 수정은 격리 후보에 구현·검증되어 있으며 서비스 반영 완료가 아니다. 포인터를 바꾸지 않아 서비스 롤백은 필요 없다.

6. 주요 근거
04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/artifacts/run-001/result.json
04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/artifacts/live-source-completion.json
04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/artifacts/live/cm-007/gate.json
04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/artifacts/live/cm-007/operator-stop.json
04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/artifacts/design/execution-binding-002.json
원시 모델 요청/응답과 상태는 JSON gzip, 작은 요약은 별도 JSON으로 보존했다. 미완료3번째 호출에는 응답 파일을 만들지 않았다.
'''
assert not report.exists();report.write_text(text)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'필요한 원문이 모델의 목표 선언에서 빠져도 직접 일치하는 저장 표제는 서버가 발견·등록·집행하도록 구현했다. 기술293통과·새회귀0. 실제007 두시장13조 확보 성공,3번째 모델 응답 미완료로 최종답변 없음.009미실행·MAIN112유지.',
'기존에는 명시 목표만 선집행했다. 모델이 source_targets=[]와 충분하다는 의견으로 끝내면 두시장 원문을 읽지 않고도 최종판단에 도달했다. 기존 감독의 remaining_scope는 설명일 뿐 원문 완료 증명이 아니었다.',
'[원래 사전 기준](artifacts/design/criteria.json), [실제 호출 전 내용 기준](artifacts/evaluation-only/completion-criteria.json). 표제 직접 일치·현재 권한/사용자범위·실제 원문 receipt를 요구한다. 같은 실패 재시도 없이007한번→통과시009한번이다.',
'부모1178/contained, 새scoped arm. scope_completion.py에서 초기/조기 handoff 전, source_goal_control에서 선택·집행 전 발견한다. law_navigation/law_candidates/프로필에 연결했다. 번호·문서명은 저장 데이터에서 취하며 정답 사례는 평가에만 둔다. 최초16목표 한도 밖은 미해결로 보존한다.',
'같은 MAIN112데이터와 권한65문서, Qwen3.8/ChutesFP8, 확정429시에만NearAI1회,40물리/1024도구/1800초·출력상한없음. 최종 제품rev002465파일. 실행 영수증은 [별도 동결](artifacts/design/execution-binding-002.json). 원문/출력의 큰자료는gzip과hash로 보존한다.',
'[결과](artifacts/run-001/result.json), [실제 원문 확보](artifacts/live-source-completion.json).293기술조건·211회귀의 새실패0.007:서버5도구로3원문확보,물리3/차감3,원문72/입력122불일치0·권한위반0. 최종 답변 없으므로 전체미통과,009미실행.',
'rev001 OFF설정 호환 문제와 제한환경 대기 보존. rev002292통과/1fixture 실패 정정. 같은제품 재검사에서291통과/2결과경로충돌을 보존하고3관련검사를 별도 실행했다. 작업폴더 동시 변경으로 추가고정은중단;실제제품은기존rev002다. 실제007의3번째호출은단계기한초과로제어측중단,원격결과UNKNOWN이다.',
'실제0073호출,완료응답2/결과불명1.475.648초는로컬중단기록까지이며 속도개선율이 아니다.완료2응답의usage만집계했고 총비용미확인이다. [단계원장](artifacts/run-001/retrieval-ledger.json)의 인용0은최종답변없음을뜻하며필수원문미확보가아니다.',
'모델이 선언하지 않은 두13조가 실제 확보됐으므로 이번 서버 발견/선집행의 실행 효과는 확인했다. 원문 해석·최종답변 품질은 미확인이다. 모델기한과진행중통신대기의종료가일치하지않은현상을 별도 남긴다.',
'표제전체가사용자요구에직접맞는본문조원문을일반적으로찾는다. 모든의미적필수·동의어·위임·예외의자동판정이아니다. 알려진질문probe,decision_eligible=false,quality_certified=false.Oracle/GENOS현장·강한모델비교미수행.',
'Proposed/main_wiring=unchanged.작업제품통합·MAIN승격미수행.원문/권한/누락/예산위반시채택금지.7번최종답변미통과로9번금지.포인터미변경으로서비스롤백불필요.',
'검사·회귀·실제실행 코드는06_TOOLS/EXPERIMENTS/adr_1179에 있다. 완료아티팩트를 덮어쓰거나실제질문을 자동재실행하지않는다. 새시험은새ADR과독립실행기록으로분기한다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract --final`'
]
pth=ADR/'README.md';front=pth.read_text().split('---',2)[1];pth.write_text('---'+front+'---\n\n# 미선언 원문 목표 발견과 완료 계약\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 인덱스\n\n[CM007](질문-001-cm-007.md):필수원문확보,모델3번째응답미완료/중단,최종답변미통과.\n\n[CM009](질문-002-cm-009.md):007미통과로미실행.\n\n[실행/계보](manifest.json), [결과](../artifacts/run-001/result.json), [단계별원장](../artifacts/run-001/retrieval-ledger.json).법률정답률미인증.\n')
put(ART/'report.json',{'path':str(report.relative_to(ROOT)),'sha256':sha(report)})
# Preserve other tasks' contemporaneous guide changes.
pth=ROOT/'AGENTS.md';s=pth.read_text();marker='<!-- SOURCE_SCOPE_1179 -->';assert marker not in s
note='''<!-- SOURCE_SCOPE_1179 -->
**2026-10-28 — 미선언 원문 목표 발견·007 재시험:** [결과 TXT](09_ARTIFACTS/AUDITS/20261028-source-scope-completion/수정과_재시험결과.txt) · [ADR1179](04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract/README.md). 격리1178에서 질문과 직접 맞는 저장 표제를 서버가 목표로 등록·선집행하고, 다른 원문/설명만으로 제외하지 못하게 수정했다. 특정13조·문서명·ID 하드코딩없음. rev002465파일·293기술조건·211회귀189통과/기존9실패/준비오류13동일·새회귀0. 실제007은 최초모델뒤선택모델추가0/도구5회로 두시장13조와유가시행세칙9조를모두확보했다. 원문72/입력122불일치·권한위반0,물리3=차감3. **3번째모델호출이단계기한을넘겨도응답미완료하여제어측중단(전체기록475.648초),2응답/1결과불명·최종답변미통과·009미실행**. 확정429없어공급자전환/자동재요청0. 원격취소·미응답비용미확인. OFF설정/검사보조/기록경로실패·동시작업변경에따른추가freeze중단을보존했다. 직접표제일치범위의발견효과이며전체의미추론·최종답변·기한종료해결로확대하지않는다. 작업제품통합·MAIN승격·GENOS·강한모델비교미수행, **MAIN112유지**.
<!-- /SOURCE_SCOPE_1179 -->

'''
s=s.replace('# 8-AGENT 작업 가이드\n', '# 8-AGENT 작업 가이드\n\n'+note,1);pth.write_text(s)
for name in ['adr1179-check-rev002','adr1179-check-final','adr1179-repaired-check','adr1179-regression-parent','adr1179-regression-candidate','adr1179-live-cm007']:
 src=Path('/tmp')/(name+'.log')
 with gzip.open(ART/(name+'.log.gz'),'xb') as out:out.write(src.read_bytes())
print(report)
