"""Read-only source audit report; no engine/model invocation or setting change."""
from pathlib import Path
from collections import Counter
import ast
import csv
import hashlib
import json

ROOT = Path('/home/jin/8-AGENT')
OUT = Path(__file__).parent
PREFIX = '02_BACKEND/semantic_runtime/legal_agent/'
rows = []


def add(block, name, value, kind, behavior, continuation, source, needle, status='현행'):
    path = source if '/' in source else PREFIX + source
    lines = (ROOT / path).read_text(encoding='utf-8').splitlines()
    found = next((i for i, line in enumerate(lines, 1) if needle in line), None)
    if found is None:
        raise ValueError((path, needle))
    rows.append(dict(id=f'L{len(rows)+1:03d}', block=block, name=name, value=value,
                     kind=kind, status=status, behavior=behavior, continuation=continuation,
                     path=path, line=found, expression=lines[found-1].strip()))


add('공통', '원문 질문 길이', '10000자', '계약 상한', 'runtime.request의 질문 길이 계약. 초과 입력을 자동으로 앞부분만 잘라 통과시키지 않는다.', '요청 계약 위반 처리. 모델이 출력하는 task 600자 제한과 별개다.', '00_SYSTEM/SCHEMAS/term-runtime-v1.schema.json', '"maxLength": 10000')
add('공통', '물리 모델 시도', '40회', '실행 중단', '분류·명령·확인·탐색·판단·수정·전송 재시도 모두 같은 원장에 소비한다.', '동일 request 재개는 기존 사용량을 이어받는다.', 'repository.py', "budget['model_reserved'] >= cap")
add('공통', '마지막 판단용 예약', '3회; 조사 한계 37회', '실행 중단', 'INVESTIGATE는 40-3=37 시도 상한, FINALIZE는 전체 40 시도 상한.', '추가 조사 전 남은 조사 시도가 2회 미만이면 탐색을 정리한다.', 'repository.py', "cap = budget['model_limit']")
add('공통', '도구 행동', '1024회', '실행 중단', '공통 원장의 reserve_tool에서 실제 도구 시도를 제한한다. 화면 이동과 모든 SQL 조회를 각각 1회로 세는 것은 아니다.', '초과는 BudgetExhausted. 성공한 기록은 남는다.', 'repository.py', 'tool_used<tool_limit')
add('공통', '요청 시간', '1800초', '실행 중단', '전체 요청 deadline. 동일 요청 재개 시 최초 deadline 유지.', '재개한다고 새 1800초를 주지 않는다.', 'completion_budget.py', 'deadline=min(')
add('공통', '한 모델 호출 timeout', 'min(180초, 남은 시간, 단계 timeout)', '실행 중단', '모델 호출 단위 timeout을 제한한다. 탐색/참조도 남은 실행 시간과 함께 적용한다.', '네트워크 timeout 등은 완료로 취급하지 않는다.', 'memory_binding.py', 'limit=min(180,')
add('공통', '모델 출력', '6400토큰', '생성 상한', '로컬 모델 정책의 max_output_tokens로 팩토리가 프로필 값을 결속한다. 입력 6400토큰 제한이 아니다.', 'finish_reason이 stop이 아니면 로컬 어댑터가 불완전 응답으로 거절한다.', 'bounded_source_session.py', "'max_tokens': self.profile['max_output_tokens']")
add('공통', '동시 요청', '프로세스당 4개', '접수 제한', '선택 로컬 프로필 기본값의 semaphore. 초과는 즉시 접수 거절한다.', '대기열로 무한 대기시키는 설정이 아니다. GENOS의 0 오버라이드는 별도.', '02_BACKEND/semantic_runtime/legal_agent_adapter.py', "request_limit = self.profile['max_concurrent_requests_per_process']")
add('공통', '입력 길이 설정', '100000자', '부분 경로 검사', '참조 JSON 입력 길이를 검사한다. 모든 memory/법령 탐색/판단 입력을 자동 슬라이스하는 공통 검사는 확인되지 않았다.', '현재 법령 SELECT/ASSESS의 전체 입력은 이 값만으로 상한 보장되지 않는다.', 'unit_relations.py', 'if len(json.dumps(data,ensure_ascii=False))>max_context_chars:')
add('공통', '입력 byte 메타데이터', '2000000바이트', '강제 안 됨', '모델 binding에 남아 있으나 프로필 코드가 inert metadata라고 명시한다. 실제 요청 크기 강제 검사로 간주할 수 없다.', '크기 초과 시 2MB로 자동 자르는 동작이 없다.', 'domain.py', '# Old pinned byte fields remain inert metadata', '비활성 메타데이터')
add('공통', '공개 자료 범위', '승인 목록 145문서와 요청 권한의 교집합', '권한 필터', '개수 때문에 top145를 자르는 것이 아니라 승인된 문서 ID만 허용한다.', '다음 페이지로 권한 밖 자료를 열 수 없다.', 'local_gemma.py', 'scope-allowed')
add('공통', '모델/provider fallback', '0; fallback_allowed=false', '전송 제한', '고정된 Qwen3.8/Parasail 경로 외 자동 대체 없음.', '장애를 다른 모델의 성공 응답으로 덮지 않는다.', 'local_gemma.py', "'quantizations': ['fp8'], 'allow_fallbacks': False")

add('LLM 1 분류', '짧은 안내 출력 길이', '2000자', '출력 계약', 'DIRECT answer의 maxLength. 질문이나 법령 본문을 2000자로 자르는 것이 아니다.', '초과 출력은 계약 거절/수정 대상.', 'source_query_planning.py', "'answer': {'type': 'string', 'maxLength': 2000}")
add('LLM 1 분류', '분류 이유 길이', '1000자', '출력 계약', 'CASE/DIRECT reason의 최대 길이.', '초과 출력은 계약 거절/수정 대상.', 'source_query_planning.py', "'reason': {'type': 'string', 'minLength': 1, 'maxLength': 1000}")
add('LLM 1 분류', '진행 중인 사건 목록', '별도 개수 슬라이스 없음', '상한 없음', '현재 goals의 목적·사실·상태를 모두 투영한다.', '40회 호출/6400 출력 상한이 사건 입력 개수 상한은 아니다.', 'case_repository.py', "'current_goals':[{'task':g['state']['task']")

