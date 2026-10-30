"""Finalize the one-shot actual009 record without changing measured code or results."""
from common import *
import re,sqlite3,statistics
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
P=ART/'live/cm-009';f=read(DES/'freeze-live.json');b=read(DES/'baseline.json');m=read(ADR/'실험/manifest.json')
d=read(P/'diagnosis.json');a=read(P/'audit.json');s=read(P/'exact-scope-audit.json');integrity=read(ART/'post-run-integrity.json')
assert all(integrity['checks'].values()) and d['calls']==11 and d['http_status']==422
content={'case_id':'cm-009','passed':False,'failure_type':'required_reference_not_declared_and_final_change_record_omitted',
 'required_source_acquisition':False,'required_final_input_delivery':False,'final_answer_delivered':False,
 'source13_reference_text_delivered':all(x['source13_original_reference_delivered'] for x in s['final_inputs']),
 'large_corporation_definition':'This run acquired KOSDAQ article2 and sent its definition to both ASSESS calls; both drafts include the two thresholds. The prior missing-definition gap did not recur.',
 'reference_gap':'Both final drafts name article31 ma/ba exclusions but do not acquire or explain their qualification bodies. Both bodies remain absent from final input.',
 'use_change':'Both drafts omit change_review on two NOT_USED rows despite schema, instructions, current purpose IDs and repair feedback being physically delivered.',
 'semantic_caution':'The earlier SUPPORT findings already say the relevant definition/exemption is absent from these portions. Thus SUPPORT to NOT_USED is a use/disposition change; a substantive change in legal interpretation is not demonstrated for these two rows. Valid exclusion must remain possible.',
 'gap_recovery':'Drafts have gaps=[] and SATISFIED; no REQUIREMENT_GAPS_RECONCILED event. This does not exercise the material-gap recovery fix.',
 'reviewer':'No advisory reviewer used; stopped before accepted ASSESS/answer assembly.',
 'legal_accuracy':None,'new_model_calls':0,'quality_certified':False}
put(P/'content-review.json',content)
checks={'same_frozen_code':all(integrity['checks'].values()),'source_integrity':not a['source_mismatches'] and not s['flat_mismatches'],
 'acl':not a['acl_violations'] and not s['flat_acl_violations'],'physical_budget':a['physical_budget_matches'],
 'known_transport':d['unknown_attempts']==0 and d['all_workers_reaped'],'resources':not d['resource_stop'],
 'required_subclause_acquired':s['required_source_complete'],'required_subclause_final_input':s['required_final_delivery_complete'],
 'final_judgment_accepted':False,'final_answer_stored':False,'content_passed':False}
