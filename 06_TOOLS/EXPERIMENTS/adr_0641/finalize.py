from pathlib import Path
import ast,hashlib,json,statistics
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
run=read(ADR/'artifacts/run-001.json');assert len(run['results'])==6
m=read(ADR/'실험/manifest.json');data=read(ADR/'artifacts/inputs.json')
passed=sum(r['status']=='ACCEPTED' for r in run['results'])
m['runs'][0].update(status='complete',sha256=sha(ADR/'artifacts/run-001.json'))
m['results']={'status':'complete','by_arm':{'baseline':{'status':'complete','measurement':'structural reference only; legal answer comparison not executed'},'integrated':{'status':'complete','accepted':passed,'total':6,'contract_tests':51,'v3_regressions':30}},'comparisons':[],
 'judge_disagreements':0,'usage':{'calls':run['model_calls'],'receipts':run['usage']},'latency':{'seconds':[r['seconds'] for r in run['results']],'p50_seconds':statistics.median(r['seconds'] for r in run['results'])},
 'error_taxonomy':[{'type':'other','reason':r.get('error'),'case_id':r['case_id']} for r in run['results'] if r['status']!='ACCEPTED']}
sections={}
for node in ast.parse((ROOT/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('ADR_HEADINGS','QUESTION_HEADINGS_COMMON'):
  sections[node.targets[0].id]=ast.literal_eval(node.value)
qheads=sections['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
for index,case in enumerate(data['cases']):
 cid=case['id'];folder=ADR/'artifacts/run-001'/cid
 call=next((ADR/'artifacts/run-001/provider').glob('call-*'+cid))
 payloads={p.name:read(p) for p in call.glob('*.json')}
 raw='\n\n'.join('### '+name+'\n\n```json\n'+json.dumps(value,ensure_ascii=False,indent=2)+'\n```' for name,value in payloads.items())
 contents=[f'ADR-0641 / run-001 / integrated. Actual Qwen3.8 provider payloads: exact. Baseline model not invoked.',case['question'],
 '법률 기준답변을 만들거나 채점하지 않았다. 사전 계약: 정확한 원기록 추적·미해결 보존·임의 도구/확정 판단 금지. 제품 입력에 골든 답변 없음.',
 '```json\n'+json.dumps(read(folder/'snapshot.json'),ensure_ascii=False,indent=2)+'\n```',
 '해당 없음: 명시된 원문 snapshot을 전달하는 compiler 계약 검사. RAG 회수·탈락 효과를 측정하지 않음.',raw,
 '이 호출 자체가 wiki compiler다. 추가 router/verifier/judge 호출 없음.',
 '코드의 span·참조·계약 검증 결과이며 법률 정답 판정이 아니다.',
 '```json\n'+json.dumps(run['results'][index],ensure_ascii=False,indent=2)+'\n```']
 path=ADR/'실험'/m['questions'][index]['file'];path.write_text('# '+cid+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qheads,contents))+'\n');m['questions'][index]['sha256']=sha(path)
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
texts=[f'구현 probe 완료. 법률 품질 승격 판단은 유보. 계약51·기존회귀30 통과, 실제 compiler {passed}/6 수락. MAIN·활성 릴리스·GENOS 불변.',
 '기존 v6는 완료 경험 위주이며 설계의 즉시 수신과 독립 지식 단위가 없었다. 새 v4 후보는 저장소·compiler·API·CLI·선택형 재사용을 격리 구현했다.',
 'artifacts/preregister.json과 실험 manifest에 실행 전 동결. C01-C20 계약과 실제6개 출력의 정확한 member 참조를 요구했다.',
 '공개 합성6사례, 고정 원문9블록, Qwen3.8 6회. legal answer baseline A/B는 수행하지 않았으며 이를 품질 개선으로 해석하지 않는다.',
 '후보 rev-001, baseline-pins.json, inputs.json 및 provider 요청·응답을 hash로 보존한다. Parasail FP8/reasoning none/fallback 없음.',
 f'실제 수락 {passed}/6. 51개 계약 및 기존 v6 30개 회귀 통과. 코드 기반 모의 검사와 실제 모델 출력 계약의 차이가 드러났다.',
 '\n'.join('- '+r['case_id']+': '+r.get('error','ACCEPTED') for r in run['results']),
 '실제 호출별 usage와 지연은 artifacts/run-001.json. 온라인 지연 개선·법률 정확도는 미측정이다.',
 '실제 모델 응답에는 법률 근거가 부족하거나 인용이 정확하지 않은 주장이 포함됐다. 이를 정상 법률 주장으로 넣지 않고 UNVERIFIED 관찰로 보존한다. 잘못된 주장은 미해결 관찰로 격리해 원자료와 함께 보존했다. 무검증 법률 판단 승인은 금지한다.',
 '6개는 합성 시스템 수락 사례이며 독립 법률 holdout이 아니다. GENOS 현장 접근·배포 없음. 다중 writer/NFS/법률 판단 재사용 품질 미인증.',
 '독립 법률 비교 평가 전에는 MAIN에 배선하지 않는다. 모든 코드·DB는 격리 연구 경로이며 활성 포인터 변경 없음. 후속 후보는 새 ADR에서 선점한다.',
 '`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine --final`\n\n완료 모델 실행은 재실행하지 않는다. 계약 검사는 `SHORTCUT_CANDIDATE_SNAPSHOT=revisions/rev-001/snapshot .venv/bin/python -m pytest 06_TOOLS/EXPERIMENTS/adr_0641`.' ]
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0641 shortcut v4 후보\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(sections['ADR_HEADINGS'],texts))+'\n')
(ADR/'실험/README.md').write_text('# 실제 compiler 사례 기록\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n\n법률 답변 비교가 아닌 공개 합성 기록의 지식 구성 수락 검사. 기존 v6와의 품질 우열은 미측정.\n')
files=[]
for p in (ADR/'artifacts').rglob('*'):
 if p.is_file() and p.name!='manifest.json' and p.suffix not in {'.pyc'}:
  files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'frozen compiler input, output or contract receipt','contains_raw_prompts_and_outputs':p.name in {'request.json','response.json','output.json'}})
put(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0641','created_at':m['reservation']['created_at'],'files':files})
index=ROOT/'04_EXPERIMENTS/ADR/README.md'
text=index.read_text();index.write_text(text.replace('# ADR workspace','# ADR workspace\n\n- [ADR-0641 shortcut v4 후보](ADR-0641-shortcut-claim-quarantine/README.md) — 계약51·회귀30 통과, 실제 실제 compiler 6/6 구성, 법률 판단 승인 없음, MAIN 불변.',1))
print('recorded',passed,'of 6')