add('LLM 2 명령', '사건별 모델용 이력', '최초 1개 + 최근 48개 + 지목한 정정', '입력 생략', '중간 이벤트를 모델 문맥에서 생략. 중복을 제거하므로 항상 49개는 아니며 지목 정정 추가 시 49개를 넘을 수 있다.', '원본 DB 이력 보존. event_count/history_partial 표시. 이력 API after/limit로 조회 가능하지만 자동 추가 호출은 아니다.', 'case_repository.py', "events[:1]+events[-48:]")
add('LLM 2 명령', '개인 과거 질문 목록', '24개', '첫 페이지', 'personal_history에 질문 페이지 24개를 공급한다.', 'next cursor와 별도 조회 API가 있다. 명령 LLM이 이 페이지 뒤를 자동 조회하지는 않는다.', 'case_repository.py', 'knowledge.questions(principal,limit=24,')
add('LLM 2 명령', 'legal_wiki 힌트 목록', '8개', '첫 페이지', 'shortcut 켜짐+인증 사용자일 때 topic/question만 공급. 저장 결론은 힌트 입력에서 제외한다.', '전체 위키 조회 API는 별도. 다음 힌트 페이지 자동 모델 조회 없음.', 'shortcut_cases.py', 'pages=self.shortcut.search(principal,limit=8)')
add('LLM 2 명령', '과거 확정 경험 후보', '현재 shortcut 경로는 []', '기능 필터', 'ShortcutCases.candidates가 과거 경험으로 검증을 우회하지 못하게 빈 목록을 반환한다.', 'CaseRepository 경로의 32 후보 제한은 별도 조건부 경로.', 'shortcut_cases.py', '# Old USER_CONFIRMED experience cannot bypass')
add('LLM 2 명령', '문서 목록 입력 제거', 'allowed_documents/document_ids 제거', '필드 투영', 'resolver/command-check/repair 입력에서 재귀 제거. ACL용 원본은 호스트가 유지한다.', '모델이 전체 문서 ID를 골라 권한을 확대하지 않는다.', 'corrected_memory.py', "if k not in ('allowed_documents','document_ids')")
add('LLM 2 명령', '검색어 개수', '최대 4개', '출력 계약', '명령 queries 배열의 maxItems.', '초과는 거절. 자동으로 앞 4개를 잘라 실행하지 않는다.', 'corrected_memory.py', "COMMAND['properties']['queries'].update(maxItems=4)")
add('LLM 2 명령', '검색어 길이', '각 180자', '출력 계약', '명령 queries 원소 길이.', '초과는 거절/수정. 이후 SELECT RESEARCH 출력의 queries에는 같은 개수/길이 상한이 없다.', 'corrected_memory.py', "COMMAND['properties']['queries']['items']['maxLength']=180")
add('LLM 2 명령', '사실 개수', '최대 16개', '출력 계약', '명령 facts 배열의 maxItems. 기존 입력 사실 목록을 매번 [:16]으로 자르는 동작은 아니다.', '변경 출력 계약 거절/수정.', 'corrected_memory.py', "COMMAND['properties']['facts'].update(maxItems=16)")
add('LLM 2 명령', '사실 이름 길이', '100자', '출력 계약', 'FACT.name 길이 제한.', '초과 출력 거절/수정.', 'corrected_memory.py', "FACT['properties']['name']['maxLength']=100")
add('LLM 2 명령', '사실 값 길이', '600자', '출력 계약', 'FACT.value 문자열 길이 제한.', '초과 출력 거절/수정.', 'corrected_memory.py', "FACT['properties']['value']['maxLength']=600")
add('LLM 2 명령', '목적 task 길이', '600자', '출력 계약', '원문 입력을 600자에서 자르는 것은 아니지만 모델이 정리하는 task 출력은 600자 이하.', '원문 요구사항을 축소할 위험은 의미 검토 대상. 원문은 별도 보존.', 'corrected_memory.py', "COMMAND['properties']['task']['maxLength']=600")
add('LLM 2 명령', '명령 이유 길이', '600자', '출력 계약', 'command.reason의 maxLength.', '초과 출력 거절/수정.', 'corrected_memory.py', "COMMAND['properties']['reason']['maxLength']=600")
add('LLM 2 명령', '복원 필드 개수', '최대 5개; 중복 불가', '출력 계약', 'task/source_category/document_ids/facts/queries 다섯 상태 필드의 지정 복원.', '없는 필드나 중복은 허용하지 않는다.', 'corrected_memory.py', "COMMAND['properties']['restore_fields'].update(maxItems=5")
add('LLM 2 명령', '저장 명령 문서 ID 제한', '160개, ID 각 64자', '조건부 계약', '기본 COMMAND 계약에 존재. 현재 모델용 resolve 스키마는 document_ids를 null로 고정한다.', '현행 모델이 최대160 문서를 고르는 입력/행동으로 설명하면 안 된다.', 'corrected_memory.py', "COMMAND['properties']['document_ids'].update(maxItems=160", '호스트/기존 계약')
add('LLM 2 명령', '명령 의미 수정', '최초 1회 + 수정 1회', '재시도 제한', 'resolve의 range(2). 두 번째 의미/명령 검사 실패는 CLARIFY.', '출력 JSON gateway 수정 1회는 별도 층이며 같은 전체 예산 소비.', 'corrected_memory.py', 'for attempt in range(2):')
add('LLM 3 명령 확인', 'check 출력/입력 개수', '별도 maxLength/maxItems 없음', '상한 없음', 'context+command+execution_contract; valid와 reason 반환. 같은 model_context 필드 제거 적용.', 'false이면 LLM 2의 한 번 수정에 연결. 전체 출력 토큰/예산 적용.', 'corrected_memory.py', "CHECK = object_schema({'valid'")

add('LLM 4 쟁점 분리', '쟁점 개수', '최소1, 최대8개', '출력 계약', 'INTENT issues 배열 제한. 원문을 앞8문장으로 자르는 코드는 아니다.', '9개 이상의 요구를 그룹으로 묶을 수 있지만 요구 누락 여부는 의미적으로 확인해야 한다.', 'investigation_contracts.py', "'minItems': 1, 'maxItems': 8")
add('LLM 4 쟁점 분리', '목적·개념·쟁점 문장', '별도 개수/길이 상한 없음(issues 개수 제외)', '상한 없음', 'purpose/concepts와 ISSUE.question/subject에 별도의 숫자 길이 상한은 없다.', '전체 모델 출력 6400토큰 상한은 함께 적용.', 'memory_rag.py', "INTENT=object_schema(")
add('LLM 4 쟁점 분리', '기반 원문 조각 번호', '최대64조각; 나머지는 마지막에 합침', '무손실 분할', 'RequestContext.pieces의 기계적 문장 분할. 의미 쟁점 8개와 다른 번호 체계다.', '63조각 이후 원문 나머지 전체를 Q64에 보존. 버리지 않는다.', 'context.py', 'if len(pieces) == 63:')

add('검색 준비', '검색 변형', '최대3개', '검색 표현 슬라이스', '원문/업무 문맥/첫 줄 변형을 중복 제거 후 [:3].', '생략한 변형 전용 다음 페이지 없음. 원문은 보존.', 'source_recall.py', 'if v.strip()))[:3]')
add('검색 준비', '문서명 제거 보조 검색', '최대4개', '검색 표현 슬라이스', 'focused_queries에서 extra[:4].', '다른 표현은 SELECT 새 검색으로 제안 가능.', 'source_recall.py', 'extra[:4]+numeric[:2]')
add('검색 준비', '수치 보조 검색', '최대2개', '검색 표현 슬라이스', '숫자·단위 주변에서 만든 numeric[:2].', '모든 숫자 표현이 보조검색으로 생성되는 것은 아니다.', 'source_recall.py', 'extra[:4]+numeric[:2]')
add('검색 준비', '수치 앞 단어 탐색 범위', '앞40자', '문맥 창', '수치 앞 40자를 단어 후보로 삼는다. 모델 질문 입력을 40자로 자르는 것은 아니다.', '원문 질문은 별도 유지.', 'source_recall.py', 'match.start()-40')
add('검색 준비', '초기 검색 표현 묶음', '최대13개', '검색 표현 슬라이스', 'focused_queries가 중복 제거 후 [:13]. 실제 초기 상한이며 개별 표현 처리와 다르다.', 'SELECT law_search_queries가 있으면 이 묶음을 대신 쓰므로 이후 검색까지 모두13개 제한은 아니다.', 'source_recall.py', 'numeric[:2]))[:13]')
add('검색 준비', '한 검색 표현의 형태소', '최대32개', '검색 토큰 슬라이스', '질문/검색어 각각에서 고유한 내용 형태소를 등장순 [:32]로 사용한다.', '법령 본문/LLM 질문은 잘리지 않지만 뒤쪽 검색 개념이 빠질 수 있다. 여러 표현의 합집합은32개를 넘을 수 있다.', '02_BACKEND/semantic_runtime/fulltext.py', '[:MAX_TERMS]')
add('검색 준비', '일상어→법률 용어 연결', '최대4개', '검색 단서 슬라이스', 'NavigationMatcher._bridge가 용어 연결 후보 [:4] 반환.', '동일 표면어의 모든 연결이 시작 힌트로 들어가는 것은 아니다.', '02_BACKEND/semantic_runtime/navigation_match.py', 'return rows[:self.BRIDGE_LIMIT]')
add('검색 준비', '명시 구조 원문 선택', '최대16 source ID', '분기 경계', '명시 제목/조문 경로 결과가16개를 넘으면 구조 MATCH를 하지 않고 STRUCTURE_SELECTION_LIMIT으로 MISS.', '앞16개만 정답처럼 확정하지 않고 전문 검색 경로로 이어진다.', 'structure_query.py', 'if len(sources) > 16:')
add('검색 준비', '명시 정의 경로', '인용 용어 길이2~40자; 정의 후보최대16개', '분기 경계', '한 개의 인용 용어+한 문서의 정의에서만 직접 경로. 후보 초과면 직접 경로를 쓰지 않는다.', '일반 탐색은 별도 가능. 이 값으로 전체 질문을 자르지 않는다.', 'structure_query.py', 'if not rows or len(rows) > 16:')

