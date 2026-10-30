"""Post-selection audit only; no model calls, no product inputs modified."""
from common import *
import sys,sqlite3,gzip,statistics,math,collections
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
cases=read(DES/'cases.json');summary=read(RUN/'summary.json');assert summary['completed']>0
cases=[c for c in cases if (RUN/c['id']/'analysis.json').exists()]
m=read(ADR/'실험/manifest.json');refs={x['id']:x for x in read(ART/'evaluation-only/cases.json')};data=ROOT/read(DES/'baseline.json')['release']['data_path'];nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
for sid,raw in nav.execute('SELECT id,json FROM source'):
 x=json.loads(raw);c=x.get('article_coordinate') or {};did=c.get('doc_id',x.get('document_id'));node=c.get('node',x.get('unit_id'))
 if did in scope and str(node).isdigit():source[sid]=(did,int(node));corpus.add(source[sid])
nav.close()
def tuples(xs):return {(x['doc_id'],int(x['node'])) for x in xs}
def coords(xs):return [{'doc_id':d,'node':n} for d,n in sorted(xs)]
graded=[];audits=[];before=0;counts=[];finalgold=0;goldtotal=0
for case in cases:
 cid=case['id'];p=RUN/cid;a=read(p/'analysis.json');reads=tuples(a['read_coordinates']);cites=tuples(a['final_coordinates']);seen=set(reads);presented=set();delivered=set();views=[]
 for path in sorted((p/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  v=json.load(gzip.open(path,'rt'))['view'];visible=set()
  for x in v.get('read_candidates',[]):
   for node in reversed(x.get('path',[])):
    if node.get('level')=='조' and str(node.get('unit_id','')).isdigit() and x.get('document_id'):
     visible.add((x['document_id'],int(node['unit_id'])));break
  for x in v.get('sources',[]):
   if x.get('source_id') in source:
    visible.add(source[x['source_id']]);delivered.add(source[x['source_id']])
  seen|=visible;presented|=visible
  views.append({'call':int(path.name.split('.')[0]),'read_candidates':len(v.get('read_candidates',[])),'tools':len(v.get('tool_options',[])),'visible_original_roots':coords(visible),'goal_observation':v.get('answer_progress_context'),'source_stage':v.get('source_stage'),'pages':v.get('read_candidate_page')})
 gold={(x['doc_id'],int(x['node'])) for x in refs[cid]['targets']};rec=StageLedgerRecorder(cid,'supervised',identity_canonicalizer);rec.record_stage('delivered_or_read','source',coords(seen));rec.record_stage('original_read','select',coords(reads),parent_stage_ids=['delivered_or_read'],discard_reasons=[{'identity':x,'reason':'Presented candidate not acquired in this execution; no irrelevance claim'} for x in coords(seen-reads)]);rec.record_stage('final_cited','present',coords(cites),parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Acquired source not cited in final published claims'} for x in coords(reads-cites)]);graded.append(grade_capture(rec.capture(),coords(gold)));before+=len(seen);counts.append(len(cites));finalgold+=len(gold&cites);goldtotal+=len(gold)
 row={'case_id':cid,'http':a['http_status'],'outcome':a['outcome'],'calls':a['model_calls'],'claims':a['claim_count'],'seconds':a['elapsed_seconds'],'gold_total':len(gold),'gold_observed_union':len(gold&seen),'gold_presented':len(gold&presented),'gold_server_acquired':len(gold&reads),'gold_original_delivered':len(gold&delivered),'gold_cited':len(gold&cites),'target_trace':[{'coordinate':x,'presented':(x['doc_id'],x['node']) in presented,'server_acquired':(x['doc_id'],x['node']) in reads,'original_delivered':(x['doc_id'],x['node']) in delivered,'cited':(x['doc_id'],x['node']) in cites} for x in coords(gold)],'views':views,'generation_errors':a['generation_errors'],'assessment_errors':a['assessment_errors']};put(p/'focus-audit.json',row);audits.append(row)
ledger=build_experiment_artifact('ADR-1168',m['experiment_id'],[build_run_artifact('run-001',graded,{'supervised':['delivered_or_read','original_read','final_cited']})]);put(RUN/'retrieval-ledger.json',ledger)
result={**summary,'status':'complete','execution_complete':summary['completed']==3,'candidate':'ADR1167 rev001 unchanged copied to ADR1168 rev001','active_main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'freeze.json')['pointer_sha256'],'quality_certified':False,'correct':None,'accuracy':None,'judge_calls':0,'focus_audits':[{k:v for k,v in x.items() if k not in ('views','assessment_errors','generation_errors')} for x in audits]};put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'supervised':{'status':'complete','total':3,'attempted':summary['completed'],'correct':None,'accuracy':None,'legal_accuracy':'not_scored','outcomes':summary['outcomes']}},comparisons=[],judge_disagreements=None,usage={'product_model_calls':summary['model_calls'],'offline_evaluator_calls':0,**summary['usage']},latency={k:summary[k] for k in ['elapsed_sum_seconds','p50_seconds','p95_seconds']},error_taxonomy=[{'type':k,'count':v} for k,v in summary['outcomes'].items()]);m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=before,after_filter=sum(counts),presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=sorted(counts)[int((len(counts)-1)*.95)],golden_recall=finalgold/goldtotal,selectivity=sum(counts)/(len(corpus)*len(cases)))
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 if not (RUN/q['case_id']/'analysis.json').exists():continue
 cid=q['case_id'];a=read(RUN/cid/'analysis.json');link='../artifacts/run-001/'+cid
 texts=[f'run-001 / focused / exact / {cid}; isolated candidate HTTP, Qwen3.8 Parasail FP8. MAIN unchanged.',refs[cid]['question'],refs[cid]['reference_answer']+'\n\n제품입력비공개; 법률정답률 미인증.',f'[요청]({link}/request.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json), [화면별후보·읽기·인용]({link}/focus-audit.json). 최종present단계는 최종답변 인용이며 미관측SQL풀의 회수율이 아니다.',f'{link}/raw/call-*/request.json,response.json; canonical/*.json.gz; wire/*.json.gz에 실제 원문·응답·스키마를 보존.',f'[보완·실패]({link}/analysis.json), model calls {a["model_calls"]}.','Evaluator0; no automatic legal correctness grade; known in-sample cases, no generalization.',f'{a["outcome"]};HTTP{a["http_status"]};claims{a["claim_count"]}. [반환답변]({link}/answer.txt).']
 p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['실패 CM3문항 재실행 기록. MAIN변경없음; 일반 법률 품질 인증아님.','ADR1151의001/007최종실패,009중단 및 후보선택 이탈.','[사전기준](artifacts/design/criteria.json).','각질문1회,순차실행,최대40호출/1024도구/1800초. 사례재시도·judge없음.','ADR1167rev001과459파일동일. MAIN112 기반이며 선택 MAIN112는 유지. 동일65공개원문범위,CM반출허용,정답은평가영역에만 보존.',json.dumps(result,ensure_ascii=False,indent=2),'각 case focus-audit.json 및 analysis.json. HTTP200만으로 충분한법률답변으로 판정하지 않음.','[원시usage및시간](artifacts/run-001/summary.json). p95는3개 관측 요약일뿐 모집단추정아님. 입력후보→읽기→인용을구분.','저장입력계약검사와 새모델행동은별도. 과거MAIN109단일실행은동시통제기준선아님.','알려진3사례·단일실행. 회수원장은제시/확보자료만 다루며 전체SQL후보탈락 미관측. 정답버전미검증,법률정답률미채점.','활성MAIN112 유지, 승격·GENOS·Git·메일없음. 실패보존.','prepare.py→live.py --preflight→batch.py→summarize.py→finalize.py→hash/status/validate/graph. 이미실행한문항재호출금지.']
p=ADR/'README.md';meta=p.read_text().split('---',2)[1];p.write_text('---'+meta+'---\n\n# CM3 수정본 실모델 재실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(ADR/'실험/README.md').write_text('# 질문별 결과\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
print(json.dumps({k:result[k] for k in ['model_calls','outcomes','active_main_unchanged','focus_audits']},ensure_ascii=False))
