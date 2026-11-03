from common import *
import re,shutil,tarfile
a=read(ART/'source-wire-audit.json');r=read(ART/'live/result.json');g=read(ART/'stored-public-graph-summary.json')
display=read(ART/'genos-display/result.json');handoff=read(ART/'handoff-verification.json')
analysis={'verdict':'NOT_PASSED','reason':'Third physical call ConnectError, no headers/body; UNKNOWN; native API502',
    'final_claims':0,'review_reached':False,'final_answer_reached':False,'duplicate_test':'not reached after failure',
    'stored_graph':g,'observed_model_paths':'read direct title trust-contract; request commercial code article341; then transport failure',
    'entry_scope_omission':'Model named Commercial Act enforcement decree only; capital-market enforcement decree was allowed but not named',
    'read_judgment_issue':'Non-governing trust-contract paperwork and shareholder-proposal articles were tagged SUPPORT; not accepted final legal claims',
    'reference_follow_history_count':0,'repeated_no_progress_count':0,
    'originals_in_successful_model_exchange_article_count':4,
    'originals_in_assembled_wire_article_count':5,
    'unknown_wire_not_claimed_received':True,
    'can_prove_no_connections_in_data':False,'can_prove_infinite_loop':False,
    'photo_request_reproduced':False,'field_genos_verified':False,
    'display_only_fallback':'Acquired document/heading scope, not semantic summary or successful final legal review',
    'no_progress_diagnosis':'The trace advances through three navigation steps; failure prevents full loop assessment',
    'postrun_graph_injected_into_model':False}
put(ART/'analysis.json',analysis)
# Preserve original runtime bytes without changing journals. No active process remains.
runtime=ART/'live/runtime';members=[]
with tarfile.open(ART/'runtime-preserved.tar.gz','w:gz') as archive:
    for p in sorted(runtime.rglob('*')):
        if p.is_file():
            name=str(p.relative_to(runtime));members.append({'path':name,'sha256':sha(p),'bytes':p.stat().st_size})
            archive.add(p,arcname=name,recursive=False)
with tarfile.open(ART/'runtime-preserved.tar.gz','r:gz') as archive:
    for row in members:
        with archive.extractfile(row['path']) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
put(ART/'runtime-preserved-receipt.json',{'archive_sha256':sha(ART/'runtime-preserved.tar.gz'),'files':members,
    'originals_retained':True,'restore':'Extract to a NEW empty directory; compare each recorded SHA256. Do not overwrite original failure records.'})
folder=ROOT/'08_DEPLOYMENT/GENOS/handoffs/connected_sources_20261103_r1'
shutil.move(folder/'검증_인계.json',ART/'handoff-initial-receipt.json')
result={**r,'source_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches')),
    'budget_matches':a['budget_matches'],'reported_cost_usd':a['reported_cost_usd'],'reported_input_tokens':a['input_tokens'],
    'reported_output_tokens':a['output_tokens'],'missing_usage_calls':1,'analysis':analysis,'display':display,
    'candidate_files':540,'main_unchanged':a['main_pointer_unchanged'],'candidate_unchanged':a['candidate_unchanged'],
    'handoff':handoff,'source_schema_changes':0,'oracle_writes':0,'main_promoted':False,'product_workspace_changed':False}
