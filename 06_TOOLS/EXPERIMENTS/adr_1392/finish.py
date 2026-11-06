from common import *

out=ART/'main'
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
rollout=read(out/'activation.json')
assert active==rollout['active'] and active['generation']==146
release=read(ROOT/active['manifest_path'])
gold=read(ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json')
assert release['files']==gold['engine_files'] and gold['engine_manifest_sha256']==sha(ROOT/active['manifest_path'])
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
checks={}
for phase,expected in [('candidate-review',39),('prepared-review',67),('selected-review',2)]:
    record=read(ART/phase/'result.json')
    assert record['exit_code']==0 and record['passed']==expected and record['failed']==0 and record['code_unchanged']
    checks[phase]=expected
assert read(ART/'contract-runtime-archives.json')['all_files_hash_verified']
chat=read(out/'selected-chat-probe.json')
assert chat['physical_sends']==0 and chat['status']==200
summary={'active':active,'serving_files':len(release['files']),'delta':rollout['changed'],'checks':checks,
    'default_service':rollout['main_checks'],'gold_connector':rollout['gold_checks'],
    'oracle_prepared_plans':640,'old_plans_equivalent':639,'default_chat_text':chat['body']['answer']['text'],
    'rollback_manifest':read(DES/'baseline.json')['pointer']['manifest_path'],
    'rollback_gold_binding':rollout['old_gold_binding'],'new_external_model_calls':0,
    'field_deployed':False,'quality_certified':False}
put(ART/'result.json',summary)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True},'integrated':summary},
                    comparisons=[],judge_disagreements=0,error_taxonomy={},usage={'model_calls':0},
                    latency={'note':'Local activation; no new inference latency benchmark.'})
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
body=['로컬 기본 MAIN146으로 재검토 수정본을 선택했다. 릴리스는 bound-chat-review-20261105-r1이다. 로컬 Gold 연결기도 같은 엔진을 읽는다.',
'기존 MAIN145에서 화면 안내 문장을 새 질문으로 해석해 명령 선택에서 504가 발생했다. 이번 반영은 같은 대화 직전 답변에 결속되는 재검토 동작과 안내를 대상으로 했다.',
'사용자가 “이거 메인에 반영해봐”라고 지시했다. MAIN145의 원문·권한·진행 중인 다른 작업을 보호하면서 같은 실제 운영 진입점에 수정본을 연결하는 것을 기준으로 삼았다.',
'MAIN145에서 시작해 확인된 백엔드 세 파일, 화면 안내 함수 한 개, 준비 SQL과 관련 엔진 해시만 결합했다. 원래 화면 함수 일치와 원복 시 파일 바이트 복원을 확인했다.',
'528개 파일 전체 SHA를 후보·준비 릴리스·선택본에서 대조했다. 변경 36개(기능 파일 4개·파생 SQL 1개·엔진 및 파이프라인 핀 31개). 기존 639개 SQL 실행 표현 보존, 직전 요청 확인 조회 하나 추가.',
'후보 검사 39개, 준비 릴리스 검사 67개 통과. 전환 후 새 프로세스 기본 서비스 HEALTH 200 및 외규 모드 긴 문구 HTTP 200, 외부 모델 0회. 실제 원문·작업 상태가 없는 채팅은 “이 대화의 직전 답변에 다시 실행할 검토가 없습니다.”로 응답했다. 선택본 API의 검토 실패 대역 검사에서는 긴/짧은 문구가 모두 같은 질문의 ASSESS·COMPOSE 재개 및 중복 비용 0을 재확인했다(2개, 준비본과 중복). 기본 서비스 검증 21항목, 로컬 Gold 엔진 연결 9항목 통과.',
'입력 범위가 달라지거나 이미 사용한 재검토를 새 작업으로 다시 요청한 경우를 명시적으로 구분한다. 이전 코드에서 생성된 대화는 실행 바인딩 확인으로 재검토가 거절될 수 있다.',
'이번 승격의 새 외부 모델 호출 0. 이전 ADR1390은 첫 검토 실패를 통제하고 실제 Qwen 1회·35.652초에 세 항 답변을 복구한 별도 실행이다.',
'재검토 문구가 실제 선택된 MAIN에 연결됐고 기존 원문·사건 상태 검사 및 최종 검증이 유지됐다.',
'사용자 지시 로컬 전환이다. 현장 GENOS, 운영 Oracle, 삼성메일 발송 및 전반적인 법률 답변 품질 인증은 이번 범위 밖이다.',
'MAIN145 복원 대상은 새 릴리스 rollback/ACTIVE_RELEASE.json, 이전 Gold 바이트는 artifacts/main/gold-binding-before-exact.json에 보존했다. 기본 서비스와 Gold가 동일 엔진을 바라보는지 함께 확인해야 한다.',
'adr_1392/setup.py → freeze.py → check.py → 공식 prepare → 준비본 check → 공식 apply --confirm-main → main_entry.py·gold_entry.py → 선택본 check → archive.py·finish.py.']
front=(ADR/'README.md').read_text().split('---',2)[1].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')
(ADR/'README.md').write_text('---'+front+'---\n\n# 로컬 MAIN146 채팅 재검토\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,body),1))+'\n')
q=m['questions'][0]
sections=[('실행 메타','run-001/integrated, MAIN146.'),('사용자 질문 원문','이거 메인에 반영해봐'),('기준답변 — 채점 전용, 제품 입력 비공개',body[2]),('제품 입력을 구성한 원값','### 회수·탈락 단계 원장 — run·arm별\n\n로컬 승격 확인. 새로운 법률 검색 평가는 없다.'),('제품 모델 호출 — run·arm별 실제 원문','외부 모델 호출 0회.'),('중간 LLM 호출 — router/compiler/verifier/repair','추가 0회. 준비본 기능 검사는 통제 응답을 사용했다.'),('채점 호출과 반복 판정','채점 모델 0회. 실제 선택 포인터, 엔진, 헬스, 세션 및 해시를 확인했다.'),('사례 최종 판정',body[5])]
(ADR/'실험'/q['file']).write_text('# MAIN146 서비스 및 복구 확인\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 로컬 MAIN 변경\n\n[검사 결과]('+q['file']+')\n')
paths=[p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json']
paths.extend(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Local MAIN cutover, selected checks or rollback receipt','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
