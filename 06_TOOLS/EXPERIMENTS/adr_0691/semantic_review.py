"""Render the human-readable review from individually inspected source notes."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout'
read=lambda p:json.loads(p.read_text())
dataset=read(A/'artifacts/design/dataset.json')
lines=['# 판단 루프 후보의 의미 검토','',
'고정된 로컬 원문과 실제 답변을 비교한 진단이다. 인용 일치는 의미 정확성과 다르며, 최신 법령이나 현장 성능을 인증하지 않는다. 새로운 judge 모델 호출은 하지 않았다.',
'','신규 조문은 이 프로젝트의 조사된 이전 실행 입력과 평가 자료에서 제외한 조문 root라는 뜻이다. 사전학습에 포함되지 않은 법률이나 전체 비공개 업무를 뜻하지 않는다.',
'','후보와 기준의 장단점을 함께 기록한다. 세부 판단 오류는 후속 개선으로 남기며 사전 동결된 승격 기준을 소급 변경하지 않는다.','']
for case in dataset['cases']+dataset['regression_cases']:
    cid=case['case_id'];lines+=['## '+cid,'',case['question'],'']
    for arm in ('baseline','repaired'):
        result=read(A/'artifacts/run-001'/arm/cid/'result.json')
        lines+=['### '+arm,'',f"HTTP: {result['http_status'] if result['http_status'] is not None else '중단·최종 응답 미확인'}. 모델 호출 시도: {result['model_calls']}회.",'']
        note=A/'artifacts/semantic-notes'/(cid+'-'+arm+'.json')
        if note.exists():
            n=read(note);lines += ['- '+x for x in n.get('findings',n.get('observed',[])+n.get('remaining_detail',[]))]
        else:lines += ['- 아직 개별 의미 검토를 기록하지 않았다. 기계 검사 통과로 대체하지 않는다.']
        lines+=['',f'[원 실행 결과](artifacts/run-001/{arm}/{cid}/result.json) · [계약·인용·상태 진단](artifacts/run-001/{arm}/{cid}/diagnostic.json)','']
(A/'SEMANTIC_REVIEW.md').write_text('\n'.join(lines)+'\n')
print('Rendered source-grounded semantic review')