put(ART/'final-result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'live/result.json'))
m['retrieval_accounting']=read(ART/'retrieval-metrics.json')
m['results'].update(status='complete',by_arm={'verified':{'attempted':1,'answers_completed':0,'claims':0,'semantic_accuracy':None,'contracts_passed':49}},
    comparisons=[],judge_disagreements=None,usage={'physical_calls':3,'reported_cost_usd':a['reported_cost_usd'],
        'input_tokens':a['input_tokens'],'output_tokens':a['output_tokens'],'missing_usage_calls':1},
    latency={'request_seconds':r['seconds'],'model_seconds':a['model_seconds']},
    error_taxonomy=[{'type':'other','reason':'CONNECT_ERROR_UNKNOWN; no final answer or review; scope omission observed, causality untested'}])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
'실제 복합 법령 답변 실험은 미통과(Rejected)로 완료 기록한다. 정상 모델 응답2 뒤 세 번째 연결 오류/UNKNOWN으로 API502, 최종 주장0. GENOS 표시 수정은 별도 계약49개 및 실제 Python run/dict/socket/로컬 브라우저 클릭을 통과했지만 현장 미검증이다. 후보와 인계본만 준비했으며 MAIN134·작업 제품은 변경하지 않았다.',
'사진의 검토 미완료 답변은 completion_contracts.render_source_excerpt_reply가 원문을 본문으로 나열하고, GENOS _public_answer_text가 그대로 표시하던 경로다. 기존 details 출처 기능이 있더라도 본문 중복은 해소되지 않는다. 후보는 엄격한 source_excerpt_reply 영수증만 문서·조항 범위로 표시하고 원문은 닫힌 출처에 한 번 보존한다. 이는 내용 요약이나 법률 결론 생성까지 해결한 것이 아니다.',
'호출 전에 design/criteria.json·freeze-v2.json 동결. 공개4문서에서 실제 최종 주장과 3문서 이상 근거 연결, 원문/ACL/wire 일치, GENOS 반환/스트림 및 접힘 동작, 중복 요청 추가0. UNKNOWN이면 후속 모델0. 확보 연결/모델 제시/선택/최종 활용을 구분하며 불완료 응답을 성공으로 계산하지 않는다.',
'완료 부모 ADR1292/verified, MAIN134와 같은 백엔드539파일을 격리하고 표시1파일 수정 및 새 검사1파일로540개 rev-001 동결. historical baseline은 이번 호출 없음. local public four-doc corpus·financial_team 정상 ACL·native /v1/rag/ask·격리SQLite. 실제 모델1질문1회. 사후 사람 주도2단계 그래프 조사는 모델 입력에 주입하지 않은 별도 읽기전용 진단이다.',
'질문은 상장회사의 자기주식 직접/신탁 취득 방법·한도·결정 절차 비교다. 상법, 상법 시행령, 자본시장법, 자본시장법 시행령의 저장 판본을 사용했다. 정확한 코드/정책/데이터 해시는 design/freeze-v2.json과 source-wire-audit.json, 원문 판본은 각 source_artifact_versions다. Qwen3.8-27b/Parasail FP8, 출력 토큰상한 없음. 승인 Gold나 외부 judge 없음; 현행 법률 정답 검증은 아니다.',
f'실제 API502/{r["seconds"]:.3f}초, 물리3(정상2/UNKNOWN1), 최종 주장0/답변0. 보고 비용 ${a["reported_cost_usd"]:.8f}, UNKNOWN사용량 미보고. 원문 대조30개 span 불일치0/ACL0/wire0, 예산3=시도3. 표시49계약 및 로컬 브라우저 접힘·펼침·재접힘·360px 확인. 설치기 check/apply/동일재실행/rollback 및 다른 파일 거절7조건 통과. 실제GENOS0.',
'첫 진입 모델은 일반적인 “시행령”을 상법 시행령으로만 정해 자본시장법 시행령이 허용 목록에는 있으나 검색 지정에서 빠졌다. 신탁계약 표제와 상장회사·신탁 정의를 먼저 확보했고, 본문이 자기주식 핵심 규정이 아님을 설명하면서 SUPPORT로 분류한 중간 판단도 있었다. 이어 상법341조를 직접 요청하여 확보했으나 다음 모델 호출 ConnectError로 끝났다. reference_history는0, no_progress는0이며 무한루프나 최종 검토 실패는 이번 실행에서 재현되지 않았다. 원래 사진의377초 실행 로그를 확보한 것은 아니다. 준비 실패 risk_team ACL거절(모델0), pytest 예약인자, bytecode 동결거절, manifest준비오류를 보존했다. 사후 검사기의 article_coordinate dict 타입 오류와1MiB 요약상한 거절도 원본/수정 기록을 남겼다.',
f'공개4문서 조문root3371 → 확보8 → 전송용 요청 조립5. 그중 정상 응답과 결속된 모델 입력 원문은4개 조문이며 나머지 포함 UNKNOWN요청을 수신 성공으로 세지 않는다. retrieval-stage-ledger.json.gz는 모든 좌표와 탈락 사유를 보존한다. Gold 미승인으로 recall/정확도는 null. 원문 확인30span과 조문root 수는 다른 단위다. 모델 구간{a["model_seconds"]:.3f}초; 전체 요청{r["seconds"]:.3f}초. peakRSS 3168584KiB, 자원중단0. runtime 압축/원본 해시 전부 검증해 보존했다.',
'저장 연결 없음 가설은 이 사례에서 지지되지 않는다. 사후 기존 참조를 따라4문서·11조문·36참조 중34연결(문서 간17/공식 위임3)을 원문과 대조했고, 미해결2를 그대로 보존했다. 자본시장법165조의3에서 상법341조(방법/결정),462조(한도), 자본시장법 시행령176조의2(위임)로 연결되며 상법341조에서 상법 시행령9조,462조에서 시행령19조로 이어진다. 구조적 참조의 존재와 적용 관계 판단·답변 완성은 별개다. 실제 자동 조사에서는 저장 참조를 따라간 경로/최종 활용은 확인되지 않았고, 정의 연결 확보만 관측했다.',
'공개 저장 판본1질문·외부Qwen의 부분 실행이다. 내규/PF 사진 질문 재현, GENOS 내부모델, 온톨로지 게시 활용, Oracle/NFS 내구 및 동시성, 법률 현행성·정확도·인과 개선율을 검증하지 않았다. HTML 정제는 실제GENOS 화면에서 SOURCE_DISPLAY_CHECK로 확인해야 한다. source-only 표시가 확보 범위를 간추린 것은 실제 내용 요약 답변을 완성했다는 뜻이 아니다.',
'현재 MAIN134 유지·승격0·작업 제품 수정0·DB/DDL/Git push/메일/현장변경0. GENOS_CONNECTED_SOURCES_20261103_R1.zip은 MAIN134 의존 해시를 검사하는 부분 패치이며 필드 버전이 다르면 적용 전 중단한다. 실제 ~/DEV 적용과 편집기 저장, 같은commit/generation 게이트, 새서빙리비전 및 워크플로우 테스트가 각각 필요하다. 이전파일 백업/원복명령 포함; 인계 최종 해시는 artifacts/handoff-verification.json을 따른다.',
'기록된 순서: prepare → 표시수정/49검사 → freeze → preflight v1 ACL거절/모델0 보존 → v2올바른팀 동결 → 실제1회 → audit → 사후 inspect_graph/ledger → package/설치기 검증 → finalize → adr_structure hash/status/validate --final/graph. 완료된 live_v2.py를 같은 경로로 재실행하지 않는다. 새 실제시험은 새ADR/새runtime·사전기준이 필요하다. 모든 raw/canonical/state는 gzip 및 압축 전후 해시와 함께 보존했다.'
]
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 복합 공개법령 연결과 GENOS 출처 표시\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
q=m['questions'][0];question=read(DES/'cases-v2.json')[0]['question']
sections=[('실행 메타','2026-11-03 04:34~04:36 UTC; run-001/verified; 원본 exact; baseline미실행. 요청/응답/중간 canonical 및 UNKNOWNpartial 전부 보존.'),
('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','승인 기준답변 없음/정답률 미채점. 사전criteria는 실행·근거·표시 완료조건이며 법률 정답 Gold가 아니다. 사후 저장 연결조사를 제품 입력으로 주입하지 않았다.'),
('제품 입력을 구성한 원값','design/cases-v2.json·freeze-v2.json·live/canonical/*.json.gz·raw/call-*/request.json.gz에 정확한 원값.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/retrieval-stage-ledger.json.gz: source3371→acquired8→present5. present는 UNKNOWN을 포함한 요청 조립이며 정상 수신 확인4와 구분. Golden recall null; 골드 유입0.'),
('제품 모델 호출 — run·arm별 실제 원문','../artifacts/live/raw/call-001~003/request.json.gz, 001~002/response.json.gz, 003/partial-response.json.gz. system/user/schema원문·공급자·사용량·지연 calls.json 및 canonical 전체 gzip. 각 파일 옆 .ref.json에 해시와 원래용량.'),
('중간 LLM 호출 — router/compiler/verifier/repair','request-entry1, read-choice2. 정상2+ConnectError/UNKNOWN1. 최종ASSESS/compose/repair 미도달; UNKNOWN뒤 모델0. native단계는 generations.json과states/*.json.gz.'),
('채점 호출과 반복 판정','judge0/다수결없음/확률반복없음/중복조회미도달. 사후 source-wire-audit와analysis.json으로 원문·전송·예산·실제선택 경로만 확인.'),
('사례 최종 판정','NOT_PASSED. ConnectError→API502→최종주장0. other(전송오류); scope_actor_mismatch는 초기 범위 좁힘 관찰이지 최종 실패 인과판정이 아니다. 원문/ACL/wire 불일치0; 표시49통과는 별도 범위. 후속 가설: 위임 연결을 조사 범위로 확장하고 선택한 참조의 출발·도착 원문을 함께 제시했을 때 실제 연결 판단이 개선되는지 새 실험으로 확인.')]
(ADR/'실험'/q['file']).write_text('# 공개 법령 복합 연결 실제 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text(f'# 실행 기록\n\n- [{q["case_id"]}]({q["file"]}) — 실제1회 미통과, 표시검사 별도통과\n')
out=ROOT/'09_ARTIFACTS/AUDITS/20261103-connected-law-genos';out.mkdir(exist_ok=True)
(out/'실험결과와_GENOS수정.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n\nZIP SHA256: '+handoff['zip_sha256']+'\n')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1300','files':[{'path':str(p.relative_to(ROOT)),
    'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved exact probe/display/inspection record',
    'contains_raw_prompts_and_outputs':'raw' in p.parts or 'canonical' in p.parts} for p in sorted(ART.rglob('*')) if p.is_file() and p!=ART/'manifest.json']})
print('FINAL_RECORD_WRITTEN: actual probe NOT_PASSED; GENOS local display49 PASS; field unverified')
