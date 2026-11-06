"""Record exact MAIN selection and the limited deterministic repair evidence."""
from common import *
import re,sqlite3

b=read(DES/'baseline.json');activation=read(ART/'main/activation.json')
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
assert pointer==activation['active'] and pointer['generation']==149
release=read(ROOT/pointer['manifest_path']);f=read(DES/'candidate-repaired.json')
assert release['files']==f['selected_files']
assert all(sha(ROOT/release['code_root']/n)==h==sha(ROOT/n) for n,h in release['files'].items())
assert release['data_path']==b['release']['data_path'] and release['data_manifest_sha256']==b['release']['data_manifest_sha256']
changed=read(DES/'delta.json')['changed']
assert len(changed)==32
assert [n for n in changed if not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json']==['02_BACKEND/lawrag/core/legal_coordinate.py']
prepared=read(ART/'prepared-review/result.json');comparison=read(ART/'regression-comparison.json')
assert prepared['passed']==73 and prepared['failed']==0 and comparison['new_failures']==0
assert read(ART/'main/main-entry.json')['passed'] and read(ART/'main/gold-entry.json')['passed']
assert sha(ROOT/'05_TESTS/CONTRACTS/test_annex_dash_coordinate.py')==sha(Path(__file__).with_name('test_annex_dash.py'))

# Metadata observation only. Never rewrite a published legacy coordinate or infer
# an attachment's presence/absence from a single parent-document row.
source=ROOT/release['data_path']/'store.sqlite'
rows=[]
with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as db:
 for uid,raw in db.execute('SELECT unit_id,json FROM source_unit WHERE document_id=?',('5c292593a5e4e4e4',)):
  value=json.loads(raw)
  if '17-1' in str(value.get('title','')) or '17-1' in str(value.get('surface','')):
   rows.append({'unit_id':uid,**{k:value.get(k) for k in ('surface','title','legal_coordinate','coordinate_key','coordinate_scope')}})
put(ART/'published-pf-metadata-observation.json',{'rows':rows,'read_only':True,
 'scope':'Parent document metadata only; attachment discovery and source reading were not executed. Does not establish missing originals.',
 'no_metadata_rewrite':True})

result={'status':'LOCAL_MAIN149_SELECTED','active':pointer,'serving_files':530,'changed_files':32,
 'product_modules':1,'dependent_pins':31,'new_annex_contracts_passed':17,
 'related_suite_passed':106,'related_suite_failed':5,'same_baseline_failures':5,'new_failures':0,
 'prepared_contracts_passed':73,'prepared_contracts_failed':0,'prepared_is_subset_recheck':True,
 'actual_service_checks':activation['main_checks'],'gold_code_binding_checks':activation['gold_checks'],
 'native_SQL_plans_unchanged':640,'new_external_model_calls':0,'new_Oracle_connections':0,
 'data_unchanged':True,'scope':'Shared legal_coordinate.py grammar, label, canonical surface and key for dashed annex/form numbering; all other MAIN148 product bytes preserved.',
 'quality_certified':False,'deployment_basis':'USER_DIRECTED_CUTOVER','field_deployed':False,
 'rollback_release':b['pointer']['release_id'],'rollback_gold':str((ART/'main/gold-binding-before-exact.json').relative_to(ROOT)),
 'limits':['PF end-to-end model answer not rerun; no answer-quality or performance claim.',
 'Published data and historical coordinate metadata not rewritten; missing or ambiguous stored targets remain unresolved.',
 'Existing 5 regression failures retained, independently identical on MAIN148; no fixture relaxation.',
 'Gold code import only; no Oracle/GENOS field execution.']}
put(RUN/'result.json',result);put(ART/'final-verification.json',result)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_MAIN':148,'failed_tests':5,'failure_signatures':comparison['failure_signatures']},'repaired':result},
 comparisons=[],judge_disagreements=0,usage={'external_model_calls':0,'Oracle_connections':0},
 latency={'not_measured':'Deterministic repair and release wiring; no controlled latency evaluation'},
 error_taxonomy=['Existing model-scope fixture failures2, Oracle mock release_id missing1, annex regex instrumentation expectations2; same on baseline.'])
