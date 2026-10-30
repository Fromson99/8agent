from common import *
r=read(RUN/'result.json');m=read(ADR/'실험/manifest.json')
r.update(overall_success=False,question_completeness_passed=False,additional_server_failure=read(ART/'scope-bug.json'))
put(RUN/'result.json',r);m['runs'][0].update(sha256=sha(RUN/'result.json'),success_criteria_met=False);m['results']['by_arm']['guarded'].update(overall_success=False,question_completeness_passed=False,additional_server_failure=r['additional_server_failure']);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
'PARTIAL/INSUFFICIENT의 빈 핵심 gap을 ASSESS 채택 전에 거절하고, 미해결 판단의 최종 생성·선송신을 막아 기존 주장과 한계로 조립했다. 저장001 원응답7개 재생에서 기존 잘못된 ASSESS를 거절하고 보완으로 진입했다(외부 모델0). 기술156검사 통과. 새001/007/009를 각1회 실행했다. 판단-답변 일치와 저장은 확인했지만007 범위 누락,009 탐색 실패 및 잘못된 coordinate_scope 허용 결함이 남아 전체 성공은 아니다. 격리 후보만 수정, MAIN112 유지.',
'부모1173의 실제001은 PARTIAL인데 gaps=[]를 허용했고, COMPOSE가 불확실성을 받지 못한 채 해석을 추가했다. 원문 필요 여부의 의미 판단과 이미 확정된 목표 집행은 별도다. 완료1173 원본·실패 기록은 그대로 보존했다.',
'[사전 기준](artifacts/design/criteria.json). 실제 재실행 전에 기술 검사·저장 재생, 001 통과 뒤007/009를 순차 실행. 이번 일치 게이트는 정답률이나 전체 답변 충족 인증이 아니며, 명시적 제한 답변은 허용하도록 사전 구분했다. 같은 실패 자동 재호출은 하지 않는다.',
'입력·소비자: ASSESS→기존 DecisionJournal→COMPOSE→API/저장. PARTIAL/INSUFFICIENT에는 같은 쟁점의 material gap 필요. 스키마 검증 뒤 보정 전·후에 확인하고 기존 첫 판단+수정1회만 사용한다. 원문 부족은 기존 reentry, 사실 부족은 사실 질문, 반복 오류는 InvestigationPending. 의미·조문번호·gap을 서버가 만들지 않는다. 완료된 판단이 아니거나 보이는 한계가 있으면 모델 재서술을 호출하기 전에 차단한다. 기존 default_plan과 원문 발췌·미확인 사유를 그대로 조립한다. 정상 완료의 기존 서술 경로는 유지하고 그 입력에도 쟁점 상태를 전달한다. 계약 버전을 assessment basis/cache binding에 포함한다.',
'ADR1173 rev012를 부모로 격리했고 MAIN112 데이터/권한·Qwen3.8·Chutes FP8·확정429에만NearAI1회·40/1024/1800·출력상한없음을 유지했다. 후보 rev004464파일, 부모대비제품/프로필5+pin31=36경로. rev003과rev004 제품464파일 동일, rev004는 공통 회귀 fixture 등록만 바뀌었다. 실제 프로세스는 하나씩 순차 실행했다. 초기 작은 합성 검사와 회귀가9초 겹쳐 회귀를 일시 정지한 이력은 verification-notes에 기록했다.',
'기술156통과(부모130+신규26). 스트리밍 검사까지 통과한rev003 결과는 동일464파일인rev004에 결속했다. 확장171검사: 부모/후보 모두149통과·9실패·13setup오류, 항목별 새회귀0. 최초 공통fixture 누락22오류와rev002 토큰기대 오류3개는 보존했다.\n\n| 사례 | 실제 모델 | 시간 | 결과 | 남은 내용 문제 |\n|---|---:|---:|---|---|\n| CM001 | 6 | 130.172초 | ANSWER/COVERED·주장2·저장완료, COMPOSE 모델0 | 해석 정답 미인증; 일반 범위 주의문 유지 |\n| CM007 | 9 | 332.028초 | 근거 연결 오류1회 보완, 주장2·저장완료, COMPOSE 모델0 | 유가증권시장 제13조 미확보·누락 |\n| CM009 | 6 | 132.327초 | LIMITED_ANSWER/INSUFFICIENT·주장0·저장완료 | 필요한13/31 미확보, 잘못된 scope 허용 결함 |',
'001의 실제 재실행은 ASSESS에서 해석C2를 명시했으며 PARTIAL 빈gap 거절이 자연 발생한 실행은 아니다. 해당 거절은 원응답 재생과 오류 주입으로 증명했다. 007은 선언된 코스닥13⑤ 목표의 LOOKUP→READ→ACQUIRED를 새 선택 호출 없이 수행했다. 최종 근거 결속 오류는 기존 보완1회로 해결했으나 유가증권시장13 제외 판단은 남았다. 009는 정의 원문을 선택하고 유가증권12를 목표로 선언했는데 coordinate_scope=조를 서버가 허용했다. 실제 원문 저장에는 같은 문서12가 body로 존재한다. 잘못된 필터를0건으로 처리한 것은 모델의 입력 오류와 서버 계약 검증 누락이며 단순 자료 부재가 아니다. 제한 답변은 부족을 보존하고 법률 주장을 만들지 않았다. 이 결함은 새 후속 ADR에서 별도 수정하며 이번 결과를 소급 변경하지 않는다.',
f'실제총21호출(6+9+6), 추가 평가모델0·동일질문재실행0. 입력{r["usage"]["input_tokens"]}·출력{r["usage"]["output_tokens"]}토큰, 제공자 비용${r["usage"]["cost_usd"]:.9f}. 확보262구간·모델전달459구간 불일치0·권한위반0. 각 요청의 물리호출과 예산 차감 일치, 실제429없음. 속도 개선율로 일반화하지 않는다. [회수 원장](artifacts/run-001/retrieval-ledger.json)은 원문좌표 회수율이며 정답률이 아니다.',
'잘못된 판단을 그대로 최종 문장으로 강화하는 경로는 제한했다. 필요한 원문을 고르지 못하는 문제, 불필요하다고 제외하는 의미 판단, 부정확한 구조 범위 값의 허용은 별개다. 읽은 조문이 있다는 이유나HTTP200을 정답으로 계산하지 않는다.',
'알려진3문항 각1회 인샘플 probe. 법률정답률·전체MAIN·GENOS현장·실제NearAI 미인증. 007·009 완전 답변 실패. 일반 NO_ANSWER_PROGRESS 주의문이 COVERED에도 붙는 기존 표시 문제는 남아 있다. 다양한 미해결 상태의 안전한 출력과 실제 질의의 완전 해결을 구분한다.',
'전체 성공·MAIN 적합으로 승인하지 않는다. 작업 제품·선택MAIN112·GENOS현장은 그대로다. 원본/실패를 보존하고후속scope 계약 수정을 새 ADR로 남긴다. 활성배포 변경이 없어 포인터 롤백은 필요하지 않다. Git commit/push·메일·더좋은모델 비교 미수행.',
'06_TOOLS/EXPERIMENTS/adr_1174의check.py, regression.py parent/candidate, replay_saved.py, live.py, audit_result.py, audit_storage.py. 완료 실행을 덮어쓰는 재실행 금지. live의dispatch와순차gate가같은사례재호출을거부한다. 원시요청/응답·저널·해시는artifacts/manifest.json.']
p=ADR/'README.md';meta=p.read_text().split('---',2)[1];p.write_text('---'+meta+'---\n\n# 판단과 답변 일치 수정 및 CM 재검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 사례별 재검증\n\n001/007/009 각1회. 일치·저장과 답변 완성도를 구분한다.007/009 미완전,009 scope검증 결함으로 전체 성공 아님.\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
P=ROOT/'09_ARTIFACTS/AUDITS/20261028-assessment-answer-consistency';P.mkdir(exist_ok=True)
(P/'수정과_재시험결과.txt').write_text('판단·답변 일치 수정과 재시험 — 2026-10-28\n\n'+texts[0]+'\n\n'+texts[5]+'\n\n'+texts[6]+'\n\n'+texts[7]+'\n\n'+texts[10]+'\n\n상세: '+str(ADR/'README.md')+'\n')
put(ART/'report.json',{'path':str((P/'수정과_재시험결과.txt').relative_to(ROOT)),'sha256':sha(P/'수정과_재시험결과.txt')})
print('report written; overall unsuccessful, MAIN112 unchanged')
