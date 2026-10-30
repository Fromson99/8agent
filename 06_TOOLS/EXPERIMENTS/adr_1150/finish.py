from common import *
import ast,statistics,subprocess
x=read(ART/'run-001/result.json');m=read(ADR/'실험/manifest.json');assert x['primary_pass']
summary='365자 선택 지침으로 일반요건3표현×2반복6/6에서PATH1+PATH2,단일·별도복수·무관질문5/5통과. 총11모델응답·보완0·재선택0. 동일원문 인샘플후보 검증이며실시간paired비교·MAIN승격은미완료.'
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','role':'historical1135and interrupted1145/1148, excluded from1150score'},'concise':{'status':'complete','scores':x['scores']['concise'],'quality_certified':False,'decision_eligible':False}},comparisons=[{'paired':False,'reason':'1145 firstbaseline request and1148secondbaseline request did not complete. Preserve aborted runs;1150candidate-only robustness, historical1135is context only.','candidate_score':x['scores']['concise']}],usage={**x['usage'],'new_model_calls':11,'new_evaluator_calls':0},latency={**x['latency'],'scope':x['latency_scope']},error_taxonomy=[],quality_certified=False,main_wiring='candidate-only')
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
ra=m['retrieval_accounting'];rows=x['cases'];counts=[r['final_article_roots'] for r in rows];gold=sum(len(r['expected_article_roots']) for r in rows);hit=sum(sum(c in r['final_cited'] for c in r['expected_article_roots']) for r in rows)
for k,v in {'before_filter':len(rows)*x['source_roots_per_cell'],'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':hit/gold,'selectivity':statistics.mean(counts)/ra['corpus_total']}.items():ra[k]={'concise':v}
ra['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
m['questions']=[{'number':i,'case_id':c['id'],'file':f"질문-{i:03d}-{c['id']}.md",'sha256':'PENDING'} for i,c in enumerate(read(ART/'cases.json'),1)];put(ADR/'실험/manifest.json',m)
table='\n'.join(f"{r['cell_id']}: {','.join(r['selected_paths']) or '빈 경로'} / {r['effective_action']} / 통과={r['route_pass']}" for r in rows)
known=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1148-scenario-complement-walltime/artifacts/run-001/concise/cm-023__r1/result.json')
known_cost=x['usage']['cost_usd']+sum(u['cost_usd'] for u in known['usage'])
detail=f'''온톨로지 경로 선택 개선 확인 — ADR1150

결과
일반 성립 요건 질문3표현을각2번확인해6/6회PATH1+PATH2를모델이직접선택했다.
단일경로3문항,혼재재산·담보차입의별도2경로1문항,무관한질문의SEARCH1문항도5/5통과했다.
새모델11회모두첫응답에서결정했다. 형식보완0·의미재선택0이며서버가경로를자동추가하지않았다.

변경
기존에는복수선택을허용했지만일반성립질문에서성립경로만으로충분하다고판단했다.
새지침은“일반 성립·적용 요건은 성립 경로와 이를 뒤집는 제외·예외 경로를 함께 선택한다. 구체적 상황은 그 상황에 필요한 경로만 고른다.”로필요범위를명시한다.
특정질문명·PATH번호·정답·선택개수2를규칙으로넣지않았다.
선택전용지침374→365문자,9자감소. 제품은ontology_scenarios.py의PROMPT만바꾸고해시고정31파일을갱신했다. 선택출력계약·사전시나리오·원문·재선택/SEARCH제어는동일하다.

실행범위
MAIN108고정코드위의동일120원문옵션·5경로를사용한선택실험이다. 원문탐색전체를새로실행하지않았다. 실제제품ASSESS→선택본문검증→그대로조립·발행을확인했다. 무관질문은SEARCH요청에서멈추며실제후속검색실행으로세지않는다.
재선택·기존검색복귀·발행은ADR1145에서새합성48검사를통과했다. ADR1148/1150의662제품파일해시가동일하므로상속했으며48검사를다시수행했다고세지않는다.

시행별기록
- ADR1145:계획22셀첫baseline호출이10분넘게미완료. 정확한실행프로세스종료,응답·사용량·과금미확인. 완료0.
- ADR1148:동일수정안첫CM023은4.83초에PATH1+PATH2로완료. 다음baseline은호출전체120초상한에걸려중단. 완료1·미완료1·미실행20.
- ADR1150:동일수정안만11셀로새로동결해완료. 이전실패를지우거나같은예약에서재실행하지않았다.
기존baseline실제요청은ADR1135의요청과JSON전체가동일했지만이번에는완료되지않았다. 과거1135의PATH1단독선택과이번후보결과는참고비교다. 같은시점의정상완료paired비교가없으므로개선율·인과적속도차이를계산하지않는다.

셀별결과
{table}

무결성과사용량
원문receipt불일치0·선택본문변경0·실제전송입력/스키마불일치0·출력상한필드0. 원문120옵션과모든시나리오본문이동일하다.
Qwen3.8 / ParasailFP8 / reasoningnone / fallback없음. 평가모델0.
1150신규11회:입력{x['usage']['input_tokens']}토큰·출력{x['usage']['output_tokens']}토큰·${x['usage']['cost_usd']:.8f}.
이번작업전체외부요청14회중12회완료·2회미완료다. 완료응답의확인비용합계${known_cost:.8f}이며미완료2회의과금은미확인이다. 총비용으로단정하지않는다.
1150선택·고정본문발행구간중앙값{x['latency']['concise']['p50_seconds']:.3f}초,최대{x['latency']['concise']['max_seconds']:.3f}초. 전체서비스응답시간이아니다.
입력은질문당약4만토큰이므로지침9자감소를전체컨텍스트최적화로설명하지않는다.

검증경계와적용상태
같은온톨로지묶음의알려진실패와작성한질문8개를반복했다.11독립질문·독립holdout·다른법률업무의일반성능·법률정답률을인증한것이아니다.
PATH1에제외문구가일부겹치는점은기존기대1+2를바꾸는근거로사용하지않았다. 시나리오구조와기대경로는수정하지않았다.
Accepted / in_sample=true / decision_eligible=false / quality_certified=false. 수정은격리후보에있다. 이작업의작업코드·MAIN포인터·데이터·GENOS변경은0이다. 동시작업에서선택한MAIN109와이실험의기준MAIN108을구분한다.
후속MAIN반영시현재선택코드에PROMPT1변경을병합하고해시·소비자계약을다시검증해야한다.
'''
(ART/'실험결과.txt').write_text(detail)
tree=ast.parse((ROOT/'06_TOOLS/EXPERIMENTS/adr_1148/finish.py').read_text());lists={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('heads','qh')}
texts=[summary,'일반성립질문에서PATH1만고르는기존실패를보고성립과이를뒤집는제외경로의함께선택을짧게명시했다. 데이터·서버자동선택은바꾸지않았다.','[동결기준](artifacts/criteria.json)·[기대경로](artifacts/rubric.json). 일반6/6·통제5/5·무결성·기존계약상속통과를요구. 사후기준변경없음.','동일수정안11셀순차. 일반3표현각2반복+통제5문항. 이전1145/1148paired중단보존. 재동결한후보만검증;새paired개선율없음.','MAIN108고정437서빙/662제품지원파일. 1145와1148의후보제품동일. [동결](artifacts/freeze.json). Qwen3.8/ParasailFP8/출력상한없음. 원문·5경로동일.',summary+' [전체결과](artifacts/실험결과.txt).','11셀경로기준오류0. 원문/본문불일치0. 원래1135선택실패와1145/1148미완료응답은독립보존.',f"신규11회·입력449541/출력1983·$0.09676060. 기존48검사는제품해시로상속.\n\n### 단계별 회수·탈락 원장\n\n[원장](artifacts/retrieval-ledger.json):셀+원문좌표110→110→{sum(counts)}. 기대시나리오좌표{hit}/{gold}는법률정확도가아니다. 검색실험이아닌보관입력선택이다.",'모델이첫응답에서필요경로를모두선택했다. 재선택을강제하거나PATH2를서버에서끼워넣지않았다. 단일경로와무관질문도선택성이유지됐다.','인샘플·한온톨로지묶음·8질문11반복셀. 새paired비교미완료·독립holdout/법률품질/전체서비스미인증.','Accepted·decision_eligible=false·후보만. 현재MAIN109반영/작업코드통합/GENOS배포/데이터변경없음. 후속도입은최신코드결합검증필요.','완료실행덮어쓰기금지. `06_TOOLS/EXPERIMENTS/adr_1150/report.py`는저장원문읽기전용평가. [산출물](artifacts/manifest.json).']
head=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted');(ADR/'README.md').write_text('---'+head+'---\n\n# 짧은 보완 경로 선택 지침 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(lists['heads'],texts),1))+'\n')
for q,c in zip(m['questions'],read(ART/'cases.json')):
 rs=[r for r in rows if r['case_id']==c['id']];links='\n'.join(f"- 반복{r['rep']}: [실제입력·응답·발행본문](../artifacts/run-001/concise/{r['cell_id']})" for r in rs)
 sections=['run-001/concise,실제Qwen3.8,보관원문선택. baseline은본ADR미실행.',c['question'],'[평가전용기대](../artifacts/rubric.json),제품입력미포함.독립법률정답없음.',links+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/retrieval-ledger.json).사후평가좌표결합.',links,'보완0·재선택0. compiler/COMPOSE/평가모델0. SEARCH실제검색은미실행.','평가모델0.기대경로·행동·본문·원문hash검사.반복전부보존.','\n'.join(f"반복{r['rep']}: {r['selected_paths']} / {r['effective_action']} / 통과={r['route_pass']}" for r in rs)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(lists['qh'],sections),1))+'\n')
(ADR/'실험/README.md').write_text('# 후보선택8질문11셀\n\n'+summary+'\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);print(args[0],r.returncode)
