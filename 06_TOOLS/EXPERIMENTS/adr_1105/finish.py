from common import *
import subprocess
x=read(ART/'run-001/result.json');b=x['arms']['baseline'];o=x['arms']['ontology'];m=read(ADR/'실험/manifest.json')
for c in m['integration']['conflicts']:c.update(id='main106-schema-preservation',between=m['integration']['parent_refs'],chosen_from='ADR-1092-experiment-v1/serving',rationale=c['resolution'])
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
m['results'].update(status='complete',by_arm={k:{'status':'complete','http_status':v['http_status'],'model_calls':v['model_calls'],'answer_coverage':v['outcome']['answer_coverage'],'disposition':v['outcome']['disposition'],'quality_certified':False,'decision_eligible':False} for k,v in x['arms'].items()},comparisons=[x['comparison']],
 usage={k:sum(v['usage'][k] for v in x['arms'].values()) for k in ('input_tokens','output_tokens','cost_usd')},latency={k:{'seconds':v['seconds'],'model_transport_seconds':v['model_transport_seconds'],'outside_model_seconds':v['outside_model_seconds'],'application_prepare_seconds':v['application_prepare_seconds']} for k,v in x['arms'].items()},error_taxonomy=x['comparison']['assessment_and_output_issues'])
m['results']['usage'].update(new_model_calls=12,new_evaluator_calls=0)
# Top summary explicitly refers to final claim citation, separate from ASSESS delivery.
m['retrieval_accounting'].update(before_filter={'baseline':b['assess_article_roots'],'ontology':o['assess_article_roots']},after_filter={'baseline':0,'ontology':2},presented_total={'baseline':0,'ontology':2},presented_mean={'baseline':0,'ontology':2},presented_p50={'baseline':0,'ontology':2},presented_p95={'baseline':0,'ontology':2},golden_recall={'baseline':0,'ontology':1},selectivity={'baseline':0,'ontology':2/m['retrieval_accounting']['corpus_total']})
m['retrieval_accounting']['summary_scope']='Final claim citations across two arm-cases. Full original acquisition and ASSESS delivery are separate measured stages in the ledger; baseline source-excerpt reply is not a cited claim.'
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)
summary=f'''최신 MAIN106에 온톨로지만 붙인 실제 실험 결과 — 2026-10-27

결론
사용자2번(승인 온톨로지 원문 확보 후 바로 ASSESS에서 답변·충분성·부족 함께 판단)은 실모델에서 작동했다.
답변 작성까지 도달했지만, 최종 정답·품질 통과로 볼 수는 없다. ASSESS 상태 모순과 COMPOSE의 의미 변형이 남았다.

같은 CM023 질문을 각1회 순차 실행
질문: 상장차익 증여의제는 어떤 요건에서 성립하는가? (업무 문맥: 주식등의 상장 등에 따른 이익의 증여)
기준 MAIN106: 모델8회 / {b['seconds']:.3f}초 / INSUFFICIENT·LIMITED_ANSWER / 기준근거0/2 / 답변 claim0.
MAIN106 + A1: 모델4회 / {o['seconds']:.3f}초 / PARTIAL·LIMITED_ANSWER / 기준근거2/2 / 답변 claim3, 인용 원문2개.

A1의 실제4호출
1 질문 해석 → 2 제41조의3 원문 READ 선택 → 서버가 승인 묶음의 원문을 조립 → 3 ASSESS → 4 narrative COMPOSE.
ASSESS 실제 입력에는 제41조의3과 시행령 제31조의3의28개 항·호, 승인 개념·관계·검토 내용과 현재 근거 번호가 함께 들어갔다.
총120개 원문 옵션에는 기존 자동 확보 정의 등도 포함된다. 온톨로지28개 모두 실제 입력 근거로 연결되었다.
원문 확보 이후 조사 메뉴 추가 호출0, ASSESS1회, ASSESS 보완0, 실제 gap0, 실모델 추가 조사0.
전체 요청을1호출로 끝낸다는 뜻은 아니다. MAIN106의 narrative 답변 작성 호출1회는 유지했다.

남은 실패와 담당 단계
1) ASSESS: 미확인 사항이 없고 gaps=[]라고 하면서 issue status=PARTIAL로 반환했다. 호스트는 그 상태를 유지해 제한 답변으로 발행했다.
2) COMPOSE: ASSESS C1에서 따로 둔 '기준금액 미만인 경우 과세 제외'와 '정산 시 가액 감소 등 별도 조건의 환급'을 최종 문장에서 합쳐, 기준금액 미만인 경우에도 환급받는 것처럼 서술했다. 제41조의3제1항(block346)과 제4항(block353)을 대조한 오류다.
3) ASSESS: 제6항(block355)의 '추정한다'와 '본다'를 하나의 '추정한다'로 합쳤고 최종 문장에도 이어졌다.
이는 보관 원문 대조에서 찾은 구체적 의미 오류다. 독립 모델 채점이나 법률 품질 인증은 하지 않았다.

기준 실행의 실패
제41조의3 대신 제45조의2 등을 골랐고, 이후 필요하다고 쓴 이유는 제41조의3인데 실제 missing_target은 제45조의2여서 목적과 대상이 엇갈렸다.
추가 조사 복귀1회 후에도 핵심 근거를 얻지 못해 기존 한도에서 MODEL_DECISION_UNRESOLVED 제한 답변으로 종료했다.

비교 해석의 한계
초기 요청의 시스템 문구는 같고 사용자 입력은 요청별 view_id만 달랐다. 그러나 첫 모델 응답의 검색어가 서로 달랐다.
온톨로지는 첫 READ 후에 활성화되므로 A1이 처음 올바른 조항을 고른 것 자체를 온톨로지 효과로 주장할 수 없다.
8→4호출·182→158초는 이번1건의 관찰값이다. 검색·선택 경로가 달라 온톨로지의 인과적 속도 개선율·정확도 개선율로 쓰지 않는다.
이번에 직접 확인한 효과는 올바른 원문 도달 뒤 묶음 확보 → 현재 근거와 함께 직접 ASSESS → 답변 작성의 연결이다.

검증·동결
MAIN106 release compact-input-20261027-r1, 공식429서빙파일. 기준 실행은429파일 전부 같은 바이트.
온톨로지 후보는 기존 제품4모듈, 신규 온톨로지5모듈·1스키마 및 엔진 결속을 변경. 구 후보의 별도 조사 메뉴·task-local·실행review·응답 스키마는 가져오지 않았다.
합성88검사 통과: 전체 원문이면 바로 판단·답변, 부족이면 기존 조사복귀 후 재판단, 동일 요청 재사용, 누락/판본/권한/해시/재개.
실제 원문 단위 검증: 기준152 + A1 208 =360개. 원문 불일치0, 권한 위반0.
실제 ASSESS 원문 옵션 대조: 기준83+94, A1 120. 불일치0. 알 수 없는 온톨로지 근거번호0, 실제 전송 출력상한 필드0.
Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음 / 출력상한 없음. 모델 총12회, 평가모델0회.
사용량: 입력{m['results']['usage']['input_tokens']}토큰, 출력{m['results']['usage']['output_tokens']}토큰, 응답 영수증 비용 ${m['results']['usage']['cost_usd']:.8f}.
기존 알려진 CM 질문1개이며 미사용 holdout·법률 품질 인증이 아니다.

반영 범위와 다음 수정 지점
격리 후보와 실험만 완료. 작업 제품코드·선택 MAIN106·GENOS·Git commit/push는 변경하지 않았다.
공통 MAIN에서 수정 중인 스키마·판단 연결 작업과 구분한다. 다음은 ASSESS의 충분성 상태 일관성, 원문의 의미 구분, COMPOSE가 승인 판단의 조건·예외 연결을 바꾸지 않는지를 확인할 대상이다.
1100/1103/1104의 검사자료 실패도 보존했다. 최종1105는 해당 제품과 같은 코드이며 검사기만 정정해88검사를 통과했다.

정본: artifacts/run-001/result.json, comparison.json, verification.json, retrieval-ledger.json, freeze.json.
각 arm/cm-023의 answer.txt·response.json·raw/call-*·canonical/*.gz·wire/*.gz·audit.json·wire-audit.json에 실제 기록을 보관한다.
'''
(ART/'실험결과.txt').write_text(summary)
header=(ADR/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약','최신 MAIN106에 온톨로지 직접 판단만 연결한 A1 실제4호출에서 원문 확보→ASSESS1회→답변 작성까지 도달했다. 최종PARTIAL·제한답변과 의미 오류가 있어 품질 인증은 아니다. [상세 TXT](artifacts/실험결과.txt).'),('문제와 변경 전 구조','기존 온톨로지 후보를 통째로 쓰면 별도 조사·응답 계약이 섞인다. 사용자 요구에 따라 선택MAIN106의 공식429파일을 기준으로 온톨로지 연결만 이식했다.'),('가설과 사전 판정 기준','[사전 기준](artifacts/criteria.json). 원문·ACL·판본·hash 보존과 현재ASSS근거 연결, 확보 다음 판단을 검사한다. 충분성·법률 판단은 모델이 맡으며 gap은 기존 MAIN 복귀로 처리한다.'),('실험 설계','완료1092/serving과1098/direct를 정확한 부모로 기록했다. 전자는 전체MAIN106 기반, 후자는 온톨로지 확보·전달·직접handoff만 채택했다.1100/1103/1104는 실패한 검사자료의 참고 관계이며 완료 부모로 사용하지 않는다. [구성](artifacts/composition.json).'),('데이터·모델·재현성','같은CM023·데이터세대·공개허용범위·Qwen3.8/Parasail FP8·출력상한 없음·40모델/1024도구/1800초. 기준답변·채점자료는 제품입력에서 분리. baseline→A1 순차 각1회, 셀 재시도0. [동결](artifacts/freeze.json).'),('결과',f'기준8호출 {b["seconds"]:.3f}초 INSUFFICIENT, A1 4호출 {o["seconds"]:.3f}초 PARTIAL. 둘 다 LIMITED_ANSWER. A1은 현재원문120옵션 중 온톨로지28원문을 COMPLETE묶음으로 받았고 ASSESS1회 뒤 narrative COMPOSE1회. 합성88통과. [결과](artifacts/run-001/result.json).'),('사례별 오류 분석','기준은 직접 조항 선택과 gap 대상이 어긋났다. A1은 PARTIAL/미확인없음 상태 모순, 추정/간주 구분 소실, 최종서술의 과세제외/환급 결합 오류가 있다. 원문 전달 실패와 구분한다. [단계별 비교](artifacts/comparison.json).'),('비용·지연·회수 규모',f'신규제품12호출·평가0. 입력{m["results"]["usage"]["input_tokens"]}, 출력{m["results"]["usage"]["output_tokens"]}토큰, 영수증비용${m["results"]["usage"]["cost_usd"]:.8f}. 원문360단위 mismatch/ACL위반0. 기준근거 좌표는 기준0/2·A1 2/2. 회수/ASSS전달/최종claim인용은 [단계원장](artifacts/retrieval-ledger.json)에서 분리했다. 최상위회수요약은 최종claim인용 범위다.'),('해석','직접 판단 연결은 실제로 작동한다. 초기 모델 검색어부터 달랐으므로 첫 원문 선택 및 전체 시간 차이를 온톨로지의 인과 효과로 해석하지 않는다. 답변 의미는 아직 별도 개선이 필요하다.'),('한계와 일반화 가능 범위','알려진1질문/arm별1회. 독립 평가모델0·holdout아님·법률품질 미인증. ASSESS의 gap복귀는 합성에서 통과했고 이번A1실모델에는gap0이라 실제복귀 효과는 관찰하지 않았다.'),('운영 결정·롤백 조건','후보 실험만 완료. 작업제품코드·MAIN106·GENOS·Git변경 없음. 무결성·권한 회귀는 허용하지 않는다. 다음 확인은 공통스키마 후속과 ASSESS/COMPOSE 의미 보존을 분리한다. [검증경계](artifacts/verification.json).'),('재현 명령','동결 runner `06_TOOLS/EXPERIMENTS/adr_1105/live.py baseline|ontology`. 보관 셀을 덮어쓰지 않는다. 새효과 비교·제품변경·재실행은 새ADR로 동결한다.')]
(ADR/'README.md').write_text('---'+header+'---\n\n# MAIN106 온톨로지 직접 판단 실제 실험\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 CM023 비교\n\n[실험결과](../artifacts/실험결과.txt). 기준8호출·A1 4호출. 직접 판단 연결 확인, 법률 품질 미인증.\n')
heads=['## 1. 실행 메타','## 2. 사용자 질문 원문','## 3. 기준답변 — 채점 전용, 제품 입력 비공개','## 4. 제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
texts=['run-001, baseline→ontology(A1), WSL nativeHTTP, known in-sample, model12/evaluator0.',read(ART/'cases.json')[0]['question'],'[평가 전용 원본](../../ADR-1066-ontology-input-unlimited/artifacts/cases-evaluator.json)의 cm-023. 실제업무 참고답변이며 현행 해석 미인증. 제품에 넣지 않았다.','[동결 파일](../artifacts/freeze.json), [기준 binding](../artifacts/run-001/baseline/binding.json), [A1 binding](../artifacts/run-001/ontology/binding.json).','[원장](../artifacts/retrieval-ledger.json): 원문 확보, ASSESS 실제 제시, 최종claim인용을 분리. 실제 제시와 인용을 동일시하지 않는다.','[baseline 원시호출](../artifacts/run-001/baseline/cm-023/raw), [A1 원시호출](../artifacts/run-001/ontology/cm-023/raw). canonical과 wire는 각 셀의 gzip 원본이며 입력/출력/사용량/지연을 함께 보관한다.','별도 compiler/verifier 모델0. 기준의 기존 조사보완2회·ASSESS2회 포함 총8호출. A1 조사선택1·ASSESS1·COMPOSE1 및 최초질문해석1로4호출.','평가모델0회. 보관 원문 좌표·내용 대조와 정성 오류분석만 수행. 반복 정답률이나 새기준 소급채점 없음.','직접 전달 연결 통과; 최종 PARTIAL 및 의미 오류. [TXT](../artifacts/실험결과.txt).']
(ADR/'실험/질문-001-cm-023.md').write_text('# CM023\n\n'+'\n\n'.join(h+'\n\n'+t for h,t in zip(heads,texts))+'\n')
art=read(ART/'manifest.json');paths=[p for p in ART.iterdir() if p.is_file() and p.name!='manifest.json']
paths += list((ART/'run-001').glob('*/binding.json'))+list((ART/'run-001').glob('*/cm-023/*.json'))+list((ART/'run-001').glob('*/cm-023/answer.txt'))+list((ART/'run-001').glob('*/cm-023/canonical/*.gz'))+list((ART/'run-001').glob('*/cm-023/wire/*.gz'))+list((ART/'run-001').glob('*/cm-023/raw/call-*/*.json'))+list(Path(__file__).parent.glob('*.py'))
art['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen binding, actual call/outcome or post-selection audit','contains_raw_prompts_and_outputs':any(k in str(p) for k in ('/raw/','/wire/','/canonical/'))} for p in sorted(set(paths))];put(ART/'manifest.json',art)
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note','CM023 baseline8/A1 4 live calls; source/wire integrity verified; partial semantic outcome preserved; MAIN unchanged'),('validate','--path',str(ADR),'--final')]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],cwd=ROOT,capture_output=True,text=True);print(args[0],r.returncode,r.stdout+r.stderr)