gate={'passed':all(checks.values()),'checks':checks,'failed':[k for k,v in checks.items() if not v],'quality_certified':False,'new_model_calls':0}
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
 rec.record_stage(sid,kind,coords(values),parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Observed but no acquired root evidence' if kind=='select' else 'Final ASSESS failed; no published answer/citation'} for x in coords(discard)])
put(RUN/'retrieval-ledger.json',build_experiment_artifact('ADR-1203',m['experiment_id'],[build_run_artifact('run-001',[grade_capture(rec.capture(),gold)],{'bound':['delivered_or_read','original_read','final_cited']})]))
result={'status':'complete','candidate_revision':f['candidate_revision'],'serving_files':len(f['files']),'cases':[{'case_id':'cm-009','executed':True,'gate':gate,'diagnosis':d,'content_review':content}],
 'physical_calls':d['calls'],'usage':d['usage'],'question_gate_passed':0,'executed_cases':1,'quality_certified':False,'legal_accuracy':None,
 'active_main_unchanged':'MAIN117/accepted-answer-20261029-r1','product_changes':False,'main_promotion':False,'genos_deployed':False,
 'stronger_model_comparison':False,'new_model_calls_during_audit':0,'retrieval_root_counts':{'observed':len(seen),'read':len(reads),'published':0},
 'source_integrity_checks':{'acquired':a['span_checks'],'nested_input':a['delivered_span_checks'],'flat_assess_input':s['flat_final_evidence_checks'],'note':'Occurrences, not distinct unique source spans.'}}
put(RUN/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'bound':{'status':'complete','live_gate_passed':False,'quality_certified':False}},comparisons=[],judge_disagreements=[],
 usage={'physical_requests':d['calls'],'offline_evaluator_requests':0,**d['usage']},
 latency={'case_seconds':[d['seconds']],'p50_seconds':d['seconds'],'p95_seconds':None,'not_measured_reason':'Single known case; no stable p95 or causal speed comparison.'},
 error_taxonomy=['other: required_reference_not_declared','other: final_change_record_omitted','other: audit_helper_import_and_argument_errors'])
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(seen),after_filter=0,presented_total=0,presented_mean=0,presented_p50=0,presented_p95=0,golden_recall=0,selectivity=0,
 metric_scope_note='Observed candidate/read roots are not entire search universe. Root gold read1/2 and published0/2 do not certify subclause bodies. Exact ma3+ba5 blocks all absent; see exact-scope-audit.json.')
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
texts=['run-001 / bound / cm-009. 실제 native API 1회. 원시기록 source=exact; 추가 재시험0.',ref['question'],ref['reference_answer']+'\n\n평가 전용; 제품 입력에는 제공하지 않음. 기준일2026-08-27/문서 시행2026-08-03, 현재 법률 효력 인증 아님.',
 '[동결 코드](../artifacts/design/freeze-live.json) · [실제 요청](../artifacts/live/cm-009/request.json) · [권한](../artifacts/design/corpus.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[조문root 원장](../artifacts/run-001/retrieval-ledger.json) · [필요 하위범위](../artifacts/live/cm-009/exact-scope-audit.json). 조문ID와 본문 확보를 구분한다.',
 '[물리 호출](../artifacts/live/cm-009/calls.json). raw/call-001~011/request.json.gz,response.json.gz에 실제 전체 요청·응답 보존. canonical/001~010.json.gz와 *-output.json.gz는 서버 검증 전후 식별자 복원 입력·응답.',
 '[단계별 호출](../artifacts/live/cm-009/generations.json). 요청 진입 보완1·최종 ASSESS 보완1 포함, 별도 최종 검토AI0.',
 '오프라인 원문·실제 전송·현재 코드 대조. 채점 모델0·동일 사례 자동 재시험0. 알려진 사례1회의 탐색 실험이며 모델·공급자 품질 비교 아님.',
 json.dumps(gate,ensure_ascii=False,indent=2)+'\n\nHTTP422/FAILED·최종답변0. 마목·바목8블록 모두 미확보/미전달. 판단 변경 기록 누락을 보완하지 못했다.']
