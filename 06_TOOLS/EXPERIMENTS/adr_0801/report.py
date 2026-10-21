from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0801-workflow-handoff-qualification';D=A/'artifacts/design';O=R/'04_EXPERIMENTS/ADR/ADR-0800-workflow-literal-request-quotes/artifacts/live'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');old=read(O.parent/'design/freeze.json');live=read(O/'result.json');response=read(O/'response.json')['body'];restart=read(O/'restart-check.json');consumer=read(A/'artifacts/candidate-consumer-v2.json');base=read(A/'artifacts/replay/baseline.json');candidate=read(A/'artifacts/replay/connected.json');baseline=read(D/'baseline.json')
checks={'all_278_native_api_and_boundary_contracts_pass':'278 passed' in (A/'artifacts/tests-final.txt').read_text(),
 'source_ui_four_checks_pass':read(A/'artifacts/ui-check.json')['status']=='PASS',
 'same_product_code_as_completed_parent':f['serving_files']==old['serving_files'],
 'frozen_code_unchanged':all(sha(R/n)==h for n,h in f['files'].items()),
 'actual_candidate_service_twelve_checks':all(consumer['checks'].values()) and len(consumer['checks'])==12,
 'same_recorded_claim_dependencies_preserved':candidate['selected']==read(O.parent/'replay/connected.json')['selected'] and len(candidate['selected'])==11,
 'bounded_replay_handoff':base['evidence_count']==94 and candidate['evidence_count']==16 and candidate['view_chars']==26301,
 'known_failure_published_as_partial':live['status']=='partial' and not response['report']['rows'] and response['quality_certified'] is False,
 'known_failure_duplicate_and_restart_preserved':all(live['checks'].values()) and all(restart['checks'].values()),
 'native_navigation_gateway_failure_code_unchanged':all(f['serving_files'][n]==baseline['manifest']['files'][n] for n in ('02_BACKEND/semantic_runtime/legal_agent/law_navigation.py','02_BACKEND/semantic_runtime/legal_agent/gateway.py','02_BACKEND/semantic_runtime/legal_agent/completion_v5.py')),
 'source_generation_unchanged':sha(R/read(D/'data-binding.json')['path']/'manifest.json')==read(D/'data-binding.json')['manifest_sha256'],
 'this_audit_no_external_calls':not (A/'artifacts/live').exists() and consumer['model_calls']==0}
limits=['Finite software boundary audit only, not statistical out-of-sample answer accuracy. All test scope was fixed before this audit. Known cases remain known; no holdout claim.',
 'ADR0800 actual Qwen observation: 7 calls, partial, zero comparison rows. Internal model repeated duplicate/missing exploration targets; external transport outcome unknown. No successful real-model comparison or legal-answer accuracy is claimed.',
 'Synthetic native API tests exercise full internal RAG, external RAG, BASIS, COMPARE and report; model replies are controlled fixtures. Real data service checks use no model. These checks verify wiring and safeguards, not Qwen judgment quality.',
 'Adopted spans are validated provenance, not certified correct legal conclusions. Required liquidity rules can still be missed. Unknown applicability/version and incomplete source closure stay deferred.',
 'Known quote-concatenation defect fixed: both real child request entries accepted exact question quotes in ADR0800. Long quotes retain all original coordinates within the existing quote size limit.',
 'GENOS not accessed or deployed; local MAIN and field adoption remain separate.',
 'Earlier ADR0797-0800 remain Rejected for their own fixed live-comparison criteria. This follow-up freezes a narrower software boundary decision before its checks; it does not regrade or replace those outcomes.']
by={'baseline':{'status':'complete','handoff':base},'connected':{'status':'complete','handoff':candidate,'contract_passed':278,'ui_checks':4,'actual_service_checks':12,'synthetic_native_comparison_passed':checks['all_278_native_api_and_boundary_contracts_pass'],'known_qwen_comparison_rows':0,'technical_integrity_qualified':all(checks.values())}}
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'by_arm':by,'qualification_scope':'Frozen finite software source/quote/state/actual API/failure/display audit, not actual model judgment success',
 'known_live_observation':{'path':str((O/'result.json').relative_to(R)),'sha256':sha(O/'result.json'),'status':live['status'],'model_calls':live['model_calls'],'comparison_rows':0,'in_sample':True},
 'usage':{'product_model_calls':0,'offline_evaluator_calls':0},'limitations':limits};put(A/'artifacts/run-001/result.json',result);assert result['strict_success'],checks
