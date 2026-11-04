"""Finish the stopped probe without converting unexecuted cases into passes."""
from common import *
import collections,re,statistics,math,unicodedata
from openpyxl import load_workbook
from copy import copy
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-integration-multiturn-check';OUT.mkdir(exist_ok=True)
R2=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r2'
R3=ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r3'
audit=read(ART/'source-wire-audit.json');cases=read(DES/'workbook-cases.json');progress=read(ART/'batch-progress.json')
by_id={x['id']:x for x in progress};allcalls=[];turns=[]
for d in sorted((ART/'public-live').iterdir()):
 if (d/'calls.json').exists():allcalls.extend({'cell':d.name,**x} for x in read(d/'calls.json'))
 if (d/'result.json').exists():turns.extend(read(d/'result.json')['turns'])
contracts=read(ART/'contracts-frozen-result.json');contract_counts=collections.defaultdict(collections.Counter)
for x in contracts['rows']:contract_counts[x['test'].split('::')[0].split('/')[-1]][x['outcome']]+=1
freeze=read(DES/'freeze-public.json');drift=[n for n,h in freeze['files'].items() if sha(ROOT/n)!=h]
candidate=read(DES/'candidate-public.json');code=ROOT/candidate['code_root'];code_drift=[n for n,h in candidate['selected_files'].items() if sha(code/n)!=h]
assert not drift and not code_drift
scope={c['id']:c for c in read(DES/'cases.json')}
edited={c['id']:c for c in read(R3/'질문수정내역.json')}
labels={'GENOS_UI_REQUIRED':'현장 화면 미실행','CONCRETE_INPUT_REQUIRED':'질문 미확정','INTERNAL_MODEL_REQUIRED':'내부 모델 미실행','NOT_RUN':'제공자 중단 후 미실행','TECHNICAL_FAILURE':'실행 미완료'}
rows=[]
for c in cases:
 state=by_id.get(c['id'],{}).get('state',c['classification']);notes=[]
 actual=[x for x in turns if x['case_id']==c['id']]
 if c['id']=='b03-25':notes.append('첫 질문: API503/제공자429, 36.284초/2호출/완성답변 없음. 그 사람 역할·주제 변경·임시총회 후속은 미실행.')
 if c['id']=='b03-27':notes.append('1턴: API200, 97.633초/7호출, 제365조 원문 전용/최종 주장0. 동일 요청 재조회는 추가호출0. 새 메시지 2턴: API504, 222.951초/8호출, 제공자 공백 응답으로 180초 제한 도달. 반복 질문 전체 통과 아님.')
 if c['id']=='b03-16':notes.append('동일 문장을 b03-27 1턴에서 확인했으나 이 독립 케이스는 미실행. 그 응답은 원문 전용으로 설명 완료 아님.')
 if c['id']=='b03-04':notes.append('동일 문장을 b03-25 1턴에서 실행했으나 제공자429. 이 독립 케이스는 미실행.')
 if state=='INTERNAL_MODEL_REQUIRED':notes.append('내부 문서의 공개 표시를 바꾸지 않음. 내부 이력 보호 경계 때문에 실제 외부 모델 시험 제외. 모의 계약 통과를 실제 답변 통과로 세지 않음.')
 if state=='GENOS_UI_REQUIRED':notes.append('망분리 GENOS 화면 접근 불가. 로컬 API 결과로 클릭·화면 통과 판정하지 않음.')
 if state=='NOT_RUN':notes.append('사전 동결한 UNKNOWN 중단 조건 적용. 자동 재전송0.')
 if state=='CONCRETE_INPUT_REQUIRED':notes.append('R2 문서명·조번호 자리표시자 미확정. 현재 자료에는 직접 외규 인용 사례 없음.')
 if c['id'] in edited:notes.append('R3 수정: '+edited[c['id']]['reason'])
 rows.append({**c,'state':state,'status_ko':labels.get(state,state),'observed_turns':actual,'finding':' '.join(notes),'r3_changed':c['id'] in edited,'r3_action':edited.get(c['id'],{}).get('after',{}).get('action')})
