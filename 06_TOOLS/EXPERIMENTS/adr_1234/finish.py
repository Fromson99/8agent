from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1234-gold-ontology-reference-repair';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';U=R/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-on'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
r=read(P/'result.json');a=read(P/'audit.json');e=read(O/'ontology-e2e.json');checks=read(O/'checks.json');f=read(D/'freeze.json');same={p:sha(R/p)==h for p,h in f['files'].items()};assert all(same.values());put(O/'post-run-integrity.json',same)
result={'status':'INCOMPLETE_PROVIDER_429_ADAPTER_HANDLING','real':r,'audit':a,'ontology':e,'checks':{'passed':checks['passed'],'failed':checks['failed']},'applied_connector':read(U/'applied.json'),'diagnosis':'ExperimentClient raises HTTP429 envelope; experiment reserved_send returned it as a successful transport value. Native gateway then model-validates error body; its existing ContractError branch references unbound exc. Normal LocalQwen38Transport would raise TransportError with KNOWN_REJECTED and switch under approved policy. This failed test transport is not installed in Gold connector.','quality_certified':False};put(O/'result.json',result)
report='''골드 온톨로지 ON 수정본 실제 시험 — 2026-10-30 / ADR1234

골드 연결기 ON/DB 반영 및 health 통과. 최신 DTLS 물리명13테이블/60컬럼 연결.
두 연결 오류를 별도 runtime patch로 수정: 현재 검증 원문으로 취득ID 재결속, 새claim ID와 기존온톨로지 구성요소 별칭 분리.
관련40검사통과. 실제새질문은 상법369조 게시물1개·원문4개·온톨로지3경로 모두 최종요청에 포함했다.
실제271.660초·SQL2770·물리4(Parasail정상3/HTTP429 1)·도구4·보고비용$0.00928172.
확보19/중첩18/평면9 원문대조 불일치0·권한위반0, 전송요청4동일, UNKNOWN0·자원중단0·swap증가0.
최종모델응답0·최종답변0·전체E2E는 미통과다. 원문 취득/전송 성공을 모델 사용·답변 완성으로 확대하지 않는다.

추가 원인 정정
HTTP429 실패를 시험 전송기의 reserved_send가 예외로 전달하지 않고 정상반환했다.
그 결과 기존gateway가 오류본문을 모델응답으로 검사하다가 미할당 exc 참조로 UnboundLocalError가 났다.
429는 온톨로지/SQL 오류가 아니다. 실제 LocalQwen38Transport는 TransportError+KNOWN_REJECTED를 보존하는데 시험 어댑터가 이를 보존하지 않았다.
시험 어댑터는 설치된 골드 연결기에는 포함되지 않았다. 후속은 이 어댑터만 바로잡아 기존429 1회전환 정책을 지키는 새시험이다.

설치범위: 별도Gold connect.py/ontology_settings.json/runtime_patch_binding.json/runtime_patches 2파일.
MAIN123 선택/프로필과 기존MAIN120 파일·원본DB불변. DB쓰기0. 기존게시3건 유지.
기본 서비스 연결 시 open_store의 store.gold_profile을 create_app의 legal_agent_profile로 전달한다.
사용자ON요청에 따라 기능설정은 반영했지만 완전한 법률답변 성공이나 MAIN 승격을 주장하지 않는다.
이번실제시험은 복원한 최종claim을 받기 전 중단되어 alias수정의 새실모델 최종효과는 미확인이다.
''';(U/'ON_수정본_실제결과.txt').write_text(report)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'repaired':result},comparisons=[],usage={'physical_calls':4,'provider_429':1,'unknown':0,'reported_cost_usd':a['reported_cost_usd']},latency={'seconds':r['seconds']},error_taxonomy=[{'kind':'provider_429','count':1},{'kind':'experiment_adapter_swallowed_transport_failure','count':1}]);m['design']['code_isolation']['main_wiring_unchanged']=True
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];q=m['questions'][0];vals=['run-001/repaired; rev001',read(D/'cases.json')[0]['request']['json']['question'],'기준답변 주입/채점모델0.', '[동결입력](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n기존순위/회수정책유지. 원문4/ontology3 최종전송결속은 ontology-lineage.json.gz.', '[raw/canonical](../artifacts/run-001/live/gold-369/) 전체 보존.', '진입/조사3정상, 최종429. 전환0.','40계약·실제원문/wire 대조. 추가채점0.','미통과: 최종답변0. 시험전송기 오류를 후속별도수정.'];p=A/'실험'/q['file'];p.write_text('# gold-369\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p);put(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369]('+q['file']+'): 최종429·시험전송기오류·답변0\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=['Rejected: 연결 수정/원문4·경로3 실제전송 확인, 최종답변0.','ADR1233별칭충돌·이전evidence ID만허용.','동결 criteria.json. 원문·경로·claim·답변 전체연결.', '원래질문1회, 최신 DTLS 매핑명시고정, 검증기/모델/권한유지.','원문19/18/9·wire4대조; 전체raw보존.','\n'+report,'시험 어댑터가429 envelope를성공처럼return하여정상전환이막혔다.', '271.660초/4물리/2770SQL/$0.00928172. A/B성능주장없음.', '현재원문ID 재결속 실제효과 확인, 새claim최종응답미수신.', '일반 ASSESS의 온톨로지 인과적사용·법률품질 미인증.', '사용자ON지시의별도Gold설정/2패치만반영. MAIN123불변. rollback은audit/rollback.','checks.py; preflight.py; audit.py gold-369; ontology_audit.py. 완료run재실행금지.']
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(A/'README.md').write_text('---'+front+'---\n\n# ADR-1234: 골드 온톨로지 연결 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(f.relative_to(R)),'sha256':sha(f),'bytes':f.stat().st_size,'description':'Actual run or isolated contract evidence; failures preserved','contains_raw_prompts_and_outputs':'/raw/' in str(f) or '/canonical/' in str(f)} for f in (A/'artifacts').rglob('*') if f.is_file() and f!=p];v.pop('notes',None);put(p,v)