subprocess.run(['.venv/bin/python','06_TOOLS/EXPERIMENTS/adr_0801/ledger.py'],check=True,stdout=subprocess.DEVNULL)
p=A/'실험/질문-001-K01.md';s=p.read_text().replace('별도 실제 Qwen 호출6건 원문은 ../artifacts/live/raw.', '이번 감사의 외부 모델 호출0. 알려진 실패는 ADR0800 artifacts/live/raw와 result.json을 경로·해시로 참조한다.').replace('INTAKE1, 자식 진입/수정4, BASIS1. 실제 새 질문의 인용 오류로 자식 조사 실패.', '이번 감사는 제품 코드를 바꾸지 않고 전체 소프트웨어 경계278검사와 실제 로컬 서비스12검사를 수행한다. 통제된 모델 응답으로 양측 RAG→BASIS→COMPARE→표시를 확인한다.').replace('실제 실행은 자식 질문 인용 실패로 비교0행이므로 후보를 기각한다.', 'ADR0800 실제 Qwen은 내규 탐색 제안 오류/외규 전송 결과 미확인으로 비교0행이다. 이를 성공으로 바꾸지 않는다. 이번 결정은 동결한 소프트웨어 기능·오류 경계에 한정한다.');p.write_text(s)
m=read(A/'실험/manifest.json');m['questions'][0]['sha256']=sha(p);m['decision_eligible']=True;m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm=by,usage=result['usage'],latency={'external_model_seconds':0},error_taxonomy=['WRONG_SOURCE_HASH_SCOPE_STATE_REFUSED','INCOMPLETE_PAIR_DEFERRED','UNKNOWN_DELIVERY_NO_RESEND','FAILED_CALL_NOT_EVIDENCE','KNOWN_LIVE_COMPARISON_UNAVAILABLE']);put(A/'실험/manifest.json',m)
parts=[('결정 요약','Accepted promotion-candidate. 전달 최적화의 원문·상태·복구·비교 API·표시 기능을 소프트웨어 경계로 검증한다. 알려진 실제 Qwen 질의의 비교0행을 보존하며 답변 품질 성공으로 해석하지 않는다.'),
 ('문제와 변경 전 구조','MAIN73은 자식에서 읽은 전체94근거를 전달해 동일 기록 입력128976자로 한도를 넘었다. 채택된 claim span의 정규 ID와 현재 revision으로 전달·표시를 연결한다.'),
 ('가설과 사전 판정 기준','이번 코드 변경은 없다. 완료된 ADR0800의 동일336서빙 파일을 격리했다. design/criteria.json에 기능·실패·실제 API 경계로 한정한 기준과 알려진 실패를 검사 전에 동결했다. 기존 실험을 재채점하지 않는다.'),
 ('실험 설계','278계약에는 실제 native API의 양측 RAG→BASIS→COMPARE, 복구 성공/실패/한도/재개/중복/해시/권한/상태/표시 검사를 포함한다. 모델 답변은 통제된 fixture다. 실제 원문 세대에서는 서비스12검사를 모델 없이 수행한다.'),
 ('데이터·모델·재현성','MAIN73의 원문·최신 선택·정의 최초 검색·프로필·모델 정책을 유지한다. 이번 감사는 외부 모델0회다. ADR0800 Qwen3.8/Parasail FP8/reasoning none/no fallback 실제 기록을 경로와 해시로 참조한다.'),
 ('결과',json.dumps({'checks':checks,'contract_passed':278,'source_ui':4,'actual_service':12,'known_qwen_status':'partial','known_qwen_rows':0},ensure_ascii=False)),
 ('사례별 오류 분석','선택되지 않은 조사 원문은 자식 원장에 보존한다. 새 원문 ID는 정확 좌표·해시 검사를 통과해야 한다. 실패한 도구를 근거/부재로 인정하지 않는다. 원문 인용 선택은 생성 계약이며 잘못된 인용을 사후 절삭하는 보정이 아니다.'),
 ('비용·지연·회수 규모','같은 자식 기록 재생94→16근거,45088→1132원문자,128976→26301입력자. 채택 의존 조문11개를 모두 보존했다. 새 외부 모델0회. 지연·정답률 일반화 추정 없음.'),
 ('해석','검색을 임의 top-k로 자르지 않고 채택한 근거만 전달한다. 원문 문맥은 기존 열람 기록에서 우선 재사용한다. 기술 기능 승격과 LLM의 실제 질문 성공은 별도 상태다.'),
 ('한계와 일반화 가능 범위','\n\n'.join(limits)),
 ('운영 결정·롤백 조건','검증한 동일 코드를 작업 경로에 필요한 변경만 통합하고 로컬 MAIN에 승격한다. 실제 선택 포인터·파일 해시·서비스 binding을 확인한다. 이전 포인터/세대와 적용·원복 영수증을 유지한다. GENOS 반입은 별도다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0801의 run_tests/replay/ui_check/consumer_check candidate/report. live.py는 이 감사에서 실행하지 않는다. 완료 자료를 덮어쓰지 않는다. stable adr_structure validate --final/graph 및 rag_main_promotion prepare/apply --confirm-main.')]
meta=f"---\nadr_id: ADR-0801\ntitle: 대사 근거 전달 기능 경계와 로컬 MAIN 연결 감사\nstatus: Accepted\ndecision_date: 2026-10-15\nphase: audit\nin_sample: false\ndecision_eligible: true\nmain_wiring: promotion-candidate\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n');(A/'실험/README.md').write_text('# 대사 소프트웨어 경계 감사\n\n278계약·UI4·실제 서비스12. 실제 Qwen 성공이나 정답률은 미인증. [알려진 기록 재생](질문-001-K01.md).\n')
subprocess.run(['.venv/bin/python','06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(A),'--status','completed','--note','Frozen software integrity and consumer boundary qualified; no product delta and known actual Qwen failure explicitly retained'],check=True,stdout=subprocess.DEVNULL)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not any('runtime' in x for x in p.relative_to(A/'artifacts').parts)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0801','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Finite software boundary evidence; external observation explicitly unsuccessful','contains_raw_prompts_and_outputs':False} for p in files]})
print('PASS finite software checks',len(checks),'known actual Qwen comparison remains unavailable')
