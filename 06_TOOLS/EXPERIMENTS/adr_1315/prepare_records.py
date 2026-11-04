from common import *
m=read(ADR/'실험/manifest.json');criteria=read(DES/'criteria.json')
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=['Gold종류별SQLprojection·SQLite초기준비반복최적화후현행누적코드를사용자요청에따라MAIN반영한다. 실제답품질인증은별도.','1311은SQLite동등재생73.76%감소,1312는실제모델UNKNOWN으로FINISH효과미확인. 실제Oracle는이번수정효과미검증.','사전criteria.json 및 query-cases.json에 정확ID·오류·반복SQL·원문해시 조건 고정. 원문/ACL불일치와예산초과는중단.','현재538파일각동결·동일nativeSQL638준비계약과최신GoldCHAN_NO매핑보존. SQLitebefore/after→Oraclebefore/after각1회. 실제원문·구조hash·catalogue동일성및반복SQL을확인한다.','기존공개상법문서/동일store SHA, 로컬Oraclereadonly계정과게시Goldquery. 모델0, DDL/DML0.','아직실행전.','현재새실행전. 모든실패는원본보존하고기존결과로덮어쓰지않는다.','시작준비/사례/SQLexecute-fetch벽시간별도. 순수DBCPU아님. FTS페이지/순서/원문값보존.','실제SQL수와요청내재사용을확인하며코드mock검사와실제DB를분리한다.','로컬Oracle23,현장Oracle19/Dataiku부하/최종답품질인증아님.','검증후사용자요청으로공식prepare/apply·Gold동일MAIN결속·실제root/Gold진입점검사. 기존DB/매핑/세대/온톨로지값유지. 새모델0·현장배포0.','freeze.py→check.py→query.py sqlite→query.py oracle→원문대조/분석/보관/ADR최종검사.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n';p.write_text(front+'\n# SQLite·Oracle 다양한 조회 검증\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{b}' for i,(t,b) in enumerate(zip(titles,bodies),1))+'\n')
for q in m['questions']:
 (ADR/'실험'/q['file']).write_text(f'''# {q['case_id']}

## 1. 실행 메타

run-001, sqlite/oracle 단회, 원값exact, 현재미실행.

## 2. 사용자 질문 원문

SQLite와Oracle 둘다 다양한케이스를 테스트해 확인. 사례묶음: {q['case_id']}.

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

artifacts/design/query-cases.json 정확조문ID/오류및원문6블록. 정답ID는조회함수에전달하지않고결과assert에만사용.

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

모델탐색실험아님. 지정문서에서query-cases.json에고정한구조선택/용어만API에전달. 원문/결과전부artifacts/actual/<arm>/result.json에보존예정.

## 5. 제품 모델 호출 — run·arm별 실제 원문

[]; 모델호출을차단한조회검사. 모델0.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

[]; 없음.

## 7. 채점 호출과 반복 판정

모델0. 정확ID/오류/원문/해시·반복SQL수및두DB원값직접대조. 기준단회,재시도0.

## 8. 사례 최종 판정

미실행. 준비오류는별도로보존.
''')
(ADR/'실험/README.md').write_text('# 질문 인덱스\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
print('Prospective records prepared')
