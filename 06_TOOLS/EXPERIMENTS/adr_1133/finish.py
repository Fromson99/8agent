from common import *
import subprocess
x=read(ART/'run-001/result.json');m=read(ADR/'실험/manifest.json')
summary='사전 조립5경로를 기존 ASSESS/COMPOSE에 연결했다. 140계약검사 통과·실제 선택4호출·사전 기준3/4. CM023의 복수 경로 선택 기준은 미달. 최종 선택 본문/출처 보존, MAIN107 불변. 품질 승격은 기각하고 구현 후보와 실패를 보존한다.'
report='''사전 조립 시나리오를 업무 질문에 맞게 선택하는 MVP — ADR1133

구현한 동작
원문에 연결된 명시적 조립 명세 → 질문 전에 시나리오를 컴파일 → JSON 보관 → 요청 시 현재 원문·판본·인용 결속 → 모델이 경로 ID·선택 이유·부족 사실만 반환 → 기존 답변 경로가 선택 본문을 그대로 출력한다.
사전 컴파일과 최종 법률 본문 작성에는 모델을 호출하지 않는다. 모델이 법률 조문을 이어 붙이거나 조건·산식을 새로 쓰지 않는다. 제출하지 않은 과거 원문 판단은 pending으로 유지한다.
조건부 선택은 부족한 사건 사실을 기록하며, 일반 규정 질문에는 개인 사실을 요구하지 않는다. 범위에 맞는 경로가 없으면 NO_MATCH와 제한 답변을 남긴다. 경로 선택은 관련성 판단이지 개별 사건의 법적 사실 확정이 아니다.

이번 데이터
원문28조각에 연결한22구성요소로5경로를 만들었다.
PATH1 일반 성립·정산 / PATH2 기준금액 미달 제외 / PATH3 가액 하락 환급 / PATH4 혼재재산 추정 / PATH5 담보 차입 취득 간주.
각 경로에는 그 경로에 필요한 정의·계산·조건·효과·예외·원문 출처를 펼쳐 넣었다. 모든 그래프 연결 조합을 열거하지 않고, 명세에 선언한 업무 경로의 의존만 조립한다.
조립 명세는 이번에 Codex가 원문을 보고 명시적으로 작성한 실험 자료다. 자동 온톨로지 생성이나 사람의 법률 승인 완료를 뜻하지 않는다. 상태는 EXPERIMENT_SOURCE_AUTHORED_NOT_APPROVED다. 신주·전환사채·부정행위·무상주 등 확장, 참조 문서의 추가 정의는 완전히 펼치지 않았고 해당 한계를 기록했다.

실제 선택 실험
1. CM023 성립 요건: PATH1 선택. 사전 기준은 PATH1+PATH2여서 실패.
2. 가액 하락 환급: PATH3 선택 — 통과.
3. 기준금액 미달: PATH2 선택 — 통과.
4. 관련 없는 대출 연체이자: NO_MATCH — 통과.
사전 기준 결과는3/4다. PATH1 본문 안에도 기준 미달 예외가 있으므로 첫 결과만으로 법률 오답을 단정하지 않는다. 중복 내용을 가진 경로들의 복수 선택 기준도 후속 설계 대상이다. 결과를 본 뒤 통과 기준을 바꾸지 않았다.
선택된3답변은 저장된 시나리오 본문·인용을 그대로 유지했다. NO_MATCH는 법률 claim 없이 제한 답변을 냈다. 결과4건 모두 입력 원문과 선택 출처의 불일치0, 최종 본문 변경0.

연결 검사와 실행 범위
140검사 통과: 기존111검사와 신규29검사. 모의 모델의 실제 HTTP 진입점에서 정상 선택·경로 없음·조건부 사실 부족·잘못된 선택 보완1회·요청 재사용·최종 문장 보존을 확인했다. HTTP 실행 중 컴파일 함수를 금지하는 검사도 통과했다.
실제 Qwen3.8 호출은 보관된 ASSESS 원문을 사용하는 제품 선택기/답변 조립기 구간의4질문이다. 신규 전체 검색에서 시작한 실모델 HTTP 실험은 아니다. 검색·권한을 새로 조회한 성능 또는 전체 서비스 품질을 인증하지 않는다.
이전1130의 계약/검사자료 실패,1131의 원문 메타데이터 누락,1132의 선택 기록 스키마 실패는 별도 완료 기록으로 보존했다. 이 세 실행의 실제 모델 호출은0이다.

비용과 자료 규모
실제 선택4호출, 보완0, 컴파일 모델0, 최종 문장 재작성 모델0, 평가 모델0.
입력163,739토큰·출력604토큰·총$0.04062616. Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음 / 출력 상한 필드0.
선택 및 보관 원문 결속·출력 구간은4.57~4.71초, p50 4.624초. 전체 서비스 지연이나 개선율이 아니다.
각 질문에 기존 원문120옵션(정규 조문 좌표10개)을 유지했다. 질문당 약4.1만 입력 토큰으로 입력 절감은 아직 확인하지 않았다. 네 질문의 반복 노출480개를 독립 원문480개로 세지 않는다.
최종 인용 조문은 질문별2,2,2,0개. 평가용 정규 좌표6/6 포함은 원문 범위 확인이며 법률 정확도100%가 아니다. 환급/제외 질문의 기대 좌표는 합성 평가 설계이고 독립 승인 정답이 아니다.

저장·적용 상태
MAIN107 기반662파일 격리 후보와 MVP 문서를 변경했다. 활성 포인터와 동결 코드 해시를 보존했다. 운영 MAIN/GENOS 및 Dataiku·S3·Oracle 게시를 변경하지 않았다. Git commit/push 없음.
Dataiku 쪽 자동 명세 작성·사람 검토·DB 게시 연결, 더 넓은 업무 경로와 일반화 검증, 입력 최소화는 남아 있다.
실험은 사전4/4 조건에 미달했으므로 Rejected / decision_eligible=false / quality_certified=false로 닫는다. 구현 자체는 검증 가능한 후보로 보존한다.

근거 파일
사전조립_시나리오.txt: 실제 모델에 제공한5시나리오 본문
package.json / recipe.json: 컴파일 결과와 명세
run-001/result.json: 질문별 선택·사전 기준·비용
run-001/scenario/<질문ID>/: 실제 요청·응답·선택·최종 답변
check-001.json / wire-audit.json: 연결·보존 검사
retrieval-ledger.json: 보관 원문→선택기 제시→최종 인용의 단계별 좌표
completion-audit.json: 동결 코드·선택 포인터·최종 문서 검증 범위
'''
(ART/'실험결과.txt').write_text(report)
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),arm_ids=['scenario'])
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Historical completed parent only; not paired baseline'},'scenario':{'status':'complete','route_pass':3,'route_total':4,'primary_passed':False,'quality_certified':False,'decision_eligible':False}},comparisons=[{'paired':False,'reason':x['paired_reason']}],usage={**x['usage'],'new_model_calls':4,'new_evaluator_calls':0,'compiler_model_calls':0,'compose_model_calls':0},latency=x['latency'],contract_checks=140,error_taxonomy=[{'type':'other','count':1,'denominator':4,'detail':'CM023 selected PATH1 only while frozen rubric required PATH1+PATH2. PATH1 includes threshold exception; route-coverage mismatch is not independently certified legal error.'}])
ra=m['retrieval_accounting']
for key,value in {'before_filter':40,'after_filter':6,'presented_total':6,'presented_mean':1.5,'presented_p50':2,'presented_p95':2,'golden_recall':1.0,'selectivity':1.5/8489}.items():ra[key]={'scenario':value}
ra['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
ra['summary_scope']='Final claim citations; per-case original inputs120 options/10 roots unchanged. Counts aggregate case+root. CM023 known reference; refund/exclusion synthetic expected source coordinates, unknown denominator0. Not legal-quality score.'
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
sections=[summary,'1124의 노드·의존 전달 이후에도 모델이 조건과 법률 문장을 조립했다. 사용자 요청대로 데이터를 사전 조립하고 요청 모델은 업무 경로만 선택하게 바꿨다.1132의 저장 계약 오류는 선택 receipt를 기존 assessment_basis에 넣어 수리했다.', '[호출 전 동결 기준](artifacts/criteria.json), [경로 기대값](artifacts/rubric.json). 무결성·HTTP검사 전부 및 경로4/4, 선택 본문 보존을 요구했다. 사후 기준 변경 없음.', '직접부모1132/scenario, MAIN107 기반662파일 격리 후보. baseline은 역사 참조로 미실행. 같은5경로에4질문을 순차1회 실행. 실제 제품 선택기 구간과 모의 HTTP 검사를 구분한다.', '[동결](artifacts/freeze.json). 명시적 원문 기반 조립 명세22구성요소/28원문/5경로. CM023 알려진 질문과 합성3질문. 제품 입력에 기준답변/판정 없음. Qwen3.8 Parasail FP8 reasoning none, fallback/출력상한 없음. 실험 명세는 Codex 작성이며 미승인.', '140검사 통과. 실제 선택3/4: CM023 PATH1(기준 PATH1+PATH2) 실패, 환급 PATH3·미달 PATH2·무관 NO_MATCH 통과. 최종 본문·출처 불일치0. [질문별 결과](artifacts/run-001/result.json), [상세](artifacts/실험결과.txt).', 'CM023의 복수 경로 기준 미달1/4. PATH1 본문에도 미달 예외가 있으므로 이 결과만으로 법률 오답을 단정하지 않는다. 중복 경로 의미와 선택 기준은 후속 과제다.1130~1132의 연결 실패도 덮어쓰지 않았다.', '실제4호출·입력163739/출력604토큰·$0.04062616. 컴파일/COMPOSE/평가 모델0. 선택 구간 p50 4.624초/p95 4.715초(n4), 전체서비스 아님.\n\n### 단계별 회수·탈락 원장\n\n[단계 원장](artifacts/retrieval-ledger.json): 보관 원문40→선택기40→최종 인용6(case+정규 조문 좌표). 질문당120옵션/10조문 유지. 최종 인용 평균1.5/p50 2/p95 2, 참고 corpus8489. 좌표 기대6/6은 의미 정확도가 아니며 합성2질문의 좌표도 포함한다.', '질문 전에 완성된 경로를 제공하고 선택 본문을 바꾸지 않는 실행은 확인했다. 업무 경로 선택의 전부 성공은 확인하지 못했다. 명세의 의미 정확성을 hash 검사가 보장하지 않는다.', '알려진 사례와 합성3문항, 단일 실행. 조립 명세 자동 생성/사람 승인 없음. 일부 확장 경로·외부 정의 미완성. 실제 전체 검색·실모델 HTTP/Oracle/GENOS 검증 없음. 입력 약4.1만토큰이므로 컨텍스트 절감 근거 없음.', 'Rejected는 사전 전체 성공/승격 조건 미달을 뜻한다. 후보 구현은 보존한다. MAIN107/GENOS/운영 적재 변경 없음. 후속 변경은 새ADR, 기존 결과·실패 불변. 게시 및 활성화는 별도 검증 대상이다.', '동결 runner는 `06_TOOLS/EXPERIMENTS/adr_1133/{build,check,live}.py`. 완료 출력은 덮어쓰지 않는다. 읽기 전용 집계는 `report.py`, 완료 문서 기록은 `finish.py`. 새 모델/조건 변경은 새ADR.\n\n[원시 산출물 색인](artifacts/manifest.json) · [실험 manifest](실험/manifest.json)']
(ADR/'README.md').write_text('---'+head+'---\n\n# 사전 조립 시나리오와 업무 경로 선택\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(heads,sections),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(ART/'cases.json') if c['id']==q['case_id']);r=next(v for v in x['cases'] if v['case_id']==q['case_id']);base='../artifacts/run-001/scenario/'+q['case_id']
 sections=['run-001/scenario, actual saved-source selector once. Native HTTP is separately synthetic.',case['question'],'[사전 경로 기준](../artifacts/rubric.json). CM023 기존 평가 좌표는 선택 뒤 결합. 다른3질문은 합성이고 독립 승인 법률 정답이 없다. 기대 경로/판정은 제품 입력 비공개.',f'[실제 입력]({base}/input-1.json), [package](../artifacts/package.json), [freeze](../artifacts/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/retrieval-ledger.json): 보관 원문→선택기→최종 인용, 정규 조문 좌표와 탈락 이유.',f'[요청·응답 원문]({base}/raw/call-001-memory-assess), [모델 출력]({base}/output-1.json), [최종 답변]({base}/answer.txt).','선택1회/보완0. 사전 컴파일/최종 문장 모델0. 별도 신규 검색 없음.','평가 모델0. 고정 경로ID와 본문/출처 보존 비교. 제품 결과 수정 없음.',f"선택 {r['selected_paths']}, 사전 경로기준 통과={r['route_pass']}. 선택 본문 보존={r['final_body_exact']}. 법률품질 인증 없음."]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(qh,sections),1))+'\n')
(ADR/'실험/README.md').write_text('# 사전 경로 선택4문항\n\n'+summary+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';txt=index.read_text();line='- [ADR1133 사전 시나리오 조립·업무 경로 선택](ADR-1133-scenario-selection-receipt/README.md) — 140검사 통과, 실제4호출/경로기준3/4, 최종 본문 보존. MAIN107 불변.\n'
if 'ADR1133 사전 시나리오' not in txt:index.write_text(txt.replace('# ADR workspace\n','# ADR workspace\n\n'+line,1))
a=read(ART/'manifest.json');a['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen design, actual calls, synthetic contracts or post-selection reporting','contains_raw_prompts_and_outputs':('/raw/' in str(p) or p.name.startswith(('input-','output-')))} for p in sorted(set([p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']+list(Path(__file__).parent.glob('*.py'))))];put(ART/'manifest.json',a)
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary),('validate','--path',str(ADR),'--final')]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],cwd=ROOT,capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);print(args[0],r.returncode,r.stdout+r.stderr)
