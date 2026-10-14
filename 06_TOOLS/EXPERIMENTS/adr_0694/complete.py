from pathlib import Path
import json,hashlib,gzip,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0694-structure-first-read-plan'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def suite(name):
 p=A/'artifacts/contracts'/(name+'.xml');cs=list(E.parse(p).iter('testcase'));bad=[c.get('name') for c in cs if c.find('failure') is not None or c.find('error') is not None];return {'tests':len(cs),'passed':len(cs)-len(bad),'failures':bad,'path':str(p.relative_to(R)),'sha256':sha(p)}
x=suite('structured-reading');b=suite('parent');new=set(x['failures'])-set(b['failures']);assert not new
pre=read(A/'artifacts/preflight/result.json');assert pre['status']=='READY'
m=read(A/'실험/manifest.json');r={'status':'complete','new_failures':[],'contracts':x,'parent_contracts':b,'new_structure_read_contracts':8,'package_preflight':pre,'model_calls':0,'main_changed':False,'genos_deployed':False,'limitations':['Nine legacy fixtures fail in both parent and candidate; historical experience fixture also excluded as previously recorded.','Contract probe only; no measured model efficiency or legal answer comparison.','Fulltext and schema contracts retained; no quality waiver or promotion.']}
put(A/'artifacts/contracts/result.json',r);m['results'].update(status='complete',by_arm={'baseline':{'status':'complete',**b},'structured-reading':{'status':'complete',**x,'package_preflight':'READY'}},usage={'model_calls':0},latency={'not_measured_reason':'No model calls'},error_taxonomy=['legacy_fixture_failures']);m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/contracts/result.json'));put(A/'실험/manifest.json',m)
head=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
body=['구조 우선 검색과 선택 범위 읽기 후보를 구현했다. 연구 검증 완료이며 MAIN46은 유지한다.','초기 discover와 후보 카드 구성에서 전체 본문 검색이 구조 조회보다 먼저 실행되던 두 경로를 제거했다.','design/criteria.json: 구조 미적중의 전체 검색 전환 금지, 명시 범위·cursor 결속, 읽기 재개·중복 제거, 확보·전달·채택 분리가 기준이다.','완료된 ADR0693/consistent-judgment를 확장했다. 구조 조건은 opt-in profile로 고정하며 일반 구버전 경로는 유지한다. 합성 검사 전 고정 revision과 실행기 해시를 manifest에 기록했다.','MAIN46 원문 세대를 읽기 전용으로 공유한다. 새 세대의 별칭·원본 폴더 projection 두 파일도 MAIN46과 같은 해시로 포함했다. 외부 모델 호출 없음.',f"후보 {x['passed']}/{x['tests']} 통과. 실패9건은 부모에도 있는 구 응답/경험 fixture다. 새로운 실패0, 새 구조·범위·재개 검사8개 통과. 실제 앱 기동·profile·case binding 확인 READY.",'개발 중 profile 해시와 누락 projection을 수정했다. 첫 기동 실패와 수정 전후 회귀 원문을 별도 보존한다. 기본 기동 테스트는 본문 표현만 있는 질문의 구조 미적중을 정확히 확인하도록 기대값을 변경했다.','모델 호출0, 실제 토큰·지연 개선은 미측정이다. 묶음 전달은 현재 API의 실제 직렬화 character budget 안에서만 준비한다. 페이지 수를 모델 호출이나 token으로 간주하지 않는다.','모델이 구조에서 문서·하위 범위를 고르고 코드가 그 범위의 fulltext·읽기 중복 제거·완료 단계 재사용을 실행한다. 자료 확보와 모델 확인·명시적 채택은 계속 구분된다.','현행 공개65문서에서 실제 모델 비교와 독립 질문 검증이 필요하다. 합성 통과를 일반화 또는 현장 성능으로 간주하지 않는다.','제품 작업 경로·MAIN 포인터·GENOS 변경 없음. 독립 품질 기준을 통과하기 전 활성화하지 않는다.','06_TOOLS/EXPERIMENTS/adr_0694/validate_frozen.py 및 preflight.py. contracts/bindings.json과 preflight/result.json에 동일 frozen 코드와 실행 binding을 기록했다.']
fm=f"---\nadr_id: ADR-0694\ntitle: MAIN46 구조 우선 검색과 범위 결속 읽기\nstatus: Proposed\ndecision_date: 2026-10-08\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(head,body),1))+'\n');(A/'실험/README.md').write_text('# 합성 구조 검색·읽기 계약\n\n모델 호출 없음. [고정 결과](../artifacts/contracts/result.json).\n')
receipts=[]
for p in Path('/tmp').glob('adr694*.log'):
 t=A/'artifacts/logs'/(p.name+'.gz');t.parent.mkdir(exist_ok=True);data=p.read_bytes()
 with gzip.open(t,'wb') as f:f.write(data)
 receipts.append({'path':str(t.relative_to(R)),'sha256':sha(t),'raw_sha256':hashlib.sha256(data).hexdigest(),'restore':'gzip -dc archive.gz > original.log'})
put(A/'artifacts/logs/receipts.json',receipts)
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0694','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Synthetic contracts and actual no-model app binding','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and 'runtime' not in p.parts]})
print('Complete probe: 250 passed,9 shared legacy failures; new failures0; package READY')
