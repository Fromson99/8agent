"""Record the observed one-shot timeout and independently validated need-loss path."""
from common import *
import re,sqlite3
f=read(DES/'freeze-live.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))  # Offline ledger helper excluded from serving snapshot.
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
P=ART/'live/cm-009';b=read(DES/'baseline.json');m=read(ADR/'실험/manifest.json')
d=read(P/'diagnosis.json');a=read(P/'audit.json');s=read(P/'need-scope-audit.json');u=read(P/'uncommitted-need-audit.json');integrity=read(ART/'post-run-integrity.json')
assert d['http_status']==504 and d['calls']==4 and d['unknown_attempts']==1
assert all(integrity['checks'][k] for k in ('candidate_files_unchanged','frozen_inputs_unchanged','frozen_scripts_unchanged','own_working_products_unchanged'))
assert all(x['independent_progress_contract_valid'] for x in u['navigation_proposals'])
content={'case_id':'cm-009','full_case_passed':False,'answer_content_graded':False,'legal_accuracy':None,
 'direct_end':'Final ASSESS physical call4: HTTP200 header then60 whitespace chunks/660 bytes; absolute deadline179.879seconds; UNKNOWN and API504; no final model output or answer.',
 'earlier_navigation_failure':'Both FOLLOW_CONNECTION proposals reference a new judgment absent from their submitted review; READ_ACTION_JUDGMENT_REFERENCE repeated after one correction; MODEL_DECISION_UNRESOLVED handoff.',
 'implementation_gap':'The same material_need appears in both rejected navigation replies and independently passes progress validation. Recording is downstream of whole-action validation, so this valid need never enters the ledger or final canonical/wire input.',
 'selected_target_continuity':'Three acquired source-goal GN IDs and need-continuity prompt/schema reached final input. No material MN IDs committed; this is not evidence that all model-declared needs survive.',
 'change_review':'No prior accepted positive judgment/purpose exists here. Conditional-required branch and ROLE_ONLY outcome are not exercised. No final model output was received.',
 'reference_scope':'31 ma blocks407-409 and ba410-414 were neither selected/acquired nor delivered; source13 reference sentence was delivered. No server sibling expansion event.',
 'semantic_limits':'No inference that definitions are absent from corpus; no final COVERED/gaps=[] output exists in this run; no meaning reversal or final omission judgment can be attributed to the unreturned ASSESS.',
 'new_model_calls_during_review':0,'quality_certified':False}
put(P/'content-review.json',content)
checks={'frozen_execution_integrity':all(v for k,v in integrity['checks'].items() if k!='active_main_pointer_unchanged'),
 'source_bytes_acl':not a['source_mismatches'] and not a['acl_violations'] and not s['flat_mismatches'] and not s['flat_acl_violations'],
 'physical_budget':a['physical_budget_matches'],'resources':not d['resource_stop'],
 'all_declared_need_text_reaches_final':u['declared_need_text_in_final_wire'],
 'required_subclauses_acquired':s['required_source_complete'],'required_subclauses_delivered':s['required_final_delivery_complete'],
 'known_complete_transport':d['unknown_attempts']==0,'final_answer_stored':False,
 'frozen_active_pointer_unchanged':integrity['checks']['active_main_pointer_unchanged']}
gate={'passed':False,'checks':checks,'failed':[k for k,v in checks.items() if not v],
 'not_exercised':['accepted-material-need final resolution','conditional change_review/ROLE_ONLY output','final answer content'],
 'environment_drift':'Another reserved task ADR1204 selected MAIN118 during this isolated run. Frozen candidate471 files and explicit API binding stayed identical; no activation command in this task.',
 'quality_certified':False,'new_model_calls':0}
put(P/'gate.json',gate)
nav=sqlite3.connect((ROOT/b['release']['data_path']/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
scope=set(read(DES/'corpus.json')['document_ids']);source={};corpus=set()
for sid,raw in nav.execute('select id,json from source'):
 x=json.loads(raw);c=x.get('article_coordinate') or {};did=c.get('doc_id',x.get('document_id'));node=c.get('node',x.get('unit_id'))
 if did in scope and str(node).isdigit():source[sid]=(did,int(node));corpus.add(source[sid])
nav.close();reads={source[sid] for sid in a['read_source_ids'] if sid in source};seen=set(reads);cites=set()
for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(p)['view']
 for x in v.get('read_candidates',[]):
  for n in reversed(x.get('path',[])):
   if n.get('level')=='조' and str(n.get('unit_id','')).isdigit() and x.get('document_id'):seen.add((x['document_id'],int(n['unit_id'])));break
 def walk(x):
  if isinstance(x,dict):
   if x.get('source_id') in source and x.get('text'):seen.add(source[x['source_id']])
   for y in x.values():walk(y)
  elif isinstance(x,list):
   for y in x:walk(y)
 walk(v)
def coords(xs):return [{'doc_id':d,'node':n} for d,n in sorted(xs)]
ref=read(ART/'evaluation-only/cases.json')[0];gold=[{'doc_id':x['doc_id'],'node':int(x['node'])} for x in ref['targets']]
rec=StageLedgerRecorder('cm-009','bound',identity_canonicalizer)
for sid,kind,parents,values,discard in [('delivered_or_read','source',[],seen,[]),('original_read','select',['delivered_or_read'],reads,seen-reads),('final_cited','present',['original_read'],cites,reads-cites)]:
 rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Observed but no acquired root evidence' if kind=='select' else 'Final ASSESS timed out; no published answer/citation'} for x in coords(discard)])
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1205',m['experiment_id'],[build_run_artifact('run-001',[grade_capture(rec.capture(),gold)],{'bound':['delivered_or_read','original_read','final_cited']})]))
result={'status':'complete','candidate_revision':f['candidate_revision'],'serving_files':len(f['files']),
 'cases':[{'case_id':'cm-009','executed':True,'gate':gate,'diagnosis':d,'content_review':content}],
 'physical_calls':d['calls'],'usage':d['usage'],'question_gate_passed':0,'executed_cases':1,'answer_content_graded_count':0,'legal_accuracy':None,'quality_certified':False,
 'product_changes_this_experiment':False,'main_promotion_this_task':False,'active_main_after':integrity['pointer_after']['generation'],
 'parallel_main_promotion':integrity['pointer_after'],'genos_deployed':False,'automatic_retry':False,
 'stronger_model_comparison':False,'new_model_calls_during_audit':0,
 'retrieval_root_counts':{'observed':len(seen),'read':len(reads),'published':0,'corpus':len(corpus)},
 'source_integrity_checks':{'acquired':a['span_checks'],'nested_input':a['delivered_span_checks'],'flat_assess_input':s['flat_final_evidence_checks'],'note':'Occurrences; not unique spans or legal-answer quality.'}}
put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'bound':{'status':'complete','live_gate_passed':False,'full_case_passed':0,'cases':1,'answer_content_graded':0,'quality_certified':False}},comparisons=[],judge_disagreements=[],
 usage={'physical_requests':d['calls'],'offline_evaluator_requests':0,**d['usage']},
 latency={'case_seconds':[d['seconds']],'p50_seconds':d['seconds'],'p95_seconds':None,'not_measured_reason':'One known case, with incomplete final call; no stable p95 or causal comparison.'},
 error_taxonomy=['other: model_absolute_deadline_whitespace_unknown','other: repeated_read_action_judgment_reference','required_issue_omission: rejected_proposal_need_not_carried','other: concurrent_main_pointer_change'])
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(seen),after_filter=0,presented_total=0,presented_mean=0,presented_p50=0,presented_p95=0,golden_recall=0,selectivity=0,
 metric_scope_note='Observed candidate/read roots, not all search candidates. Root acquisition does not certify subclause completeness. Final answer absent, published roots0; ma/ba bodies0/8.')
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
texts=['run-001/bound/cm-009. 격리 native API 실제1회. 원시 기록 exact, 추가 재시험0.',ref['question'],ref['reference_answer']+'\n\n평가 전용; 제품 입력 비공개. 현행성 새 인증 없음.',
 '[동결 코드](../artifacts/design/freeze-live.json) · [실제 요청](../artifacts/live/cm-009/request.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[조문root 원장](../artifacts/run-001/retrieval-ledger.json) · [필요·범위 감사](../artifacts/live/cm-009/need-scope-audit.json) · [거절된 필요 감사와 집계 해석 정정](../artifacts/live/cm-009/uncommitted-need-audit.json).',
 '[호출](../artifacts/live/cm-009/calls.json). raw/call-001~004/request.json.gz에 전체 요청 저장.001~003/response.json.gz는 원응답,004/partial-response.json.gz는 기한 종료 전 전체 수신660바이트.004 정상 응답은 없음.',
 '[단계](../artifacts/live/cm-009/generations.json). canonical/001~004.json.gz 전체 서버 입력/스키마,001~003-output.json.gz 구조 응답,004-summary.json 실패. 조사 보완1, 감독0, 최종 보완0, 별도 검토AI0.',
 '추가 채점 모델0. 종료 후 저장 원문/전송/코드 대조 및 answer_progress 독립 검증2회. 결과를 바꾸는 재실행 없음.',
 '실행 기준0/1·최종 답변0·내용 채점 불가. HTTP504/FAILED. 원문 목표3ID 전달, 거절된 응답의 유효한 필요 문장은 최종 입력에서 유실. change_review 조건부 필수 사례는 이번에 미도달.']
