"""Publish source-backed scores and criterion checks before terminal lifecycle."""
import argparse, hashlib, importlib.util, json
from pathlib import Path
R=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--adr',required=True);p.add_argument('--turns',type=int,required=True);p.add_argument('--release',action='store_true');a=p.parse_args();A=R/a.adr;D=A/'artifacts/design'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(A/'실험/manifest.json')['reservation']['status']=='in_progress'
spec=importlib.util.spec_from_file_location('accounting',R/'06_TOOLS/EXPERIMENTS/adr_0649/finalize.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main(a.adr)
p=A/'artifacts/run-001/result.json';v=read(p);b=read(D/'bindings.json')
seals=['freeze.json']+(['release-freeze.json'] if a.release else [])
v['checks'].update(expected_turns=v['summary']['integrated']['total']==a.turns,contracts_passed='103 passed' in (A/'artifacts/contracts.txt').read_text(),frozen_bindings=all(sha(R/f)==h for seal in seals for f,h in read(D/seal)['files'].items()),active_unchanged=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['active_pointer_hash'],request_p95_within_240_seconds=v['summary']['integrated']['p95_seconds']<=240,calls_within_100=v['summary']['integrated']['calls']<=100)
if a.release:v['checks']['cli_wiring']=all((A/'artifacts'/name).read_text().startswith('usage:') for name in ['cli-action-memory.txt','cli-unified-memory.txt'])
v['strict_success']=all(v['checks'].values());put(p,v)
m=read(A/'실험/manifest.json');m['runs'][0]['sha256']=sha(p);m['results']['comparisons']=[{'paired':v['paired'],'checks':v['checks']}];put(A/'실험/manifest.json',m)
text=(A/'README.md').read_text();text=text.replace('status: Proposed','status: '+('Accepted' if a.release and v['strict_success'] else 'Proposed' if v['strict_success'] else 'Rejected'))
if a.release:text=text.replace('decision_eligible: false','decision_eligible: true')
if a.release and v['strict_success']:text=text.replace('main_wiring: unchanged','main_wiring: promotion-candidate')
text=text.replace('빈 첫 선택과 누락 검토의 의미가 섞인 지침을 구분하고, 빈 선택에는 원문 구간과 이탈 사유를 제공한다. 현재 사실과 사건 연결은 실제 모델로 검증한다.','ADR-0652에서 확인한 정정 범위 손실을 보완한다. ASSESS는 현재 요청 원문을 받으며, 특정 금지 제외를 전체 영업 허용으로 역추론하지 않도록 판단 범위와 미확인 조건을 보존한다. 원문 인용·현재 사실 정정·저장된 탐색 절차의 결정적 재실행 계약은 유지한다. 추가 모델 호출은 없다.')
text=text.replace('MAIN 불변. 후속 분리 평가 통과 전 승격하지 않는다.',('사전 기준 전부 통과. 이 완료 기록을 Accepted promotion-candidate로 고정하고, 별도 해시 결속 prepare/apply 영수증으로 로컬 MAIN을 승격한다. 현재 결정 시점의 MAIN은 불변이며 완료 기록은 변경하지 않는다.' if a.release and v['strict_success'] else 'MAIN 불변. 알려진 실패 사례의 수정 확인이며 분리 평가 전 승격하지 않는다.'))
text+='\n## 전체 사전 기준 확인\n\n'+module.block(v['checks'])+'\n분리 평가에서 baseline은 직전 완료 후보의 명시적 v6 선택이고 integrated는 고정된 후보의 기본 설정 선택이다. 과거 활성 MAIN보다 품질이 높다는 비교는 아니다. p95는 n이 작은 표본의 최근접 순위값(최대값)이고 독립 사례의 동시 실행 지연을 포함한다.\n'
if not a.release:text+='\n실패 기점: ASSESS 입력에는 과거 task 요약과 현재 facts만 있었고 현재 사용자의 판단 범위 원문은 없었다. COMPOSE에는 원문이 있었으나 ASSESS의 과도한 claim을 그대로 복사해야 하는 계약이 있어 뒤늦게 좁힐 수 없었다. 수정은 ASSESS에 current_request를 직접 전달하며 그 원문이 네이티브 호출 저널에 남는다.\n'
(A/'README.md').write_text(text)
files=[]
for p in sorted((A/'artifacts').rglob('*')):
 if p.is_file() and p!=A/'artifacts/manifest.json' and not p.name.endswith(('-wal','-shm')) and '__pycache__' not in p.parts:
  files.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design, actual model sequence and source-only judgments, contract results and raw journals','contains_raw_prompts_and_outputs':p.name in ['request.json','response.json']})
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':files})
print(json.dumps({'summary':v['summary'],'checks':v['checks'],'strict_success':v['strict_success']},ensure_ascii=False,indent=2))
