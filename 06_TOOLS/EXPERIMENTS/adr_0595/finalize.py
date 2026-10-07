"""Finalize reports and metadata only; never alter product output or frozen scoring."""
import hashlib
import json
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0595-rag-chain-command-repair'
REPORT=ROOT/'07_DOCS/REFERENCE/REPORTS/ADR-0595_RAG_CHAIN_STRICT_REPAIR_20261001.md'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'

def main():
    run=ADR/'artifacts/run-001';m=json.loads((ADR/'실험/manifest.json').read_text());r=json.loads((run/'result.json').read_text());s=r['summary'];gold=json.loads((ADR/'artifacts/design/gold.json').read_text());inputs=json.loads((ADR/'artifacts/design/inputs.json').read_text())
    failures=[{'case':g['case_id'],'checks':[x for x in g['arms']['REPAIRED']['checks'] if not x['pass']]} for g in r['grades'] if not g['arms']['REPAIRED']['all_pass']]
    diagnostics={'review_kind':'Read-only completed-output review; frozen grading unchanged','result_sha256':sha(run/'result.json'),'unexpected_status':[],'unnecessary_reassessment':[],'final_text_mismatch':[],'response_binding_errors':[],'rejected_drafts':[],'command_repairs':[]}
    for c in r['products']:
        for i in c['arms']['REPAIRED']:
            o=i['observed'];t=i['product_input'];b=i['measurement']
            allowed={'ERROR'} if t.get('fault') else {'FIXTURE'} if t.get('action')=='wrong_link' else {'READY','INSPECTED','REUSED'}
            if o['status'] not in allowed:diagnostics['unexpected_status'].append({'case':c['case_id'],'turn':i['turn'],'observed':o})
            if c['case_id']=='SEQ01' and 3<=i['turn']<=14 and o.get('executed')!=['COMPOSE']:diagnostics['unnecessary_reassessment'].append({'turn':i['turn'],'executed':o.get('executed')})
            for v in i.get('text_audits',[]):
                if not v['consistent']:diagnostics['final_text_mismatch'].append({'case':c['case_id'],'turn':i['turn'],'audit':v})
            if o['status'] in ('READY','INSPECTED','REUSED') and (o.get('route_id')!=b['route_id'] or o.get('route_goal')!=b['route_goal']):diagnostics['response_binding_errors'].append({'case':c['case_id'],'turn':i['turn']})
        db=sqlite3.connect(run/c['case_id']/'REPAIRED/chain.sqlite')
        for tid,kind,payload in db.execute("SELECT turn_id,kind,payload FROM receipt WHERE kind IN ('ANSWER_CONTRACT','COMMAND_CONTRACT')"):
            x=json.loads(payload)
            if kind=='ANSWER_CONTRACT' and not x['accepted']:diagnostics['rejected_drafts'].append({'case':c['case_id'],'turn':tid,**x})
            if kind=='COMMAND_CONTRACT' and x['attempt']>0:diagnostics['command_repairs'].append({'case':c['case_id'],'turn':tid,**x})
        db.close()
    write(run/'diagnostic-audit.json',diagnostics)
    cause_table=['| 원인 | 수정 |','|---|---|','| FOLLOW가 명시 단계를 덮어씀 | 지정한 단계와 변경 조건·pending 중 가장 앞단부터 재실행 |','| 원본 없는 복원 명령 수용 | 동일 질문의 회수 원발언 확인; 원본이 없으면 상태를 바꾸지 않고 적용 보류 |','| 직접 변경/과거 복원 표현 차이로 정상 요청 거부 | 실제 적용 값의 의미 동등성 확인, 불필요한 복원 메타데이터 정리, 명령 수리 최대 1회 |','| 기존 근거 설명에 재판단 실행 | 설명은 COMPOSE, 선별·검토·판단 요청은 해당 단계로 구분 |','| 조회/재사용 응답에 판단 누락 | 소비 경로의 immutable 노드에서 assessment·retrieval·goal·revision 함께 반환 |','| 다른 질문의 마지막 검색을 집계 | 최종 응답의 실제 route_id와 goal에 집계 결속 |','| LLM 답변 문장이 현재 판단과 모순 | facts·절차·출처의 기계 검사와 text 검증; 작성 수리 1회 실패하면 게시 차단 |','| 긴급 미확인과 비긴급을 혼동 | null/false/true를 상태·판단·답변에서 유지 |','| native 기록 실패 뒤 head 변경 | node/head 트랜잭션 롤백 |']
    b=s['by_arm']['REPAIRED'];g=s['guard_checks'];cal=s['calibration']
    lines=['# 멀티턴 체인 엄격 수정 결과','', 'ADR-0595 · WSL 로컬 · 합성 원문 6단위 · 6개 연속 대화·49턴 · Qwen3.8 · MAIN 미변경','', '이번 구현은 research 프로토다. 실제 RAG API/Coordinator, GENOS, 의미 기반 wiki 검색, DB 관리·법률 승인 연결은 포함하지 않는다.','',f"순차 기능 검사 **{b['checks_passed']}/{b['checks_total']}**, 전체 사례 **{b['sequences_passed']}/{b['sequences_total']}**. 모델 0회 adversarial 계약 **{g['passed']}/{g['total']}**, 실제 모델 text 검증기 calibration **{cal['passed']}/{cal['total']}**(false pass {cal['false_pass']}, false fail {cal['false_fail']}).",'','## 원인별 수정','',*cause_table,'','## 관측 누락을 포함한 별도 확인','',block({k:len(v) for k,v in diagnostics.items() if isinstance(v,list)}),'재시도는 제품 command 1회·compose 1회로 제한하며 원 요청·거절 이유·수리 결과를 기록한다. 실험 전체를 몰래 재실행하지 않는다.','', '## 기능별 확인','', '| 사례 | 통과 검사 | 핵심 확인 |','|---|---|---|']
    descriptions={'SEQ01':'긴 대화의 최초 조건 역추적, 설명 12턴의 upstream 유지, 최종 경로 재사용','SEQ02':'다른 질문 보존, 정정·재정정·조회','SEQ03':'PLAN·SELECT 재진입, 표/문장 작성만 실행, 긴급 판단 조회','SEQ04':'잘못 연결한 경험만 수정, 다른 묶음 보존','SEQ05':'반복 정정·오차단 회귀·ASSESS 실패 후 재개·퇴역 경로 재수집 차단','GUARD':'미확인→비긴급→긴급→미확인, 조회·재사용'}
    for x in r['grades']:a=x['arms']['REPAIRED'];lines.append(f"| {x['case_id']} | {a['passed']}/{a['total']} | {descriptions[x['case_id']]} |")
    lines+=['','## 미충족 항목','',block(failures),'## 비용·지연·범위','',block(s),'코드·schema·prompt를 바꾼 인샘플 실험이므로 일반 법률 정확도나 GENOS 성능으로 일반화하지 않는다. 검증기 calibration 15개는 작은 합성 표본이며 완전한 의미 검증을 인증하지 않는다.','', '[전체 턴·모델 원문](../../../'+str((ADR/'실험/README.md').relative_to(ROOT))+') · [코드·계보](../../../'+str((ADR/'README.md').relative_to(ROOT))+')']
    REPORT.write_text('\n'.join(lines)+'\n')
    ledger=json.loads((run/'retrieval-stage-ledger.json').read_text())
    for q,c,gr in zip(m['questions'],r['products'],r['grades']):
        cid=q['case_id'];parts=['# '+cid,'','## 1. 실행 메타','ADR-0595 / REPAIRED / run-001 / qwen/qwen3.8-27b / 합성 연속 대화','## 2. 사용자 질문 원문',block(next(x for x in inputs if x['case_id']==cid)),'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid]),'## 4. 제품 입력 원값',block(c),'### 회수·탈락 원장',block([x for a in ledger['runs'][0]['arms'] for x in a['cases'] if x['case_id']==cid]),'## 5. 제품/중간/오프라인 모델 호출 원문']
        folders=list((run/'provider').rglob('call-*'+cid+'-*'))+list((run/'offline-evaluator').rglob('call-*'+cid+'-*'))
        if cid=='GUARD':folders+=list((run/'calibration').glob('call-*'))
        for folder in sorted(set(folders)):
            parts+=['### '+str(folder.relative_to(run))]
            for name in ['request.json','validation-schema.json','binding.json','response.json','output.json','error.json']:
                p=folder/name
                if p.exists():parts+=['#### '+name,block(json.loads(p.read_text()))]
            if not (folder/'response.json').exists():parts.append('provider 원응답 미확보: error receipt를 확인한다.')
        parts+=['## 6. 중간 LLM 호출','resolve, command-verify, command-repair, select, assess, compose, text verifier와 compose repair를 위 원문으로 보존했다.','## 7. 채점·반복 판정','제품 완료 후 별도 offline evaluator가 text를 검사했다. 불일치 시 사전 선언한 추가 audit 1회만 수행하며 제품을 바꾸지 않는다. calibration labels도 모든 해당 출력을 얻은 뒤에만 결합했다.','## 8. 사례 판정',block(gr)]
        if cid=='GUARD':parts+=['### 모델 없는 계약 검사',block(r['guard_result']),'### 실제 검증기 calibration',block(json.loads((run/'calibration-result.json').read_text()))]
        (ADR/'실험'/q['file']).write_text('\n'.join(parts)+'\n')
    m['runs'][0].update(status='complete',artifact_path=str((run/'result.json').relative_to(ROOT)),sha256=sha(run/'result.json'))
    m['results'].update(status='complete',by_arm=s['by_arm'],comparisons=[],judge_disagreements=s['judge_disagreements'],usage=s['usage'],latency=s['turn_latency_seconds'],error_taxonomy=[{'type':'other','failures':failures}])
    for k,v in s['retrieval']['REPAIRED'].items():m['retrieval_accounting'][k]={'REPAIRED':v}
    m['retrieval_accounting']['stage_ledger'].update(artifact_path=str((run/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256=sha(run/'retrieval-stage-ledger.json'))
    write(ADR/'실험/manifest.json',m)
    front=(ADR/'README.md').read_text().split('---',2)[1]
    headings=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
    texts=['원인별 엄격 수정 및 순차 회귀. [상세 결과](../../../'+str(REPORT.relative_to(ROOT))+')','ADR0594에서 정상 정정이 메타데이터 표현 차이로 차단되고 설명 요청에 ASSESS가 반복됐다. 앞선 기록은 보존한다.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'6개 case·49턴, case별 순차 실행, 격리 client/DB 두 worker. 부모 arm은 재호출하지 않아 paired 비교는 없다.','합성 자료만 사용. Qwen3.8 Parasail FP8 reasoning none. frozen manifest·code·runner hash 일치 후 실행.',block(s['by_arm'])+'\n\n'+block({'guards':g,'calibration':cal}),block(failures),block({'usage':s['usage'],'latency':s['turn_latency_seconds'],'retrieval':s['retrieval']}),'score만으로 전체 정상성을 주장하지 않는다. 진단 audit·수리·게시 여부도 함께 확인했다. 이전 76/77·237/242와 다른 검사 범위다.','작은 합성 인샘플. 실제 법률·GENOS·공유 세션 경합·wiki 의미 검색 미검증. 동일 모델 기반 의미 판정 한계가 있다.','MAIN unchanged. 활성 포인터·원문·SQL·완료 부모 보존. 전역 graph의 기존 오류가 남으면 전체 정식 절차 완료라고 보고하지 않는다.','동결 runner는 기존 run이 있으면 거부한다. 새 반복·코드·채점 변경은 새 ADR로 기록한다.']
    (ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0595 — 멀티턴 체인 명령 수리\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+t for i,(h,t) in enumerate(zip(headings,texts),1))+'\n')
    (ADR/'실험/README.md').write_text('# 질문 인덱스\n\n| 사례 | REPAIRED 검사 |\n|---|---|\n'+'\n'.join('| ['+q['case_id']+']('+q['file']+') | '+str(g['arms']['REPAIRED']['passed'])+'/'+str(g['arms']['REPAIRED']['total'])+' |' for q,g in zip(m['questions'],r['grades']))+'\n')
    index=ROOT/'04_EXPERIMENTS/ADR/README.md'
    if ADR.name not in index.read_text():index.write_text(index.read_text()+'\n- [ADR-0595 — 멀티턴 체인 엄격 수정]('+ADR.name+'/README.md)\n')
    print(json.dumps({'summary':s,'report':str(REPORT.relative_to(ROOT))},ensure_ascii=False))
if __name__=='__main__':main()