put(ADR/'실험/manifest.json',m)
verdict='별표 붙임 번호 처리 수정만 로컬 MAIN149에 반영 완료. 별표 17-1을 17로 잘라 읽던 공통 파서에 붙임 번호를 보존했다.'
limits='PF 질문의 실제 Qwen 답변은 재실행하지 않았다. 번호 파서·원문 목표 검증·구조 조회 계약과 실제 선택 연결의 수정이며 법률답변 품질 인증이 아니다. 기존 데이터와 과거 저장 좌표는 재작성하지 않았고, 저장된 목표의 부재·중복·권한·원문 검증은 유지했다. 현장 GENOS/Oracle 실행·배포·메일0.'
text=verdict+'\n\n릴리스 annex-dash-coordinate-20261105-r1 / MAIN149 / 서빙530파일.\nMAIN148 대비 제품1(legal_coordinate.py)+파생pin31=32변경; SQL640 동일.\n신규17통과, 관련포함106통과·기존5실패(수정전148 동일), 준비본73통과(부분집합 재검사).\n실제 root service29·Gold 코드 연결9통과. 외부모델0·Oracle연결0.\n17 / 17-1 / 17-2 키와 조회 분리, 문서라벨/참조/원문목표 동일 번호 보존.\n\n'+limits+'\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n'
(ART/'수정과_메인반영_결과.txt').write_text(text)
front=(ADR/'README.md').read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
front=re.sub(r'(?m)^main_wiring:.*$','main_wiring: user-directed-cutover',front)
sections=[('결정 요약',verdict),
 ('문제와 변경 전 구조','ADR1402에서 좌표 별표 17-1은 공통 ANNEX_PATTERN에 의해 별표 17까지만 인식되어 전체 좌표 검증이 거절했다. 같은 모듈의 라벨 파서·키·표면형도 붙임 번호를 보존하지 않았다. 기존 조문 dash 처리와 같은 명시 번호 필드를 사용한다.'),
 ('가설과 사전 판정 기준',json.dumps(read(DES/'criteria.json'),ensure_ascii=False)),
 ('실험 설계','MAIN148 포인터·530파일·작업 원본·Gold 바이트를 보관하고 공식 격리후보에서 제품1파일만 수정, SQL 및 pin 재검증 후 동결했다. 신규17과 관련94 조건의 검사111개에서106통과/5실패. 실패5개만 수정 전 MAIN148로 대조하여 동일함을 확인했다. 준비된 동일530코드의73조건과 실제선택 서비스29/Gold코드9를 검증했다.'),
 ('데이터·모델·재현성','기존 원문세대와 manifest 유지. 합성 별표/별지 번호, 붙임 조문, 범위/잘못된 좌표, 서로 다른 문서/분기/권한과 원문목표 연결을 검사했다. 외부 모델·채점 모델0. 현재 PF 부모문서의 첨부 제목행651은 별표17-1 이름만 있고 법률좌표가 없는 것을 읽기 전용으로 기록했다. 별도 첨부 원문 존재 여부나 실제 회수를 검증한 결과는 아니다.'),
 ('결과',json.dumps(result,ensure_ascii=False,indent=2)),
 ('사례별 오류 분석','별표17/17-1/17-2를 구분하며 정확 조회 후 원문목표 matches까지 연결했다. 잘못된 suffix·복수좌표·범위는 기존 SOURCE_TARGET_COORDINATE_INVALID로 거절한다. 검사상 기존5실패는 모의API2·Oracle fixture release_id 누락1·정규식 계측 기대2이며 별표 수정 전후 오류 서명이 일치한다. 제품/fixture를 변경해 실패를 숨기지 않았다.'),
 ('비용·지연·회수 규모','신규17은106통과에 포함, 준비73은 같은 검사의 부분집합이다. 두 수를 독립 성능 표본으로 합산하지 않는다. 실제 선택service29·Gold코드9. 새 모델/실Oracle0·속도/회수율/법률정답률 미측정.'),
 ('해석','공통 번호 처리를 수정하여 올바른 붙임 번호를 코드가 잘못된 좌표로 거절하던 원인을 제거했다. 해당 원문이 저장되어 있고 권한·분기·유일성 검증이 맞아야 기존 원문조회가 성공한다. 번호 수락 자체가 원문 확보나 답변 성공을 뜻하지 않는다.'),
 ('한계와 일반화 가능 범위',limits),
 ('운영 결정·롤백 조건','사용자 지시로 MAIN149를 선택했다. 기존148 멀티턴 상태 검증·공통 감시·모델/검색프로필 전부 바이트 보존. 심각한 회귀이면 공식 rollback --confirm-main과 artifacts/main/gold-binding-before-exact.json으로 이전148의 Gold 바이트를 함께 복원한다.'),
 ('재현 명령','06_TOOLS/EXPERIMENTS/adr_1404/bootstrap.py → 후보 legal_coordinate 수정 → freeze.py → check.py → prepare.py → 준비본 check.py → apply_working.py → activate.py → finish.py.\n신규 영구검사:05_TESTS/CONTRACTS/test_annex_dash_coordinate.py.\n실제포인터:01_DATA/ACTIVE/local/ACTIVE_RELEASE.json.\n메인 검증:artifacts/main/main-entry.json·gold-entry.json·activation.json.')]
(ADR/'README.md').write_text('---'+front+'---\n\n# 별표 붙임 번호 수정과 MAIN149\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 번호 처리 및 선택 연결 검사\n\n새 법률질문·외부 모델 평가0. 합성계약·원문목표/조회 소비자 검사, 수정전 기존실패 대조, 준비본 및 실제서비스 연결 검증은 artifacts/run-001/result.json과 main/에 보존한다.\n')
audit=ROOT/'09_ARTIFACTS/AUDITS/20261105-annex-dash-main149';audit.mkdir(exist_ok=True)
(audit/'수정과_메인반영_결과.txt').write_text(text);put(audit/'최종검증.json',result)
paths={p for p in ART.rglob('*') if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json'}
paths.update(Path(__file__).parent.glob('*.py'));paths.add(ROOT/'05_TESTS/CONTRACTS/test_annex_dash_coordinate.py')
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1404','files':[
 {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Coordinate repair, preserved failures, frozen code or MAIN verification evidence','contains_raw_prompts_and_outputs':False} for p in sorted(paths)]})
print('MAIN149 exact530; parser1+pin31, new17/related106, existing5, prepared73, service29/Gold9.')
