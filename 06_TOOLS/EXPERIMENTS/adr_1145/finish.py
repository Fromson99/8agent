from common import *
import subprocess,statistics
x=read(ART/'run-001/result.json');m=read(ADR/'실험/manifest.json');criteria=read(ART/'criteria.json')
scores=x['scores'];ok=x['primary_pass'];decision='Accepted' if ok else 'Rejected'
summary=f"일반 요건 선택 baseline {scores['baseline']['general']['passed']}/6 → concise {scores['concise']['general']['passed']}/6, 통제 {scores['baseline']['control']['passed']}/5 → {scores['concise']['control']['passed']}/5. 선택 지침374→365문자. 새 모델{x['new_model_calls']}회. 인샘플·후보만 검증, MAIN 반영 없음."
m['results'].update(status='complete',by_arm={arm:{'status':'complete','scores':v,'quality_certified':False,'decision_eligible':False} for arm,v in scores.items()},comparisons=[{'paired':True,'unit':'case_id+repeat','scores':scores,'system_prompt_only':True,'in_sample':True,'holdout':False}],usage={**x['usage'],'new_model_calls':x['new_model_calls'],'new_evaluator_calls':0},latency={**x['latency'],'scope':x['latency_scope']},error_taxonomy=[{'type':'required_issue_omission','arm':r['arm'],'case_id':r['cell_id'],'observed':r['selected_paths'],'expected':r['expected']['exact_paths']} for r in x['cases'] if not r['route_pass']],quality_certified=False,main_wiring='candidate-only')
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=ok)
ra=m['retrieval_accounting'];ra['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
for arm in scores:
 rows=[r for r in x['cases'] if r['arm']==arm];counts=[r['final_article_roots'] for r in rows]
 gold=sum(len(r['expected_article_roots']) for r in rows);hit=sum(sum(c in r['final_cited'] for c in r['expected_article_roots']) for r in rows)
 for k,v in {'before_filter':len(rows)*x['source_roots_per_cell'],'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':hit/gold if gold else 1.0,'selectivity':statistics.mean(counts)/ra['corpus_total']}.items():ra[k][arm]=v
m['questions']=[{'number':i,'case_id':c['id'],'file':f"질문-{i:03d}-{c['id']}.md",'sha256':'PENDING'} for i,c in enumerate(read(ART/'cases.json'),1)]
put(ADR/'실험/manifest.json',m)
table='\n'.join(f"{r['arm']} / {r['cell_id']}: {','.join(r['selected_paths']) or '빈 경로'} / {r['effective_action']} / 통과={r['route_pass']}" for r in x['cases'])
detail=f'''온톨로지 보완 경로 선택 비교 — ADR1145

{summary}

변경
일반 성립·적용 요건은 성립 경로와 이를 뒤집는 제외·예외 경로를 함께 선택하도록 짧게 명시했다. 구체적 상황은 필요한 경로만 선택한다. 경로 ID나 질문의 정답은 지침에 넣지 않았다. 서버가2개를 강제로 채택하거나 본문을 재작성하지 않는다.
MAIN108과 제품 모듈1개(선택 지침) 및 해시 고정31파일만 다르다. 원문120옵션,사전 시나리오5개,선택 스키마,모델·제공자·추론 설정은 동일하다. 선택 전용 지침은374→365문자로9자 줄었다. 전체 입력은 약4만 토큰이므로 전체 입력량 최적화라고 하지 않는다.

실험
알려진 CM023 및 같은 주제의 일반요건 표현2개를 각2반복, 단일 경로3문항·서로 다른 업무2경로1문항·무관한 질문1문항을 각1회씩 양쪽에서 실행했다.8질문22셀을 순차 교차 순서로 실행했다. 반복과 표현 변경은 독립 holdout이 아니다.
모든 셀은 같은 보관 원문으로 실제 제품 ASSESS 선택→검증→시나리오 본문 그대로 조립·발행을 수행했다. SEARCH 셀은 검색 요청에서 멈춘다. 신규 검색부터의 전체 서비스 실험이 아니다. 기존 복귀·발행 경로는 별도 합성48검사로 확인했다.
독립 법률 정답 검증은 수행하지 않았다. 사전 경로 기준과 본문 보존을 측정했다. PATH1에도 제외 문구가 일부 있지만 사전 기대1+2는 그대로 평가했다.

셀별 결과
{table}

검증
원문 receipt 불일치{x['source_receipt_mismatches']},선택 본문 변형{x['final_body_mismatches']}. 실제 전송 입력·스키마·출력상한 검사는 wire-audit.json에 기록했다. 서버 보완과 모델 직접 선택은 raw응답으로 구분했다.
의미 재선택{x['semantic_reselections']}회,형식 보완{x['schema_repairs']}회. 평가 모델0회.
사용량: 입력{x['usage']['input_tokens']},출력{x['usage']['output_tokens']},비용${x['usage']['cost_usd']:.8f}. 전체 서비스 속도 개선율은 계산하지 않았다.

상태
사전 기준 통과={ok}. {decision}, in_sample=true, decision_eligible=false, quality_certified=false. 이 작업은 MAIN 포인터·GENOS·데이터를 변경하지 않았다. 운영 통합·승격은 별도 검증 사항이다.
동일 후보 재실행이나 완료 기록 덮어쓰기를 금지한다. 후속 변경·재시험은 새 ADR로 수행한다.
'''
(ART/'실험결과.txt').write_text(detail)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'MAIN108은 복수 선택과 충분성 판단을 허용했지만 알려진 질문에서PATH1만으로 충분하다고 보고PATH2를 누락했다.','[사전 동결](artifacts/criteria.json), [평가 전용 기대 경로](artifacts/rubric.json). 일반요건6/6,통제5/5,baseline보다 개선·무결성·합성계약 모두 요구. 사후 기준 변경 없음.','8질문22셀.3일반요건×2반복과5통제,양쪽 실제 모델 신규 호출. 교차 실행,한번에1프로세스. [순서](artifacts/schedule.json).','MAIN108의437서빙파일 및 고정 도구/검사 총662파일.후보는 지침1개+pin31개 변경. [동결](artifacts/freeze.json).Qwen3.8/ParasailFP8/reasoningnone/출력상한없음. 원문120옵션·5경로 동일.',f"{summary} [상세](artifacts/실험결과.txt). 사전 기준통과={ok}.",'실제 선택 목록·사유·보완 내역을 [결과](artifacts/run-001/result.json)에 셀별 보존했다. 원래 실패1135를 수정하거나 재채점하지 않았다.',f"모델{x['new_model_calls']}회·평가0, ${x['usage']['cost_usd']:.8f}. 선택과 고정본문 발행 구간만 측정.\n\n### 단계별 회수·탈락 원장\n\n[원장](artifacts/retrieval-ledger.json). 셀별 보관 원문→모델 전달→최종인용. 기대 좌표는 평가 단계에서만 결합. 반복 관측과 독립 원문 수 구분.",'모델 직접 선택과 서버 자동 채택을 분리했다. 경로 추가/본문 변경 로직은 없다. 별도 합성48검사로 재선택·SEARCH복귀·발행 계약 확인.','알려진 실패를 보고 조정한 인샘플,한 법률 주제·원문묶음.8독립 법률 사례/22독립 질문이 아니다. 원문이 다른 신규 업무·전체서비스·법률정확도 미인증.','후보만. MAIN/GENOS/데이터 변경0. 부적합 시기존MAIN108 유지. 다른 작업의 포인터 변경은 본 실험 적용과 구분한다.','`06_TOOLS/EXPERIMENTS/adr_1145/run.py`는 완료/부분실행 덮어쓰기 방지. `report.py`는 저장결과 읽기 전용평가. 새호출은 새ADR. [산출물](artifacts/manifest.json).']
head=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+decision)
(ADR/'README.md').write_text('---'+head+'---\n\n# 짧은 보완 경로 선택 지침\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,c in zip(m['questions'],read(ART/'cases.json')):
 rows=[r for r in x['cases'] if r['case_id']==c['id']]
 links='\n'.join(f"- {r['arm']} 반복{r['rep']}: [입력·원응답·발행본문](../artifacts/run-001/{r['arm']}/{r['cell_id']})" for r in rows)
 sections=['run-001/baseline+concise,실제Qwen3.8,보관원문선택.',c['question'],'[사전 기대 경로](../artifacts/rubric.json). 모델 입력에 넣지 않음. 독립 승인 법률 정답 없음.',links+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/retrieval-ledger.json). 원문과 경로 본문 동일. 평가좌표 사후결합.',links,'실제 보완과 재선택 수는 각result.json에 기록. 신규router/compiler/COMPOSE모델0. SEARCH요청 후실제탐색은 이셀에서미실행.','평가모델0. 경로ID·행동·원문·본문 hash 검증. 반복 결과 전부보존.','\n'.join(f"{r['arm']}반복{r['rep']}: {r['selected_paths']} / {r['effective_action']} / 통과={r['route_pass']}" for r in rows)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,sections),1))+'\n')
(ADR/'실험/README.md').write_text('# 선택 비교8질문\n\n'+summary+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);print(args[0],r.returncode)
