"""Close the development probe without authorizing MAIN promotion."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0776-schema-recovery-runtime'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0776/recovery'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');c=read(C/'candidate.json');rev=c['revisions'][-1]
assert rev['revision_id']=='rev-010'
suite=next(E.parse(A/'artifacts/development/regression-r10.xml').iter('testsuite'))
assert suite.get('errors')==suite.get('failures')=='0'
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(A/'artifacts/design/baseline.json')['pointer_sha256']
changed=[]
for row in c['files']:
    name=row['target_path'];after=sha(C/'snapshot'/name)
    if after!=row.get('upstream_sha256'):
        changed.append({'path':name,'before':row.get('upstream_sha256'),'after':after})
put(A/'artifacts/changed-files.json',changed)
result={'strict_success':True,'classification':'in-sample development probe, not promotion qualification',
 'checks':{'817_contracts_passed':True,'known_failures_preserved':True,'no_model_calls':True,
 'no_main_pointer_change':True,'single_correction_and_durable_budget':True},
 'candidate_revision':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'by_arm':{'baseline':{'status':'complete','scope':'Known preexisting fixture failures; see baseline-known-tests.xml; not a paired accuracy comparison'},
 'recovery':{'status':'complete','passed':817,'skipped':1,'failures':0}},
 'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0},
 'limitations':['No GENOS access or real model effectiveness/latency measurement.',
 'Keyed decision objects and sparse patches remain conditional future experiments, not enabled.',
 'The skipped chosen-unit module has no collected tests; it is not counted passed.',
 'Legacy v5 CLI fixture selects its full v5 profile explicitly; current service binding is verified separately at promotion.']}
path=A/'artifacts/run-001/result.json';put(path,result)
m['runs'][0].update(status='complete',sha256=sha(path));m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],
 judge_disagreements=0,usage=result['usage'],latency={'kind':'Deterministic local contracts only','seconds':float(suite.get('time'))},
 error_taxonomy=['OUTPUT_JSON_INVALID','OUTPUT_SHAPE_INVALID','DECISION_CONFLICT','EVIDENCE_INVALID','STATE_OR_BINDING_INVALID','OUTPUT_INCOMPLETE','TOOL_RESULT_REJECTED'])
put(A/'실험/manifest.json',m)
parts=[
('결정 요약','Accepted 개발 후보. 정본 배열과 원문·권한·해시·revision·발행 규칙을 유지하면서 공통 출력 계약과 단계별 단일 복구를 구현했다. 이 probe는 인샘플이며 MAIN 승격 자격이 없다. 별도 사전 고정 감사가 필요하다.'),
('문제와 변경 전 구조','사진의 duplicate branch or missing reason은 모델 판단 제안 검증 실패이며 SOURCE_INVESTIGATION_INCOMPLETE는 그 뒤 원문 조사가 끝나지 않았다는 최종 상태다. JSON/스키마와 필드 관계·근거 검증을 분리했다. 과거 H01~H17의 설계 근거는 원래 HISTORY와 EVIDENCE를 수정하지 않고 참조한다.'),
('가설과 사전 판정 기준','artifacts/design/criteria.json의 I01~I15와 실패 주입 목록을 구현 전 고정했다. 정상 제안은 추가 호출0, 동일 논리 결정의 교정은 최대1회, 상태·전체 예산은 재개에도 보존한다. 구현 중 결과는 개발 기록이며 과거 실패를 삭제하지 않았다.'),
('실험 설계','baseline은 MAIN61 및 기존 작업 차이를 기록했다. candidate rev-001~010을 보존하고 현재 소비자와 과거 버전의 계약을 확인했다. 구조화 basic/compact/legacy는 첫 응답+교정1회로 통일하되 의미 검수·페이지 분할은 기존 별도 단계로 유지했다. 결과를 본 뒤 수정한 개발 리비전을 독립 holdout으로 부르지 않는다.'),
('데이터·모델·재현성','원문 generation과 공개/내부 경계를 변경하지 않았다. 실제 모델 호출0이며 synthetic transport, 합성 원문, SQLite/HTTP 서비스 계약을 사용했다. code isolation manifest가 파일과 immutable revision을 결속한다. 실제 내부 모델 성능은 미확인이다.'),
('결과','rev-010: 총818개 중817통과/1collection skip/0실패. 새 파서·원장·실제 gateway/AD/build 어댑터, 기존 source/reference/completion v4~v8, v5 서비스·CLI와 문서 구조화 계약 포함. baseline의 예전 fixture 실패는 별도 XML에 보존하며 법률 정확도 개선 수치로 환산하지 않는다.'),
('사례별 오류 분석','중복 JSON key·비표준 숫자·빈 이유·독립 충돌은 구체 경로로 보고한다. 완전 동일 중복만 원본/정규화 hash를 남기고 재검증한다. 번호 codec 오류 메시지 보정에서 dict를 str.replace에 전달하던 결함을 고쳤다. 도구 부분 성공은 완료 revision과 구조화된 실패 목록에 결속하며 성공한 선택을 보존한다. 일부 송신 후 실패는 재생성으로 이어 붙이지 않는다.'),
('비용·지연·회수 규모','모델/토큰0. 실제 지연·정답·스키마 오류 발생률을 측정하지 않았다. 전송400의 숨은 문법 fallback을 제거하고 실제 호출 수를 기록한다. 문서 재개는 호출 ledger에서 기존 결과·예산을 재사용하며 RESERVED unknown은 재전송하지 않는다.'),
('해석','스키마 통과는 법률 판단 승인과 다르다. 미확보 근거·조건·예외는 계속 미확인으로 남는다. 테스트는 오류 숨김 대신 정상/복구/중단/저장 소비자 연결을 검증한다. 예전 테스트의 공개 raw 오류, 고정 domain 모델 단계, 세 번째 교정 기대는 현재 보안·운영 계약과 최대1교정 정책에 맞게 갱신했다.'),
('한계와 일반화 가능 범위','실제 Qwen/GENOS 호출이 없으므로 발생 빈도 감소나 법률 정답 개선을 주장하지 않는다. 구 checkpoint는 구 code/binding으로 보존되며 새로운 코드의 구조화 cache namespace로 자동 승인하지 않는다. 현장 코드·모델·설치·워크플로우는 별도 검증이 필요하다.'),
('운영 결정·롤백 조건','작업/MAIN은 이 probe에서 변경하지 않았다. 후속 독립 audit의 frozen candidate와 같은 파일만 사전 해시 대조 후 통합하고 qualified promotion으로 로컬 MAIN을 갱신한다. GENOS는 별도 설치 inventory·백업·check/apply/rollback 및 기존 ~/DEV gate를 검증한다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0776/freeze.py, development_tests.py regression-r10, report.py. stable adr_candidate validate, adr_structure status/validate --final/graph. 완료 실험 재실행·재채점은 새 ADR에서 한다.')]
meta=f"---\nadr_id: ADR-0776\ntitle: 모델 출력 계약·단일 복구·영속 상태 전역 구현\nstatus: Accepted\ndecision_date: 2026-10-14\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 모델 출력 복구 개발 검사\n\n계약/실패 주입과 합성 API 검사이며 법률 품질 평가가 아니다. artifacts/development의 초기 실패와 최종 결과를 함께 보존한다. 실제 모델 호출0.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0776','created_at':m['reservation']['created_at'],
 'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Development evidence and preserved failures',
 'contains_raw_prompts_and_outputs':p.suffix in ('.log','.xml')} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']})
print('817 passed; probe report complete; no promotion')
