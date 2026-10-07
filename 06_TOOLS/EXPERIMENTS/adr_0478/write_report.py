"""Render sealed model results and complete payloads without changing the candidate."""
import hashlib
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest'
OUT=ADR/'artifacts/run-001'
def read(p):
    return json.loads(p.read_text())
def write(p,value):
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
    m=read(ADR/'artifacts/metrics.json')
    r=read(OUT/'result.json')
    trace=read(OUT/'trace.json') if (OUT/'trace.json').exists() else {}
    tables=read(OUT/'journal-tables.json') if (OUT/'journal-tables.json').exists() else {}
    views={v['view_id']:json.loads(v['body_json']) for v in tables.get('model_view',[])}
    phases=Counter(views.get(a['view_id'],{}).get('phase','unknown') for a in tables.get('model_attempt',[]))
    provider=sorted({u.get('upstream_provider','unknown') for u in r.get('usage',[])})
    success=bool(m['controller_completed'] and m['claim_count']>0)
    summary={'structural_success':success,'phase_attempts':dict(phases),
             'recovery_used':trace.get('recovery_used',0),'providers':provider,
             'limitations':trace.get('limitations',[]),'independent_accuracy':'not_evaluated',
             'permanent_policy_changed':False,'simultaneous_baseline':False,
             'stored_reference_agreement':m['reference_diagnostic']['agreement']}
    write(ADR/'artifacts/outcome.json',summary)
    verdict='선택·작성·검토 전환은 통과했지만 답변은 저장 기준과 불일치' if success else '자율 인용 답변 생성 기준 미달'
    stage='| 단계 | 원문 수 | 결정 조문 수 |\n|---|---:|---:|\n'
    for name,row in m['stages'].items():
        stage+=f'| {name} | {row["sources"]} | {row["decisive"]}/2 |\n'
    old=(ADR/'README.md').read_text()
    header=old.split('---',2)[1]
    if not success:
        header=header.replace('status: Proposed','status: Rejected')
    answer=r.get('result',{}).get('answer',{}).get('text','(최종 답변 없음)')
    sections=[
        ('결정 요약',verdict+'. 이는 CM003 단회 결과이며 법률 정답 인증이나 운영 승격이 아니다. 영구 전송 정책 변경 및 MAIN 변경 없음.'),
        ('문제와 변경 전 구조','ADR0476은 원문을 제시했어도 같은 READ를 반복하며 선택·주장 0개로 끝났다. ADR0477은 현재 제시 E와 읽음 상태, 직전 행동 결과, 요청 전체 1회 복구를 구현하고 합성 계약 33개를 통과했다. 이번에는 그 코드를 바꾸지 않고 실제 Qwen으로 재검증했다.'),
        ('가설과 사전 판정 기준','[PLAN](PLAN.md)과 [frozen-design](artifacts/frozen-design.json)을 첫 호출 전에 고정했다. FINAL뿐 아니라 모델의 명시적 근거 선택·초안·검토·인용 claim을 요구한다. 결정 원문 2개의 제시·선택·보존은 종료 후 별도 집계한다. 독립 법률 채점은 하지 않는다.'),
        ('실험 설계','CM003 한 문항, 후보 단독 1회. baseline은 부모 합성 구조 참고만이며 동시 실호출하지 않았다. 따라서 전후 효과 크기나 개선 인과를 추정하지 않는다. 공개 145문서, 동일 question/generation, 14 physical attempts, reserve3, tool56, wall300초, context60000자, output2800토큰. 실패 후 코드 수정·유료 재시도 없음. 구성요소 controller 경로이며 API/publication 실험은 아니다.'),
        ('데이터·모델·재현성','사용자 지시: qwen재검증만 일단 해봐. 기존 공개 원문 승인 범위에 이번 요청의 source fingerprint·scope·OpenRouter endpoint·Qwen 모델을 결속했다. 원문 manifest와 작업 gateway는 수정하지 않았다. 모델 qwen/qwen3.5-122b-a10b, FP8/no thinking 고정. 실제 provider: '+', '.join(provider)+'. 모델 입력에는 기준답변이나 decisive 좌표를 주입하지 않았다.'),
        ('결과',stage+'\n단계별 모델 시도: '+json.dumps(dict(phases),ensure_ascii=False)+
         f'\n\n시도 {m["physical_calls"]}회 / journal {m["journal_attempts"]}회, 최종 주장 {m["claim_count"]}개, gate={m["gate"]}, recovery={summary["recovery_used"]}.\n\n오류: '+json.dumps(m['error'],ensure_ascii=False)+'\n\n### 모델 최종 답변 원문\n\n'+answer),
        ('사례별 오류 분석','실제 요청 행동: '+json.dumps(m['tool_actions_requested'],ensure_ascii=False)+
         '\n\n한계 기록: '+json.dumps(summary['limitations'],ensure_ascii=False)+
         '\n\n원문 발견→제시→선택→최종 보존을 위 표에서 구분한다. 사후 저장 기준답변 대조에서는 불일치다. 모델은 제3호, 기준답변은 시행세칙 제23조 제4항 제2호의 예외에 따른 제3호 제외·제4호 적용이다. 탐색 입력에는 E7(시행세칙 제23조 전문)이 있었지만 E4(상장규정 제26조)만 채택했다. compose/review에는 E4만 원문으로 전달됐고 review는 SUPPORTED/RESOLVED로 승인했다. 즉 원문 미검색이 아니라 근거 선택에서 예외 원문을 잃고 검토에서도 복구하지 못했다. 이는 저장 기준과의 사후 대조이며 독립 법률 정확도 인증은 아니다.'),
        ('비용·지연·회수 규모',f'입력 {m["input_tokens"]:,}토큰, 출력 {m["output_tokens"]:,}토큰. Provider 보고 비용 ${m["provider_reported_cost_usd"]:.8f}. 초기화 포함 전체 {m["seconds"]}초. 단회라 일반화 가능한 p50/p95 없음. 실제 물리 시도와 journal 일치: {m["call_accounting_matches"]}. 회수 원장 gold는 제품 종료 후에만 결합했고 baseline 빈 집합은 기준군 0점이라는 뜻이 아니다.'),
        ('해석','구조적 자동 실행 관문: '+str(success)+'. 합성 검사와 실제 모델 결과를 구분한다. 실행 중단 문제와 별개로, 저장 기준답변과는 결론이 달라 CM003 답변까지 성공했다고 볼 수 없다. 현재 병목은 예외 원문의 채택·작성/검토 보존이다. 복구 분기는 이번에 0회로 실모델 효과를 검증하지 못했다. 이 한 사례로 Qwen 일반 성능이나 후보의 정답률 개선을 인증하지 않는다.'),
        ('한계와 일반화 가능 범위','인샘플 단회, 동시 기준군 없음, 독립 judge 없음, 최신 법령 확인 없음. 재검증 성공/실패를 51문항 품질이나 GENOS 현장 성능으로 확대하지 않는다.'),
        ('운영 결정·롤백 조건','document-navigation-v1 및 영구 전송 정책 불변. 후보 explicit injection만 사용했고 기본 registry에 등록하지 않았다. 추가 코드 변경·반복·전수 검증은 새 요청/ADR 범위다. 저장소 전역 graph에는 기존 ADR0305/0444/0158 오류가 있어 전체 저장소 검증 통과로 보고하지 않는다.'),
        ('재현 명령','실행 디렉터리가 있으면 --execute 재실행을 거부한다. 새 유료 반복은 새 ADR에서 한다.\n\n```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0478/run_autonomy.py\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest --final\n```\n\n[질문별 전체 기록](실험/질문-001-cm-003.md) · [지표](artifacts/metrics.json) · [산출물](artifacts/manifest.json)')
    ]
    (ADR/'README.md').write_text('---'+header+'---\n\n# 행동 피드백 후보 CM003 Qwen 재검증\n\n'+
        '\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
    (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | 판정 | 기록 |\n|---|---|---|\n| cm-003 | '+verdict+' | [전체 입출력](질문-001-cm-003.md) |\n\n독립 법률 채점 및 동시 기준군 없음. MAIN unchanged.\n')
    q='# 질문 001 — cm-003\n\n## 1. 실행 메타\n\n2026-09-20 / run-001 / qwen-retest / exact. 모델·횟수·오류는 아래 원시 결과와 지표 정본.\n\n## 2. 사용자 질문 원문\n\n'+read(ADR/'fixture.json')['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n독립 judge 채점 없음. 사후 기준답변 대조는 별도 reference-diagnostic.json에 기록했다. 결정 조문 좌표는 제품 종료 후 원장에만 결합.\n\n## 4. 제품 입력을 구성한 원값\n'
    payloads=[('### 원문·카드·선택 trace',OUT/'trace.json'),
              ('### 회수·탈락 단계 원장 — run·arm별',ADR/'artifacts/retrieval-stage-ledger.json'),
              ('## 5. 제품 모델 호출 — run·arm별 실제 원문',OUT/'journal-tables.json')]
    for d in sorted((OUT/'calls').glob('call-*')):
        payloads.extend(('### '+d.name+' / '+p.name,p) for p in sorted(d.glob('*.json')))
    payloads.extend([('### 전체 실행 결과',OUT/'result.json'),('### 지표',ADR/'artifacts/metrics.json'),('### 사후 기준답변 대조 (제품 입력 아님)',ADR/'artifacts/reference-diagnostic.json')])
    for title,path in payloads:
        if path.exists():
            q+='\n'+title+'\n\n```json\n'+path.read_text().rstrip()+'\n```\n'
    q+='\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n모든 단계와 형식 수리 포함 실제 요청은 위 호출 기록에 전량 보존. 단계별 시도: '+json.dumps(dict(phases),ensure_ascii=False)+'\n\n## 7. 채점 호출과 반복 판정\n\njudge 0회, 단회 자율 실행. 독립 정확도 미평가.\n\n## 8. 사례 최종 판정\n\n'+verdict+'. 법률 정답률과 구별한다.\n'
    (ADR/'실험/질문-001-cm-003.md').write_text(q)
    paths=[p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p!=ADR/'artifacts/manifest.json']
    paths+=list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0478').glob('*.py'))+[ADR/'PLAN.md',ADR/'fixture.json']
    am=read(ADR/'artifacts/manifest.json')
    am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                  'bytes':p.stat().st_size,'description':'Sealed autonomous Qwen retest artifact',
                  'contains_raw_prompts_and_outputs':p.name in ('request.json','response.json','journal-tables.json','journal.sqlite')} for p in sorted(paths)]
    write(ADR/'artifacts/manifest.json',am)
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
    main()