q=m['questions'][0];qp=ADR/'실험'/q['file'];qp.write_text('# CM009 실제 시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n');q['sha256']=sha(qp)
put(ADR/'실험/manifest.json',m)
summary='수정본으로 실제9번을1회 실행했으나 미통과했다. 196.368초·물리11회·도구38회 뒤 HTTP422/FAILED로 종료됐다. 이번에는31조 목표 자체가 없어 마목3블록·바목5블록 모두 미확보/최종 미전달이었다. 최종 최초·보완 모두2개 NOT_USED 판단의 change_review를 생략하여 새 검증기가 거절했다. 대형법인 정의는 이번에 확보·최종 입력/초안 반영했다. 최종답변0, MAIN117과 작업 제품 유지.'
sections=[
 ('결정 요약',summary+' 실제 답변 완료 가설은 지지되지 않아 이번 probe는 Rejected로 기록한다. 이전1202의 기술검사 통과나 작업통합 기록을 소급 변경하지 않는다.'),
 ('문제와 변경 전 구조','이전1201 실제009는31조 마목만 목표로 선언하고 정의 탐색 목적을 붙였다. 마목과 상위6블록만 읽었고 바목5블록은 미확보였다. 최종에서는 정의가 아니라며 NOT_USED로 바꿨고 별도 material gap/SATISFIED 모순으로422가 났다.1202는 명시 목표를 출발점으로 참조 묶음을 확장하고 목적별 판단 변경 기록과 gap 연결을 검증했다. 이번은 그 정확한 수정본의 실제 전체 요청 시험이다.'),
 ('가설과 사전 판정 기준','[사전 동결 기준](artifacts/design/criteria.json). 같은65문서·데이터·모델·예산으로 실제9번1회. 마목·바목의 정확한 본문과13조 상위 문맥을 확보/최종 전달하고, 판단 변경을 원래 목적·근거에 연결하며, 핵심 미확인을 보존해 정상 답변 또는 기존 조사/제한 경로를 수행해야 한다. 정확 원문·권한·물리 차감·동일 코드 검증을 유지한다. 조문ID 존재만으로 본문 확보 통과를 선언하지 않는다. 같은 실패 시 자동 재시험하지 않는다.'),
 ('실험 설계','직접 부모1202/bound rev004와 바이트 동일한468파일을1203/bound rev001에 동결했다. 격리 native API에 실제 LocalQwen38Transport를 연결했다. 최종 원문 대조 advisory AI1201은 비활성. 추가 제품 변경이나 MAIN 교체 없이 실제1회 요청과 사후 읽기 전용 감사를 수행했다.'),
 ('데이터·모델·재현성','MAIN117의 동일65문서 권한과 latest-selection-20261015-r1 데이터. 모델 qwen/qwen3.8-27b, Parasail FP8 기본·확정429만 NearAI FP8 한 번 전환.40물리/1024도구/1800초·개별180초·출력상한없음·온톨로지OFF·자원기준 유지. 기준답변/31조필요범위는 평가 전용 파일에만 있고 제품에 전달하지 않았다. 사전 검사와 실행 후468파일·입력·실행기·작업468파일·MAIN포인터 해시 동일. 법령 현행성은 새로 검증하지 않았다.'),
 ('결과','사전 동일 코드/부모141검사 영수증과 실행 준비 검증 통과 후 실제1회 실행했다. Parasail 첫 요청429→NearAI 정상10응답. 실제 HTTP422·실행/요청FAILED, 최종답변0·COMPOSE모델0·새검토AI0. UNKNOWN/만료/자원중단0. 마목407~409·바목410~414 전체8블록은 미확보·최종 최초/보완 입력에서도 미전달.13조의 참조 문장 자체는 두 입력에 전달됐다. 대형법인 정의는 코스닥2조에서 읽고 두 초안의 조건에 수치·시점과 함께 반영했다.'),
 ('사례별 오류 분석','① 참조 목표 누락: 최종 목표는 코스닥13조·유가13조·유가세칙9조3개뿐이다. reference_bundles.expand는 기존 목표와 같은 참조 좌표가 현재 원문에 있어야 시작한다. 이번 모델은31조를 목표로 안 올렸으므로 마목·바목 묶음도 활성화되지 않았다. 관측 묶음 이벤트3개는 기존13/13/9 자체 표제 결속이며 새31조 확보 효과가 아니다.\n\n② 최종 변경 기록 누락: 유가2조와 유가세칙9조를 SUPPORT에서 NOT_USED로 처리하면서 필수 change_review를 최초·보완 모두 생략했다. 실제 두 요청에 새 지시문·스키마·이전판단/목적이 있었고 보완에는 오류 경로·목적ID도 전달됐다. FINAL_REVIEW_PURPOSE_CHANGE 두 건을 다시 거절해 ASSESS에서 종료했다. 이 두 이전 finding은 이미 해당 정의/면제 규정이 아니라는 내용이므로 실제 의미 반전이 있었다고 단정할 수 없다. 사용 분류 변경과 의미 변경을 구분해야 한다. 정상 제외를 가능하게 유지하면서 출력 조건과 보완을 더 구체화할 필요가 있다.\n\n③ 이번 초안은 gaps=[]/SATISFIED여서 이전 gap 연결 모순 복구는 발동하지 않았다. 복구 효과 통과로 확대하지 않는다. 감독 CONTINUE_TARGETED+다른행동 거절1회도 남았으나 이후 조사가 계속됐으므로 직접 종료원인은 아니다.'),
 ('비용·지연·회수 규모',f"전체{d['seconds']:.3f}초=모델{d['model_seconds']:.3f}초+기타{d['other_seconds']:.3f}초. 물리11=예산차감11·도구38. 보고 입력{d['usage']['input_tokens']}·출력{d['usage']['output_tokens']}토큰·비용{d['usage']['known_response_cost_usd']:.9f}달러;429사용량미보고. 원문317·중첩입력775·평면최종입력306구간 대조 불일치/권한위반0(구간 출현 횟수). 최소가용RAM{d['min_available_gib']:.3f}GiB·스왑증가0·통신프로세스전부회수. 조문root 관측{len(seen)}→확보{len(reads)}→최종인용0. gold root 확보1/2·인용0/2, 실제 필요31조하위8블록은0/8. p95/속도 개선율/공급자 인과효과는 산출하지 않는다."),
 ('해석','현재 수정은 모델이 참조 중 하나라도 목표로 지정한 경우의 누락을 막지만, 필요한 참조를 전혀 목표로 올리지 않는 경우에는 부족하다. 질문에 채택된 원문의 적용조건·예외가 의존하는 참조를 서버가 목표로 연결하는 경로가 필요하며, 표제의 자기참조·관련 없는 인용·무제한 연쇄 확장은 구분해야 한다. 변경 검증은 부실 출력을 차단했지만 정상적인 미사용 설명도 안정적으로 제출하지 못해 사용자 답변까지 막았다. 이번 결과로 의미 오류 탐지율 개선을 주장하지 않는다.'),
 ('한계와 일반화 가능 범위','알려진9번1회뿐이며007 재실행·모델비교·GENOS시험은 없다.1201과 조사 경로와 입력 자체가 달라져 단순 속도/품질 개선 비교는 성립하지 않는다. 대형법인 정의가 corpus에 없다는 과거 추측은 하지 않으며 이번에는 실제 확보했다. 사후 감사의 reader import 누락, composition helper 인자 누락, 임시 상태 경로 착오를 보존하고 읽기 전용 감사에서 정정했다. 동결 실행기나 제품은 고치지 않았고 새 모델 호출0이다.'),
 ('운영 결정·롤백 조건','MAIN117·작업제품·GENOS 유지. 이번에 추가 운영 반영 없음. 같은9번 자동 재시험·후속 질문·Git·메일 없음. 후속 수정 대상은 모델 미선언 참조 목표 연결과 실제 출력에 맞는 목적별 변경/정상 제외 보완이다. 기존 실패/보완 응답을 저장 재생해 먼저 검증해야 하며 법률 조건이나 실패 검증을 느슨하게 만들어 통과시키지 않는다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1203/setup.py 및 live.py cm-009가 동결·실제 실행을 수행했다. live.py는 기존 dispatch 존재 시 반복을 거절한다. audit_v2.py는 사후 호환 리더로 원문/물리차감을 확인했고 audit_exact.py는 실제본문 범위·실제전송·거절·코드무결성을 대조했다. composition_audit.py cm-009는 최종조립 미도달을 기록한다. document.py는 모델 호출 없이 원장/문서를 만든다. 출력은 append-only이므로 동일 경로를 덮어쓰는 재실행은 하지 않는다. [결과](artifacts/run-001/result.json) · [범위](artifacts/live/cm-009/exact-scope-audit.json) · [실패](artifacts/live/cm-009/diagnosis.json) · [무결성](artifacts/post-run-integrity.json).')]
meta=(ADR/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Rejected',meta)
(ADR/'README.md').write_text('---'+meta+'---\n\n# 참조 묶음·판단 변경 수정본 실제 CM009\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제009 한 번 실행\n\n[질문별 원시 입력·출력·판정](질문-001-cm-009.md) · [최종 결과](../artifacts/run-001/result.json). 전체 미통과·최종답변0·자동 재시험0.\n')
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-reference-purpose-live';O.mkdir(exist_ok=True)
(O/'실험결과.txt').write_text('참조 묶음·판단 변경 수정본 실제009 결과\n\n'+'\n\n'.join(h+'\n'+v for h,v in sections)+'\n')
(O/'핵심결과.txt').write_text(summary+'\n')
put(O/'observations.json',{'result':result,'integrity':integrity,'scope_audit_path':str((P/'exact-scope-audit.json').relative_to(ROOT))})
print(summary)
