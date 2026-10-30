from common import *
c=read(DES/'candidate.json');m=read(ADR/'실험/manifest.json');T=Path(__file__).parent
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(c['candidate_revision'],candidate_id='diagnostic',experiment_id=m['experiment_id'],arm_id='diagnostic',run_ids=['run-001'],runner_path=str((T/'probe.py').relative_to(ROOT)),runner_sha256=sha(T/'probe.py'))])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 body=['run-001/diagnostic; 합성 JSON 문법 진단','왜 계속 error랑 null이 나오는지 원인 찾아서 수정해봐','법률 gold 없음. 입력에 명시한 합성 JSON 동일 출력만 점검.',str((DES/'requests.json').relative_to(ROOT))+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n합성 입력만 사용, 검색 없음.','호출 전. live/calls에서 전송·응답 무손실 보존.','중간 모델 0. 선언한 8변형 최대9물리/429전환1.','채점 모델0. JSON 동일성과 schema 유효성 점검.','실행 전. 원인 미확정. 제품 변경 없음.']
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+v for i,(h,v) in enumerate(zip(heads,body),1))+'\n');q['sha256']=sha(p)
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
inputs={str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')}
put(DES/'freeze.json',{**c,'inputs':inputs,'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
print('FROZEN synthetic only, 4 variants maximum5physical calls')
