"""Record an exact one-call reference replay without changing product results."""
from pathlib import Path
import json,hashlib,sys
ROOT=Path(__file__).resolve().parents[3];A=ROOT/sys.argv[1];ART=A/'artifacts'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def fence(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','PEND\\u0049NG').replace('TODO','TO\\u0044O')+'\n```'
m=read(A/'실험/manifest.json');arm=m['design']['arms'][0]['id'];out=ART/'run-001/reference-menu-v6';r=read(out/'result.json');ok=r['http_status']==200
m['runs'][0].update(status='complete',sha256=sha(out/'result.json'))
m['results']={'status':'complete','by_arm':{arm:{'request_success_count':int(ok),'request_total':1,'all_reasons_present':r.get('all_reasons_present',False),'schema_repairs':r.get('schema_repairs'),'model_calls':r['model_calls'],'whole_api_rerun':False,'answer_quality':None,'not_graded_reason':'Reference schema probe, no legal answer/evaluator.'}},'comparisons':[],'judge_disagreements':None,'usage':{'model_calls':r['model_calls'],'input_tokens':sum(x.get('input_tokens',0) or 0 for x in r['usage']),'output_tokens':sum(x.get('output_tokens',0) or 0 for x in r['usage']),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in r['usage'])},'latency':{'seconds':r['seconds'],'generalization':'One exact stage replay, no latency/quality generalization.'},'error_taxonomy':[] if ok else ['other:provider_schema_grammar_failure']}
put(A/'실험/manifest.json',m)
transcript=[{p.name:read(p) for p in sorted(folder.glob('*.json'))} for folder in sorted((out/'provider').glob('call-*'))]
q=m['questions'][0];qp=A/'실험'/q['file'];qp.write_text('\n\n'.join(['# 실제 참조 선택 도구 입력 재실행','## 1. 실행 메타',fence({'adr_id':m['adr_id'],'arm_id':arm,'run_id':'run-001','scope':'reference menu only'}),'## 2. 사용자 질문 원문',r['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개','별도 법률 기준답변이나 채점 호출 없음. complete schema/scope/reading obligation 검사만 수행.','## 4. 제품 입력을 구성한 원값',fence(read(ART/'design/replay-data.json')),'### 회수·탈락 단계 원장 — run·arm별','해당 없음. 기존 참조 메뉴 재생이며 검색/필터/READ를 실행하지 않음.','## 5. 제품 모델 호출 — run·arm별 실제 원문',fence(transcript),'## 6. 중간 LLM 호출 — router/compiler/verifier/repair','위 공급자 단일 호출이 전부이며 숨은 보정/fallback 없음.','## 7. 채점 호출과 반복 판정','독립 judge 미수행.','## 8. 사례 최종 판정',fence(r)])+'\n')
front=(A/'README.md').read_text().split('---',2)[1]
sections={'1. 결정 요약':'참조 도구 스키마 수정의 정확 단계 probe. 결과 '+str(r['http_status'])+'; 전체API 재실행 없음. Proposed/MAIN unchanged.','2. 문제와 변경 전 구조':m['lineage']['hypothesis_delta'],'3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],'4. 실험 설계':'완료 부모의 첫 참조 입력을 원값 그대로 재생. 이전 거절 결정/답변/수정 지시 주입 없음. 공급자1회, 숨은 repair0.','5. 데이터·모델·재현성':'승인 공개145 scope/Qwen3.8/Parasail FP8/reasoning none/no fallback. frozen candidate, runner, data/request/offered/source/parent hashes.','6. 결과':fence(r),'7. 사례별 오류 분석':'원본 provider request/response 및 validation-schema는 artifacts/run-001/reference-menu-v6에 보존. 원문 READ/전체답변 실행으로 해석하지 않는다.','8. 비용·지연·회수 규모':fence(m['results']['usage'])+'\n\n검색/필터/READ 없음.','9. 해석':'제품 model 실제 출력의 schema/핸들/연결 의무 검증. 품질 정답률/대기시간 개선은 인증하지 않는다.','10. 한계와 일반화 가능 범위':'인샘플 정확 stage replay이며 전체API 성공 기록은 부모 ADR0668에 있다. GENOS 내부 모델 미접근.','11. 운영 결정·롤백 조건':'로컬 활성generation42/코드·데이터 포인터 unchanged. 승격 요건 미충족으로 MAIN 반영/GENOS 배포 없음.','12. 전체 실험 흐름과 다음 후보 관계':'정확 완료 부모 '+m['lineage']['parents'][0]['experiment_id']+'/'+m['lineage']['parents'][0]['arm_id']+'; 후속 변경/재실행은 새 ADR로 동결.','13. 아티팩트':'실험/manifest.json, artifacts/design/bindings.json, artifacts/contracts-final.log, provider original payloads.'}
(A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' 참조 선택 도구 스키마 검증\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in sections.items())+'\n')
(A/'실험/README.md').write_text('# 정확 단계 실행\n\n[질문 원값과 호출 기록]('+q['file']+').\n\n실제 전체 API 답변은 부모 ADR0668 기록을 사용한다.\n')
files=[]
for p in ART.rglob('*'):
 if p.is_file() and p.name!='manifest.json':files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, exact stage request/response, or contract verification.'})
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
print(json.dumps({'http_status':r['http_status'],'model_calls':r['model_calls'],'seconds':r['seconds']},ensure_ascii=False))
