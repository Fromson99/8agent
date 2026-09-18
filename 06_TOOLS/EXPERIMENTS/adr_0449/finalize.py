from runtime import *
import json

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 v=read(A/'verification-adapter-fix.json');m=read(D/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((A/'verification-adapter-fix.json').relative_to(R)),sha256=sha(A/'verification-adapter-fix.json'))
 m['design']['arms'][0].update(changes='Exact completed parent reference; not replayed',controls='Parent0448 frozen code; no model comparison')
 m['design']['arms'][1].update(changes='Multi-entry union/review guard and path/title/structure navigation implementation',controls='Frozen parent code and selected source generation; ordinary contracts only')
 m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}}
 m['dataset'].update(name='Ordinary synthetic contracts and read-only current metadata wiring',version='folder-navigation-contract-v1',frozen_source=str((A/'origin-projection.json').relative_to(R)),sha256=sha(A/'origin-projection.json'),version_note='Metadata identity/structure verification only, no legal interpretation or answer evaluation')
 m['results'].update(status='complete',by_arm={'baseline':{'execution':'Not replayed; completed parent code reference only'},'multi':v},comparisons=[],usage={'model_calls':0,'external_transmission':False},latency={'not_measured':'ordinary contracts, not a speed comparison'},error_taxonomy=['14 selected documents lack verified path origin; retained unknown','No stored 제1조제3항 in actual ESG rule; no ancestor fallback'])
 write(D/'실험/manifest.json',m)
 sections=[
 ('결정 요약','격리 후보 rev-002에 복수 진입점 합집합과 폴더·문서명·구조 범위 조회를 구현했다. 일반 계약30개 통과. 실제159문서 중145개의 폴더 출처를 연결했고14개는 미확인으로 유지한다. 모델0회, MAIN·원문·GENOS 변경 없음. Proposed/decision_eligible=false.'),
 ('문제와 변경 전 구조','이전 도구는 독립된 초기 A/A′ 진입점을 함께 검토하도록 보장하지 않았고, document.json에 폴더가 없어 내규/외부 분류를 확정할 수 없었다. 구조 노드는 있었지만 문서 목록→제목 검색→선택 유지→목차/정확 항 조회의 대화 연결이 없었다.'),
 ('가설과 사전 판정 기준','원본 폴더로 분류하고 문서 이름·구조 제목·특정 구조 안 본문을 분리한다. 허용 범위와 이전 선택 범위를 교집합으로 유지하며 빈 결과·없는 좌표·복수 문서를 임의 복구하지 않는다. 후보 미검토나 채택 근거의 범위 밖 참조가 있으면 sufficient를 막는다. [사용자 추가 요청에 따른 실행 전 감사 설계](artifacts/amended-design-before-implementation.json).'),
 ('실험 설계','최초6문항 A/B 계획은 모델 호출 전에 사용자 추가 구현 요구에 맞춰 일반 구현 감사로 변경했다. [원래 계획](artifacts/pre-amendment-manifest.json)과 미실행 질문 파일은 보존한다. 이번에는 기준 대비 답변 정답률·회수율을 측정하지 않았다. 최초 부모 복사본 생성이 설계 저장 성공보다 먼저인 절차 이탈을 명시한다. 후보 구현 편집은 설계 저장 후였으며 이를 승격 근거로 사용하지 않는다.'),
 ('데이터·모델·재현성','모의 내규/ESG 문서는 일반 계약용이다. 실 DB는 ACTIVE_RELEASE가 선택한 navigation-source-20260916-v1을 읽기 전용으로 검사했다. RAW 파일 해시 앞16자리 document_id, 선택 구조 artifact 전체 해시, meta.doc_id를 대조해 origin projection을 만든다. 제목 유사도나 임의 최신 파일을 출처로 사용하지 않는다. 명시적으로 고른 package 구조 root만 사용한다. [입력 결속](artifacts/input-lock-adapter-fix.json). 외부 모델 전송0.'),
 ('결과','계약30개 통과. 실제 외부145개(kofia72, krx11, law62), 분류 미확인14개. internal 문서가 없다는 의미가 아니다. 외부 문서명 ESG채권 검색은 ESG채권 인증평가 가이드라인1개를 반환했다. 저장 구조 목차14개 항목, 제1조제3항은 없음, 제5조제3항은 원본7블록을 반환했다. [검사 결과](artifacts/verification-adapter-fix.json), [공개 문서 연결 기록](artifacts/public-navigation-example-adapter-fix.json).'),
 ('사례별 오류 분석','마지막 소비자 검사에서 대화 context를 Result 최상위에 추가하면 기존 계약과 충돌함을 확인했다. rev-002는 context를 허용된 term_agent 상태 안으로 옮기고 반환 직전 Result를 다시 검증한다. rev-001과 최초 검사 기록은 보존했다. 본문에만 ESG채권이 있는 방해 문서는 제목 검색에서 제외된다. 유효하지 않은 컨텍스트, 범위 밖 문서, 없는 구조 좌표·노드, 불완전한 원문 block span을 거부한다. 1조3항의 제 생략은 질문 표기만 정규화하고 저장 좌표에 대조한다. 부모 제1조를 제3항 결과로 대체하지 않는다. 실제14개 경로 미확인은 별도 출처/세대 이행 대상이다.'),
 ('비용·지연·회수 규모','신규 모델 호출0, 토큰0, 새 정답률·회수율 없음. 30는 계약 개수이며 정답 문항 수가 아니다. 기존12조문10문서 모의 계약에서 다중 진입점 후보 합집합·중복제거·전체 페이지 보존·조기 종료 방지를 검사했다. 실제 원문 내용이나 내부 자료를 외부로 전송하지 않았다.'),
 ('해석','A/A′ 등록 진입점별 occurrence와1홉 등록 관계를 합쳐 중복 조문은 하나로 유지하고 경로는 모두 보존한다. 채택된 명시 참조는 후속 후보로 연결한다. 폴더는 RAW 원위치 그대로 유지하고 public source는 검색용 external 상위 그룹 아래 보여준다. internal 아래 자료에는 내규 태그를 붙인다. 표제만 찾을 때는 document.name만 비교하며, subtree 검색은 저장 노드 span 안으로 제한한다. [연결 사용법](USAGE.md).'),
 ('한계와 일반화 가능 범위','일반 계약과 저장 연결 검사만 수행했으므로 실제 LLM의 도구 선택·복수근거 답변 품질은 미검증이다. 초기 회수는 등록 용어/구조와1홉 연결에 한정돼 미등록 표현을 모두 잡는다는 뜻이 아니다. 제목의 관련성은 공백·대소문자 정규화 문자열 검색이다. 목차는 저장된 파서 구조로 만든 것이며 인쇄 목차 원본이 별도 존재함을 뜻하지 않는다. 대화 context는 프로세스 메모리 안의 대화별 객체이고 웹/API/UI 및 재시작 영속화는 미배포다.'),
 ('운영 결정·롤백 조건','explicit runtime.create_conversation이 matcher+origin projection을 결속하고 기존 retrieve/select/assemble/answer 파이프라인을 소비한다. metadata 답변만 Conversation 어댑터가 저장 조회 결과로 렌더링한다. 본문 질의는 선택된 document allowlist로 기존 도구 루프에 진입한다. 원본 DB·RAW 이동/수정 없음, 운영 registry·서비스·MAIN generation14 그대로다. 롤백은 실험 주입을 빼고 부모0448 객체를 쓰면 된다.'),
 ('재현 명령','`PYTHONPATH=02_BACKEND ADR449_TEST_FROZEN=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider 06_TOOLS/EXPERIMENTS/adr_0449`. explicit factory 및 메타데이터 API는 [USAGE](USAGE.md). `verify_navigation.py`는 완료 산출물을 덮어쓰지 않으며 새 결과 비교는 새 ADR에서 수행한다. 최종 검사 상태는 [VALIDATION](VALIDATION.md).')]
 front=(D/'README.md').read_text().split('---',2)[1];(D/'README.md').write_text('---'+front+'---\n\n# 복수 진입점과 폴더·구조 탐색\n'+''.join(f'\n## {i}. {title}\n\n{body}\n' for i,(title,body) in enumerate(sections,1)))
 (D/'실험/README.md').write_text('# 일반 구현·연결 감사\n\n모델 호출·A/B·답변 채점 없음. 최초6문항은 실행하지 않았고 사전 계획을 보존한다. 일반 계약30개와 실제 저장 메타데이터 연결만 검사했다.\n\n- [결과](../artifacts/verification-adapter-fix.json)\n- [계약 원출력](../artifacts/tests-adapter-fix.json)\n- [원래 미실행 계획](../artifacts/pre-amendment-manifest.json)\n- [감사 설계](manifest.json)\n')
 for row in read(A/'dataset/product-cases.json'):
  p=next((A/'planned-questions').glob('질문-*-'+row['id']+'.md'));p.write_text('# 미실행 계획: '+row['id']+'\n\n질문: '+row['question']+'\n\n최초 비교 계획 보존용. 모델 제품 호출·채점·arm 비교·정오 판정 없음. 사용자 추가 요구에 따라 실행 전에 일반 구현 감사로 전환했다. 원래 설계는 artifacts/pre-amendment-manifest.json, 합성 입력과 채점용 기대값은 artifacts/dataset 및 artifacts/grading에 보존한다. 제품 입력에 기대값을 제공하지 않았다.\n')
 index=R/'04_EXPERIMENTS/ADR/README.md';text=index.read_text();link='- [ADR-0449 복수 진입점·폴더/제목/목차 탐색](ADR-0449-multi-entry-catalogue-navigation/README.md) — 계약30통과, 실제145개 폴더 연결·14미확인; 제목 검색→문서 선택→목차/정확 항 조회. 모델0·MAIN 미반영.\n\n'
 if 'ADR-0449 복수' in text:index.write_text(text.replace('계약29통과, 실제145개','계약30통과, 실제145개'))
 else:index.write_text(text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+link,1))
 paths=[p for folder in [A,T,C] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=A/'manifest.json' and p.suffix!='.log']
 write(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0449','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved design, ordinary contracts, frozen candidate or metadata projection'} for p in sorted(paths)]})
 print('implementation audit report recorded; model calls 0')
if __name__=='__main__':main()