add('LLM 5 탐색', '법령 후보 페이지', '12개', '페이지', '검색 결과 법령 목록은 페이지당12개. 현재 채택/직접 지정 법령을 덧붙여 최종 laws 입력이12개를 넘을 수 있다.', 'NEXT_LAWS. 전체 total/next_cursor 보존.', 'law_candidates.py', "limit=policy(s)['law_page_size']")
add('LLM 5 탐색', '첫 자동 진입 조항', '법령당1개', '초기 선택', '첫 법령 페이지의 각 법령에서 조항1개를 가져온다.', '법령별 OPEN_LAW로 다른 조항 선택 가능.', 'law_candidates.py', "allowed(s), limit=1)")
add('LLM 5 탐색', '첫 자동 진입 적중', '조항당1개', '초기 선택', '첫 진입 조항에서 hit1개를 확보한다.', 'NEXT_HITS로 다음 적중 위치.', 'law_candidates.py', "limit=1)['items']:")
add('LLM 5 탐색', '법령 열기/다음 조항 페이지', '4개', '페이지', 'OPEN_LAW/NEXT_ARTICLES는 설정 article_page_size=4.', 'NEXT_ARTICLES. 현재 ACTIVE 경로 추가 때문에 전체 branch 입력4개 제한은 아니다.', 'law_navigation.py', "limit=self.policy['article_page_size']")
add('LLM 5 탐색', '후보 조항 목록의 초기 크기', '8개', '첫 페이지', 'article_menu에서 아직 저장 조항 페이지가 없으면 하드코딩 limit=8. 설정4개와 별도.', '법령을 열면4개씩 제공하는 경로 이용. 이 요약 메뉴 자체가 항상8개 이하인 것도 아니며 저장 페이지를 재사용한다.', 'law_navigation.py', 'lc.allowed(self.s),limit=8)')
add('LLM 5 탐색', '조항 요약용 적중', '각3개', '요약 선택', 'article_menu가 처음3개의 hit 중 표시할 본문 위치를 선택.', '다른 위치는 해당 조항 적중 탐색으로 확인.', 'law_navigation.py', 'lc.allowed(self.s),limit=3)')
add('LLM 5 탐색', '조항 요약 미리보기', '앞240자', '본문 슬라이스', 'article_menu preview=body.text[:240].', 'READ_ARTICLES로 원문 읽기. 전문을 읽었다는 의미 없음.', 'law_navigation.py', "body['text'][:240]")
add('LLM 5 탐색', '읽은 적중 미리보기', '앞360자', '본문 슬라이스', 'add_reads가 profile.preview_chars=360으로 미리보기 생성. 코드 fallback400은 현행 설정으로 덮인다.', 'READ_PARENT/READ_SCOPE 또는 저장 원문 재열람.', 'law_navigation.py', "r['text'][:self.s.profile.get('preview_chars', 400)]")
add('LLM 5 탐색', '다음 적중 위치 페이지', '8개', '페이지', 'NEXT_HITS의 hit_page_size=8.', 'NEXT_HITS. SQL의 total/cursor 유지.', 'law_navigation.py', "self.policy['hit_page_size'])")
add('LLM 5 탐색', '미리보기 이력 표시', '최근8개', '입력 슬라이스', '그룹별 previews[-8:]만 현재 카드에 표시.', 'preview_total/omitted_previews. 전체 이력은 저장되나 앞 미리보기 전용 페이지는 없다. 과거 화면/원문 확인 경로.', 'law_navigation.py', "previews=group['previews'][-self.policy['hit_page_size']:]")
add('LLM 5 탐색', '형제 구조 목록', '앞8개', '입력 슬라이스', '부모 범위 sibling_rows[:8]. 제목 목록이며 원문 읽기 아님.', 'sibling_total/sibling_list_complete 표시. READ_PARENT로 부모 전체 원문.', 'law_navigation.py', "'siblings': sibling_rows[:self.policy['hit_page_size']]")
add('LLM 5 탐색', '이번 원문을 제시할 그룹', '최대8그룹', '입력 페이지', 'focus 우선+읽기 대기 그룹을 중복 제거 후 [:8]. 그룹당 현재 페이지를 보여준다.', '나머지 그룹의 읽기/이어보기 선택지와 상태 유지.', 'law_navigation.py', "if g in waiting]+waiting))[:8]")
add('LLM 5 탐색', '그룹별 원문 전달 페이지', '12000자', '무손실 페이지', '좌표 구간을 max_read_chars 크기로 나눠 전달한다. 줄바꿈·메타데이터는 추가되므로 전체 JSON길이는 더 크다.', 'READ_PARENT 이어보기. 후속 페이지 존재·실제 전달 범위 기록.', 'law_navigation.py', "limit = self.s.profile['max_read_chars']; pages")
add('LLM 5 탐색', '동시 여러 조항 읽기 선택', '최대8대상', '출력 계약', 'READ_ARTICLES targets maxItems8.', '다음 호출에서 추가 조항 읽기 선택 가능.', 'law_navigation.py', "(8 if kind == 'READ_ARTICLES' else 1)")
add('LLM 5 탐색', '다른 행동 대상 수', '1개; FINISH/PENDING/DECIDE는0개', '출력 계약', '여러 행동을 임의 묶어 한 번에 실행하지 못하게 제한.', '다음 탐색 호출에서 다음 행동 선택.', 'law_navigation.py', "'maxItems': 0 if terminal else")
add('LLM 5 탐색', '선택 이유 길이', '512자', '출력 계약', '행동 이유와 법령/자료 이유 maxLength512.', '초과 출력은 수정/거절.', 'law_navigation.py', "nonempty = {'type': 'string', 'minLength': 1, 'maxLength': 512}")
add('LLM 5 탐색', '탐색 메모 길이', '1024자', '출력 계약', 'notes maxLength1024. 현재 메모를 새 메모로 갱신하며 명시 행동·이유는 별도 이력에 보존.', '메모에 모든 이력을 다시 넣는 구조가 아니다.', 'law_navigation.py', "'notes': {'type': 'string', 'maxLength': 1024}")
add('LLM 5 탐색', '충분성 이유 길이', '512자', '출력 계약', 'sufficiency_reason maxLength512.', '초과는 수정/거절. 탐색 종료가 모든 쟁점 해결을 뜻하지 않음.', 'law_navigation.py', "'sufficiency_reason': {'type': 'string', 'maxLength': 512}")
add('LLM 5 탐색', '요약 참조 의존 카드', '앞16개', '입력 슬라이스', 'reference_overview dependency_cards[:16].', 'omitted_dependency_cards; FOLLOW_CONNECTION 상세 메뉴.', 'law_navigation.py', 'dependency_cards=cards[:16]')
add('LLM 5 탐색', '요약 미해결 참조', '앞8개', '입력 슬라이스', 'reference_overview unresolved[:8].', 'unresolved_count는 별도. 상세 참조 메뉴/내부 상태는 별도 유지.', 'law_navigation.py', 'unresolved=unresolved[:8]')
add('LLM 5 탐색', '새 검색 라운드', '전체8라운드; 초기 이후 재진입최대7회', '실행 중단', 'query_history가8이면 RESEARCH 메뉴를 추가하지 않음. 동일 정규화 검색은 별도 거절.', '미해결을 남기고 확보 근거 판단/중단. 평가상의 전체 호출40회와 별도.', 'law_navigation.py', "len(self.p['query_history']) >= self.policy['search_rounds']")
add('LLM 5 탐색', '진전 없는 반복', '2회', '실행 중단', 'no_progress>=2면 NO_PROGRESS 정리. 성공한 새로운 원문/선택이 있어야 진전으로 계산.', '새 assessment gap 서명이 바뀌면 이 카운터는 리셋되지만 공유 모델/도구 예산은 리셋되지 않는다.', 'law_navigation.py', "self.p['no_progress']>=self.s.profile['max_no_progress']")
add('LLM 5 탐색', '판단 단계 시간 예약', '30초', '실행 중단', 'SELECT의 remaining-30초, 탐색 내 FINALIZATION_TIME_RESERVE 검사.', '채택 근거가 있으면 판단으로 넘기고 없으면 미완료. 최종 응답30초 성공 보장 아님.', 'memory_rag.py', 'self.s.context.remaining()-30')
add('LLM 5 탐색', '행동 형식·계약 수정', '한 번', '재시도 제한', 'law navigation이 한 번 교정하고 gateway schema repair는0으로 꺼 중첩을 막음.', '재수정 실패는 MODEL_DECISION_UNRESOLVED bounded_result. 채택 근거가 있으면 FINISH, 없으면 PENDING.', 'law_navigation.py', '# Preserve the second failure; never execute or retry a third time.')
add('LLM 5 탐색', '중복 입력 필드 제거', 'flat articles, basis 본문, receipt span 목록', '필드 투영', 'articles는 laws[].articles에 한 번만 전송. basis text/spans·read_receipt의 *_spans는 제거하고 unverified_blocks 추가.', '법률 본문은 sources에서 전달. 저장된 원래 view/좌표는 보존.', 'law_navigation.py', "if k!='articles'" )
add('LLM 5 탐색', '행동·이유 체인', '개수 슬라이스 없음', '상한 없음', '모든 steps를 전달하며 반복 결정 내용을 judgments 참조로 중복 제거.', '저장 이력과 현재 입력 증가 가능. 전역10만자 자동 컷으로 보호된다고 볼 수 없음.', 'investigation_chain.py', '# Every explicit action and reason remains visible. No history truncation.')
add('LLM 5 탐색', '복귀 지점·저장 목록·채택 목록·부족 목록', '별도 개수 슬라이스 없음', '상한 없음', '현재 생성되는 return_points/saved_inventory/adopted_evidence/assessment_gaps에 숫자 top-k 없음.', '단 FINISH에서 assessment_gaps를 제거하는 현재 결함은 별도 존재.', 'law_navigation.py', "data['return_points']=trail.points(self.p)")
add('LLM 5 탐색', 'RESEARCH 검색어 출력', '별도 개수·길이 max 없음', '상한 없음', 'RESEARCH는 queries 최소1개. resolver의4개/180자 제한과 다른 스키마.', '중복 검색·검색 라운드·전체 출력/호출 한도는 적용.', 'law_navigation.py', "'minItems': 1} if kind == 'RESEARCH'")