put(ART/'case-review.json',rows)
metrics={'status':'NOT_PASSED','selected_main':137,'release_id':read(DES/'baseline.json')['pointer']['release_id'],'selected_files':524,'planned_workbook_cases':60,'concrete_groups':49,'planned_turns':55,'dispatched_groups':2,'dispatched_turns':len(turns),'completed_substantive_answers':0,'source_only_responses':1,'technical_errors':2,'unexecuted_workbook_cases':58,'case_states':dict(collections.Counter(x['state'] for x in rows)),'physical_calls':len(allcalls),'http200':sum(c.get('http_status')==200 for c in allcalls),'http429':sum(c.get('http_status')==429 for c in allcalls),'unknown':sum(c['status']=='unknown' for c in allcalls),'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in allcalls),'prompt_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) for c in allcalls),'completion_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) for c in allcalls),'request_seconds':sum(t['request_seconds'] for t in turns),'model_seconds':sum(c.get('seconds',0) for c in allcalls),'contracts':dict(contract_counts),'source_span_checks':sum(a['source_checks'] for a in audit['cells']),'delivered_span_checks':sum(a['delivered_checks'] for a in audit['cells']),'source_mismatches':sum(len(a['source_mismatches']) for a in audit['cells']),'acl_violations':sum(len(a['acl_violations']) for a in audit['cells']),'wire_mismatches':sum(len(a['wire_mismatches']) for a in audit['cells']),'budget_matches':all(a['budget_matches'] for a in audit['cells']),'duplicate_extra_model_calls':sum(t.get('duplicate',{}).get('extra_model_calls',0) for t in turns),'quality_certified':False,'code_drift':code_drift,'support_drift':drift,'product_changes':0,'MAIN_changes_by_this_task':0,'GENOS_executions':0,'new_email_sent':False,'revised_questions':18,'R3_live_answer_validation':False}
put(ART/'run-004/result.json',metrics)
for rid,area,reason in [('run-001','live','Native app rejected API_TYPE/channel fields with HTTP422; no model call'),('run-002','native','Native app rejected inconsistent public flag with HTTP422; no model call'),('run-003','checked-admission','Private ordinary history refused external public-session path; no model call')]:
 put(ART/rid/'result.json',{'status':'HARNESS_OR_BOUNDARY_FAILURE','reason':reason,'original_path':str((ART/area/'b03-25-selected-main').relative_to(ROOT)),'physical_calls':0,'product_changes':0,'preserved':True})
put(ART/'semantic-review.json',{'method':'Manual inspection of actual final payload, model response, exact stored source and memory view. No evaluator LLM. No approved full-answer key or accuracy claim.','rows':[
 {'case_id':'b03-25','turn':1,'verdict':'TECHNICAL_ERROR','basis':'Request entry accepted. Next read-choice call returned provider429; API503. No final answer; dependent turns not run.'},
 {'case_id':'b03-27','turn':1,'verdict':'SOURCE_ONLY','basis':'Stored article365 acquired. Model C1 stated annual general-meeting rule, but UNRESOLVED read judgment and EXCLUDED requirement accompanied covered reasons; one repair retained conflict. Final coverage INSUFFICIENT, claims0, original-text-only. Original-text retrieval is not a completed answer.'},
 {'case_id':'b03-27','turn':2,'verdict':'TECHNICAL_ERROR','basis':'Actual memory input included prior goal and original-text response. RESEARCH_REENTER selected the exact prior goal with KEEP source scope; derived task stayed on regular general meeting. Later NearAI HTTP200 headers with60 whitespace chunks/660bytes, then179.855sec deadline/API504. Memory receipt does not prove final multi-turn answer quality.'}],
 'multiturn_contracts':{'passed':72,'failed':0,'meaning':'17 structured scope +4 actual API synthetic +51 applied-mode contracts; deterministic mock responses, no real-model success claim.'},
 'additional_structure_contracts':{'passed':24,'failed':3,'meaning':'Existing heading-term expansion offers extra navigation candidates; failures are exact-list expectations (short heading, addendum query, non-article definition). No code fix made and not dismissed as passed.'}})
