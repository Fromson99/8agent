from common import *
import subprocess
m=read(ADR/'실험/manifest.json');c=read(ART/'check-001.json');result={'status':'complete','terminal':'CONTRACT_TEST_FAILED','passed':c['passed'],'failed':c['failed'],'failures':[r['test'] for r in c['rows'] if r['status']=='failed'],'new_model_calls':0,'quality_certified':False,'answer_cases_run':0,'build':read(ART/'build-result.json')};put(ART/'run-001/result.json',result)
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Historical reference only'},'scenario':{'status':'complete','terminal':'CONTRACT_TEST_FAILED','quality_certified':False}},comparisons=[],usage={'new_model_calls':0},latency={'contract_checks_seconds':c['seconds']},error_taxonomy=[{'type':'other','count':4,'detail':'All four native paths failed before model selection because scenario source header omitted document_id and evidence_refs required by existing source-span delivery validation.'}])
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
m['design']['planned_but_unexecuted_retrieval_stage_plan']=m['design']['retrieval_stage_plan'];m['design']['retrieval_stage_plan']['stages_by_arm']={}
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Actual selector runs cancelled after contract test failure; only local synthetic fixtures and offline compilation executed.')
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',artifact_path=None,sha256=None,summary_run_id=None,not_applicable_reason=m['retrieval_accounting']['not_applicable_reason'])
for key in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):m['retrieval_accounting'][key]=None
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
summary='사전 조립5경로·662파일 후보를 만들었으나134검사 통과/4실패로 실제 선택 실험은 취소했다. 모델0회·MAIN107 불변.'
texts=[summary,'1124는 노드와 의존을 전달했으나 사용자 요구는 사전에 완성한 시나리오의 경로 선택이다.','[동결 기준](artifacts/criteria.json). 경로 선택과 원문·문장 보존을 검사한다.','직접부모1124/semantic. 단일 scenario arm, 역사 baseline 미실행. 실제4문항은 검사 실패로 미실행.','[동결662파일](artifacts/freeze.json). 원문28·명시적 레시피22구성요소·5경로. Qwen3.8 계획, 실제 호출0.',summary,'선택 입력 source header의 document_id/evidence_refs 누락으로 native4검사가 실제 원문 전달 검증에서 차단됐다. [검사 원문](artifacts/check-001.json).','생성모델0·답변모델0·평가0. 실제 회수 없음.','컴파일 결과는 생성됐지만 실제 요청 연결은 검증 미완료다.','합성/API 실패 기록이며 법률 품질/실모델 선택 효과는 미측정.','MAIN/GENOS/운영지식 변경 없음. 후속ADR에서 계약과 fixture만 보완한다.','동결코드와 check-001 보존. 완료 build/check를 덮어써 재실행하지 않는다.']
(ADR/'README.md').write_text('---'+head+'---\n\n# 사전 시나리오 컴파일 — 계약 실패 보존\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
for q in m['questions']:
 p=ADR/'실험'/q['file']
 if not p.exists():
  candidates=list((ADR/'실험').glob('*'+q.get('case_id','')+'*.md'));p=candidates[0] if candidates else p
 hs=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
 case=next((r for r in read(ART/'cases.json') if r['id']==q.get('case_id')),None)
 ts=['구현 계약 실패로 실제 미실행.',case['question'] if case else '사전 cases.json에 등록한 질문; 미실행.','기준답변 제품 미제공·채점 미실행.','[원문과 레시피](../artifacts/recipe.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n실제 모델/회수 미실행. 합성 계약검사만 수행.','실제 호출0.','사전 컴파일 모델0.','평가모델0.',summary]
 p.write_text('# 검사 실패로 미실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(hs,ts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 선택 미실행\n\n'+summary+'\n')
a=read(ART/'manifest.json');a['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Failed candidate retained','contains_raw_prompts_and_outputs':False} for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json'];put(ART/'manifest.json',a)
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary),('validate','--path',str(ADR),'--final')]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],capture_output=True,text=True);print(args[0],r.returncode,(r.stdout+r.stderr)[-2000:])