add('원문 읽기', '읽기 응답의 블록/구간', '페이지당40개', '페이지', 'page_size=40. 내부41개 조회는 다음 항목 존재를 확인하기 위한 것.', 'block/char cursor로 같은 요청 범위의 다음 페이지.', 'source_tools.py', 'for n, row in enumerate(rows[:page_size]):')
add('원문 읽기', '읽기 응답의 본문', '페이지당12000자', '페이지', 'max_read_chars. 블록 중간에서 끝나면 char cursor 보존.', 'unit_reading.read가 cursor를 따라 요청 범위를 끝까지 읽음. 실패 시 완료 표시하지 않음.', 'source_tools.py', "remaining = self.profile['max_read_chars']")
add('원문 읽기', '누적 새 원문 확보량', '1600000자', '실행 중단', 'unit_reading initial_chars. 이미 확보한 검증 원문 재사용은 새 확보량과 분리.', '초과 BudgetExhausted. 일회 모델 입력1.6M자 제한이 아님.', 'unit_reading.py', "action_state['chars']+new_chars>POLICY['initial_chars']")
add('원문 읽기', '누적 원문 읽기 도구', '1024회', '실행 중단', 'unit_reading read_actions. 공통 tool1024와 함께 적용.', '한도가 더 먼저 걸리는 층에서 중단. 재진입 read_state 이어받음.', 'unit_reading.py', "action_state['count']>=POLICY['read_actions']")
add('원문 읽기', '블록 길이 SQL 처리 묶음', '400개씩', '무손실 처리 묶음', 'block_chars의 SQL IN 조회를400개씩 나눔. 전체 ID를 처리함.', '401번째부터 버리지 않는다.', 'unit_reading.py', 'for start in range(0, len(missing), 400):')

add('LLM 6 참조', '한 번에 조사할 출발 원문', '16개', '페이지/작업 묶음', 'anchors_per_round=16. 초과 미조사 출발점 표시.', '남은 작업과 스캔 상태를 보존. 작업/시간/호출 상한 안에서 계속.', 'unit_relations.py', "for anchor in anchors[:LIMITS['anchors_per_round']]:")
add('LLM 6 참조', '출발 원문별 연결 스캔', '256개', '페이지', 'SQL257개 조회 후256개 처리. more_available와 after_reference_id 기록.', 'cursor로 이어 스캔.256개를 전체 연결 수로 단정하지 않음.', 'unit_relations.py', "for raw_row in rows[:LIMITS['edges_per_anchor']]:")
add('LLM 6 참조', '한 모델 메뉴의 연결 그룹', '최대16개', '메뉴 묶음', 'groups_per_batch16; 그룹 JSON24k자 조건이 먼저 걸리면 더 적음.', 'omitted_groups/queue 유지, 후속 참조 메뉴. 실제 law 호출은 배치1개로 돌아감.', 'unit_relations.py', "len(rows)>=LIMITS['groups_per_batch']")
add('LLM 6 참조', '연결 그룹별 제시 문구', '앞8개', '입력 슬라이스', 'connections[:8]. reading_obligations는 모든 연결에서 작성.', 'omitted_connections. 전체 내부 연결 보존; 9번째 witness 자동 이어보기 전용 메뉴는 없다.', 'unit_relations.py', "connections = group['connections'][:LIMITS['witnesses_per_group']]")
add('LLM 6 참조', '참조 문구 본문', '각 앞600자', '본문 슬라이스', 'witness[:600]; 전체 원문/해시로 사전 검증한 뒤 짧게 표시.', 'witness_chars/witness_truncated 표시. 출발 원문 읽기 경로로 전체 문맥 확인 가능.', 'unit_relations.py', "'witness': witness[:LIMITS['witness_chars']]")
add('LLM 6 참조', '그룹 목록 JSON 크기', '24000자', '메뉴 묶음', '다음 그룹을 추가했을 때24k를 넘으면 목록 구성을 멈춤.', '첫 그룹부터 초과하면 reference_item_context_limit. 해당 그룹을 자동 분할하지 않는다.', 'unit_relations.py', "json.dumps(rows+[row],ensure_ascii=False))>LIMITS['relation_context_chars']")
add('LLM 6 참조', '최종 참조 입력 JSON 크기', '100000자', '실행 중단', '질문·출발 원문·이력 등 합친 data를 검사. gateway exact_evidence 추가 전의 검사다.', '초과 reference_context_limit; 이후 wire 중복/메타데이터를 포함한 전체 HTTP100k보장 아님.', 'unit_relations.py', 'if len(json.dumps(data,ensure_ascii=False))>max_context_chars:')
add('LLM 6 참조', '한 메뉴에서 FOLLOW 그룹', '최대8개', '출력 계약', '전체 표시16그룹은 각각 결정하지만 FOLLOW는8그룹 이하.', '나머지 SKIP/DEFER 등 이유 기록. 초과는 거절/수정.', 'unit_relations.py', "followed > LIMITS['follow_groups']")
add('LLM 6 참조', 'FOLLOW 그룹별 읽기 범위', '최대4개', '출력 계약', 'scopes_per_group4; SKIP/DEFER는0개.', '각 그룹에 제공한 scope만 선택. 다른 그룹 범위는 거절.', 'unit_relations.py', "'maxItems': LIMITS['scopes_per_group']")
add('LLM 6 참조', '참조 이유·적용 이유', '각512자', '출력 계약', 'reason/applicability_reason 최대512자.', '초과 거절/수정.', 'unit_relations.py', "'reason': {'type': 'string', 'minLength': 1, 'maxLength': 512}")
add('LLM 6 참조', '한 탐색 행동의 참조 판단 배치', '1개', '실행 묶음', 'law_navigation이 max_model_batches=1로 호출. 기본 batches64가 실제1로 좁혀짐.', '한 메뉴 판단 후 탐색으로 돌아옴.64번 연속 모델 호출이 아님.', 'law_navigation.py', 'max_model_batches=1,')
add('LLM 6 참조', '참조 엔진 기본 배치 상한', '64개; 현행 law 호출은1개', '조건부 기본값', 'max_model_batches 미지정일 때만64. 현재 law 호출에서는min(64,1).', '수정 호출 등 물리 시도40회는 별도 함께 적용.', 'unit_relations.py', "batch_limit=LIMITS['batches'] if max_model_batches is None", '기본값; 현행은1')
add('LLM 6 참조', '참조 작업 반복', '호출당128단계', '실행 중단', 'work_steps128은 스캔·큐 처리 등 내부 반복.128 LLM 호출을 뜻하지 않음.', 'reference_work_limit에 미조사 그룹/출발점 저장.', 'unit_relations.py', "work_steps<LIMITS['work_steps']")
add('LLM 6 참조', '참조 깊이', '8', '실행 중단', '깊이8 출발 원문에서 더 재귀 스캔하지 않음. 깊이7에서 따라 읽어 깊이8 자료를 확보할 수 있음.', 'REFERENCE_DEPTH_LIMIT로 남은 조사 표시.', 'unit_relations.py', "state['depths'].get(sid,0)<LIMITS['max_depth']")
add('LLM 6 참조', '참조 의미/선택 수정', '한 번', '재시도 제한', '유효 JSON이지만 연결 coverage/scope/applicability 검사에서 거절되면 수정 입력1회.', 'gateway JSON수정1회와 별도 층. 모든 시도는 전체40회에 소비.', 'unit_relations.py', "'rejected_decision':decision,'contract_error':str(exc)")
add('LLM 6 참조', '참조 전체 의무·미해결 목록', '별도 개수 상한 없음', '상한 없음', 'reading_obligations/전체 unresolved/관계 이력 등은 witness8개 표시와 별개.', '24k/100k 입력 검사 때문에 큰 한 그룹에서도 멈출 수 있음.', 'unit_relations.py', "for c in group['connections']],")