q=m['questions'][0];qp=ADR/'실험'/q['file'];qp.write_text('# CM009 필요 연결 계약 실제 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(qp)
put(ADR/'실험/manifest.json',m)
sections=[
 ('결정 요약','실제9번1회는294.097초·물리4·HTTP504/FAILED·최종답변0으로 미통과다. 최종 ASSESS가 HTTP200헤더 뒤 공백660바이트만 보내179.879초 절대기한에 종료했다. 그 이전에 거절된 조사 응답의 유효한 필요 문장이 최종 입력에서 유실되는 구현 공백도 확인했다. 이번 probe는 Rejected이며 추가 제품 수정/재시험/승격은 없다.'),
 ('문제와 변경 전 구조','1203은 조사 필요와 최종 needs 연결 부족 및 NOT_USED의 change_review 누락으로 실패했다. 후속 일반 구현은 material_need ID 누적, 원문 목표/범위·claim/gap 연결, 조건부 스키마와 ROLE_ONLY, 참조 자동 확장 제거를 작업 코드에 넣고 고정 사본169계약을 통과했다. 이번은 그 정확한 사본의 실제 모델1회다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 선언 필요가 최종까지 유지되고 명시 해결/제외/미해결에 결속되며, 참조 범위는 모델이 선택한다. 형식과 원문·권한·물리예산·내용 검사를 분리한다. 필요한31조 마목/바목 본문과 실제 최종 답변까지 확인해야 전체 통과다. 알려진 사례의 단일 인샘플로 속도·품질 인과효과를 주장하지 않는다.'),
 ('실험 설계','ADR1203/bound 완료 arm을 부모로, 일반 구현의 검증 사본471파일을1205/bound rev001로 snapshot/freeze했다. 작업의 병행 온톨로지 파일을 가져오지 않았다. native /v1/rag/ask에 frozen app와 실제 serving transport를 명시 주입했다. 제품 입력에 평가답·필요 조문 목록은 넣지 않았다. 동일 코드169검사 영수증을 상속하고 실행 전 핀/권한/자원 검사를 통과했다.'),
 ('데이터·모델·재현성','동일 CM009·65문서·latest-selection-20261015-r1 데이터. Qwen3.8 qwen/qwen3.8-27b, Parasail FP8 기본, 확정429만 NearAI1회 전환 정책을 유지했다. 이번 실제는 Parasail4회·전환0이다.40물리/1024도구/1800초·개별180초·출력상한없음·온톨로지OFF. frozen471파일·입력·실행기·작업 제품7파일 불일치0. 실행 중 별도ADR1204가07:51:22 UTC에 MAIN117→118(source-accordion)을 선택했다. 이는 동결 기준의 포인터불변 항목 실패로 보존하며 실험이 고정 snapshot에서 계속 실행된 사실과 구분한다.'),
 ('결과','정상 모델3응답 후 마지막 ASSESS는 UNKNOWN. 최종 보완/답변/내용채점0, 감독0. source_goal3개의 GN ID·원문·필요 연결 지시문·스키마는 실제 최종 입력에 전달됐다. 그러나 material_need MN은0개이며 거절 응답에 있던 필요 문장이 canonical와 wire 양쪽 모두에 없다. 마목407~409·바목410~414는0/8확보·전달,13조의 참조 문구만 전달됐다. 모델이31조를 별도 목표로 선언하지 않았고 자동 형제 참조 이벤트0이다.'),
 ('사례별 오류 분석','① 조사 판단: FOLLOW_CONNECTION의 judgment_refs에 같은 응답 new_reviews로 제출하지 않은 새 J번호를 최초·보완 모두 사용했다. READ_ACTION_JUDGMENT_REFERENCE 거절 뒤 MODEL_DECISION_UNRESOLVED로 최종 인계했다.\n\n② 필요 저장 공백: 두 조사 응답은 대형법인·적격 해외증권시장 정의가 더 필요하다고 썼다. 해당 answer_progress 부분은 사후 독립 계약 검증2/2통과다. 그러나 law_navigation의 전체 행동 검증 실패가 supervisor.before_execute보다 앞서므로 need_continuity.record에 도달하지 않았다. 유효한 필요 선언까지 기록되지 않아 최종 goals=[]·material needs0이 됐다. 잘못된 행동/판단을 채택하지 않으면서 독립 검증한 필요만 미해결로 보존할 경로가 남았다.\n\n③ 직접 종료: ASSESS는 HTTP200헤더/60조각/660바이트 공백만 수신해179.879초 종료, worker회수. 최종 출력 자체가 없으므로 이번에 COVERED/gaps=[]로 바뀌었다거나 서버가 최종답변을 누락했다고 단정하지 않는다. 원격 원인·취소 확인·미완료 비용은 미확인이다.\n\n④ change_review: 현재 최종 heads는모두DEFER·review_purposes0. 필드는 전달됐지만 조건부 필수 분기와ROLE_ONLY 결과는 미검증이다. 앞선169합성 검사와 이번 실모델 효과를 구분한다.'),
 ('비용·지연·회수 규모',f"전체{d['seconds']:.3f}초=모델{d['model_seconds']:.3f}초+기타{d['other_seconds']:.3f}초. 물리4=차감4·도구23. 보고 입력{d['usage']['input_tokens']}·출력{d['usage']['output_tokens']}토큰·비용{d['usage']['known_response_cost_usd']:.8f}달러, 마지막UNKNOWN 사용량/비용미확인. 원문{a['span_checks']}·중첩입력{a['delivered_span_checks']}·평면최종{s['flat_final_evidence_checks']}구간 대조 불일치/권한위반0. 최소가용RAM{d['min_available_gib']:.3f}GiB·최대worker RSS약3.242GiB·스왑증가0·자원중단0·통신프로세스회수. 조문root 관측{len(seen)}→확보{len(reads)}→최종인용0; 전체corpus{len(corpus)}. root집계와 필요한하위8블록 확보는 별도다."),
 ('해석','169개 단위/합성 API 검사는 승인된 필요의 누적과 최종 계약을 검증했지만, 행동 계약에 실패한 응답 안의 유효한 필요를 보존하는 경로는 구현하지 못했다. 이것이 이번에 추가로 드러난 제품 공백이다. 최종 모델 통신 미완료와 이 공백의 인과관계는 입증하지 않았다. 사후 need-scope-audit의 declared_need_input_continuity=true는 누적MN0개에 대한 공집합 검사였다. 원본을 보존하고 uncommitted-need-audit에서 NOT_EXERCISED로 해석 정정했으며 통과 근거로 쓰지 않는다.'),
 ('한계와 일반화 가능 범위','알려진9번1회, 정상 최종출력0으로 법률 정확도는 미채점이다. 이번 결과를 공급자 일반 성능이나 개선율로 확대하지 않는다. 정의의 corpus부재를 단정하지 않는다. 준비 메타 검사에서 회수 집계 null9항목이 거절되어 호출 전 명시적인 측정대기 값으로 정정했다. 원본 실패를 보존했고 최종에는 실제원장 집계로 치환했다. 병행 MAIN118 선택은 이 작업의승격이 아니며 frozen코드471파일에는 영향이 없었다.'),
 ('운영 결정·롤백 조건','이번 작업의 제품 수정·MAIN승격·GENOS배포·Git·메일·자동재시험0. 다른 작업이 선택한 MAIN118을 되돌리지 않았다. 후속 수정 대상은 전체 행동 거절과 독립적으로 검증 가능한 필요 선언의 영속화 및 최종 인계다. 실제 의미/근거가 틀린 판단이나 실행 행동을 자동 채택하는 복구로 확대하면 안 된다. 재실험은 새로운 승인범위/ADR에서 수행한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1205/setup.py가 고정 사본을 준비했다. timeout1860초 아래 live.py cm-009를1회 실행했으며 dispatch가 있으면 재실행을 거절한다. audit_result.py cm-009, audit_storage.py cm-009, composition_audit.py cm-009, inspect_run.py는 읽기전용 사후감사다. document.py는 결과/원장/문서를 작성한다. 완료 기록을 같은 경로로 재실행해 덮어쓰지 않는다. [전체 결과](artifacts/run-001/result.json) · [누락 경로](artifacts/live/cm-009/uncommitted-need-audit.json) · [기한 수신 기록](artifacts/live/cm-009/raw/call-004/finished.json) · [실행 결속](artifacts/post-run-integrity.json).')]
meta=(ADR/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Rejected',meta)
(ADR/'README.md').write_text('---'+meta+'---\n\n# 선언 필요 연결 계약 실제 CM009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제009 한 번 실행\n\n[질문·입력·출력·판정](질문-001-cm-009.md) · [최종 결과](../artifacts/run-001/result.json). HTTP504·전체미통과·최종답변0·자동재시험0.\n')
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-need-continuity-live';O.mkdir(exist_ok=True)
(O/'실험결과.txt').write_text('선언한 필요 연결 계약 실제009 결과\n\n'+'\n\n'.join(h+'\n'+v for h,v in sections)+'\n')
put(O/'observations.json',{'result':result,'integrity':integrity,'need_loss_audit':str((P/'uncommitted-need-audit.json').relative_to(ROOT))})
print('Recorded one case: HTTP504,4physical,valid rejected need lost, no final answer; candidate unchanged, concurrent MAIN118 preserved.')
