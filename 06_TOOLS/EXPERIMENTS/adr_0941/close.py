"""Close a technical ADR without replacing its frozen implementation or failures."""
from pathlib import Path
import hashlib,json,subprocess,sys,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3]
A=R/sys.argv[1];status=sys.argv[2];note=sys.argv[3]
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');arm=m['design']['arms'][-1]['id'];d=A/'artifacts/design'
checks=[]
for p in sorted((A/'artifacts').glob('*.xml')):
    tests=list(ET.parse(p).iter('testcase'));fail=[t.attrib['classname']+'.'+t.attrib['name'] for t in tests if t.find('failure') is not None or t.find('error') is not None]
    checks.append({'path':str(p.relative_to(R)),'tests':len(tests),'passed':len(tests)-len(fail),'failed':fail})
result={'status':'complete','technical_only':True,'strict_success':status=='Accepted','checks':checks,
        'model_calls':0,'quality_certified':False,'main_changed':False,'conclusion':note}
out=A/'artifacts/run-001';out.mkdir(exist_ok=True);put(out/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(out/'result.json'))
m['results'].update(status='complete',by_arm={arm:result},comparisons=[],usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={},error_taxonomy=[])
put(A/'실험/manifest.json',m)
p=A/'README.md';front=p.read_text().split('---',2)[1].replace('status: Proposed','status: '+status)
criteria=read(d/'criteria.json')
sections=[('결정 요약',note),('문제와 변경 전 구조','후보 발견과 원문 확보의 진전 계산, 부모 미확보 항목과 자식 획득 이력을 연결한다. 기존 원문·권한·판본·재개·예산 검사는 유지한다.'),
 ('가설과 사전 판정 기준',criteria['hypothesis']+'\n\n사전 동결: artifacts/design/criteria.json. 성공/실패 기준은 해당 파일에 보존한다.'),
 ('실험 설계','동결 코드의 기술 계약과 실제 API를 모의 원문·모의 모델로 순차 검사한다. 법률 정답률·회수율·지연 비교가 아니다.'),
 ('데이터·모델·재현성','합성 기술 자료. 외부 모델 호출 0회. 후보/실행기와 입력 지문은 artifacts/design/freeze.json 및 후보 binding에 있다.'),
 ('결과','\n'.join(f"- {Path(c['path']).name}: {c['passed']}/{c['tests']} 통과, 실패 {len(c['failed'])}." for c in checks)),
 ('사례별 오류 분석',note+'\n\n실패명은 artifacts/run-001/result.json, 원래 traceback은 checks 로그/XML에 보존한다.'),
 ('비용·지연·회수 규모','모델0회·실자료 로딩0회. RSS·디스크·실행 시간은 각 resources.json에 기록했다. 품질·회수·응답 속도 개선률은 측정하지 않았다.'),
 ('해석','기술 상태의 연속성과 실제 소비자 연결을 검사한다. LLM이 적절한 근거를 선택하거나 의미를 정확히 판단한다는 보증은 아니다.'),
 ('한계와 일반화 가능 범위','완료 후보를 변경하지 않은 사전 고정 유한 상태·합성 서비스 계약 범위다. 실제 모델의 긴 원문 미확보 탐색 경로는 미검증이며, 탐색 복구는 새 물리 대상이 있을 때 최대3회이며 실제 모델 효과는 후속 검증 대상이다. GENOS 현장·실제 내부 모델·대규모 데이터는 실행하지 않았다.'),
 ('운영 결정·롤백 조건','이 ADR에서는 작업 제품과 선택 MAIN을 변경하지 않았다. 승인되지 않은 후보는 통합하지 않는다. 통합·분리 검증·실제 API 확인은 별도 기록으로 남긴다. MAIN 승격과 법률 품질 승인은 포함하지 않는다. 원문·권한·상태·예산 회귀 시 통합하지 않는다.'),
 ('재현 명령','실제 명령은 각 artifacts/*resources.json의 command에 보존했다. 일반 검사: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path '+str(A.relative_to(R))+' --final`.')]
p.write_text('---'+front+'---\n\n# '+m['adr_id']+' 조사 연속성 기술 검사\n\n'+'\n\n'.join('## '+str(i)+'. '+title+'\n\n'+body for i,(title,body) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 기술 검사 인덱스\n\n질문 단위 법률 평가 없음. 동결 합성 계약·API 결과는 [검사 기록](../artifacts/run-001/result.json)에 있다.\n')
(A/'RESULT.txt').write_text(note+'\n\n모델0회. 제품/MAIN/GENOS 변경 없음. 원시 실패 기록 보존.\n')
artifact=read(A/'artifacts/manifest.json')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']+[A/'RESULT.txt']
artifact['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen technical design or actual verification result','contains_raw_prompts_and_outputs':False} for p in sorted(paths)]
put(A/'artifacts/manifest.json',artifact)
for args in (['hash','--path',str(A)],['status','--path',str(A),'--status','completed','--note',note],['validate','--path',str(A),'--final']):
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py',*args],check=True)
