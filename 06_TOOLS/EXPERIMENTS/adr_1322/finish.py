from common import *
import re,collections
from openpyxl import load_workbook
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-multiturn-repair';P=ROOT/'04_EXPERIMENTS/ADR/ADR-1319-multiturn-command-assessment-repair/artifacts'
a=read(ART/'contracts-final/result.json');b=read(ART/'scope-modes/result.json');w=read(ART/'working-api/result.json');integration=read(ART/'working-integration.json');prior=read(P/'run-001/result.json')
assert a['passed']==124 and b['passed']==51 and w['passed']==4 and a['failed']==b['failed']==w['failed']==0
assert (ART/'working-native-check.log').read_text().strip()=='Checked 639 Oracle query plans'
f=read(DES/'candidate-integrated.json');assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items());assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer']
layout=[]
for agent in (3,5):
 src=next((ROOT/'09_ARTIFACTS/REPORTS/DOCUMENTS/20261104-integration-template-r3').glob(f'Agent8_과제{agent}_*.xlsx'))
 dst=OUT/f'Agent8_과제{agent}_통합테스트30_수정후점검_20261104.xlsx';before=load_workbook(src);after=load_workbook(dst);name=f'A8_ITE_00{agent}';x=before[name];y=after[name]
 assert before.sheetnames==after.sheetnames and y.max_row==33
 assert [str(r) for r in x.merged_cells.ranges]==[str(r) for r in y.merged_cells.ranges]
 assert all(x.cell(r,c).value==y.cell(r,c).value for r in range(1,34) for c in range(1,9))
 assert all(x.column_dimensions[c].width==y.column_dimensions[c].width for c in 'ABCDEFGHIJ')
 layout.append({'agent':agent,'same_three_sheets':True,'same30_questions_conditions_expected_results':True,'same_columns_and_merges':True,'result_columns_only':True,'final_live_pass_count':0,'sha256':sha(dst)})
