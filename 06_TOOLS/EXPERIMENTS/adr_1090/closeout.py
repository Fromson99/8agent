from common import *
import re,sys,subprocess
from datetime import datetime,timezone

def finish(a,accepted):
 m=read(a/'실험/manifest.json');art=a/'artifacts';result=read(art/'run-001/result.json');number=m['adr_id'];state='Accepted' if accepted else 'Rejected'
 if accepted:
  assert result['strict_success'] and all(result['checks'].values())
  assert '127 passed' in (art/'secondary/contracts.log').read_text()
  f=read(art/'design/freeze.json');assert all(sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items())
  text='사전 동결한 신규 페이지252조건과 실제 journal SQL20조건을 모두 통과했다. 관측 보조127검사도 통과했다. 제품430파일은 완료1086rev004와 동일하다. 기계 계약 범위에서 Accepted·promotion-candidate이며 법률 품질은 인증하지 않는다.'
  detail='1089의 fixture 기대값이 유지되는 metadata_json을 빠뜨려 첫 비어 있지 않은 SQL조건에서 실패했다. 1089실패·412페이지 성공·빈 SQL6조건 기록을 보존했다. 1090은 다른 페이지 크기4/9/13의0~83후보252조건과 원문4/6/12/24/82개×span2/4개×정순/역순20조건을 실행 전 동결했다. 기대값은 원래 입력 행으로 독립 조립하며 메타데이터 원문 문자열도 비교한다. 제품 코드 변경은0이다.'
 else:
  m['decision_eligible']=False
  text='검증 fixture의 기대값에서 metadata_json을 빠뜨려 기각했다. 제품을 수정하거나 검사를 완화하지 않았고 MAIN은 그대로다. 실행 전에 runner 구문 오류가 있었으며 그 원본도 보존한다.'
  detail='페이지412조건과 빈 journal6조건까지 통과했으나 첫 원문2개 조건에서 기대값이 원래 DB메타데이터 문자열을 누락한 오류가 드러났다. 남은35조건은 미실행이다. 이 실패 결과는 승격 근거가 아니며 후속1090은 독립 선점·동결했다.'
 m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'Fixed mathematical partition and independent original-row oracle; no baseline model'},'qualified':{'status':'complete','decision':state,'result':bound(art/'run-001/result.json')}},comparisons=[],usage={'new_model_calls':0,'offline_evaluator_calls':0},latency={'full_service_comparison':False,'primary_wall_seconds':result.get('wall_seconds')},error_taxonomy=[] if accepted else [{'kind':'fixture_oracle_missing_field','field':'metadata_json'}],main_wiring='promotion-candidate' if accepted else 'unchanged',quality_certified=False)
 for run in m['runs']:
  run.update(status='complete',sha256=sha(ROOT/run['artifact_path']),success_criteria_met=accepted)
 put(a/'실험/manifest.json',m)
 meta=(a/'README.md').read_text().split('---',2)[1]
 for k,v in [('status',state),('main_wiring','promotion-candidate' if accepted else 'unchanged'),('decision_eligible','true' if accepted else 'false')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
 body=f'''# {number} 공통 최소입력·SQL 기술 검증

## 1. 결정 요약

{text}

## 2. 문제와 변경 전 구조

최소 입력과 읽기 후보20개 페이지를 구현한1086은 알려진 질문의 관측 probe다. 그 결과를 소급해 분리평가로 바꾸지 않는다. MAIN105와 작업 코드에는 기존 판단·연결 범위·구조/별표 기능 등의 차이도 있다. 선택할 전체430파일과 MAIN105대비66차이를 design/integration.json에 명시했다. 기존 Oracle 물리 매핑과 공통 클라이언트 모듈도 이 테스트 코드 inventory에 포함되지만 로컬 SQLite 서비스의 경로이며 Oracle 현장 배선을 인증하지 않는다.

## 3. 가설과 사전 판정 기준

design/criteria.json·matrix.json을 첫 제품 실행 전에 동결했다. 모든 후보를 페이지마다 정확히 분할하고 원문·판단 연결·실행 대상을 보존하며 SQL을 전체 원문 조회2회 이내로 제한해야 한다. 누락·변조·실패·조건 생략을 허용하지 않는다. 실제 원문의 법률적 해석 정확도는 이 검증의 평가 대상이 아니다.

## 4. 실험 설계

{detail}

## 5. 데이터·모델·재현성

모의 문서·원문 행만 사용했다. 법률 corpus나 정답·judge 입력은 없다. 신규 모델0회, 네트워크0회다. 코드·프로필·SQL·데이터 세대·예산·출력상한 없음은 design/freeze.json 및 baseline.json에 결속했다. 후보는 연구 snapshot을 명시적으로 import하며 선택 MAIN은 검증 동안 바꾸지 않았다.

## 6. 결과

원시 조건과 결과는 artifacts/run-001에 있다. {text} 기존1086의127검사는 보조 회귀이며 새 법률 holdout로 세지 않는다. 본 실험은 페이지·원문 연결·SQL 기계 계약의 유한 검사다.

## 7. 사례별 오류 분석

{detail} 별개로1086 실제 질문은9모델호출 뒤 제한 답변이었다. 모델이 새 조문의 판단에 다른 조문의 J번호를 중복 사용했고 한 번의 수정에서도 반복했다. 재탐색은 같은 원문에 대한 보완 한도를 재설정하지 않아 새 행동0회로 종료됐다. 확인한 조항은 전달했지만 시간 기준은 미확인으로 남았다. 토큰 오류·DB오류·40회 전역 예산 소진이 아니다. 이 동작과 실제 원시 응답은 변경하지 않았다.

## 8. 비용·지연·회수 규모

신규 모델0회다. 이번 기계 검증으로 전체 응답시간·Oracle/GENOS 속도·법률 recall을 추정하지 않는다. 1086의 모델 밖82.254초 중 첫화면32.281초를 빼면49.973초다. 그중 session.prepare18.054초, 후속화면8.988초, 별도 함수 계측 없는 잔여22.930초다. 잔여를 전부 SQL이나 모델 시간으로 단정하지 않는다.

## 9. 해석

모델에 보낼 표현과 서버의 원문·권한·판단 연결 검증을 분리했다. 원문 내용과 판단 J번호·source_refs의 대응은 신규 projection 검사에서 보존됐다. 모델이 번호를 잘못 고르는 문제와 입력 축소의 기계적 무손실성은 구분한다.

## 10. 한계와 일반화 가능 범위

유한 모의 계약 통과는 모델의 원문 이해나 판단 품질 인증이 아니다. 첫화면32초와 기타 잔여 비용도 남았다.1086 전체 delivery회귀의 기존36실패는 변경 전후 동일했고 해결했다고 하지 않는다. 온톨로지1088·GENOS배포·Git push는 별도다.

## 11. 운영 결정·롤백 조건

{'사용자가 MAIN 반영을 명시했다. 완료된 이 기술검증 arm을 공식 hash 고정 prepare/apply --confirm-main으로 선택하고 실제 service 진입점을 별도 확인한다. source에는 promotion-candidate를 유지하며 활성화 receipt는 따로 기록한다. 심각한 원문·권한·상태 회귀 시 공식 rollback으로 MAIN105 복원 영수증을 남긴다.' if accepted else 'Rejected, MAIN unchanged. 후속1090을 별도 검증하고 실패 기록을 보존한다.'}

## 12. 재현 명령

동결과 실행 경로는 design/freeze.json이다. `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_{number.split('-')[1]}/run.py`는 해당 frozen revision을 검증·실행한다. 원래 결과는 덮어쓰지 않고 재실행은 새 ADR에서 수행한다. `adr_structure.py validate --final`과 graph를 stable runner로 실행한다.
'''
 (a/'README.md').write_text('---'+meta+'---\n\n'+body)
 (a/'실험/README.md').write_text(f'# {number} 기술 검증\n\n질문별 법률 답변 평가가 없는 모의 페이지·원문 journal 계약 검사다. 실험/manifest.json의 run과 artifacts/run-001/result.json을 참조한다. 신규 모델0회, {state}.\n')
 paths=[p for p in art.rglob('*') if p.is_file() and p.name!='manifest.json']+list((ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+number.split('-')[1])).glob('*.py'))
 put(art/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':number,'created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[dict(bound(p),bytes=p.stat().st_size,description='Frozen engineering contract, failure preservation or observed support; no legal quality claim',contains_raw_prompts_and_outputs=False) for p in sorted(paths)]})

finish(ROOT/'04_EXPERIMENTS/ADR/ADR-1089-compact-main-qualification',False)
finish(ADR,True)
index=ROOT/'04_EXPERIMENTS/ADR/README.md';s=index.read_text()
for number,slug,desc in [('1089','compact-main-qualification','fixture 원문 메타데이터 기대값 실패 보존'),('1090','compact-main-valid-oracle','신규272기계조건·관측127검사, 최소입력 MAIN 기술검증')]:
 name=f'ADR-{number}-{slug}'
 if name not in s:s=s.replace('# ADR workspace\n\n',f'# ADR workspace\n\n- [{name}]({name}/README.md) — {desc}\n\n',1)
index.write_text(s)
