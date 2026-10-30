from common import *
c=read(DES/'candidate.json');m=read(ADR/'실험/manifest.json');T=Path(__file__).parent
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(c['candidate_revision'],candidate_id='main120',experiment_id=m['experiment_id'],arm_id='main120',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,case in zip(m['questions'],read(DES/'cases.json')):
 body=['run-001/main120; 실제 저장 판단 조각 순차 시연','MAIN120 스키마 최적화 결과로 실제 모델 실험해봐','evaluation-only/expectations.json은 사후 점검 전용. 법률 gold 점수 미확정.',json.dumps(case,ensure_ascii=False,indent=2)+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n고정 원문 단위의 authoring만 실행. RAG 회수/가지치기 없음. 용어 후보는 별도 영수증에 기록.','호출 전. live/calls/에서 전송 원문·응답을 무손실 보존한다.','NORMALIZE 다음 ACCUMULATE. 단계당 형식 보완 최대1회.','별도 채점 LLM 0. 원문과 저장 결과를 사후 대조한다.','실행 전. 기준·제품 코드 변경 없이 결과와 실패를 보존한다.']
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+v for i,(h,v) in enumerate(zip(heads,body),1))+'\n');q['sha256']=sha(p)
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
inputs={str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')}
put(DES/'freeze.json',{**c,'inputs':inputs,'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
print('FROZEN, maximum 9 physical calls, no live calls yet')
