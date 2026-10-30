"""Record measured scope, preserved fixture failures and unchanged MAIN."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[3];A=ROOT/'04_EXPERIMENTS/ADR/ADR-1087-ontology-context-input-sql';ART=A/'artifacts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
result=json.loads((ART/'check-002.json').read_text());assert result['passed']==122 and not result['failed'] and not result['import_leaks'] and not result['changed_files']
f=json.loads((ART/'freeze.json').read_text());base=json.loads((ART/'baseline-binding.json').read_text());code=ROOT/f['code_root']
changed=[]
for p in code.rglob('*'):
 if p.is_file():
  n=str(p.relative_to(code));h=sha(p)
  if h!=base['files'].get(n):changed.append({'path':n,'before':base['files'].get(n),'after':h})
measure={'schema_version':'ontology-preparation-measurements-v1','synthetic_only':True,
 'evidence_sql':[{'ids':n,'before':2*n,'after':2*((n+127)//128)} for n in [0,1,8,80,129,300]],
 'receipt_rows':{'stored_navigation_events':1000,'selected_presentation_events':2,'plan':'SEARCH event USING INDEX ontology_delivery_presentation_v1 (<expr>=?)','initial_index_build_cost_measured':False},
 'attach':{'two_provision_fixture':{'evidence_sql_before':4,'evidence_sql_after':2,'compiler_calls_before':2,'compiler_calls_after':1,'full_server_card_equal':True}},
 'ontology_card_characters':[{'mode':m,'selected':s,'before':b,'after':a,'reduction_percent':round(100*(b-a)/b,3)} for m,s,b,a in [('A1','all',2963,2471),('A2','all',3022,2530),('A1','one',2880,2388),('A2','one',2939,2447),('A1','none',2795,2303),('A2','none',2854,2362)]],
 'exact_source_semantics':True,'service_latency_measured':False,'model_tokens_measured':False,'quality_certified':False,'changes':changed,
 'working_tree_integration':False,'common1086_integrated_here':False,'new_model_calls':0,
 'remaining_review':'First index creation inside an outer transaction can be rolled back while the per-object optimization flag remains set. Queries remain correct, but indexed lookup is then not guaranteed until reopen. Address in separately frozen combined follow-up; no claim for that failure path.'}
put(ART/'measurements.json',measure)
m=json.loads((A/'실험/manifest.json').read_text())
m['runs'][0].update(status='complete',artifact_path=str((ART/'check-002.json').relative_to(ROOT)),sha256=sha(ART/'check-002.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','scope':'Frozen1079 function comparisons and unchanged SQL semantics'},'optimized':{'status':'complete','contract_passed':122,'quality_certified':False}},comparisons=measure['ontology_card_characters'],judge_disagreements=None,usage={'new_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'synthetic_tests_seconds':result['seconds'],'service_measured':False},error_taxonomy=[{'kind':'TEST_FIXTURE_MIGRATION','count':12,'details':'9 subtraction fixtures expected injected evidence method;2API expectations referenced prior wire version;1hash mutation failed DB constraint. Product bytes unchanged between rev001/002; receipts preserved.'}])
put(A/'실험/manifest.json',m)
old=(A/'README.md').read_text();header=old.split('---',2)[1]
body='''
# ADR-1087: 온톨로지 입력·조회 사전 수리

## 1. 결정 요약

온톨로지 전용4제품 파일을 수정한 `ontology-r2/rev-002`의122검사가 통과했다. A1/A2 원문·관계·값·미확보·전달 상태를 유지하며 내부 증명 필드 표시, 반복 검증·컴파일·근거 조회와 전달 이력 검색을 줄였다. 실모델0회, MAIN105·GENOS·공통 작업코드 미변경이다. 결정은 Proposed이며 A1 선택 품질은 아직 평가하지 않았다.

## 2. 문제와 변경 전 구조

ADR1086은 공통 입력 압축·후보20개 페이지·근거 일괄조회다. 이 후보의 온톨로지 경로는1079에서 분기했으며 공통 수정과 별도다. 기존 온톨로지 실행 review는 원문 중복을 이미 제거했다. 남은 문제는 매화면 전체 승인 스키마 검증, 사용하지 않는 반대 조건 컴파일, 조각별근거SQL, 전체 전달이력 탐색, 모델에 필요없는 원문 식별자·hash 표시다.

## 3. 가설과 사전 판정 기준

[사전 기준](artifacts/criteria.json)을 구현 전에 동결했다. 같은 원문·판단·선택·권한·미확보를 유지하고 필요한ID에 한정한 조회, A1/A2정보동등성, API·실패 계약이 통과해야 한다. 새 의미값·자동 채택·범위 확대는 금지했다. 최초 index 구축 비용과 rollback 뒤 index 캐시 상태는 측정·보완이 남았다.

## 4. 실험 설계

baseline은 완료1079/A2의 rev002 코드다. optimized는 그 코드의 ontology_context·ontology_review와 신규 ontology_io·ontology_input 네 파일 및30엔진pin+PIPELINE, 두 API/fixture 검사만 바꿨다. 기존 선택 정책·모델·데이터는 바꾸지 않았다. 1086은 의존 관계이며 이 결과에 결합한 것으로 보고하지 않는다. 신규 제품4파일+pin31파일+검사2파일=37개 차이다.

## 5. 데이터·모델·재현성

합성 원문·작은 요청 journal과 기존 승인 메타데이터만 사용했다. 실제 corpus나 외부 모델은 읽지 않았다. [동결](artifacts/freeze.json)·[기준선](artifacts/baseline-binding.json)·[동일 import 검사](artifacts/check-002.json)를 따른다. 외부 실험 정책은Qwen3.8/Parasail FP8·출력상한 없음이나 이번 모델호출0회다.

## 6. 결과

| 구간 | 이전 | 수정 |
|---|---:|---:|
| 선택 근거80개 SQL |160|2|
| 두조각 attach 근거SQL |4|2|
| 실행 review 컴파일 |2|1|
| 전달이력1000개의 현재화면 조회 |전체1000행 반환 후 필터|색인으로2행|
| 합성 A1카드 문자(all) |2963|2471|

122검사 통과, import 혼입0, 동결파일 변경0이다. A1카드16.605%는 해당 합성 카드의 문자 감소이며 전체 프롬프트·토큰·응답시간 감소가 아니다. [기계 집계](artifacts/measurements.json).

## 7. 사례별 오류 분석

처음110통과·12실패는 API format v2와 새 일괄조회에 맞지 않는 모의 fixture11개, 잘못된 길이의 hash 변조fixture1개였다. 검사만 수정한 rev002에서122개가 통과했다. 두 revision의 제품 바이트는 동일하다. 별도로 pytest hook 인자 오류는 제품 검사 전 실패했으며 원로그를 보존했다. 병행1086이 작업코드를 바꿔 최초 후보동결이 거부됐고, r1과 기록을 보존한 뒤 새upstream provenance의r2를 만들었다.

## 8. 비용·지연·회수 규모

모델0회·비용0, 실제 corpus로딩0이다. 계약검사 약20초는 서비스 성능 측정이 아니다. 원문선택·회수집합을 바꾸지 않는 합성 계약 검사로 법률 정답률·golden recall·selectivity는 해당하지 않는다. 조회단위를 명시해 함수호출수와 실제SQL수를 혼동하지 않았다.

## 9. 해석

온톨로지 전용 반복 작업과 입력메타데이터의 감소는 확인했다. 조회된 원문이 답변에 쓰이는지, 추가조사가 실제 올바른 원문선택으로 이어지는지는 이 검사로 입증하지 않는다. 공통1086과의 결합은 새동결 후보로 검증해야 한다.

## 10. 한계와 일반화 가능 범위

로컬SQLite 요청 journal만 바꿨으며 Oracle corpus SQL·GENOS 현장은 검사하지 않았다. 최초 index 구축은 기존관련이력을 읽는다. 최초생성이 외부 transaction에서 rollback되면 in-memory ready표시가 남아 재개시 성능계획이 보장되지 않는 검토사항을 후속에 남긴다. 원문결과 자체는 보존된다. A1실모델 적절성·법률품질은 미검증이다.

## 11. 운영 결정·롤백 조건

연구후보에만 적용했다. 기본작업코드와MAIN105를 이 후보로 덮어쓰지 않는다. 후속은 완료된1086 공통수정과 선별 결합하고 index rollback 경로를 보완한 뒤 A1선택검증용코드를 동결한다. 롤백 기준은 원문·관계·선택참조·권한·상태차이이며1079정본을 보존했다.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1087/check.py new-check-name.json
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1087-ontology-context-input-sql --final
```

모의검사는 외부호출하지 않는다. 재실행 결과는 새이름으로 보존하며 완료실험의 효과 재측정은 새ADR에서 한다.
'''
(A/'README.md').write_text('---'+header+'---\n'+body)
(A/'실험/README.md').write_text('# 온톨로지 사전 수리 검사\n\n질문 단위 법률 평가를 하지 않았다. 합성122검사와 정확한SQL·입력표현 비교는 [검사](../artifacts/check-002.json), [측정](../artifacts/measurements.json), [사전 기준](../artifacts/criteria.json)에 있다.\n')
artifact=json.loads((ART/'manifest.json').read_text());artifact['files']=[]
paths=[p for p in ART.iterdir() if p.is_file() and p.name!='manifest.json']+list((ROOT/'06_TOOLS/EXPERIMENTS/adr_1087').glob('*.py'))
for p in paths:artifact['files'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved ontology repair criteria, source binding, tests or measured result','contains_raw_prompts_and_outputs':False})
put(ART/'manifest.json',artifact)
print('Recorded122 contracts; MAIN unchanged')