add('LLM 7 판단', '인용 선택 조각', '한 조각1200자', '무손실 분할', '채택 원문을 줄 단위로 나눈 뒤 긴 줄은1200자씩 계속 분할. 이후 조각을 버리지 않음.', '모든 비공백 조각에 S ID. 조각 전체 개수 top-k 없음.', 'completion_contracts.py', 'for start in range(0, len(line), 1200):')
add('LLM 7 판단', '판단 항목(claim) 수', '최대12개', '출력 계약', 'claims 배열의 maxItems=12. 한국어 문장 부호로 센 문장 수 제한은 아니다.', '초과 출력 거절/수정. 한 claim이 여러 쟁점/원문에 연결 가능.', 'completion_contracts.py', "'claims': {'type': 'array', 'maxItems': 12")
add('LLM 7 판단', '판단 항목 본문 길이', '각3000자', '출력 계약', 'claim.text 최대3000자. 원문 입력3000자 제한과 다름.', '전체 출력6400토큰이 별도 적용.', 'completion_contracts.py', "'maxLength': 3000")
add('LLM 7 판단', '형식 오류 수정 메시지', '최초16개 오류', '피드백 슬라이스', 'JSON Schema 오류가 있으면 errors[:16]만 모델 수정 피드백에 연결.', '나머지 오류가 이미 고쳐졌다는 뜻 아님. 다음 검사에서 다시 발견될 수 있고 수정은1회뿐.', 'completion_contracts.py', 'return errors[:16]')
add('LLM 7 판단', '판단 수정 횟수', '최초1회 + 수정1회', '재시도 제한', 'completion_execution range(2). gateway schema repair0으로 중첩 방지.', '수정 실패 InvestigationPending. 이 분기는 부분 답변 분기보다 앞.', 'completion_execution.py', 'for attempt in range(2):')
add('LLM 7 판단', '판단 부족으로 추가 탐색 복귀', '최대2회', '실행 중단', 'ASSESS_GAP_REENTRY와 assessment_reentry_limit2.', '한도/예산/시간 부족이면 근거 있는 claim은 부분 답변으로 이어갈 수 있음.', 'completion_execution.py', "['assessment_reentry_limit']")
add('LLM 7 판단', '부분 답변 설명 개수', '내부 저장 계약 최대64개', '저장 계약', '현재 completion 내부 ASSESS/COMPOSE limitations maxItems64. 구형8개 제한을 확장.', '앞64개로 슬라이스하는 코드가 아님.64 초과 생성이면 저장 단계 계약 실패 가능.', 'completion_contracts.py', "schema['properties']['limitations']['maxItems'] = 64")
add('LLM 7 판단', '판단 입력 원문·근거 조각·gaps', '별도 개수/본문 길이 슬라이스 없음', '상한 없음', '현재 채택 originals와 모든 evidence_options 공급; issue_assessments와 gaps 배열에 개별 maxItems 없음.', '쟁점은 제시된 것 전부 평가하도록 코드 검사. 전체 입력10만자 공통검사 없음.', 'completion_execution.py', "'issues': self.issues, 'sources': sources, 'evidence_options': options,")
add('LLM 7 판단', '참조 입력 필드', 'pending/groups/unresolved/limits만', '필드 투영', 'reference_navigation에서 선택한4필드만 판단에 전달. 전체 nav 본문·actions·batches를 복사하지 않음.', 'SELECT 저장 상태/행동 이력은 별도 유지. projection 목적과 누락 영향 구분.', 'completion_execution.py', "if k in ('pending', 'groups', 'unresolved', 'limits')")

add('수정 공통', 'gateway JSON 수정', '최대1회; 법령 탐색/판단에서는0회', '재시도 제한', 'resolve/check/intent/reference는 gateway max_schema_repairs1. source-law-navigation과 memory-assess는 단계 자체 수정만 사용.', '서로 다른 수정 층을 모두 합쳐1회라고 설명하면 안 됨.', 'bounded_source_session.py', "profile['max_schema_repairs'] = 0")
add('수정 공통', 'gateway 오류 로그', '앞2000자', '로그 슬라이스', 'OUTPUT_SCHEMA_INVALID 이벤트의 오류 문구.', '전체 model response는 원장에 별도 보존.', 'gateway.py', "'error': str(exc)[:2000]")
add('수정 공통', 'gateway 수정용 오류 설명', '앞1000자', '피드백 슬라이스', 'schema repair의 error 문자열.', '전체 오류 목록을 보장하는 피드백은 아님.', 'gateway.py', 'repair_error = str(exc)[:1000]')
add('수정 공통', 'gateway 수정용 잘못된 출력', '앞4000자', '피드백 슬라이스', 'invalid_response_excerpt. 원래 출력 뒤쪽은 수정 모델 입력에 없음.', '원시 출력은 원장에 보존. law/assess 자체 수정 입력은 이4000자 규칙과 별개.', 'gateway.py', "content[:4000] if isinstance(content, str)")
add('수정 공통', 'gateway 수정 대화', '최초2메시지 + 최신 수정1메시지', '대화 투영', 'messages[:2]에 최신 수정 지시를 붙인다. 원래 system과 user view 유지.', '수정 대화를 무한 누적하지 않음.', 'gateway.py', "request['messages'][:2]+[{")
add('전송 공통', '전송 재시도', '최대1회', '재시도 제한', 'completion_contract 경로에서 확실히 거절된429만 재시도. timeout/수신 불명/5xx는 자동 재전송 안 함.', '다른 모델로 fallback 안 함. 재시도도 물리40회에 포함.', 'gateway.py', "response.get('status_code')==429")
add('전송 공통', '429 대기', '최소1초; 최대30초 조건', '재시도 제한', 'Retry-After 대기가30초 이내이고 남은 시간이 대기+1초보다 커야 재시도.', '대기가 길거나 시간 부족하면 재시도하지 않고 장애 반환.', 'gateway.py', 'retry_delay<=30')
add('전송 공통', '동일 원문 중복 제거', '중복 span.text 제거', '필드 투영', 'exact_evidence.text에 포함된 span.text를 wire에서 제거. 좌표/본문은 유지.', '원문 요약이나 첫N자 잘라내기가 아니다. 저장 view/wire projection 검증.', 'gateway.py', "span.pop('text')")
add('전송 공통', '출력 스키마 중복 제거', 'compact user.output_schema 생략', '필드 투영', '응답 형식의 JSON schema는 유지하고 user 본문에 중복 삽입하지 않음.', '스키마를 제거해서 아무 형식이나 허용하는 동작이 아니다.', 'bounded_source_session.py', 'if not self.compact:')

add('결과·조회', 'API 오류 detail', '앞1000자', '응답 슬라이스', '사용자 오류 메시지 detail을1000자로 줄인다.', '내부 원장/예외 진단과 구분.', '02_BACKEND/semantic_runtime/app.py', "obs._redact_secrets(str(exc))[:1000]")
add('결과·조회', 'API 진단 필드', '지정5필드만', '필드 투영', 'schema_version/stage/cause_codes/resume_available/stop_reason. 목록앞5개가 아니라 필드 whitelist.', '자료 목록·blockers·issues 등 다른 상세 정보가 이 예외 응답에서 빠질 수 있음.', '02_BACKEND/semantic_runtime/app.py', "('schema_version','stage','cause_codes','resume_available','stop_reason')")
add('결과·조회', 'API 질문/경험/위키 페이지', '기본32; 최대100', '페이지', 'knowledge questions/search와 shortcut search의 페이지 개수.', 'after/next. LLM2에 실제 넣는24/8과 구분.', 'knowledge_repository.py', 'limit=max(1,min(limit,100))')
add('결과·조회', '사건 이력 페이지', '메서드기본50; API기본32; 최대100', '페이지', 'CaseRepository.events_page와 ShortcutRepository.history는 기본50, memory/query는 공통limit32 전달.', 'after/next로 다음 이력. 이력 DB 삭제 없음.', 'case_repository.py', 'def events_page(self,gid,principal,*,after=0,limit=50):')
add('결과·조회', '사건/제목 표시', '제목 앞200자', '메타데이터 슬라이스', 'shortcut 사건 제목 생성에 intake text[:200]. 원래 intake 질문 본문과 다르다.', '원문 intake/history에서 확인.', 'shortcut_repository.py', "event['payload']['text'][:200]")
add('결과·조회', 'session/request ID', '각256자', '입력 계약', '사건 API에서 비어 있지 않은 문자열과256자 제한.', '초과 거절. 질문 본문 길이 제한이 아님.', '02_BACKEND/semantic_runtime/app.py', "len(body[field])>256")

