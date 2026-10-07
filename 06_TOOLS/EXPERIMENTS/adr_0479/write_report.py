"""Render sealed model results and complete payloads without changing the candidate."""
import hashlib
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence'
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
    success=bool(m['controller_completed'] and m['claim_count']>0 and m['linked_bounds_pass'])
    summary={'structural_success':success,'phase_attempts':dict(phases),
             'recovery_used':trace.get('recovery_used',0),'providers':provider,
             'limitations':trace.get('limitations',[]),'independent_accuracy':'not_evaluated',
             'permanent_policy_changed':False,'simultaneous_baseline':False,
             'stored_reference_agreement':m['reference_diagnostic']['agreement']}
    write(ADR/'artifacts/outcome.json',summary)
    verdict=('제한 보존 구조 통과' if success else '구조 또는 실행 기준 미달')+'; 저장 기준 대조: '+m['reference_diagnostic']['agreement']
    stage='| 단계 | 원문 수 | 결정 조문 수 |\n|---|---:|---:|\n'
    for name,row in m['stages'].items():
        stage+=f'| {name} | {row["sources"]} | {row["decisive"]}/2 |\n'
    old=(ADR/'README.md').read_text()
    header=old.split('---',2)[1]
    if not success:
        header=header.replace('status: Proposed','status: Rejected')
    answer=r.get('result',{}).get('answer',{}).get('text','(최종 답변 없음)')
    historical=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest/artifacts/metrics.json')
    token_delta=m['input_tokens']-historical['input_tokens']
    token_pct=100*token_delta/historical['input_tokens']
    history_root=ROOT/'04_EXPERIMENTS/ADR/ADR-0478-action-feedback-qwen-retest/artifacts/run-001'
    def phase_usage(result,journal):
        phase_by_view={v['view_id']:json.loads(v['body_json'])['phase'] for v in journal['model_view']}
        aggregated={}
        assert len(result['usage'])==len(journal['model_attempt'])
        for attempt,usage in zip(journal['model_attempt'],result['usage']):
            p=phase_by_view[attempt['view_id']]
            row=aggregated.setdefault(p,{'calls':0,'input_tokens':0,'output_tokens':0})
            row['calls']+=1
            row['input_tokens']+=usage.get('input_tokens') or 0
            row['output_tokens']+=usage.get('output_tokens') or 0
        return aggregated
    cost_comparison={'historical':phase_usage(read(history_root/'result.json'),read(history_root/'journal-tables.json')),
                     'candidate':phase_usage(r,tables),'simultaneous_baseline':False}
    write(ADR/'artifacts/phase-cost-comparison.json',cost_comparison)
    cost_table='| 입력 토큰 | 역사적 ADR0478 | 이번 ADR0479 |\n|---|---:|---:|\n'
    for phase in ('investigate','compose','review'):
        oldp=cost_comparison['historical'].get(phase,{})
        newp=cost_comparison['candidate'].get(phase,{})
        cost_table+=f'| {phase} | {oldp.get("input_tokens",0):,} ({oldp.get("calls",0)}콜) | {newp.get("input_tokens",0):,} ({newp.get("calls",0)}콜) |\n'
    sections=[
        ('결정 요약',verdict+'. 후보 구현과 합성 계약 47개, CM003 Qwen 단회까지 검증했다. 전체 품질 인증이나 운영 승격은 아니다. MAIN 및 영구 전송 정책 불변.'),
        ('문제와 변경 전 구조','ADR0478에서는 결정 원문 2개가 최초 입력에 있었지만 모델이 상장규정만 선택했다. 작성·검토의 selected-only 필터로 시행세칙 원문이 사라졌고 저장 기준과 다른 결론을 냈다. 이번 변경은 모든 읽기 기록을 모델에 누적하지 않고 직접 연결 원문만 작게 유지한다.'),
        ('가설과 사전 판정 기준','[PLAN](PLAN.md)과 [동결 설계](artifacts/frozen-design.json)을 호출 전에 고정했다. 같은 scope·hash의 이미 READ된 근거 중 선택 근거와 강하게 해소된 1홉 참조만 허용한다. 실제 읽은 참조 문장에 단서·예외·정하는·준용 표지가 있는 경우 최대 2개 원문, 합계 3000자만 보존한다. 특정 조문명·번호·정답 ID 없음. 원문 보존과 저장 기준 일치를 별도로 판정한다.'),
        ('실험 설계','CM003 후보 단회. 모델의 selected는 그대로 두고 server packet에 supplemental evidence를 추가한다. 작성 모델이 실제 제시받은 E를 인용할 때만 claim이 생긴다. 새 검색/READ/모델 단계/다중 hop/finding 선행 요구 없음. 선택 원문 우선, 보조 원문 예산 초과는 미제시 기록. 이미 인용한 보조 원문이 review에서 안 들어가면 중단한다. 합성 1차 46통과/1실패는 잘못된 테스트 기대값을 수정했고 후보 코드는 변경 없이 2차 47통과했다. 실제 Pipeline 합성 연결 포함; 실모델은 구성요소 controller 경로이며 API/publication 검증은 아니다.'),
        ('데이터·모델·재현성','부모 ADR0478 rev-001을 복제해 4개 source-first 모듈만 바꾼 동결 후보 rev-001이다. 사용자 진행 및 기존 공개 원문/Qwen 승인 범위로 145문서·source fingerprint·OpenRouter endpoint를 이번 요청에 결속했다. 모델 qwen/qwen3.5-122b-a10b, thinking off, 실제 provider '+', '.join(provider)+'. model14/reserve3/tool56/wall300/context60000/output2800 고정. 정답과 결정 조문 좌표는 제품에 주입하지 않고 종료 후 결합했다.'),
        ('결과',stage+'\n모델 명시 선택(보조 문맥과 별개): '+json.dumps(m['model_selected'],ensure_ascii=False)+
         '\n\n단계별 모델 시도: '+json.dumps(dict(phases),ensure_ascii=False)+
         '\n\n추가 원문 실제 제시: '+json.dumps(m['linked_presentations'],ensure_ascii=False)+
         f'\n\n물리 {m["physical_calls"]}회 / journal {m["journal_attempts"]}회; 주장 {m["claim_count"]}개; gate={m["gate"]}; recovery={summary["recovery_used"]}. 오류: '+json.dumps(m['error'],ensure_ascii=False)+
         '\n\n### 모델 최종 답변 원문\n\n'+answer),
        ('사례별 오류 분석',m['reference_diagnostic']['explanation']+
         '\n\n실제 요청 행동: '+json.dumps(m['tool_actions_requested'],ensure_ascii=False)+
         '\n\n한계 기록: '+json.dumps(summary['limitations'],ensure_ascii=False)+
         '\n\n참조 연결/제외 기록: '+json.dumps(m['linked_packs'],ensure_ascii=False)+
         '\n\n회수 원장의 packed는 모델 선택이 아니라 작성 입력 봉투다. model_selected를 별도 기록해 자동 채택으로 오해하지 않게 했다.'),
        ('비용·지연·회수 규모',cost_table+'\n\n'+f'입력 {m["input_tokens"]:,}토큰 / 출력 {m["output_tokens"]:,}토큰 / 비용 USD {m["provider_reported_cost_usd"]:.8f} / 초기화 포함 {m["seconds"]}초. 최대 2개·3000자 상한 검사: {m["linked_bounds_pass"]}. 물리 호출 회계 일치: {m["call_accounting_matches"]}. 역사적 ADR0478 입력 {historical["input_tokens"]:,}토큰 대비 {token_delta:+,} ({token_pct:+.1f}%). 동시 기준군이 아니고 모델 행동 차이를 포함하므로 증가분 전부를 보조 원문의 비용으로 단정하지 않는다. 3000자는 토큰도 전체 직렬화 크기도 아니며 호출마다 반복 비용이 생긴다. 단회 p50/p95 성능 추정 없음.'),
        ('해석',m['reference_diagnostic']['interpretation']+
         '\n\n모델이 틀릴 수 있다는 전제를 추가 설명·모든 원문 누적·새 검토 루프로 구현하지 않았다. 서버가 이미 읽은 직접 연결 근거를 정해진 크기로 남기는 접근을 시험했다. 이 규칙은 연결 누락·잘못된 참조 해소·표지 없는 예외·미독 원문·3000자 초과를 해결하지 못하며 포괄적 예외 검사도 아니다.'),
        ('한계와 일반화 가능 범위','CM003 인샘플 1회, 동시 기준군/독립 judge/법령 최신성 확인 없음. 저장 기준답변과의 사후 대조일 뿐 독립 법률 정확도 인증이 아니다. 무모델 계약과 실모델 결과를 구분한다. 모델 일반 성능이나 51문항 정답률 개선으로 확대하지 않는다. 첫 읽기에서 못 찾은 예외를 이번 정책이 찾아주지는 않는다.'),
        ('운영 결정·롤백 조건','운영 document-navigation-v1과 영구 전송 정책 유지. 기본 registry에 등록하지 않은 후보 explicit injection만 실행했다. 결과 후 후보 수정·유료 재실행 없음. 승격 전 같은 시점의 기준군과 51문항을 비교해야 한다. 저장소 전역 graph의 기존 ADR0305/0444/0158 오류는 이번 결과와 별도이며 전체 저장소 통과를 주장하지 않는다.'),
        ('재현 명령','이미 실행 디렉터리가 있으면 --execute를 거부한다. 새 유료 반복은 별도 사전 고정이 필요하다.\n\n'
         '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0479/run_autonomy.py\n\n'
         '.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0479-bounded-linked-evidence --final\n\n'
         '[전체 질문·요청·응답](실험/질문-001-cm-003.md) · [지표](artifacts/metrics.json) · [산출물](artifacts/manifest.json)')
    ]
    (ADR/'README.md').write_text('---'+header+'---\n\n# 직접 연결 원문의 제한 보존과 CM003 Qwen 검증\n\n'+
        '\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
    (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | 판정 | 기록 |\n|---|---|---|\n| cm-003 | '+verdict+' | [전체 입출력](질문-001-cm-003.md) |\n\n독립 법률 채점 및 동시 기준군 없음. MAIN unchanged.\n')
    q='# 질문 001 — cm-003\n\n## 1. 실행 메타\n\n2026-09-20 / run-001 / linked-context / exact. 모델·횟수·오류는 아래 원시 결과와 지표 정본.\n\n## 2. 사용자 질문 원문\n\n'+read(ADR/'fixture.json')['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n독립 judge 채점 없음. 사후 기준답변 대조는 별도 reference-diagnostic.json에 기록했다. 결정 조문 좌표는 제품 종료 후 원장에만 결합.\n\n## 4. 제품 입력을 구성한 원값\n'
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
    paths+=list((ROOT/'06_TOOLS/EXPERIMENTS/adr_0479').glob('*.py'))+[ADR/'PLAN.md',ADR/'fixture.json']
    am=read(ADR/'artifacts/manifest.json')
    am['files']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                  'bytes':p.stat().st_size,'description':'Sealed autonomous Qwen retest artifact',
                  'contains_raw_prompts_and_outputs':p.name in ('request.json','response.json','journal-tables.json','journal.sqlite')} for p in sorted(paths)]
    write(ADR/'artifacts/manifest.json',am)
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
    main()





