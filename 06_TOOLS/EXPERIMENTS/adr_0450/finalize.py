from runtime import *
import json

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 v=read(A/'verification.json');m=read(D/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'verification.json'));m['results'].update(status='complete',by_arm={'baseline':{'execution':'Completed ADR0449/multi rev002 code reference, not replayed'},'typed':v},comparisons=[],usage={'model_calls':0,'external_transmission':False},latency={'not_measured':'ordinary contract checks; no performance comparison'},error_taxonomy=[]);write(D/'실험/manifest.json',m)
 sections=[
 ('결정 요약','등록 메타데이터의 타입을 질문 키워드에 붙이고 타입별 실행 도구 안내를 LLM 문맥/응답 스키마에 연결했다. 폴더→하위 폴더/트리→문서명 검색→문서 선택 경로를 추가했다. 후보 rev-001, 일반 계약16통과, 모델0. 실제 kofia는72문서·72하위 폴더. MAIN 미반영.'),
 ('문제와 변경 전 구조','ADR0449는 목록 요청의 문자열 패턴으로 provider를 필터링했지만, kofia가 폴더이며 여러 문서와 하위 폴더를 포함한다는 설명과 도구 선택지를 LLM에 주지 않았다. `kofia에 있는 문서 알려줘` 표현도 기존 목록 정규식에 잡히지 않았다.'),
 ('가설과 사전 판정 기준','본문 검색어와 폴더·문서·구조·좌표·용어 개체를 구별한다. 메타데이터 문자 매칭의 결과에는 타입·정체성·관계·권한 범위·가능한 도구가 붙는다. 동일 표기의 타입 충돌과 다른 경로의 같은 폴더 이름은 보존한다. 타입이 맞지 않는 도구·임의 핸들·범위 이탈을 거부한다. [실행 전 설계](artifacts/design-before-snapshot.json).'),
 ('실험 설계','완료 ADR0449/multi rev002의 정확한 자식이다. 일반 구현·연결 감사이며 baseline 재실행, 모델 호출, 정답률·회수율 비교 없음. 최초 snapshot 명령의 experiment-id 누락을 보정해 정식 snapshot/register/freeze를 수행했고, 후보 실행은 동결 뒤 검사했다. 개발 중 일반 단위 검사는 효과 평가로 사용하지 않았다.'),
 ('데이터·모델·재현성','부모의 합성 문서/폴더 계약과 모의 동명 용어·동명 폴더를 사용했다. 실제 확인은 선택된 로컬 DB의 document metadata와 검증된 origin projection만 사용했다. 원문 검색이나 외부 모델 전송 없음. [입력 해시](artifacts/input-lock.json).'),
 ('결과','계약16개 통과. 폴더 카드의 실제 포함 수·하위 폴더 수, 트리 순서, 제목만 검색, 현재 제시 핸들 제한, 문서 선택 이후 범위 축소, 구조 좌표 타입, 같은 단어의 폴더/용어 충돌, 모호한 폴더 선택, Result 계약을 검사했다. scripted provider가 받은 keyword_types와 OPEN_FOLDER 실제 실행까지 확인했다. 이는 실제 LLM 선택 성능이 아니다. [검사 결과](artifacts/verification.json).'),
 ('사례별 오류 분석','kofia 문서 목록은 folder 경로로 처리한다. kofia 문서의 지급요건·내용 질문은 목록으로 삼키지 않고 타입 안내를 포함해 기존 내용 탐색으로 넘긴다. 동일 규정 폴더가 kofia/krx 양쪽에 있으면 경로 선택을 요구한다. 폴더와 용어가 모두 kofia여도 두 타입을 병합하지 않는다. 아직 제시하지 않은 다음 페이지 핸들은 선택 enum에 넣지 않는다.'),
 ('비용·지연·회수 규모','모델0회·토큰0. 메타데이터 요청은 로컬 DB 조회이고 복잡한 질문의 기존 LLM 호출 문맥에 타입 안내를 추가한다. 별도 LLM 라우터 호출을 만들지 않았다. 답변 정답률·회수율·지연 전후 개선 주장은 없다.'),
 ('해석','문자 매칭을 없앤 것이 아니라 대상이 타입을 가진 저장 개체 색인으로 바뀌었다. 폴더 카드의 document_count/child_folder_count/parent_path는 현재 허용 문서 범위에서 계산한다. registry의 KH 핸들은 세션에서 실제 제시된 타입에 결속된다. 폴더 열기와 트리 보기는 근거 읽기가 아니며, 제목 검색은 document.name만 읽는다. SELECT_DOCUMENT 이후 문서·구조·후보·레지스트리 범위가 함께 좁아진다.'),
 ('한계와 일반화 가능 범위','새로운 미등록 별칭·의미 유사 표현은 자동으로 완전히 해결되지 않는다. 메타데이터 문자 매칭과 등록된 별칭을 사용한다. live LLM의 선택 정확도 미검증, GENOS 현장 미검증. 출력은 실제 저장 메타데이터를 반영하며 파서/원본 출처가 잘못된 경우 의미적으로 교정하지 않는다. kofia72는 선택 로컬 세대의 수이며 전체 외부 수집 문서 총량이 아니다.'),
 ('운영 결정·롤백 조건','`runtime.create_conversation`으로 주입한다. TypedAgent→TypedSession.context/response_schema→OPEN_FOLDER/FOLDER_TREE/DOCUMENT_TITLES/SELECT_DOCUMENT/DOCUMENT_OUTLINE→부모 select/assemble/answer와 대화 렌더러로 이어진다. 운영 registry·service·MAIN 변경 없음. 실험 주입을 부모0449로 되돌리면 롤백된다. [안내](GUIDE.md).'),
 ('재현 명령','`PYTHONPATH=02_BACKEND ADR450_TEST_FROZEN=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider 06_TOOLS/EXPERIMENTS/adr_0450/test_typed_navigation.py`. `verify.py`는 완료 산출물 덮어쓰기를 거부한다. 실제 kofia 카드/트리는 [공개 메타데이터 예시](artifacts/public-example.json). [최종 검증](VALIDATION.md).')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 키워드 타입과 탐색 도구 안내\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'실험/README.md').write_text('# 키워드 타입·도구 배선 계약 감사\n\n질문별 모델 평가 없음. 일반 계약16개와 실제 선택 DB의 kofia 메타데이터 연결만 확인했다.\n\n- [결과](../artifacts/verification.json)\n- [계약 출력](../artifacts/tests.json)\n- [실제 kofia 타입 카드](../artifacts/public-example.json)\n- [설계·계보](manifest.json)\n')
 index=R/'04_EXPERIMENTS/ADR/README.md';s=index.read_text();line='- [ADR-0450 키워드 타입·탐색 안내](ADR-0450-typed-keyword-navigation/GUIDE.md) — 폴더/문서/구조/좌표/용어 카드와 타입별 도구 선택지. 계약16통과, 실제 kofia72문서·모델0·MAIN미반영.\n\n'
 if 'ADR-0450 키워드' not in s:index.write_text(s.replace('# ADR workspace\n\n','# ADR workspace\n\n'+line,1))
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0450','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen typed candidate, metadata contracts and read-only verification'} for p in sorted(paths)]});print('typed routing audit recorded')
if __name__=='__main__':main()