# These values are present, but do not cap the current law-first selector.
add('조건부·비활성', 'CORE/SUPPLEMENTAL 5 기본값', '기본5+5; 선택 프로필24+24', '비활성 경로', 'workflow_tiers_policy의 기본값은5지만 현재 설정24로 덮임. 현행 law SELECT는 tier 선택 함수를 실행하지 않음.', '법령 근거가5개나24개에서 자동 잘린다고 설명하지 않는다.', 'workflow_tiers_policy.py', "'max_core_sources':5", '현행 law 경로 미사용')
add('조건부·비활성', '선택 원문 excerpt', '1600자', '비활성 경로', '구형 tier 선택 span 상한. 현재 ASSESS evidence_options는1200자 조각화이며 전체를 제공.', '두 설정을 같은 본문1600자 컷으로 설명하지 않는다.', 'workflow_tiers_policy.py', "'max_source_excerpt_chars':1600", '현행 law 경로 미사용')
add('조건부·비활성', '원문 카드 페이지', '4개', '비활성 경로', 'source_page_size4는 구형 tier wire view. 현행 law 페이지4개와 값만 같고 별도.', '현재 법령 탐색에는 law/article/hit 상한이 적용.', 'workflow_tiers_policy.py', "'source_page_size':4", '현행 law 경로 미사용')
add('조건부·비활성', '구형 단위 초기 후보', '512개; 첫12그룹 읽기', '비활성 경로', 'unit_reading.prepare의 queue[:512], acquire_batch[:12]. law_candidates.prepare가 대신 호출됨.', '현재 법령 경로를 첫12그룹 읽기라고 설명하면 정확하지 않음.', 'unit_reading.py', "queue=queue[:POLICY['initial_units']]", '현행 law 경로 미사용')
add('조건부·비활성', '구형 단위 묶음', '그룹12000자/32단위', '비활성 경로', 'group_hits 묶음 경계. law_candidates의 초기 acquire_batch는group_hits를 호출하지 않음.', '그룹 분할은 내용 삭제와 별개.', 'unit_reading.py', "len(chunk)>=POLICY['group_units']", '현행 law 경로 미사용')
add('조건부·비활성', '구형 단위 선별', '선택16/재검토8; 후보8배치/검토8라운드', '비활성 경로', 'unit_selection 경로. 현행 law_navigation으로 먼저 dispatch.', '현행 전체 모델 시도40과 별도 과거 선택 정책.', 'unit_reading.py', "'batch_groups':12,'group_chars':12000", '현행 law 경로 미사용')
add('조건부·비활성', '구형 단위 미리보기/입력', '400자/80000자', '비활성 경로', 'unit_reading POLICY preview_chars/context_chars. law preview는현재360 및 article240.', '현재 모든 입력8만자 제한으로 설명하지 않는다.', 'unit_reading.py', "'preview_chars':400,'context_chars':80000", '현행 law 경로 미사용')
add('조건부·비활성', '구형 전역 top-k 회수', '질의64/seed64/참조seed16/선택128; 행동384/원문480000자/묶음50000자', '비활성 경로', 'source_recall_global의 숫자 정책은 law_candidates.discover 이전 dispatch 때문에 사용하지 않음.', '현재 법령 디렉터리12개 페이지는 전체top64삭제와 다름.', 'source_recall_global.py', "POLICY = {'query_top_k': 64", '현행 law 경로 미사용')
add('조건부·비활성', '구형 범위 top-k 회수', '질의64/seed96/참조seed32/범위선택160/합집합288; 범위행동512·640000자/합집합행동1024·1600000자/묶음50000자', '비활성 경로', 'source_recall._scoped_discover의 정책. 현재 법령 디렉터리 경로에서는 실행하지 않음.', '구형의 within[:8]/[:32], scoped[:72], ambiguous[:32]도 같은 조건부 경로.', 'source_recall.py', "SCOPED_POLICY = {'query_top_k': 64", '현행 law 경로 미사용')
add('조건부·비활성', '구형 평면 선별', '첫16/복구8/최종24/모델2회/240초', '비활성 경로', 'source_selection의 평면 selector. 현재 law_navigation에서 먼저 반환.', 'current SELECT는remaining-30초와 공유예산을 사용.', 'source_selection.py', "POLICY = {'first_limit': 16", '현행 law 경로 미사용')
add('조건부·비활성', 'source-query-plan 안내', '법령명3/검색어4개·각250자; 목차최대32페이지·outline6페이지', '비활성 경로', 'BoundedSourceSession.investigate의 별도 planner/목차 경로. 현재 사건의 native7단계에서 호출하지 않음.', '현재 명령 검색어4개·180자와 혼동하지 않는다.', 'bounded_source_session.py', 'def catalogue_pages(self, tool, args, label, max_pages=32):', '현행 사건 경로 미사용')
add('조건부·비활성', '옛 term-agent 선언', 'max_calls14/active_segments6/active_chars18000', '다른 엔진 설정', 'PIPELINE에 남아 있는 document navigation limits. 현재legal_agent 물리호출은40 프로필 적용.', '선언14를 현재40 상한 대신 보고하지 않는다.', '00_SYSTEM/PIPELINE.json', '"active_segments": 6', '현행 LLM 판단 경로 미사용')
add('조건부·비활성', '관계 스캔 시간', '5초', '강제 안 됨', 'relation_scan_seconds는 호환용. 관계 스캔은요청deadline 사용.', '현재 참조 작업에5초 watchdog이 있다고 설명하지 않는다.', 'relations_policy.py', '# relation_scan_seconds is retained', '호환용 미사용')
add('조건부·비활성', '구형 자동 참조 읽기', '깊이1/12대상/12000자/도구예약4', '조건부 기능', 'workflow_relations_tools의 MODEL/REVIEWER READ 후 자동 prefetch. 현재unit_reading은SYSTEM_POLICY 읽기라 이 자동 큐를 생성하지 않음.', '현재참조는LLM6의FOLLOW(최대8그룹·4scope·깊이8). 다른 상한이다.', 'workflow_relations_tools.py', "if actor in ('MODEL', 'REVIEWER'):", '현행 SYSTEM_POLICY READ 미사용')
add('조건부·비활성', '구형 관계 표시', '페이지12/14000자/preview총3600/요약60', '조건부 기능', 'generic relation tool/view/coverage 표시 상한. 현재law 참조는unit_relations의16/24k/600 등 적용.', '관련 함수가 파일에 있어도 현행law 입력의 직접상한으로 보고하지 않는다.', 'relations_policy.py', "'max_summary_items': 60", 'generic 도구·표시 경로')
add('조건부·비활성', '구형 반복·오류·검토', 'cycle3/browse깊이4/동일오류수정1/검토이의1', '조건부 기능', '일반ToolsSession/Coordinator.run의 상한. 현재run_case→unified_runtime 사건 실행과 구분.', '현재law max_no_progress2/판단재진입2/수정1과 별도.', 'tools_policy.py', "'browse_depth_limit': 4", '현행 사건 판단 루프 미사용')
add('조건부·비활성', '위키 procedure 후보 조회', '8페이지 항목', '조건부 조회', 'WikiExecution.plans가 PLAN/ASSESS 앞에8개 조회. 현재control=true이므로 과거판단을그대로복사하는분기는미사용.', '허용된 procedure의 현재원문읽기는가능. 모델힌트8개와 별도 호출.', 'wiki_execution.py', 'for unit in repo.search(self.principal,limit=8)', 'shortcut/인증/기능 설정 조건부')
add('조건부·비활성', '옛 경험 검색 후보', '32개', '조건부 조회', 'Memory.candidates 점수순[:32]. 현행ShortcutCases override는[]이며capture가 꺼진CaseRepository에서 가능.', '질문/경험 목록API pagination과 별개.', 'corrected_memory.py', "(-r['score'],r['id']))[:32]", 'capture 꺼진 경로')
add('조건부·비활성', '위키 구축 snapshot', '기본64기록/최대128/120000bytes', '비실시간 처리', 'shortcut.snapshot_page: 단일기록부터byte상한초과면거절; 페이지는다음offset으로계속.', '실시간LLM입력블록제한이아님. 별도컴파일작업.', 'shortcut_repository.py', 'def snapshot_page(self, ident, principal, *, offset=0, limit=64, max_bytes=120000):', '위키 컴파일 별도')
add('조건부·비활성', '위키 이전지식·관련입력·큐', '이전지식16/관련입력3/lease60초/재시도3', '비실시간 처리', 'shortcut compiler/queue의 함수 기본값. 현행질문판단의자료3개제한이아님.', 'nightly batch 최대8은 별도운영작업; 이 보고서에서는실행하지않음.', 'shortcut_repository.py', 'def related_inputs(self, snapshot, principal, *, limit=3):', '위키 컴파일 별도')
add('조건부·비활성', '도메인 선택 후보', 'concept/relation 각16; reason600', '코드 결정 계약', 'domain_control 스키마숫자는존재하지만 선택은코드가DISCOVERY+빈배열로고정. LLM별도호출없음.', '이를법률개념16개모델선별단계로표현하면안됨.', 'domain_control.py', 'schema[\'properties\'][key].update(uniqueItems=True,maxItems=16)', '코드 결정; 모델 선택 미사용')
add('조건부·비활성', '구형 구조·용어 입력 힌트', '문서3/구조8/제목100자/용어6/정의8; 정의 문서3 초과 시 모호 표시', '비활성 경로', 'structure_query.navigation_context의 첫 planner 입력 요약. 현재 사건의 명령·법령 탐색 입력을 이렇게 줄이지 않는다.', '정의 후보가 많거나 여러 문서에 걸치면 앞쪽을 정답처럼 채택하지 않고 모호 상태를 표시한다.', 'structure_query.py', "matches['documents'][:3]", '현행 사건 planner 미사용')
add('조건부·비활성', '구형 TermAgent 실행 기본값', '모델9회/라운드3/검색3/수정1/시간1800초; seed 앞4개', '다른 엔진 설정', 'TermAgent.retrieve 기본값이며 현재 통합 v6 사건 실행에 적용되는 40회와 다르다.', '이 함수의 literal[:4]도 현재 법령 후보 4개 제한으로 해석하면 안 된다.', '02_BACKEND/semantic_runtime/term_agent.py', "DEFAULTS={'max_rounds':3", '다른 term-agent 엔진')
add('조건부·비활성', '절차 재사용 불일치 설명 입력', '별도 개수·길이 슬라이스 없음', '상한 없음', 'procedure_deviation이 있으면 기대 입력·실제 입력의 비교 자료를 현재 모델 입력에 추가한다.', '현재 메뉴·시스템 지시·스키마 전체가 같을 때만 저장 결정을 재사용한다. 변경 시 모델 재판단에 연결되며 큰 비교 자료에 별도 길이 제한은 없다.', 'wiki_execution.py', "'procedure_deviation':unexpected or deviation", 'shortcut 절차 재사용 조건부')
add('조건부·비활성', '구형 완료 설명 목록 압축', '최대8항목; 앞7개 + 나머지 전체를 마지막 문자열로 합침', '무손실 목록 압축', 'NativeExecution.completion_limits는 원문 뒤쪽을 삭제하지 않고 마지막 항목에 합친다.', '현재 completion 계약은 limitations 최대64개이며 이 8항목 압축 경로를 쓰지 않는다.', 'memory_rag.py', "else values[:7]+", '구형 완료 계약')


