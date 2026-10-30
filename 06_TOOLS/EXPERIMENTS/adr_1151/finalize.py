"""Close CM51 collection only after every frozen case has a terminal record."""
from common import *
import sys,sqlite3
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
r=read(RUN/'summary.json');assert r['completed']==51 and read(RUN/'execution-complete.json')['completed']==51
cases=read(DES/'cases.json');m=read(ADR/'실험/manifest.json');graded=[]
for case in cases:
 a=read(RUN/case['id']/'analysis.json');rec=StageLedgerRecorder(case['id'],'selected',identity_canonicalizer)
 reads=a['read_coordinates'];cites=a['final_coordinates'];rec.record_stage('original_read','source',reads)
 rec.record_stage('final_cited','present',cites,parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Read original not cited in final response; no proof of irrelevance or absence'} for x in reads if x not in cites]);graded.append(grade_capture(rec.capture(),[]))
ledger=build_experiment_artifact('ADR-1151','ADR-1151-experiment-v1',[build_run_artifact('run-001',graded,{'selected':['original_read','final_cited']})]);put(RUN/'retrieval-ledger.json',ledger)
result={**r,'status':'complete','execution_complete':True,'all51_accounted':True,'product_code_changed':False,'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'freeze.json')['pointer_sha256'],'all_cases_answered_with_claims':sum(read(RUN/c['id']/'audit.json')['response_with_claims'] for c in cases)==51,'correct':None,'accuracy':None,'judge_calls':0,'in_sample':True,'decision_eligible':False};put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'selected':{'status':'complete','total':51,'attempted':51,'correct':None,'accuracy':None,'legal_accuracy':'not_scored','outcomes':r['outcomes']}},comparisons=[],judge_disagreements=None,usage={'product_model_calls':r['model_calls'],'offline_evaluator_calls':0,**r['usage']},latency={k:r[k] for k in ['elapsed_sum_seconds','p50_seconds','p95_seconds']},error_taxonomy=[{'type':k,'count':v} for k,v in r['outcomes'].items()])
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
# The canonical stage ledger is authoritative; no golden recall claimed.
counts=[len(read(RUN/c['id']/'analysis.json')['final_coordinates']) for c in cases];reads=sum(len(read(RUN/c['id']/'analysis.json')['read_coordinates']) for c in cases)
import statistics
nav=sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);scope=read(DES/'corpus.json')['document_ids'];corpus=nav.execute('SELECT count(*) FROM source WHERE document_id IN ('+','.join('?' for _ in scope)+')',scope).fetchone()[0];nav.close()
m['retrieval_accounting'].update(corpus_total=corpus,before_filter=reads,after_filter=sum(counts),presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=sorted(counts)[int((len(counts)-1)*.95)],golden_recall=None,selectivity=sum(counts)/(corpus*51))
refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 cid=q['case_id'];a=read(RUN/cid/'analysis.json');link='../artifacts/run-001/'+cid
 texts=[f'run-001 / selected / exact / CM51 {cid}; actual selected MAIN109 with exact user export host grant.',refs[cid]['question'],refs[cid].get('reference_answer','미작성')+'\n\n제품 입력에 사용하지 않았으며 이번 실행에서 법률 정답률을 채점하지 않았다.',f'[요청]({link}/request.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[읽기→인용 원장](../artifacts/run-001/retrieval-ledger.json). 공개원문65범위는 정답좌표로 좁히지 않았다.',f'`{link}/raw/call-*/request.json`와 response.json, canonical/*.json.gz, wire/*.json.gz에 실제 입력·출력·스키마·usage를 보존했다. 호출0회면 제품 응답만 기록한다.',f'[실행·보완·오류 분석]({link}/analysis.json). 모델{a["model_calls"]}회.','judge0회; reference answer와 drift가 독립 검증되기 전 정답/오답을 임의 확정하지 않는다.',f'{a["outcome"]},HTTP{a["http_status"]},주장{a["claim_count"]}개. [최종 반환]({link}/answer.txt). 실패와 제한답변은 그대로 보존했다.']
 p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['CM51전수실행은 완료했다. 모든 질문의 답변 성공 여부와 법률 정답률은 별개다. MAIN변경 없음.','사용자가 현재MAIN기준CM51전체 Qwen실행을 지시했다. RiskCM105는 명시적으로 제외했다.','[실행 전 기준](artifacts/design/criteria.json). 실패·보완·중단도 다음문항과 구분해 기록하며 같은 문항 재실행 없음.','CM001→051순차,새프로세스·빈runtime. 한 번에 무거운작업1개. 기존40/1024/1800예산,출력상한없음.','MAIN109440파일·선택데이터·프로필 고정. CM반출승인을 exactquestion/current65source ACL에 연결했다. 공개질문으로 허위표시하지 않았고 제품알고리즘·파일은 변경하지 않았다.',json.dumps(result,ensure_ascii=False,indent=2),'[전체답변](artifacts/run-001/전체답변과_실행결과.txt) · [표](artifacts/run-001/결과목록.csv). 각case analysis.json에 보완거절·제공자오류·미확정호출 등을 보존한다.','시간은 각 문항 요청 전체이며 프로세스 앱초기화 별도. 고정65초대기 없음. 비용은 제공자가 보고한usage만 합계하며 누락호출을 무료로 세지 않는다.','응답성공·원문일치·법률정답은 다른 지표다. 이 실행은 새 모델답변 수집이며 개선전후 비교가 아니다.','알려진CM질문,in_sample. 법률정답 미채점. 원문범위는현재MAIN외부모델허용65개이며 전체내규/GENOS접근을 뜻하지 않는다.','MAIN109유지. 승격/제품수정/GENOS배포/메일/Git없음. 후속원인수정은 새ADR로 진행한다.','prepare→preflight(외부모델0)→batch51순차→summarize→finalize→seal→status/validate/graph. 이미실행한문항을 덮어쓰거나 반복하지 않는다.']
p=ADR/'README.md';meta=p.read_text().split('---',2)[1].replace('status: Proposed','status: '+('Accepted' if result['all_cases_answered_with_claims'] else 'Rejected'));p.write_text('---'+meta+'---\n\n# MAIN109 CM51 전수실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(ADR/'실험/README.md').write_text('# CM51 실행 인덱스\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print('Final records generated')
