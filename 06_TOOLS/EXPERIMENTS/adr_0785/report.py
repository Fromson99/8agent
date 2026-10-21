"""Close the implementation audit after exact code and actual-source checks."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
summaries={arm:{'status':'complete','known_legacy_failure_count':len(v['known_legacy_failures']),
 'contracts_passed':v.get('contracts_passed'),'detail_artifact':m['runs'][0]['artifact_path']} for arm,v in result['by_arm'].items()}
m['results'].update(status='complete',by_arm=summaries,comparisons=[],judge_disagreements=0,
 usage=result['usage'],latency={'kind':'Local synthetic contract tests; internal model and GENOS latency unmeasured'},
 error_taxonomy=['Known baseline legacy GENOS progress fixture failures: 14; identical on candidate',
  'Development fixture defects and staged-data binding failure retained in development logs'])
put(A/'실험/manifest.json',m)
put(A/'artifacts/implementation-decision.json',{'status':'Accepted for working-code integration',
 'authorization':'User instruction: 이거 구현해봐; source: current conversation',
 'working_integration_approved':True,'main_promotion_approved':False,'decision_eligible':False,
 'qualification_sha256':sha(A/'artifacts/run-001/result.json'),
 'candidate':read(A/'artifacts/design/freeze.json')['candidate'],
 'limits':result['limits']})
sections=[
 ('결정 요약','공통 workflow 실행부와 risk_team_compare_workflow의 작업 코드 통합을 채택한다. 대사 입력, RAG 원문 도구, 상태 저장·재개, 관계·판정 분리, 리포트와 표시 소비자를 연결했다. 선택 MAIN66과 GENOS 배포는 전환하지 않는다.'),
 ('문제와 변경 전 구조','기존 내규·외규 조회만으로는 두 문서의 비교 관계, 부족한 쪽의 재조사, 대사 상태를 독립적으로 관리할 수 없었다. 별도 업무 패키지를 기존 RAG의 실제 도구와 gateway에 연결한다. SourceSession을 사용하며 ask 재귀 호출은 하지 않는다.'),
 ('가설과 사전 판정 기준','정확한 원문·권한·코드·세대·판정 근거를 유지한 채 호출과 복귀가 가능해야 한다. criteria.json을 구현 전에 작성했다. 명시 관계 없는 확정 판단, 숫자만의 준수 판정, 실패한 조회의 부재 처리, 예산 초기화, 중복 호출·답변 변조·권한 누출은 허용하지 않는다.'),
 ('실험 설계','모의 모델의 유한 프로토콜과 합성 원문으로 실제 API 및 service dispatcher를 실행한다. 현행 길이복구·원문·출처·실패 회귀를 함께 확인한다. 문서 제외 변경이 작업 중 도착해 첫 동결 전에 integrated 후보로 재결합했다. 초기 후보와 이력은 보존했고 app.py는 원래 바이트를 기준으로 삼방향 병합했다.'),
 ('데이터·모델·재현성','코드331파일과 검사·runner를 동결했다. 실제 외부·내부 모델 호출0회이며 모델 응답은 모두 합성이다. 제공 DOCX는 native OOXML 구조화→DatasetPackage/SourceSet→기존1546문서와 결합한 새1547문서 세대로 구축했다. 최종 API에서 제15조 원문을 확인한다. 사진 전사·2018판본·현재 유효성 미확인을 보존한다.'),
 ('결과',f"동결 코드의 선택된 계약·회귀 {result['contracts_passed']}개 통과. 별도 legacy GENOS 진행 표시14실패는 기준·후보에서 동일하다. 실제 DOCX의 API 원문 조회, 원본 해시, 모델0회, 미확인 상태를 확인했다. 법률 정답률이나 holdout 품질 평가는 수행하지 않았다."),
 ('사례별 오류 분석','개발 중 등록 미완료 도구 상태가 기존 journal enum과 달랐던 결함은 UNRESOLVED와 별도 NOT_REGISTERED 원인으로 수정했다. 모델 응답 직후 중단은 원래 수신 기록을 재검증해 복구하며 불명확한 송신은 재전송하지 않는다. 완성 전 데이터에는 navigation binding이 없어 API가 실패했으며 이를 완성 세대로 오인하지 않았다. 각 실패 로그를 보존한다.'),
 ('비용·지연·회수 규모','원문·용어·정의·참조 도구를 재사용한다. 복귀2회, 같은 판단 수정1회, 총 모델/도구/deadline은 기존 선택 프로필의 실제 journal 예산을 공유한다. 전체 전문 색인은 기존 유지 실행기로 재구축했다. 후보 회수 효과·정답 recall·실제 내부 모델 비용/지연은 측정하지 않았다.'),
 ('해석','계약 검사는 근거와 상태의 보존 및 실패 분류를 뒷받침한다. 문장 유사성·스키마 통과를 법률 관계나 준수의 증명으로 취급하지 않는다. 내용 대응만, 불명 판본, 미확보 산식은 보류한다. 상충 판정 이후 부합 문서를 찾는 재검색은 하지 않는다.'),
 ('한계와 일반화 가능 범위','현재 실제 문서에는 승인된 현재 유효성 메타데이터가 없으므로 확정 적용 판단을 하지 않는다. 내부 모델 의미 판단, 복잡한 법률 관계의 정확도, GENOS NFS 잠금/지연/리비전/화면은 미검증이다. 인증 resolver 또는 단일 사용자 서버 설정이 필요하며 body의 사용자·팀은 권한 부여 수단이 아니다. 임의의 중첩 workflow 재귀 호출은 제공하지 않는다.'),
 ('운영 결정·롤백 조건','사용자 구현 요청 범위에서 검증된 변경만 작업 코드에 적용한다. apply 전 현재 upstream 해시를 대조하고 변경 전 바이트를 보존한다. 다른 수정과 충돌하면 덮어쓰지 않는다. MAIN 승격은 이번 감사의 자동 결과가 아니며 별도 자격·plan/confirm 절차를 따른다. 원문·활성 포인터·완료 실험은 보존한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_0785/{prepare,rebase,freeze,audit,report,integrate}.py 및 stable adr_structure.py validate --final/graph. 완료 결과는 덮어쓰지 않는다. 일반 개발 회귀는 run_tests.py로 작업 코드에서 실행할 수 있으며 새 효과 비교는 별도 ADR을 예약한다.')]
metadata=f"---\nadr_id: ADR-0785\ntitle: Risk팀 대사 워크플로우 실행·복귀·근거 계약 구현\nstatus: Accepted\ndecision_date: 2026-10-15\nphase: audit\nin_sample: false\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(metadata+'\n\n'.join('## '+str(i)+'. '+t+'\n\n'+v for i,(t,v) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 대사 workflow 구현 계약 감사\n\n모의 응답·합성 원문 계약 검사와 실제 DOCX의 모델 미사용 조회. 상세 결과는 ../artifacts/run-001/result.json. 내부 모델 법률 판단·GENOS 현장 품질 인증이 아니다.\n')
print('Implementation decision recorded; MAIN promotion not authorized by this audit')