put(OUT/'최종_양식검증.json',layout)
summary={'status':'WORKING_CODE_INTEGRATED_FIELD_UNVERIFIED','unique_contracts_passed':175,'contracts_failed':0,'parent1321_preserved':{'passed':123,'failed':1},'working_api_rechecks':4,'rechecks_overlap_unique_contracts':True,'code_files_changed':38,'product_files_changed':6,'native_catalogue_changed':1,'hash_pins_changed':31,'same525_candidate_working_files':True,'active_main':139,'main_pointer_unchanged_by_this_task':True,'parallel_embedding_changes_preserved':integration['parallel_embedding_changes_preserved'],'new_models_this_ADR':0,'prior1319_actual_probe':{'turns':3,'substantive_answers':1,'source_only':1,'technical_errors':1,'physical_calls':37,'unknown':1,'reported_cost_usd':prior['reported_cost_usd'],'source_checks':470,'delivered_checks':761,'source_acl_wire_mismatches':0,'duplicate_extra_model_calls':0},'final_candidate_live_answer_test':False,'full60_live_passed':False,'native':read(DES/'native-plan-equivalence.json'),'engine':integration['engine_preflight'],'field_deployment':False,'email_sent':False,'quality_certified':False}
put(RUN/'result.json',summary);put(OUT/'최종_검증요약.json',summary)
texts=[
'멀티턴 명령·후속 질문 지침·검토 오류 안내를 수정해 로컬 작업 코드에 통합했습니다. 최종 관련 계약175개(124+51)와 작업 코드의 실제 API 모의 재확인4개가 통과했습니다. 재확인4개는175개에 포함된 검사이며 중복 합산하지 않습니다. 선택 서비스 MAIN139·GENOS 현장·메일은 이번 작업으로 변경하지 않았습니다.',
'① 같은 질문을 보완할 때 새 목표로 바뀌는 문제: method별 허용 문서범위/수정 필드를 normalize와 맞췄습니다. 거절된 원제안을 보존하고 필드 오류 보완에서는 원래 method/target을 유지합니다. 실제 의미가 다른 주제라는 검토 실패에서는 재선택을 허용합니다. 이전 call009 AUTHORIZED+RESEARCH_REENTER 오류와 원제안 소실·새목표 변경을 기준코드에서 재현했고 수정본 계약이 통과했습니다.',
'② 후속 질문 지침 누락: answer_first=false인 현재 기본 설정에서 같은 조문·제도의 후속 질문을 기존 목표로 이어가라는 system 지침이 빠졌습니다. 대화 연속성 지침을 검색 옵션과 분리하여 resolver와 command-check 양쪽에 항상 전달합니다. 실제 모델이 언제나 같은 목표를 고른다는 보장은 아니며, 최종 수정본의 실모델 재시험은 미실행입니다.',
'③ 최종 검토 보완: USE/CONDITIONAL인데 연결된 주장이 비어 있는 행, 미채택 판단과 주장 원문이 겹치는 행을 원제안 그대로 보여주며 모델이 선택할 수정 방향을 안내합니다. const뿐 아니라 enum의 유일한 분기를 찾아 정확한 오류 위치를 전달합니다. 주장·법률 상태·미확인 사항을 서버가 임의 채택/삭제하지 않고 원문·권한·해시·기존 모든 검증은 유지합니다.',
'④ 오류/재개: 기존 UNKNOWN 차단과 알려진 실패의 안전한 재개·동일요청 중복호출 방지를 검사했습니다. UNKNOWN 자동재전송을 새로 허용하지 않았습니다. 내규→외규→전체 범위 전환의 실제 API 모의 검사에서 현재 범위에 맞는 근거만 전달하고 같은 요청 재조회는 추가호출0, 같은ID의 다른 입력은409를 확인했습니다.',
'실제 모델 실험은 중간수정본 ADR1319 기준입니다. MAIN138에서 격리한 SQLite 코드, Qwen3.8-27b FP8/추론none, Parasail우선·알려진429만NearAI1회전환 정책. 1턴349.559초/15호출은 원문전용, 같은 문장2턴54.499초/7호출은 같은goal유지·정기총회 일반원칙과 결산기 예외2주장 전달. 두 응답 모두 완성 조건은 실패이므로 반복통테 전체 통과가 아닙니다.',
'별도 후속3턴 「그럼 임시총회는 언제 소집하나요?」는 대상을 상법상 임시총회로 이해했으나 CASE_START로 새goal을 만들었습니다. 위②의 지침 누락을 실제 전송입력에서 확인했습니다. 이후 보완호출이179.906초 후UNKNOWN/API504, 전체372.298초였습니다. 주제전환4턴과 전체60문항 확대는 중단했습니다. 최종후속수정 ADR1321/1322에서는 새모델0입니다.',
f'전체 실제 물리37/정상36/UNKNOWN1·알려진4290, 보고비용 ${prior["reported_cost_usd"]:.8f}(UNKNOWN 미보고). 원문470/실제전달761span 대조, 원문·ACL·wire 불일치0,예산37일치,동일요청재조회추가0. 정확도나서비스속도전후개선율로일반화하지않습니다.',
'작업코드 반영:6제품+1Oracle준비계획+31pin=38파일. 후보와작업525파일SHA일치,639실행SQL/list/AST동일·소스행번호metadata8개/sourcehash3개갱신. 준비SQL --check와30엔진/497파일preflight통과. 병행완료1320의MAIN139 임베딩수정3파일보존, 선택포인터및Gold이전binding불변. 실제Oracle실행/DDL/GENOS실모델/현장배포는이번범위아님.',
'엑셀:기존R3의v2.3양식·3시트·각30개문항·질문/조건/예상결과·열/병합보존. I열적합여부/J열비고만실제관찰과미실행으로구분하고행높이조정. 반복시나리오1개를실제시험했고59개개별문항은미실행입니다. 같은문장16번은관찰참고만남겨중복통과집계하지않았습니다. 최종실모델통과기재0.',
'실패기록보존:1319의최종원문전용·UNKNOWN·누락된지침,1321의123통과/1실패를수정하지않았습니다.1322에서enum분기진단을보완해124/0과범위51/0을확인했습니다. 첫빌드의전체PLANS동일검사는행번호metadata8변경때문에실패했으며실행SQL/AST동일성으로구분하여원본보존했습니다. 실제대화runtime2개와합성검사runtime7개는전파일SHA확인후무손실보관했습니다.']
(OUT/'최종_수정과_검증결과.txt').write_text('\n\n'.join(texts)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'parent_contracts_passed':123,'parent_contracts_failed':1,'new_models':0},'integrated':summary},comparisons=[{'metric':'same124contractset','baseline':{'passed':123,'failed':1},'integrated':{'passed':124,'failed':0},'added_scope_contracts':51}],judge_disagreements=0,usage={'physical_calls':0},latency={'contracts_seconds':a['seconds'],'scope_seconds':b['seconds'],'working_recheck_seconds':w['seconds']},error_taxonomy=[]);put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[texts[0],texts[1]+'\n\n'+texts[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False), '완료1321/integrated를부모로새ADR. 원응답/검증실패를고정하고const/enum유일분기진단만보완.124계약과51모드검사후작업코드통합.', '525파일rev001동결. 부모1319공개원응답14/15와기본profile·합성fixture. 기준답변/평가모델0.제품입력과채점분리.',json.dumps(summary,ensure_ascii=False),texts[10],f'새모델0/비용0. 합성계약{a["seconds"]:.3f}초/범위{b["seconds"]:.3f}초/작업재확인{w["seconds"]:.3f}초. 실제법률corpus조회없음. 단계원장N/A 사유manifest참조.',texts[3]+'\n\n'+texts[4],texts[5]+'\n\n'+texts[6]+'\n\n'+texts[9],texts[8]+'\n\n원복은 artifacts/working-before의38파일을해시확인후파일별복구. MAIN139는이작업으로옮기지않음. 새QA/현장승인은별도.', '06_TOOLS/EXPERIMENTS/adr_1322/setup→freeze→check(124/51)→integrate→check working-api→working native --check→workbooks→archive_contracts→finish→hash/status/validate --final/graph. 이전외부UNKNOWN요청재전송금지.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 멀티턴 수정 작업코드 통합\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
headers=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 contents=['run-001 / integrated / exact. baseline완료1321의실패보존; 새모델0.',json.dumps(next(c for c in read(DES/'cases.json') if c['id']==q['case_id']),ensure_ascii=False),'법률기준답변없음. 정확한진단위치·원문범위·중복방지·해시결속을검사.','### 회수·탈락 단계 원장 — run·arm별\n\n실제회수실행없음. 합성API·과거원응답의계약검증이므로stage_ledger not_applicable; 기존실제corpus원장은1319에보존.','제품/외부모델0. 과거원응답은1319canonical014/015. 현검사원본 contracts-final/result.json,scope-modes/result.json,working-api/result.json 및복원가능runtime보관.','새중간LLM0. 과거실모델결과를현재통과로변환하지않음.','채점LLM0. 동일124계약123/1→124/0, 추가범위51/0. 작업4재검사는중복.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headers,contents),1))+'\n')
(ADR/'실험/README.md').write_text('# 최종 구조검증3종\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1322','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen merged code, validation, selective working integration and lossless runtime receipts','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts and 'runtime' not in p.parts]})
print('Final175 unique contracts +4 overlapping working checks;38 files integrated; MAIN139unchanged; no new live model')