summary=[
 '현재 통테 질문 전체가 정상 답변된다고 확인하지 못했습니다. 실제 요청 3턴 중 설명 완성답변0, 원문 전용1, 기술오류2입니다. 60개 전체의 실패율이나 정답률을 뜻하지 않습니다.',
 '실행 환경: 로컬 MAIN137(query-latency-native-20261104-r1) 동일524파일, 선택 SQLite 원문 세대, 격리 대화 기록. Qwen3.8-27b / Near AI FP8 only / 추론none / fallback0 / ontologyOFF. 삼성 GENOS 내부 모델·화면 시험이 아닙니다.',
 '멀티턴·범위 검사: 모의72/72 통과. 내규→외규 현재 선택 우선, 근거 범위 제한, 같은 요청 중복 호출 방지, 정정 후 범위 유지 등을 확인했습니다. 추가 조문 탐색검사24/27 통과·3실패로 전체96통과/3실패입니다. 실모델 의미 품질과 구분합니다.',
 '실제 관찰① 내부회계관리자 지정 질문: 첫 해석 후 제공자429로 API503, 36.284초/2호출. 역할 후속·주제 전환·임시총회 후속은 미실행입니다.',
 '실제 관찰② 정기주주총회 질문 1턴: 97.633초/7호출, 상법 제365조 원문은 확보했지만 설명 완료 대신 원문만 표시했습니다. 모델은 기본 규칙을 썼으나 검토표 상태 UNRESOLVED/EXCLUDED와 충족 이유가 충돌해 보완 후에도 최종 연결 검토 미완료. 동일 요청 재조회는 같은 응답·추가모델0입니다.',
 '실제 관찰③ 같은 문장 새 메시지 2턴: 앞선 질문·답변이 모델 입력에 전달되고 같은 목표를 재검토 대상으로 선택했습니다. 이후 NearAI가 HTTP200 헤더 뒤 공백60조각660bytes만 보내 약180초 후 UNKNOWN/API504. 전체222.951초/8호출. 문맥 유실은 이 관찰에서 발견되지 않았지만 최종 답변·반복 일관성은 미확인입니다.',
 '계획60개 분류: 실제시도2개(3턴), 제공자 중단 후 미실행34개, 내부 모델 필요13개, 화면수행9개, 구체 입력 미정2개. UNKNOWN 후 사전 중단조건에 따라 새 전송하지 않았습니다. 미실행을 실패·통과로 집계하지 않았습니다.',
 '질문 수정: v2.3 서식·각30개를 유지하고18개 문항을 수정했습니다. 3번의 「그 사람」을 내부회계관리자로 명시했고 반복 시험은 새 메시지임을 명시했습니다. 5번은 구성·의결요건·리스크 한도/보고 주기처럼 현재 운영준칙에 없는 직접 답변을 가정한 질문을 개최 주기·안건 발의·주관부서·자료 결재·오류 수정·의사록 제공으로 바꿨습니다. 대사의 미정 문서/조번호와 직접 외규 인용 가정도 제거했습니다.',
 '내규 근거: 로컬 risk_team 등록 내규는 위험관리위원회운영준칙1건(2016-08-23 판본, 현재 유효성 미확인)입니다. R3은 이 저장 원문의 내용 확인에 따른 계획 수정이며 새 질문의 실모델 답변 통과본이 아닙니다. 현장에 다른 내규가 있다면 현장 원문으로 다시 확인해야 합니다.',
 f'실제 물리호출{len(allcalls)}: 정상HTTP200 {metrics["http200"]}, HTTP429 {metrics["http429"]}, UNKNOWN {metrics["unknown"]}. 보고비용 ${metrics["reported_cost_usd"]:.8f}, 입력/출력토큰 {metrics["prompt_tokens"]}/{metrics["completion_tokens"]}. 429·UNKNOWN 사용량은 제공자 미보고. 원문 확보27span·모델전달27span 대조, 원문/권한/전송불일치0, 예산17일치, 재조회 추가호출0. 저장원문·제품524파일 불변.',
 '남은 문제: 실제 후속 의미 연결·주제 전환·내규→외규의 최종 답변은 미확인입니다. 제공자 실패와 최종 검토표 연결 실패를 먼저 분리해 다뤄야 합니다. 확인되지 않은 성공을 만들기 위해 검토·권한 검사를 해제하지 않았습니다. 제품 코드·MAIN·원문·현장 배포·메일 변경은 없습니다.',
 '준비 실패 보존: 직접 API envelope 필드422, public flag422, private history 경계 거절은 모델0입니다. 이후 공식 chat adapter/service._normalize 경로의 공개 질문만 실제 실행했습니다. 초기 pytest 혼합 import/fixture bootstrap 실패는 별도로 보존하고 정확한524파일 origin을 확인한96/3만 결과로 사용했습니다. 집계 최초 node ID 문자열 형식오류는 원본을 보존하고 정수 좌표로 정정했습니다.',
]
(OUT/'질문_멀티턴_실제확인결과.txt').write_text('\n\n'.join(summary)+'\n')
put(OUT/'검증요약.json',metrics)
# Preserve the user's exact v2.3 test-sheet geometry in the internal result copies.
workbook_receipts=[]
for agent in (3,5):
 src=next(R2.glob(f'Agent8_과제{agent}_*.xlsx'));wb=load_workbook(src);ws=wb[f'A8_ITE_00{agent}']
 for row in [x for x in rows if x['agent']==agent]:
  n=row['number']+3;ws.cell(n,9,row['status_ko']);ws.cell(n,10,row['finding'])
  widths=[ws.column_dimensions[c].width for c in 'ABCDEFGHIJ']
  def line_count(text,width):
   return sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in line)/max(1,width-2))) for line in str(text or '').split('\n'))
  ws.row_dimensions[n].height=max(ws.row_dimensions[n].height or 60,15*max(line_count(ws.cell(n,c).value,widths[c-1]) for c in range(1,11))+6)
  if row['observed_turns']:ws.cell(n,6,'Codex(로컬)');ws.cell(n,7,'2026.11.04')
 h=wb['개정이력'];h['A13']='v2.3-R2 검증';h['D13']='기존 R2 질문의 로컬 확인 결과. 원문 전용·기술실패·미실행 구분. GENOS 현장 결과 아님.';h['E13']='통과 기재0 / 계획 R3 별도'
 path=OUT/f'Agent8_과제{agent}_R2질문_로컬검증결과.xlsx';wb.save(path)
 check=load_workbook(path);assert check[ws.title].max_row==33 and len(check.sheetnames)==3
 workbook_receipts.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'case_count':30,'passed_count':0})
