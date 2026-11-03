from common import *
import re
F=read(DES/'freeze.json');baseline=read(DES/'baseline.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/active['manifest_path']);stage=read(DES/'stage.json')
assert active['generation']==135 and active['release_id']==RELEASE
assert all(sha(ROOT/n)==sha(ROOT/F['code_root']/n)==h for n,h in F['files'].items())
assert release['files']==stage['files']
assert all(read(ART/n/'result.json').get('failed',0)==0 for n in ('contracts-r1','regression-r2','native-final','prepared-api'))
assert all(read(OUT/n)['passed'] for n in ('main-entry.json','gold-entry.json'))
scaling=read(ART/'scaling/result.json');assert len(scaling['rows'])==12 and all(r['full_input_roundtrip_equal'] for r in scaling['rows'])
result={'status':'LOCAL_MAIN_SELECTED','generation':135,'release':RELEASE,'quality_certified':False,
 'candidate_files':len(F['files']),'serving_files':len(release['files']),'delta_files':stage['changed'],
 'contracts':196,'fixture_self_check':1,'native_unique':22,'prepared_api':13,'main_entry':16,'gold_entry':9,
 'checks_overlap':'Prepared13 repeat ordinary candidate API13 on actual release copy; root/Gold checks are entry conditions, not extra independent legal samples',
 'model_calls':0,'oracle_calls':0,'data_unchanged':release['data_path']==baseline['release']['data_path'] and release['data_manifest_sha256']==baseline['release']['data_manifest_sha256'],
 'scope':'Ordinary exact-string sharing, shared review relations and host projection of fully acquired source-work needs; semantic/partial acquisition/scope judgments remain explicit',
 'scaling':bind(ART/'scaling/result.json'),'validation':{n:bind(ART/n/'result.json') for n in ('contracts-r1','regression-r2','fixture-regression','native-final','prepared-api')},
 'activation':bind(OUT/'activation.json'),'main':bind(OUT/'main-entry.json'),'gold':bind(OUT/'gold-entry.json'),
 'remaining':['Real Qwen quality and large-input latency/context limits untested','Provider whitespace UNKNOWN cause remains unconfirmed','Independent semantic/scope review still grows with sources; no incremental changed-only review','No new legal effect inference or ontology publication','Field GENOS/Dataiku/NFS/Oracle E2E not validated here']}
put(ART/'run-001/result.json',result)
rows=[r for r in scaling['rows'] if r['mode']=='per-source' and r['extra_text_chars']==100]
rows.sort(key=lambda r:r['source_count'])
table='자료수 | user입력bytes 전→후 | 출력schema bytes 전→후 | 모델필수검토행 전→후\n'
for r in rows:table+=f"{r['source_count']} | {r['before_user_bytes']}→{r['after_user_bytes']} | {r['before_schema_bytes']}→{r['after_schema_bytes']} | {r['before_rows']}→{r['after_rows']}\n"
report=f'''일반 RAG 중복 요구 정리·로컬 MAIN135 반영 (2026-11-03)

선택: {RELEASE}. 서빙{len(release['files'])}파일, MAIN134대비{stage['changed']}파일 변경(제품3 + pin31), 신규1/삭제0. 검증 후보rev001/작업540파일 일치. 공식 prepare/apply 완료, Gold 엔진도 같은 MAIN135. 사용자 “정리해보고 메인에 반영해”에 따른 USER_DIRECTED_CUTOVER/quality_certified=false.

무엇을 바꿨나
1. 일반 ASSESS/보완에도 동일한 긴 질문·원문 문자열을 한 번만 담고 정확한 참조로 공유한다. 현재 사실/가정 구분, 전체 원문과 끝의 예외, 권한·판본·ID는 유지한다. 새로운 입력v2 reader는 기존v1도 복원한다. 부분문장 압축·요약·문자 절단은 하지 않는다.
2. 일반 ASSESS에서도 같은 claim_refs/basis_refs 조합을 review_links에 한 번 정의한다. 각 판단·필요·범위·요구의 채택/제외/보류, 이유, 쟁점과 gap은 독립적으로 남긴다. 원문 일치·최종 검토·저장/재조회 검증은 그대로다.
3. SOURCE_GOAL/STRUCTURE_SELECTION 중 실제 원문 확보가 완전하고 범위가 비어 있지 않은 조사 작업만 서버가 조립한다. 모델이 scope_reviews에서 명시한 USE/EXCLUDE/OPEN, 실제 주장·근거·gap 연결을 그대로 옮겨 전체 기존 스키마/의미검증을 통과시킨다. 미확보·부분확보/독립 의미need/충돌은 모델이 계속 작성한다. 조사 작업 완료는 법률 쟁점 해결과 다르다. 보완은 기존 한도 내이며 원제안과 실패를 보존한다.

같은12입력 구성요소 비교 (새 검색/모델 실행 아님)
{table}
2개 실제합성원문을 포함하는 기준 입력의 질문 반복9→2, 첫원문6→1. compound문장 안의 질문1회는 그대로 남는다. 자료별 목적+전체묶음200개는603→402행으로201개 조사장부만 서버 조립한다. 전체묶음만 있는 bulk200은203→202행이므로 모든 요청에서201개가 줄어드는 것은 아니다. 긴 추가원문1000자/200개는606337→601723bytes, schema34437→31459bytes, 필수검토행603→402. 12개 모두 이전 모델 입력 전체를 바이트에 대응하는 동일 문자열/구조로 정확 복원했다. system 지시문은 새 설명이 추가되므로 위 수치에는 포함하지 않는다. bytes는 토큰과 다르며 큰 입력의 실제 컨텍스트 적합성/성공률/속도는 미측정이다.

검증
계약196(새25+기존171), 모의연결 API22(일반13+가정/긴gap9), 실제 준비 릴리스 API13, 실제root16조건/Gold9조건 통과. 준비API13은 앞 일반API13과 같은 검사라 합산 독립표본이 아니다. 모의모델 fixture 자체 회귀1도 별도 통과. 저장·중복재조회 모델 추가0, UNKNOWN/adapter 오류 무재전송·기존 원문전용 fallback·승인/가정 계산·옛값 거절·600자gap 유지. 실제 외부모델0/Oracle0/DDL0.

보존한 실패와 검증 한계
후보 등록API 이름 오류1, 잘못된 테스트경로로 수집0/결과저장 오류1을 준비 기록에 남겼다. 첫 native 시험은 일반13 통과, 오래된v3 가정 fixture4 실패. 현행v4 fixture로 바꾼 다음에는 일반응답의 공유연결을 두 번 변환하며 정의를 버리는 모의모델 오류4, 이후 일반 저장응답까지 가정계산으로 검사한 후처리 오류4를 각각 보존·수정했다. 제품rev001은 바뀌지 않았고 원시 runtime도 보존한다. 첫 native-r1에는 연속 자원 계측이 없었으며 중간 RSS365012KiB/Swap0은 한 시점 관측일 뿐이다. 후속 API/실제 entry는 연속 guard 적용. 전체 시간 구간의 자원 상한 준수/최대 RSS 인증은 하지 않는다.

남은 문제
독립 쟁점·자료별 채택/제외·서로 다른 범위 검토는 여전히 필요해 자료가 늘면 출력이 커진다. 변경 영향에 따른 부분 재검토(P3)는 미구현이다. ADR1297 실제 가정UNKNOWN/전체미통과, 공급자 공백 원인, N1효과 미등록/법률UNKNOWN은 해결된 것으로 바꾸지 않았다. 새 수정의 실제Qwen 답변품질·대용량 모델 지연은 별도 시험이 필요하다.

보존/원복
원문 generation·Gold query R18/매핑/설정/연결기·기본OFF/GoldON·Oraclelayout4 유지. MAIN134 pointer와 이전Gold binding은 릴리스 rollback 및 gold-before.json에 보존했다. 기존 별도 관리UI 패키지는 MAIN134 표기를 유지하며 이번에 새 현장 배포를 하지 않았다. Git push/메일/현장 GENOS/Dataiku 배포0.
'''
(OUT/'정리와_검증_메인반영결과.txt').write_text(report)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[f'로컬 MAIN135/{RELEASE} 선택. 사용자 지시 반영이며 법률/실모델 품질 인증은 아니다.',
 'ADR1299가 확인한 일반입력 중복 및 source-work 필요·범위 중복. 현재 검토 의미/근거 검증은 유지하고 동일 표현과 서버 장부만 분리한다.',
 '[사전 기준](artifacts/design/criteria.json). 완전 확보한 비어 있지 않은 v2 조사 작업만 명시 scope에서 조립. 미완료/의미 need는 모델 소유. 모든 기존 검증 유지.',
 '부모1292/선택MAIN134로 격리540파일 rev001. 새계약25/기존171, 모의native22, 동일1299 저장12조건 구성요소 replay. 새 실모델0·법률judge0. 알려진 합성 데이터의 in_sample/probe.',
 '후보/작업540·서빙516 동일. 질문/원문2개와 추가합성자료12조건은1299의 전체canonical fixture를 동일하게 재사용. schema/입력 변환만 실행하고 모델에 전송하지 않았다. 구입력v1 및 기존 review_links v1/v2 reader 유지.',
 report,
 '준비등록/수집 오류와 obsolete-v3 fixture4, mock double-share4, ordinary/scenario receipt 분류4를 각각 보존. native-final은 성공한 고유22조건만 집계하고 실패·반복 성공을 합산하지 않는다. 제품변경은rev001 그대로.',
 '외부모델0/Oracle0/DDL0. 비교단위UTF8 bytes 및 필요배열행, 실제토큰·Qwen latency 미측정. 구성요소 시간은 service 성능으로 확대하지 않음. 자원계측 범위는 별도 resource-monitor-scope.json.',
 '같은관계를 여러 번 쓰게 하던 부담과 서버가 아는 조사완료 장부는 줄였다. USE/EXCLUDE/OPEN와 의미 판단까지 서버가 대신하지는 않는다. 큰자료의 모델입력과 필요한범위검토는 여전히 증가한다.',
 '실모델 개선율·법률품질·실제 대용량 문맥 처리·GENOS/Oracle/NFS 미검증. 기존UNKNOWN·미등록효과·변경영향 부분검토 미해결. 최신MAIN 선택이 기존실패를 성공으로 소급하지 않는다.',
 '명시사용자 지시로 prepare/apply·MAIN135/Gold동일, data와모든원문·query/매핑/설정불변. MAIN134 pointer+Goldbinding 원복보존. 현장/메일/Git push0.',
 'prepare→edit→register_file→freeze rev001→check contracts/regressions/native→same-fixture scaling→release_prepare→check_prepared→activate→main_entry/gold_entry→finalize→hash/status/validate. 모든 결과/지원스크립트 SHA 결속. 실험표준에 따라 새효과실험은 새ADR.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
p.write_text('---'+front+'---\n\n# ADR1301 일반 ASSESS 중복 정리·MAIN135\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/001-ordinary-assessment-contracts.md').write_text('# 일반 ASSESS 입력·검토 계약\n\n## 1. 실행 메타\n\nrun-001/verified; 새실모델0·Oracle0.\n\n## 2. 사용자 요청\n\n정리해보고 메인에 반영해\n\n## 3. 입력과 기준\n\n'+values[3]+'\n\n## 4. 결과와 판정\n\n'+report+'\n\n## 5. 재현과 한계\n\n'+values[-1]+'\n')
(ADR/'실험/README.md').write_text('# 검증 기록\n\n[계약/모의API/메인](001-ordinary-assessment-contracts.md) · [manifest](manifest.json)\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'main':134,'historical':True},'verified':result},judge_disagreements=0,usage={'external_model_calls':0,'cost_usd':0,'oracle_calls':0},latency={'scope':'only synthetic contracts/components; no service speed claim'},error_taxonomy=[{'type':'PREPARATION_REGISTRATION_OR_PATH','count':2},{'type':'OBSOLETE_SCENARIO_FIXTURE','count':4},{'type':'MOCK_DOUBLE_SHARE','count':4},{'type':'SCENARIO_RECEIPT_FILTER','count':4}])
m['design']['code_isolation']['candidates'][0]['runner_sha256']=sha(Path(__file__).parent/'check.py');put(ADR/'실험/manifest.json',m)
entry=f'''<!-- ORDINARY_ASSESS_MAIN135_1301_20261103 -->
**2026-11-03 현재 로컬 MAIN135 — 일반 RAG 중복 입력·검토 요구 정리:** [반영·검증 TXT](09_ARTIFACTS/AUDITS/20261103-ordinary-assessment-contract-main/정리와_검증_메인반영결과.txt) · [ADR1301](04_EXPERIMENTS/ADR/ADR-1301-ordinary-assessment-contract-main/README.md). **{RELEASE}·서빙516/MAIN134대비34(제품3+pin31)·후보rev001/작업540일치**, 공식 prepare/apply·Gold동일. 일반 ASSESS/보완 무손실입력v2(구v1reader)/shared review_links 확대, 완전확보·비어있지않은 SOURCE_GOAL/STRUCTURE_SELECTION need만 명시scope USE/EXCLUDE/OPEN에서 서버조립·전체기존검증. 의미need/미확보/충돌·범위와이유 유지. **계약196(새25+기존171)/모의API22/준비API13/root16/Gold9 통과**(준비13은중복), fixture회귀1별도. 동일12구성조건에서2개 user24204→19590bytes·질문9→2/첫원문6→1, 자료별목적200개 필수행603→402·user182005→177391/schema34437→31459bytes; bulk200은203→202행, 모든입력전체정확복원. **새모델/Oracle0·대용량실모델효과 미검증**, UNKNOWN/N1·독립검토증가·부분재검토 미해결. 준비오류2/구v3 fixture4/모의공유변환4/가정저장필터4 실패원본보존·제품rev001불변. 원문·Goldquery/매핑/설정/연결기/layout4·기본OFF/GoldON 유지. **USER_DIRECTED_CUTOVER/quality_certified=false**, MAIN134+Gold이전binding 원복보존·DDL/Git push/메일/현장배포0. 아래MAIN134유지는이전시점이다.
<!-- /ORDINARY_ASSESS_MAIN135_1301_20261103 -->
'''
for name in ('AGENTS.md','00_SYSTEM/ARCHITECTURE.md'):
 p=ROOT/name;s=p.read_text();marker='ORDINARY_ASSESS_MAIN135_1301_20261103';assert marker not in s
 if name=='AGENTS.md':text=entry
 else:text=f'**2026-11-03 현재 로컬 MAIN135:** `{RELEASE}`·서빙516/작업540·Gold동일. 일반입력 무손실공유/공유검토 연결·완전확보 조사장부 서버조립을 적용했고 원문/권한/의미 검증을 유지한다. [검증·한계·원복](../09_ARTIFACTS/AUDITS/20261103-ordinary-assessment-contract-main/정리와_검증_메인반영결과.txt). 실제Qwen·큰자료법률품질 미인증. 아래 MAIN134는 이전 시점이다.\n<!-- '+marker+' -->\n'
 i=s.index('\n')+1;p.write_text(s[:i]+'\n'+text+'\n'+s[i:])
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
print('Documented MAIN135,196 contracts/22 unique API; failures and limits retained')
