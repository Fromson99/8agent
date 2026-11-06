"""Describe measured outcomes, keeping replayed responses distinct from new calls."""
from common import *

candidate=read(DES/'candidate-repaired.json')
baseline=read(DES/'baseline.json')
turns=read(ART/'turn-audit.json')
wire=read(ART/'source-wire-audit.json')['cells'][0]
cell=ART/'public-live/conversation-repaired'
calls=read(cell/'calls.json')
pressure=read(ART/'pressure-summary.json')['cells'][0]
working=read(ART/'working-integration.json')
feature=[n for n in working['product_files'] if not n.endswith('oracle_query_plans.py')]
assert all(sha(ROOT/candidate['code_root']/n)==h for n,h in candidate['selected_files'].items())
assert all(sha(ROOT/n)==candidate['selected_files'][n] for n in feature)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert active==baseline['pointer']
selected=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1394-main146-multiturn-audit/artifacts/design/candidate-selected.json')
selected_root=ROOT/baseline['release']['code_root']
assert len(selected['selected_files'])==528
assert all(sha(selected_root/n)==h for n,h in selected['selected_files'].items())
gold=read(ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json')
assert gold['engine_release_id']==active['release_id']
assert gold['engine_manifest_sha256']==active['release_manifest_sha256']
contract={k:{n:read(ART/k/'result.json')[n] for n in ('passed','failed','exit_code')} for k in ('contract-checks','working-contracts')}
assert all(x['passed']==54 and x['failed']==0 for x in contract.values())
t1,t2,t3=turns['turns'][:3]
assert t1['model_calls']==t2['model_calls']==0 and t3['status']==504
same={k:t1[k]==t2[k] for k in ('goal','revision','answer_or_failure','source_ids','claim_evidence')}
assert all(same.values())
assert t2['executed']==[] and t2['method']=='ANSWER_PRESENT' and t2['duplicate']['extra_model_calls']==0
assert len(calls)==2 and [x['status'] for x in calls]==['responded','unknown']
diag=calls[-1]['transport_diagnostics']
assert diag['whitespace_only'] and diag['received_chunks']==60 and diag['received_bytes']==660 and diag['worker_reaped']
assert wire['budget_matches'] and not any(wire[k] for k in ('source_mismatches','acl_violations','wire_mismatches'))
put(ART/'repeat-equivalence.json',{'same':same,'elapsed_seconds':t2['elapsed'],'new_model_calls':0,
    'duplicate_extra_model_calls':0,'first_turn':'Seven recorded real provider outputs replayed through product; no fresh first-turn inference',
    'working_tests':contract,'selected_main':active,'gold_matches':True,'selected_files_verified':528,
    'feature_working_matches_frozen_candidate':True})
usage={'physical_calls':2,'normal':1,'unknown':1,'reported_cost_usd':wire['reported_cost_usd'],
    'reported_tokens':wire['reported_tokens'],'unknown_unreported_cost':None,'fixture_responses':7,
    'model_attempts_including_fixture':9,'budget_reserved':wire['budget_reserved'],
    'repeated_turn_calls':0,'same_id_extra_calls':0,'sends_after_unknown':0,'judge_calls':0}
latency={'fixture_first_turn_seconds':t1['elapsed'],'literal_repeat_seconds':t2['elapsed'],
    'new_implicit_followup_seconds':t3['elapsed'],'unknown_physical_seconds':calls[-1]['seconds'],
    'new_model_seconds':wire['model_seconds']}
details=(
    '완료한 질문과 문구·문맥·문서 범위가 같은 재질문만 수정했다.\n\n'
    '| 턴 | 실행 구분 | 결과 | 시간 | 새 모델 호출 |\n'
    '|---|---|---|---:|---:|\n'
    f'| 1 | ADR1394 실제 응답 7개 재생 | 기존 검증 절차로 ANSWER/COVERED·1주장 | {t1["elapsed"]:.3f}초 | 0 |\n'
    f'| 2 | 같은 질문·새 요청 ID | 같은 goal·revision·본문·근거 재표시 | {t2["elapsed"]:.3f}초 | 0 |\n'
    f'| 3 | 새 실제 Qwen: 그럼 임시총회는? | 명령 선택 공백 응답·504/UNKNOWN | {t3["elapsed"]:.3f}초 | 2 |\n'
    '| 4 | 의결권으로 주제 전환 | UNKNOWN 중단으로 미실행 | — | 0 |\n'
    '| 5 | 검토 다시 하기 | UNKNOWN 중단으로 미실행 | — | 0 |\n\n'
    '후보 및 작업 코드에서 같은 54검사가 각각 통과했다. 신규 12검사·기존 관련 42검사이며 독립 108표본으로 합산하지 않는다. '
    '새 문장/조건/문서 범위/미완료/원문전용/판본 충돌은 기존 경로를 유지한다. '
    f'원문 {wire["source_checks"]}구간 대조·권한/저널 전송 불일치 0. 실제 새 2호출에는 원문 본문 전달 0; 첫 턴 원문은 재생된 요청 안에 있어 새 원격 전달로 세지 않는다. '
    '실행 SQL 640개 동일·작업 34파일(기능 2+native 메타 1+pin 31), 엔진 30/500 확인.'
)
observations=(
    'ADR1394에서 MAIN146은 첫 질문에 82.933초·7회로 올바르게 답했으나 동일 문구의 두 번째 질문을 다시 모델 명령 선택으로 보내 UNKNOWN이 발생했다. '
    '새 후보는 기존 literal_repeat_target의 현행 상태·동일 문구·문서 권한 검사를 통과하고 ASSESS가 ANSWER/COVERED·주장 포함인 경우만, '
    '기존 미완료 요청 복구에서 쓰던 원문/노드 검증·응답 조립 경로를 공통 committed_response로 재사용한다. '
    '고정 정답·조항 특례·의미 판정·검증 생략은 추가하지 않았다.\n\n'
    '새 실제 후속 질문의 memory-resolve 입력에서 기존 goal, 원래 질문, 앞선 정답, 두 대화 턴이 모두 확인됐다. literal_repeat_target은 None으로 정상 배제됐다. '
    'source-request-route는 CASE를 반환했지만 다음 memory-resolve는 HTTP200 헤더 뒤 공백60조각/660바이트만 주고 약179.945초에 기한 종료됐다. '
    '명령 JSON은 얻지 못했으므로 모델이 어떤 명령을 골랐는지, 원격 실행이 끝났는지, 원격 지연의 근본 원인·미보고 비용은 알 수 없다. '
    '문맥 손실이나 스왑 부족으로 단정하지 않는다.\n\n'
    '첫 검사 준비는 후보 descriptor 이름 오기 때문에 제품 실행 전에 실패했다. 올바른 descriptor를 고친 뒤 54검사를 수행했다. '
    '첫 작업 반영 시도는 별도 작업의 completion/progress 변경으로 native 메타 검사가 실패해 해당 쓰기를 복원했다. '
    '현재 작업 파일을 별도 stage로 복사해 검증한 기능 2개만 덧씌우고 native 소스 메타만 다시 생성했다. '
    '실행 SQL 640개 동일과 병행 수정 보존을 확인한 뒤 반영했다. 준비/첫 반영 실패 기록도 보존했다.'
)
limits=(
    '후보 첫 턴은 새 실제 추론이 아니라 ADR1394의 원응답 7개 재생이다. 두 번째 턴은 실제 새 API 요청이지만 모델을 쓰지 않는 기능을 검증한다. '
    '새 외부 추론은 세 번째 턴의 2호출뿐이다. 기존 UNKNOWN 요청을 재송신하지 않았고 새 UNKNOWN 뒤 후속 송신도 중단했다. '
    '암묵적 후속 질문 실패가 남았고 주제 전환/마지막 재검토는 미실행이다. 다섯 턴 전체 성공·일반 멀티턴 안정성·속도 향상·운영 품질로 일반화할 수 없다. '
    '공개 상법 SQLite·동일 1대화이고 Oracle/현장 GENOS·브라우저 클릭은 검증하지 않았다.'
)
report={
    'title':'완료된 동일 질문 재표시 수정과 실제 후속 대화 실패',
    'verdict':'정확히 같은 완료 질문은 모델 0회·0.824초로 재표시하도록 작업 반영. 실제 암묵적 후속 질문은 명령 선택 UNKNOWN/504로 실패해 멀티턴 전체 미통과. 선택 MAIN146은 유지.',
    'context':'사용자의 멀티턴 재점검 요청으로 MAIN146을 동결해 ADR1394에서 확인했다. 첫 답변은 정확했고 같은 질문을 새 요청 ID로 반복할 때 불필요한 모델 라우팅 뒤 실패했다. 대화 상태와 이전 답변은 모델 입력에 존재했다.',
    'design':'MAIN146 528파일에서 후보를 격리하고 기능 2파일만 수정했다. 완료1394의 실제 첫 턴 응답 7개를 새 대화의 제품 경로로 재생하고, 동일 재질문에는 외부 송신 tripwire를 설치했다. 그 뒤 새 문맥 후속/주제 전환/재검토를 계획하되 UNKNOWN 때 즉시 중단했다. 기존 실패응답·바인딩·DB 수정 없이 재생과 새 추론을 분리 기록했다.',
    'environment':'2026-11-05, MAIN146 bound-chat-review-20261105-r1 기반528·공개 상법1/SQLite·qwen/qwen3.8-27b·Parasail FP8·추론none·온톨로지OFF. 새 외부호출은3번째 턴뿐. 후보·원문·모델입력/출력/SSE·runtime 해시 보관. 첫 턴 법령 기준은 동결 원문과 대조한 기존1394 그대로.',
    'details':details,'observations':observations,
    'meaning':'문맥을 기억하는 상태 저장과 명령 선택 응답의 신뢰성은 별개다. 검증 완료한 동일 문구 재질문은 의미 결정을 새로 요구하지 않으므로 기존 검증 답변을 직접 조립할 수 있다. 실제 다른 후속 질문은 의미 판단이 필요하고, 이 시험에서는 그 외부 응답 경계가 남은 실패 지점이다.',
    'limits':limits,
    'release':'작업 코드에만 기능2+native 메타1+pin31 반영. 관련54검사·SQL640동일·엔진30/500. 선택 MAIN146 포인터/528파일/Gold 바인딩 유지. 다른 병행 작업 변경은 보존. 새 릴리스 전환·GENOS 현장배포·메일0. MAIN 승격은 별도 검증 대상.',
    'commands':'재송신 없는 조회: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1396/turn_audit.py\n계약검사: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1396/check.py --help\n결과 문서/대조: artifacts/final-review.json, repeat-equivalence.json, source-wire-audit.json.\n실제 live 재실행은 새 ADR·사전 기준이 필요하며 기존 UNKNOWN을 재전송하지 않는다.',
    'usage':usage,'latency':latency,
    'error_taxonomy':{'memory_context_lost':0,'unnecessary_repeat_model_route':'1394에서 재현·1396 동일완료문구 수정',
       'followup_memory_resolve_unknown':1,'after_unknown_not_started':2,'resource_stop':False,
       'source_mismatch':0,'acl_mismatch':0,'wire_mismatch':0,'fixture_setup_failure':1,'initial_integration_rolled_back':1},
    'cases':{'conversation':{'questions':'1. '+t1['question']+'\n2. '+t2['question']+'\n3. '+t3['question']+'\n4. '+turns['turns'][3]['question']+'\n5. '+turns['turns'][4]['question'],
       'expected':'재질문은 기존 검증 답변/출처 유지. 임시총회 후속은 상법 제365조 제3항의 필요시 소집. 주제 전환은 제369조 제1항의 1주1개. 재검토는 바로 앞 답변을 대상으로 동작. 기준답변은 채점 전용으로 제품 프롬프트에 주입하지 않음.',
       'raw':'artifacts/public-live/conversation-repaired: fixture/001~007는 원응답 재생, canonical/008~009와 raw/call-001~002는 새 실제 호출. turn-1~3 응답 및 요청·SSE·runtime archive·turn-audit.json 참조.',
       'result':details+'\n\n'+limits}}
}
put(ART/'final-review.json',report)
(ART/'멀티턴_수정과_검증결과.txt').write_text(report['verdict']+'\n\n'+details+'\n\n'+observations+'\n\n'+limits+'\n\n'+report['release']+'\n')
print(json.dumps({'usage':usage,'latency':latency,'contracts':contract,'same_repeat':same,'selected_generation':active['generation']},ensure_ascii=False))