put(OUT/'결과엑셀검증.json',workbook_receipts)
m=read(ADR/'실험/manifest.json')
for run in m['runs']:
 if run['purpose'] not in ('primary','repeat','regrade','holdout','audit'):run['purpose_detail']=run['purpose'];run['purpose']='audit'
 run['status']='complete';run['sha256']=sha(ROOT/run['artifact_path'])
m['retrieval_accounting']=read(ART/'retrieval-metrics.json')
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'new_model_calls':0},'selected-main':metrics},comparisons=[],judge_disagreements=0,usage={k:metrics[k] for k in ('physical_calls','reported_cost_usd','prompt_tokens','completion_tokens','unknown')},latency={k:metrics[k] for k in ('request_seconds','model_seconds')},error_taxonomy=[{'type':'other','name':'provider429','count':1},{'type':'other','name':'assessment_contract_unresolved','count':1},{'type':'other','name':'provider_whitespace_deadline_unknown','count':1}])
put(ADR/'실험/manifest.json',m)
headers=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[summary[0],summary[1],json.dumps(m['design']['success_criteria'],ensure_ascii=False)+' UNKNOWN/자원중단 또는 연속3기술오류 중단을 사전에 고정. 비어 있지 않은 문자열만으로 통과 판정하지 않음.',summary[6],summary[1]+' criteria/freeze-public/candidate-public에 코드·데이터·전송 지문 동결. 제품·채점모델 분리, 평가모델 호출0.',summary[2]+'\n\n'+summary[3]+'\n\n'+summary[4]+'\n\n'+summary[5],summary[11],summary[9]+'\n\n원장: artifacts/retrieval-stage-ledger.json.gz. 문항별 기사(root) 단위 실제 확보·전달. gold 미등록으로 recall=null; 미실행58은 skipped이며 검색 실패율 아님.',summary[7]+'\n\n'+summary[8],summary[10], '실험 전체 통과 미입증. 제품·MAIN·GENOS·메일 변경0. R2 및 실패원본 보존, R3 문서18항목 수정. 실패를 통과로 바꾸는 코드 변경0.', '06_TOOLS/EXPERIMENTS/adr_1318: prepare/freeze→live ingress 실패보존→live_public no-send admission→run_public 순차→UNKNOWN 중단→contracts(정확한 origin)→audit→ledger_v2→archive_runtime→finalize→adr_structure hash/status/validate --final/graph. 기존 dispatch 재실행 금지, 새 실험은 새ADR.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 통테 R2 실제 질문·멀티턴 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headers,values),1))+'\n')
for q in m['questions']:
 row=next(x for x in rows if x['id']==q['case_id']);d=ART/'public-live'/(q['case_id']+'-selected-main');a=next((x for x in audit['cells'] if x['case_id']==q['case_id']),None)
 contents=[f'run-004 / selected-main / MAIN137 / 실제 원본 exact. 이전 입장 run-001~003은 모델0. 원문 경로 {d.relative_to(ROOT)}. 미실행 여부: {row["status_ko"]}.',row['action'],row['expected']+'\n기준은 원래 통테 기대 결과이며 독립 승인 정답지가 아니다. 제품 입력에 정답을 넣지 않음.',json.dumps(a,ensure_ascii=False) if a else '회수 미실행. 단계 원장의 executed=false 및 사유 참조.',f'전체 system/user/schema/원응답/usage: {d.relative_to(ROOT)}/raw/call-*/request.json.gz 및 response.json.gz, canonical/*.json.gz. 결과가 없는 호출의 partial.json.gz 및 finished.json 보존.' if d.exists() else '실제 호출 없음. 원응답을 만들지 않음.',f'순서와 단계: {d.relative_to(ROOT)}/calls.json 및 generations.json. 실제 전송만 집계; 중간 출력은 최종 답변으로 세지 않음.' if d.exists() else '중간 호출 없음.', '평가 LLM 호출0. 실제 payload·저장원문·기억 상태의 수동 대조. 의미 정답률이나 실패율로 일반화하지 않음.',row['status_ko']+'\n\n'+row['finding']+'\n\n'+json.dumps(row['observed_turns'],ensure_ascii=False)]
 h=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
 (ADR/'실험'/q['file']).write_text('# 질문 '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {name}\n\n{v}' for i,(name,v) in enumerate(zip(h,contents),1))+'\n')
(ADR/'실험/README.md').write_text('# 원래60개 질문별 확인\n\n실제시도2개/3턴, 나머지58개 미실행. 전체 통과 기재0.\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1318','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved stopped question/multiturn probe record','contains_raw_prompts_and_outputs':('raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz'))} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]})
print(json.dumps(metrics,ensure_ascii=False))
