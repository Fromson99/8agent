from common import *
b=read(DES/'baseline.json');f=read(DES/'freeze.json');pf=read(DES/'port-freeze.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==124 and active['release_id']==RELEASE and active['deployment_basis']=='VALIDATED_ADR_PROMOTION'
assert release['files']==f['files'] and all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
assert sha(ROOT/release['data_path']/'manifest.json')==b['manifest']['data_manifest_sha256']
services=[read(ART/f'consumer-active-{mode}.json') for mode in ('off','on','db')];assert all(v['passed'] for v in services)
gold=read(GOLD/'binding.json');assert gold['engine_root']==release['code_root'] and gold['engine_manifest_sha256']==active['release_manifest_sha256']
assert all(sha(GOLD/Path(n).name)==h for n,h in pf['files'].items())
assert read(GOLD/'ACTIVE_MAPPING.json')==b['mapping']
for n in ('ontology_settings.json','runtime_patch_binding.json'):
 assert sha(GOLD/n)==b['gold_files'][str((GOLD/n).relative_to(ROOT))]
health=read(OUT/'gold-health.json');assert health['engine']==RELEASE and health['ontology']['ontology_enabled'] and health['ontology']['ontology_context']=={'mode':'DB'}
v=read(ART/'gold-active/consumer-verification.json');o=read(ART/'gold-active/ontology-verification.json')
assert v['status']=='PASS' and v['native_candidates']==100 and v['sql_calls']==73 and o['paths']==9 and o['sql_calls']==157
old={v for v in (ROOT/'09_ARTIFACTS/AUDITS/20261030-source-semantics-main123/adr-graph.log').read_text().splitlines() if v.startswith('ERROR:')}
new={v for v in (OUT/'adr-graph.log').read_text().splitlines() if v.startswith('ERROR:')};assert len(old)==16 and new==old
changed=read(ART/'working-integration.json')
report=f'''RAG 판단 공백 수정과 Gold 수정본 통합 결과
2026-10-30 / 로컬 MAIN124 / {RELEASE}

처리 결과
1. 미완료 최종 검토에서 판단 충돌·이전 판단이 제한사항에서 빠지던 공백을 수정했다.
2. 감독 모델 UNKNOWN을 일반 조사종료로 바꿔 최종·보완을 호출하던 경로를 차단했다.
3. 별도 Gold MAIN120 임시패치2건을 정식 엔진에 포함하고 Gold도 MAIN124를 직접 쓰도록 연결했다.
4. VCTR_SCTN_ID/DTLS_HASH_VALU 매핑과 Gold 온톨로지 ON/DB를 유지했다.

판단이 갈릴 때의 확인 결과
- 정상적인 최종 검토에서 OPEN인 material conflict는 원래도 LIMITED_ANSWER/PARTIAL로 처리됐다. 이 부분을 새 결함이라고 보지 않았다.
- 그러나 검토를 마치지 못한 INCOMPLETE 분기는 prior_needs만 제한사항에 표시했다. prior_conflicts와 prior_judgments는 영수증에 있었지만 최종 제한사항에서 빠졌다.
- 이제 필요·충돌·미완료 판단을 모두 표시하며, 어느 한쪽 판단을 코드가 정답으로 채택하거나 충돌을 자동 해결하지 않는다. 같은 제한사항 투영을 반복해도 중복되지 않는다.
- 기존 actual ADR1235의 감독 호출7은 공백응답 끝에 UNKNOWN이었다. 기존 코드는 TransportError를 ProgressHandoff로 바꿔 뒤의 최종·보완2호출로 진행했다.
- 이제 UNKNOWN은 원래 오류/상태로 전파하고 pending 영수증을 보존한다. 재개 진입점에서도 주 모델 선택/미리 선택한 원문 행동보다 먼저 확인한다.
- 합성 native API에서504, 최종ASSESS/compose0, 같은요청 재조회 추가호출0을 확인했다. 진행중실제요청 자동재시작/실제모델 재전송은 하지 않았다.

Gold 수정 통합 내용
- 동일 원문을 재조회해 evidence ID가 새로 생겨도 현재 확인한 span·내용·판본·anchor를 통과하면 온톨로지와 재결속한다.
- 새로 생성한 C1/C2/C3 claim ID와 그 claim_refs/claim_evidence_refs 키는 입력 온톨로지 구성요소의 별칭으로 바꾸지 않는다. 실제 근거ID는 계속 복원·검증한다.
- 부분원문/다른문서/변조본문/잘못된판본/관계없는근거 영수증은 계속 거절한다.
- 제품5파일: investigation_supervisor.py, law_navigation.py, read_judgment_final.py, ontology_assessment.py, navigation_input.py.
- 제품5+pin31=36변경. 나머지453서빙파일과 원래 MAIN123의 source semantics·need continuity·저장/스키마 계약을 유지했다.
- 작업·고정후보·실제선택489파일 일치. 데이터 generation·모델정책·기본 MAIN 온톨로지OFF 유지.
- Gold connect.py/새engine_common.py/binding.json은 현재 선택 release·manifest·489파일을 확인한다. 선택과 다르면 import 전에 거절한다.
- rev036 데이터 어댑터와 기존 검색게시ID는 유지했다. 고정MAIN120/MAIN123 및 기존 runtime_patches는 이력 보존, 현재 runtime exec 패치0이다.
- Gold 포트 통합과 기본 MAIN 데이터 교체는 구분한다. 기본 서비스 corpus를 Gold로 바꾸지는 않았다.

검증
- 고유223계약통과, 기존4불통과를MAIN123에서동일한마지막오류로재현, 이번범위새불통과0.
- 새기준 baseline11실패가수정후통과. 실제1233응답은그대로decode대조했으며 새모델응답이나새품질표본으로세지않았다.
- 신규 native UNKNOWN API1은모의전송, 기존 need continuity API10은완료/한번보완/반복거절/미해결/거절된필요보존/저장재조회조건을포함한다.
- 초기검사준비의 inspect충돌/pytest hook명/임시폴더/legacy fixture코드root오류는로그보존후수정했다. 제품검증기를우회하지않았다.
- 후보서비스59, 실제선택서비스 OFF/ON미설정/ON빈DB 각66=198조건, HEALTH3/모의HTTP3통과.
- Gold결속검사6:선택ID/manifest/승격근거불일치거절,선택코드import,혼합프로세스거절,patch비실행.
- 실제선택Goldhealth:13테이블60컬럼/21문서, ontology ON/DB.
- 실제Gold원문/용어/저장1024차원벡터3행/native100후보 SQL73.
- 실제Gold온톨로지3게시·12앵커·9경로 SQL157; 권한밖/이전판본/변조본문거절,원문부족9경로보류확인.
- 후보와선택후각각같은Gold구성요소를검사했다. 서로다른SQL경로를더해전체질문성능으로보고하지않는다.
- ADR1238최종검사통과. 전역graph기존16오류동일/새0.
- 외부모델0·새임베딩0·DB내용/DDL변경0·GENOS현장/Git/메일0.

아직 남은 부분
- 실제모델전체질문→최종법률답변 E2E는이번에재실행하지않았다. 공급자가공백을내는내부원인과발생률은해결됐다고주장하지않는다.
- 실제1235의 NEED_TARGET_INCOMPLETE는필요범위의원문을다확보하지않고RESOLVED로제출한것을막은검사다. 이검사는유지했다. 같은잘못을보완에서도반복하면여전히422로종료할수있다.
- 이번수정은미완료판단표시/실행중단/근거연결의공백을해결한것이다. 의미상모순을자동으로풀거나법률정답을인증하지않는다.
- MAIN123 도메인작성의실제누적저장0/두번째누적미검증은별도남은과제다.
- 벡터검색품질/recall·현장KURE/BGE-M3모델정합성·전체지연은별도검증이필요하다.

운영·롤백
정본: 01_DATA/ACTIVE/local/ACTIVE_RELEASE.json
엔진: 08_DEPLOYMENT/RELEASES/{RELEASE}/release.json
Gold: 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/README.txt
Gold ON: 같은폴더 ONTOLOGY_ON_GUIDE.txt
최신물리매핑: ACTIVE_MAPPING.json → mapping_local_vctr_current.json
MAIN123릴리스와원래Gold connect.py/binding.json을보존했다. Gold복구시두파일을함께복구한다.
롤백지침: 09_ARTIFACTS/AUDITS/20261030-judgment-gold-main124/gold-rollback.json
이미실행중인호스트프로세스를자동재시작하지않았다. 새전용프로세스에서선택된릴리스를읽는다.

근거
04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/README.md
04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/artifacts/contract-summary.json
04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/artifacts/checks-native-unknown.json
04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/artifacts/gold-active/
09_ARTIFACTS/AUDITS/20261030-judgment-gold-main124/activation.json
'''
(OUT/'판단공백_수정과_Gold통합결과.txt').write_text(report)
put(OUT/'completion.json',{'main':active,'files':489,'changed':36,'product_files':changed['products'],'technical_passed':223,'existing_failed':4,'new_failed':0,'candidate_service_checks':59,'selected_service_checks':198,'health_checks':3,'mock_http_calls':3,'gold_binding':bind(GOLD/'binding.json'),'gold_mapping':b['mapping'],'gold_health':health,'gold_source_vector_sql':73,'gold_ontology_sql':157,'ontology_publications':3,'ontology_anchors':12,'ontology_paths':9,'external_model_calls':0,'embedding_calls':0,'database_content_writes':0,'runtime_patches_executed':False,'full_live_e2e':False,'working_candidate_selected_exact':True,'new_graph_errors':0,'quality_certified':False})
note=f'''<!-- JUDGMENT_GOLD_MAIN124_20261030 -->
**2026-10-30 — 판단 공백·Gold 수정 통합 MAIN124:** [수정·검증 TXT](09_ARTIFACTS/AUDITS/20261030-judgment-gold-main124/판단공백_수정과_Gold통합결과.txt) · [ADR1238](04_EXPERIMENTS/ADR/ADR-1238-judgment-recovery-gold-main/README.md). **MAIN124 / {RELEASE}**. 미완료 최종검토의충돌·판단누락표시/중복방지, 감독UNKNOWN전파·pending보존·재개전차단, Gold동일원문새evidence재결속/새claim ID보호를정식코드에통합. **489파일·제품5+pin31=36변경·223통과/기존4MAIN123동일·새0**, 후보59/선택198(3설정)·HEALTH3/모의HTTP3. 모의native UNKNOWN504→최종0/동일재조회추가0. **별도Gold도같은MAIN124직접사용·runtime patch실행0**, 현재VCTR_SCTN_ID/DTLS매핑유지·GoldON/DB, 실제원문/용어/저장벡터3행/native100후보 SQL73·온톨로지3게시12앵커9경로 SQL157통과. 기본MAIN데이터/모델/온톨로지OFF유지·DB내용/DDL0. **외부모델/새임베딩0·전체실모델E2E아님**, 공급자공백원인·법률의미정확성/벡터품질미검증. NEED_TARGET_INCOMPLETE반복제출은계속거절422. MAIN123/고정MAIN120·기존Goldpatch/실패기록보존·GENOS현장/Git/메일0·graph기존16/새0. 아래Gold MAIN120+patch설명은통합전이력이다.
<!-- /JUDGMENT_GOLD_MAIN124_20261030 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;s=p.read_text();assert heading in s and '<!-- JUDGMENT_GOLD_MAIN124_20261030 -->' not in s;p.write_text(s.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();marker='- [ADR1238 판단 공백·Gold 통합 MAIN124](ADR-1238-judgment-recovery-gold-main/README.md) — 계약223/기존4동일·새0, 선택198, 실제Gold구성요소 통과·외부모델0/전체E2E미실행.\n'
lines=s.splitlines(True);lines.insert(2,marker);p.write_text(''.join(lines))
print('MAIN124 + Gold selected verification complete; report saved')
