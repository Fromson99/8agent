"""Seal technical results; never promote or call an external model."""
from common import *
import subprocess

f=read(DES/'freeze.json');rev=f['candidate_revision']['revision_id']
r=read(ART/('check-'+rev+'.json'))
assert r['passed']==46 and r['failed']==0 and not r['import_leaks']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
for name,h in {**f['inputs'],**f['scripts']}.items():assert sha(ROOT/name)==h,name
for name,h in f['files'].items():assert sha(ROOT/f['code_root']/name)==h,name
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1169-supervisor-cm3-memory-reclaimed/artifacts/design/freeze.json')
changed=[n for n,h in f['files'].items() if parent['files'].get(n)!=h]
product=[n for n in changed if n.startswith('02_BACKEND/semantic_runtime/')]
assert len(product)==3,product
result={'status':'complete','technical_passed':46,'technical_failed':0,
    'new_contract_items':15,'inherited_contract_items':31,'model_calls':0,
    'saved_007_guidance_schema_mismatch_reproduced':True,
    'next_previous_read_selection':True,'native_api_page_handoff_and_publication':True,
    'native_api_on_off':True,'quality_certified':False,'full_cm_runs':0,
    'MAIN112_unchanged':True,'candidate_revision':f['candidate_revision'],
    'changed_files':changed,'product_files':product,
    'failed_revisions_preserved':{'rev-001':'45 pass / fixture KeyError on empty page actions',
        'rev-002':'45 pass / fixture failed to scan paged connection cards; IndexError'},
    'limitations':['No new model execution or semantic quality measurement',
        'Explicit missing-law/article versus selected-target semantic binding remains unimplemented',
        'Supervisor paging consumes the existing two-call allowance; exhausted allowance hands off',
        'MAIN112, GENOS field and full vector/ontology combinations are not newly qualified']}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'repaired':{'status':'complete','technical_success':True,'quality_certified':False}},comparisons=[],judge_disagreements=[],usage={'new_model_calls':0},latency={'technical_seconds':r['seconds'],'performance_claim':False},error_taxonomy=['rev001/002 synthetic API fixture defects preserved; product unchanged across revisions','Actual Qwen target-selection and answer-completion failures remain unverified'])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[
 '3번 페이지 계약 결함을 격리 후보에서 수정하고 기술 검증을 마쳤다. 법률 품질 미확인으로 Proposed. MAIN112 유지.',
 'ADR1169 CM007 실제 6번째 전송은 NEXT를 안내하고 현재 페이지 이동도 표시하지만 감시 응답 스키마에서 이를 금지했다. 직접 조항조회·목차 도구는 제공됐으므로 전체 접근 차단으로 해석하지 않는다.',
 '[사전 기준](artifacts/design/criteria.json). 페이지별 스키마와 실제 상태 이동 일치, 현재 페이지 밖 대상 거부, 중단 재개, 기존 예산·원문·판단 보존이 성공 조건이다. 하나라도 실패하면 채택하지 않는다.',
 '완료1169/supervised의459파일에서 제품3파일과 종속pin만 변경. read_candidate_pages.move를 기존 선택기·감시자가 공유하고 decision_projection의 기존 prepare_page를 감시에도 전달했다. 감시의 페이지 선택은 상태에 먼저 기록한 뒤 적용하며 재개 때 중복 이동하지 않는다.',
 '저장된 CM007 실제 입력/스키마와 합성 자료를 사용했다. 저장20카드 뒤 추가한21번째 카드는 경계 검사용 합성 카드이며 실제 누락 원문 회수 증거가 아니다. 외부 모델0, 기준답변을 제품 입력으로 넣지 않았다. 최종 rev-003의459파일과 실행 스크립트 해시를 결속했다.',
 '46검사 통과(기존31+추가15), import누출0. NEXT/PREV 후 새 페이지 READ 선택, 감시2회 한도, 숨은 대상/범위 밖/변경된 메뉴 거부, 중단 전후 재개, 정상·OFF·페이지 이동 후 한도 인계의 실제 로컬 API 저장·멱등 재조회 통과. 합성 API의 최종 주장·판단·미확인 해소를 확인했으며 실제 Qwen 정답 성공으로 세지 않는다.',
 'rev001의 API 모의 응답은 남은 후보1개에서 페이지 행동이 있다고 가정해 KeyError. rev002는 제2조가 다른 페이지에 있는데 모의 응답이 FINISH로 내려가 IndexError. 각45통과/1실패를 보존했고, 모의 응답의 후보 구성을 보완하고 실제 현재 페이지를 순서대로 읽도록 수정했다. 제품3파일은 세 revision에서 동일하다.',
 '새 모델0, 모델비용0. 27.03초는 로컬 합성 검사 실행시간이며 실제 응답시간·회수시간·성능 개선율이 아니다.',
 '서버가 제공하지 못했던 페이지 행동을 실행 가능하게 했다. 다음 페이지에서도 모델이 올바른 법령·조항을 고른다는 보장은 없으며 안내 문장과 실제 target 좌표 일치 검사는 별도 과제다.',
 'Qwen의 법령 목표와 실제 선택 불일치·후속 FINISH·CM001 최종 주장0 문제를 이 수정으로 해결했다고 주장하지 않는다. 전역PSI 실험 가드와 모델 정책은 수정하지 않았다. 현장 GENOS·새 법률 품질·속도는 미검증이다.',
 '실험 후보만 보존하며 MAIN112·일반 작업 제품·GENOS·메일·Git은 변경하지 않았다. 추가 모델 실행/승격은 별도 검증이 필요하다. 회귀 시 이 후보를 선택하지 않고 부모1169의 동결본을 사용한다.',
 '완료 실험을 덮어쓰지 않는다. 별도 예약한 자식 후보에서 freeze→check(호스트의 합성 API, 외부 호출 없음)→finish→adr_structure validate --final/graph를 사용한다. 실패 revision과 현재 결과는 그대로 보존한다.'
]
p=ADR/'README.md';meta=p.read_text().split('---',2)[1]
p.write_text('---'+meta+'---\n\n# 감시자 후보 페이지 계약 및 집행 수리\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n최종 rev-003 46검사 통과. 추가15·기존31. 저장007 입력 계약 재현과 합성 API이며 신규 모델 호출0. 실패 rev001/002 보존, MAIN112 유지.\n')
audit=ROOT/'09_ARTIFACTS/AUDITS/20261028-supervisor-pagination';audit.mkdir(exist_ok=True)
(audit/'수정결과.txt').write_text('감시자 페이지 계약 수리 — ADR1170\n\n'
    '수정: 안내하던 NEXT/PREV를 현재 페이지 응답 스키마에서 허용하고 기존 페이지 실행기에 연결했다. 새 페이지 상세는 기존 준비·재사용 경로를 쓴다. 이동만으로 원문 확보·판단 완료를 기록하지 않는다.\n'
    '검증: 최종46통과(기존31+추가15). 저장된 실제 CM007의 안내/스키마 불일치 재현, 앞뒤 이동 후 READ, 숨은 대상/오래된 메뉴 차단, 중단 재개, 기존2회/40회 예산, 실제 로컬 API의 정상·OFF·페이지 인계→최종 답변 저장·멱등 재조회 확인. 모두 모의 응답이며 새 모델0. 두 번의 모의 응답기 실패와 로그를 보존했다.\n'
    '범위: MAIN112 기반 격리 감시 후보의 제품3파일·종속pin만 변경. MAIN112와 GENOS는 그대로다. 법률 품질·실제 성능 개선을 인증하지 않는다.\n\n'
    '모델 문제: 실제 Qwen은 유가증권시장 상장규정 제13조가 필요하다고 쓰고 다른 규정 제15조제7항을 골랐다. 직접 조문조회/목차 도구도 입력에 있었다. 질문 누락만으로 설명되지 않는 목표 선택·지시 이행 실패다. 같은 모델을 감시자로 추가 호출하는 것만으로 충분하지 않았다.\n'
    '권고(이번 미구현): 필요한 법령·조항을 구조화하고 서버가 정확 조회·목표 도달을 확인한다. 중간 연결 경로를 택하면 원래 목표를 유지한다. 최종 종료는 필수 부족의 미해결 여부와 연결한다. 모델 교체 판단은 저장 실패 지점에서 다른 모델의 다음 행동 선택부터 소수 비교하고, 통과 모델만 전체 조사로 검증한다. 개선 모델을 확인하지 않은 채 호출 수·프롬프트만 늘리지 않는다.\n')
a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'test-runtime' not in p.parts]
paths += [ROOT/f['candidate_revision']['manifest_path'],Path(__file__),audit/'수정결과.txt']
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen input, candidate, result or preserved technical failure','contains_raw_prompts_and_outputs':p.suffix=='.log'} for p in paths]
put(ART/'manifest.json',a)
for name,args in [('hash-final',('hash','--path',str(ADR))),
                  ('validate-before-completion',('validate','--path',str(ADR))),
                  ('status-final',('status','--path',str(ADR),'--status','completed','--note','46technical pass; saved007 and synthetic native API; newmodel0; qualityunverified; MAIN112unchanged')),
                  ('validate-final',('validate','--path',str(ADR),'--final'))]:
 out=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True)
 (ART/(name+'.txt')).write_text(out.stdout+out.stderr)
 assert out.returncode==0,out.stdout+out.stderr
print('46passed,model0,MAIN112unchanged',len(changed),'changed files',len(product),'product')