def write_csv(path, values, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)


pointer = json.loads((ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
manifest_path = ROOT / pointer['manifest_path']
manifest = json.loads(manifest_path.read_text())
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == pointer['release_manifest_sha256']
selected = ROOT / manifest['code_root']
paths = [p for p in manifest['files'] if p.startswith(PREFIX) and p.endswith('.py')]
paths += [p for p in ('02_BACKEND/semantic_runtime/legal_agent_adapter.py', '02_BACKEND/semantic_runtime/fulltext.py',
                     '02_BACKEND/semantic_runtime/unit_fulltext.py', '02_BACKEND/semantic_runtime/navigation_match.py',
                     '02_BACKEND/semantic_runtime/app.py', 'service.py', '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json',
                     '00_SYSTEM/PIPELINE.json', '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json') if p in manifest['files']]
hash_checks = []
for path in paths:
    working = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    serving = hashlib.sha256((selected / path).read_bytes()).hexdigest()
    assert working == serving == manifest['files'][path], path
    hash_checks.append(dict(path=path, sha256=working, matches_selected_and_manifest=True))
for path in sorted({r['path'] for r in rows} - set(paths)):
    if path in manifest['files']:
        working = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        serving = hashlib.sha256((selected / path).read_bytes()).hexdigest()
        assert working == serving == manifest['files'][path], path
        hash_checks.append(dict(path=path, sha256=working, matches_selected_and_manifest=True))

write_csv(OUT / 'LIMITS_BY_LLM_BLOCK.csv', rows, list(rows[0]))

profile = json.loads((selected / '00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
profile_rows = []
notes = {
    'schema_version': '프로필 설정 계약의 버전 식별자. 길이·개수 제한이 아니다.',
    'profile_id': '선택된 통합 v6 설정 묶음의 식별자.',
    'max_model_attempts': '모든 단계·수정·재시도가 함께 쓰는 물리 모델 시도 40회.',
    'finalization_reserve': '전체 40회 중 마지막 판단을 위해 3회를 남김. 조사 시도 상한은 37회.',
    'max_tool_actions': '공통 원장의 도구 시도 1024회. 모든 내부 SQL 조회를 각각 한 번으로 세지는 않음.',
    'wall_seconds': '동일 요청 전체 1800초. 재개 시 최초 마감 시각을 보존.',
    'max_no_progress': '같은 조사에서 진전 없는 반복 2회이면 탐색 정리.',
    'max_schema_repairs': 'gateway의 JSON 수정 1회. 법령 탐색과 최종 판단은 0으로 바꾸고 단계 자체 수정 사용.',
    'max_read_chars': '도구 읽기 및 원문 전달 페이지의 12000자. 전체 원문 삭제 상한이 아님.',
    'page_size': '원문 읽기 페이지의 블록·구간 40개.',
    'preview_chars': '법령 탐색의 읽은 위치 미리보기 앞 360자. 조항 후보 요약은 별도 240자.',
    'max_concurrent_requests_per_process': '선택 로컬 설정은 프로세스당 동시 요청 4개. 초과 접수는 즉시 거절.',
    'selection_time_reserve_seconds': '탐색 정리에 마지막 판단용 30초를 남기는 기준. 판단 성공을 보장하지 않음.',
    'max_cycles': '일반 coordinator.run 전용; 현재 run_case의 판정2회 재진입과 다름',
    'max_same_error_repairs': 'ToolsSession 전용; 현재법령/판단 자체수정1회와 구분',
    'max_review_disputes': '일반 검토분기; 현재 최종 의미검토 없음',
    'browse_depth_limit': 'generic browse 도구; 현재 law 행동메뉴에는 browse 없음',
    'max_preview_chars': 'generic view preview 총량; law360/240에는 전체3600자 컷 미적용',
    'relation_page_size': 'generic relation도구/자동prefetch; unit_relations groups16과 별개',
    'max_relation_chars': 'generic relation도구; 현행 참조 메뉴24k와 별개',
    'relation_scan_seconds': '호환용; 강제5초 제한 아님',
    'auto_reference_read_depth': '구형자동prefetch 깊이1; 현행참조FOLLOW 깊이8',
    'max_auto_reference_reads_per_request': '구형자동prefetch; 현행SYSTEM_POLICY read는자동prefetch 큐 미생성',
    'max_auto_reference_chars_per_request': '구형자동prefetch; 현행unit cumulative1.6M와 다름',
    'tool_finalization_reserve': 'generic system_task예약; 현재 unit_read에 별도4 예약을 강제하지 않음',
    'max_summary_items': 'generic coverage메타데이터 요약; 현재행동체인에60개 컷 없음',
    'max_core_sources': '선택설정24, tier선택 경로 전용; 현행law selector 미사용',
    'max_supplemental_sources': '선택설정24, tier선택 경로 전용; 현행law selector 미사용',
    'max_source_excerpt_chars': 'tier1600; 현행판단은모든채택원문을1200자조각화',
    'source_page_size': 'tier카드4; article_page_size4와 별개',
    'source_selection_attempts': 'tier 선택횟수. 현재law/assess 수정은 각 코드에서1회',
    'question_obligations_enabled': 'profile검증에서true 요구; 현재사용자쟁점은INTENT 최대8',
    'numbered_references_enabled': 'profiletrue이지만 bounded structured 호출에서false로 오버라이드',
    'bounded_source_selection_enabled': 'true이며 통합v6의필수조건',
    'final_review_enabled': 'false; completion COMPOSE도추가생성/의미검토 없음',
    'max_context_chars': '참조 data JSON 검사 등에 적용; 모든LLM view 자동컷 아님',
    'max_transport_retries': '현재local completion팩토리1 유지; 알려진429만재시도',
    'model_binding': '파일null; service팩토리가고정로컬Qwen3.8 binding 주입',
    'max_output_tokens': 'local모델정책6400으로factory 결속; RuntimeModel 모든호출에 적용',
    'candidate_navigation.mode': '현행 법령 → 조항 → 적중 위치의 law-first-v1 탐색 경로.',
    'candidate_navigation.law_page_size': '검색 법령 목록 한 페이지 12개. 이미 연 법령을 추가하면 전체 입력은 12개를 넘을 수 있음.',
    'candidate_navigation.article_page_size': '법령 열기·다음 조항은 페이지당 4개. 처음 요약 메뉴의 limit=8과 별도.',
    'candidate_navigation.hit_page_size': '적중 위치 페이지 8개. 최근 미리보기·형제 목록 표시에도 이 값을 사용.',
    'candidate_navigation.search_rounds': '검색 표현 라운드 전체 8개. 동일 정규화 검색식을 반복하는 것은 허용하지 않음.',
    'candidate_navigation.allow_unresolved_completion': '참조 미해결이 있다는 사실만으로 조사 종료를 금지하지 않음. 답변 범위는 최종 쟁점 판단에서 검사.',
    'candidate_navigation.investigation_control': '원래 요구·쟁점·행동 이유·추가 조사 복귀를 추적하는 통합 조사 계약 활성.',
    'candidate_navigation.assessment_reentry_limit': '최종 판단에서 추가 탐색으로 복귀 최대 2회. 기존 호출·시간 사용량은 이어받음.',
    'candidate_navigation.completion_contract': '원문을 받은 뒤 채택하고, 채택된 원문 좌표에 연결된 판단으로 답변을 구성하는 현재 계약 활성.',
}
for key, value in profile.items():
    values = value.items() if isinstance(value, dict) else [(None, value)]
    for child, item in values:
        name = key + '.' + child if child else key
        profile_rows.append(dict(setting=name, selected_value=json.dumps(item, ensure_ascii=False),
                                 usage=notes.get(name, notes.get(key, '현행 선택 프로필; 적용 지점은 LIMITS_BY_LLM_BLOCK.csv 참조'))))
write_csv(OUT / 'SELECTED_PROFILE_ALL_FIELDS.csv', profile_rows, ['setting', 'selected_value', 'usage'])

# Mechanical discovery inventory retained separately; a match is not a live cap.
raw_rows = []
for path in paths:
    if not path.endswith('.py'):
        continue
    source = (selected / path).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        kind = None
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            kind = 'slice'
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in ('min', 'max', 'range', 'islice') or any(k.arg in ('limit', 'timeout', 'max_pages', 'max_model_batches') for k in node.keywords):
                kind = 'bound_or_batch_call'
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ('maxItems', 'maxLength', 'minItems', 'minLength'):
                    raw_rows.append(dict(path=path, line=getattr(value, 'lineno', node.lineno),
                                         kind='schema_bound', expression=str(key.value)+'='+ast.unparse(value),
                                         note='기계검색 후보; 현행 적용은 수동 설명 원장 참조'))
        if kind:
            raw_rows.append(dict(path=path, line=node.lineno, kind=kind, expression=ast.unparse(node),
                                 note='기계검색 후보; 해시 ID/원문 좌표/배치/비활성 코드도 포함'))
write_csv(OUT / 'SOURCE_BOUND_CANDIDATES.csv', sorted(raw_rows, key=lambda r:(r['path'],r['line'],r['kind'])),
          ['path','line','kind','expression','note'])

by_block = {}
for row in rows:
    by_block.setdefault(row['block'], []).append(row)


def section(blocks):
    text = ['\n[이 입력/판단에 적용되는 슬라이스·상한·생략]\n']
    for block in blocks:
        for r in by_block.get(block, []):
            text += [f"{r['id']} [{r['status']}] {r['name']} = {r['value']} ({r['kind']})",
                     '  실제 처리: '+r['behavior'], '  초과/후속 확인: '+r['continuation'],
                     f"  근거: {r['path']}:{r['line']}", '']
    return '\n'.join(text)


base = (OUT.parent / 'LLM_BLOCKS_R3/AGENT_LLM_INPUT_BLOCKS_UTF8.txt').read_text()
base = base.replace('우리 legal_agent를 LLM 입력과 한 번의 판단 단위로 풀어 설명',
                    '우리 legal_agent — LLM 입력·판단 흐름과 모든 관련 슬라이스·상한 주석')
base = base.replace('이 문서는 설명을 위한 추가 문서다.',
                    'R4: 각 LLM 입력 블록에 상한·슬라이스·필드 생략을 추가한 설명 문서다.\n'+
                    '숫자의 단위, 실제 적용 여부, 초과 시 처리, 후속 조회 경로를 함께 적었다.\n'+
                    '현행/조건부/비활성 값을 구분한다. 설정에 숫자가 있다는 것과 실제 강제는 다르다.\n'+
                    '이번 검토는 코드 읽기와 해시 확인이며 LLM 실호출·72상태 실행 검증이 아니다.\n'+
                    '앞 버전 원문은 보존하고 새 파일로 작성했다.\n\n이 문서는 설명을 위한 추가 문서다.')
insertions = {
    '3. LLM 1 —': ['공통'],
    '4. LLM 2 —': ['LLM 1 분류'],
    '5. LLM 3 —': ['LLM 2 명령'],
    '6. LLM 4 —': ['LLM 3 명령 확인'],
    '7. LLM 5 —': ['LLM 4 쟁점 분리', '검색 준비'],
    '8. LLM 6 —': ['LLM 5 탐색', '원문 읽기'],
    '9. LLM 7 —': ['LLM 6 참조'],
    '10. 답변 구성과 게시 —': ['LLM 7 판단', '수정 공통', '전송 공통'],
    '11. 한 질문을 처음부터 끝까지': ['결과·조회'],
}
for anchor, blocks in insertions.items():
    assert anchor in base, anchor
    base = base.replace(anchor, section(blocks)+'\n'+anchor, 1)

base = base.replace('원래의 잘못된 행동은 실행하지 않습니다.', '원래의 잘못된 행동은 실행하지 않습니다.')
base = base.replace('위 주요 코드 15개에서 작업 코드·선택 코드·manifest의 SHA-256 일치를 확인했다.',
                    f'이번 R4에서는 관련 파일 {len(hash_checks)}개에서 작업 코드·선택 코드·manifest의 SHA-256 일치를 확인했다.\n'+
                    f'수동 설명 항목 {len(rows)}개, 선택 프로필 필드 {len(profile_rows)}개를 기록했다.\n'+
                    f'기계 검색 후보 {len(raw_rows)}개는 원문 좌표·ID 생성·비활성 경로도 포함하므로 모두 현행 제한을 뜻하지 않는다.')
base = base.replace('    수정도 실패하면 현재는 예외로 종료될 수 있다.\n',
                    '    law run()은 수정 실패를 MODEL_DECISION_UNRESOLVED로 정리한다.\n'+
                    '    채택 근거가 있으면 FINISH 결과, 없으면 PENDING 결과로 이어진다.\n'+
                    '    PENDING·도구 예외·참조 실패 등 다른 종료 경로는 구분해야 한다.\n')
base += '\n14. 설정은 있지만 현행 경로에서 같은 제한으로 쓰지 않는 항목\n'+section(['조건부·비활성'])
base += '\n15. 선택 프로필의 전체 필드 — 항목 누락 없이 기록\n'
for row in profile_rows:
    base += row['setting']+' = '+row['selected_value']+'\n  적용: '+row['usage']+'\n'
base += '\n16. 읽기 편한 해석 기준\n'
base += '''
페이지: 이번에 일부만 보여주며 total/cursor와 다음 선택지가 있다.
본문 슬라이스: 앞부분/최근부분만 보여준다. 원본 저장과 모델 전달 범위는 다르다.
출력 계약: 모델에게 허용한 개수·길이를 초과하면 거절한다. 코드가 조용히 앞N개만 실행하는 것과 다르다.
무손실 분할: 1200자 조각,12000자 페이지,400개 SQL배치처럼 전체를 나눠 처리한다.
실행 중단: 호출·시간·새원문·참조깊이 한도. 못 한 일을 없다고 단정하면 안 된다.
필드 투영: 중복·권한 목록·진단 whitelist. 생략한 내용의 목적과 소비자를 확인한다.
비활성: 설정이나 함수에 숫자가 있지만 현행 호출 경로에서는 적용되지 않는다.

특히 다음 한도는 영향 추적이 필요하다.
 - 요구사항8개/목적600자/사실16개: 입력 의도를 압축하는 모델 판단에서 요구 누락 가능.
 - 검색 형태소32개: 긴 검색 표현의 뒷부분 개념이 검색에 반영되지 않을 수 있음.
 - witness600자/8문구,의존카드16개,미해결8개: 일부 제시 상태와 실제 전체 상태를 구분.
 - ASSESS 입력: 별도 전체10만자 검사가 없어 자료·이력 누적 시 큰 입력 가능.
 - 수정 feedback16오류/1000자/4000자: 실패 원인의 뒤쪽이 수정 입력에서 빠질 수 있음.

수정 목표는 각 제한 뒤에 total/omitted/continue/stop_reason을 남기고, 원래 요구와
미해결을 보존하는 것이다. 이 문서에서 제한 값을 변경하거나 상한을 해제하지 않았다.
이 제한이 실제 오답·지연을 얼마나 만들었는지는 이번 작업에서 측정하지 않았다.
'''
(OUT / 'AGENT_LLM_INPUT_BLOCKS_WITH_LIMITS_UTF8.txt').write_text(base, encoding='utf-8')

from build_readable_html import build_html
build_html(OUT, rows, profile_rows, len(hash_checks))

evidence = dict(scope='Static source audit of the previously explained legal_agent call flow; no model or engine execution',
                release_id=pointer['release_id'], generation=pointer['generation'],
                manifest_sha256=pointer['release_manifest_sha256'], file_checks=hash_checks,
                manual_entries=len(rows), selected_profile_fields=len(profile_rows),
                mechanical_candidates=len(raw_rows), block_counts=dict(Counter(r['block'] for r in rows)),
                runtime_profile_basis='Selected configuration plus service factory source; no current process readback',
                exclusions=['Socket.IO','GENOS field runtime','ingestion/index-build budgets','AD mode model/worker execution'],
                model_calls_executed=0, engine_scenarios_executed=0, artifacts=[])
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name != 'EVIDENCE.json':
        evidence['artifacts'].append(dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(OUT / 'EVIDENCE.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:evidence[k] for k in ('generation','manual_entries','selected_profile_fields','mechanical_candidates','model_calls_executed')}, ensure_ascii=False))
