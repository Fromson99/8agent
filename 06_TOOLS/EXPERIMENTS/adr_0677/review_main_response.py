"""Record a concrete ancillary answer error in the already returned MAIN response.
Read-only source inspection; no model call, quality regrade, or sealed experiment mutation.
"""
from pathlib import Path
import hashlib,json,sqlite3
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0677-investigation-main-integrity-generalization'
f=A/'artifacts/main-smoke-response.json'
response=json.loads(f.read_text())['body'];answer=response['answer']['text']
assert '유한회사(제270조)' in answer
db=R/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation/store.sqlite'
conn=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
row=conn.execute("select json from source_unit where document_id=? and unit_id=?",('7bbe815ff43b6635','699')).fetchone()
unit=json.loads(row[0]);assert unit['surface']=='제270조'
blocks=[{'block_id':b,'text':t} for b,t in conn.execute('select block_id,text from source_block where document_id=? and unit_id=?',('7bbe815ff43b6635','699'))]
conn.close();assert blocks and '합자회사의 정관' in blocks[0]['text']
record={'kind':'MAIN_RESPONSE_OBSERVATION','run_id':response['run_id'],'response_path':str(f.relative_to(R)),'response_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'model_calls_in_this_review':0,'source_experiment_or_grade_modified':False,'observation':'Core representative-director selection answer is supported by the delivered article 389(1). Ancillary prose associates limited companies with article 270, which actually concerns limited partnerships.','answer_fragment':'유한회사(제270조)','source_generation_id':'term-source-3b667f54bb11d9477888','document_id':'7bbe815ff43b6635','document_name':'상법','source_unit':unit,'source_blocks':blocks,'diagnostic_class':'ANCILLARY_WRONG_ACTOR_REFERENCE','follow_up':'In a new ADR, test keeping final prose within requested issue scope and separately auditing any additional actor/article associations. No effectiveness claim or new product change here.'}
(A/'artifacts/main-response-observation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
(A/'artifacts/MAIN_RESPONSE_REVIEW.md').write_text('''# 실제 MAIN 응답에서 발견한 추가 판단 오류

원문 전달과 실제 서비스 지문을 확인한 질의의 첫 문단은 전달된 상법 제389조 제1항을 근거로 선정 주체와 정관 예외를 답했다. 다만 두 번째 문단에 질문 밖의 설명을 추가하면서 `유한회사(제270조)`라고 썼다. 선택 원문 세대에서 상법 제270조의 실제 제목은 **정관의 절대적 기재사항**, 본문 주체는 **합자회사**다. 회사 유형과 조문을 잘못 연결한 추가 설명이다.

이 응답은 그대로 보존했다. 서비스 지문·원문 인용 검증 통과가 최종 답변의 모든 설명을 정답으로 보증하지 않는다. 조사 제어의 인용·채택 계약 검사와 최종 문장의 의미 판단은 구분해야 한다. 다음 ADR에서는 요청 쟁점 밖의 부가 설명을 억제하고, 추가 주체·조문 연결도 원문과 대조하는 일반화 개선을 비교할 대상으로 삼는다. 이 기록에서 제품 수정, 새 모델 호출, 실험 재채점은 하지 않았다.

- [관찰·해시·선택 원문](main-response-observation.json)
- [수정하지 않은 실제 응답](main-smoke-response.json)
''')
print('Ancillary MAIN answer mistake recorded; no model calls or experiment regrade.')
