"""Read completed wire records only; no replay, evaluator, database or product changes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(ROOT))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def view(path):
    request=read(path)
    return next(json.loads(m['content'])['view'] for m in request['messages'] if m['role']=='user')

def main():
    freeze=read(ART/'design-freeze.json');matrix=ART/'matrix'
    cells=[];inputs={};total_calls=0;cost=0.;seconds=0.;navigation_calls=0;maximum_chars=0
    for d in sorted(matrix.glob('[0-9]*-*')):
        if not d.is_dir() or not (d/'result.json').exists():continue
        result=read(d/'result.json');audit=read(d/'execution-audit.json');metrics=read(d/'metrics.json')
        total_calls+=result['model_calls'];cost+=sum(u['cost_usd'] for u in result['usage']);seconds+=result['seconds']
        nav=[c for c in audit['calls'] if 'read-choice' in (c.get('source_stage') or '')]
        navigation_calls+=len(nav);maximum_chars=max(maximum_chars,*[c['request_chars'] for c in audit['calls']])
        cells.append({'cell':result['cell'],'outcome':result['outcome'],'completed':result['completed'],
            'calls':result['model_calls'],'seconds':result['seconds'],'navigation_calls':len(nav),
            'source_integrity':metrics['source_integrity'],'output_errors':metrics['output_errors'],
            'coordinates':metrics['coordinates'],'native_failures':[
                {k:e.get(k) for k in ('error_code','error_type','error_message','location')} for e in result['native_failures']]})
        for name in ('result.json','metrics.json','execution-audit.json'):
            inputs[rel(d/name)]=sha(d/name)
    d=matrix/'003-fsc-hard-005-A2'
    before_path=d/'model/call-005-service/request.json';after_path=d/'model/call-006-service/request.json'
    before,after=view(before_path),view(after_path)
    assert before['ontology_review']['pages']==after['ontology_review']['pages']
    assert before['ontology_review']['source_refs']==after['ontology_review']['source_refs']
    assert len(before['sources'])==len(after['sources'])==12
    diffs=[]
    for a,b in zip(before['sources'],after['sources'],strict=True):
        assert a['id']==b['id']
        changes={k:{'before':a.get(k),'after':b.get(k)} for k in set(a)|set(b) if a.get(k)!=b.get(k)}
        if changes:diffs.append({'source_id':a['id'],'changes':changes})
    assert len(diffs)==1 and set(diffs[0]['changes'])=={'presentation_id'}
    for p in (before_path,after_path):inputs[rel(p)]=sha(p)
    proof={'same_page_ids':[p['page_id'] for p in before['ontology_review']['pages']],
        'same_page_metadata':True,'same_source_refs':True,'source_count':12,
        'source_card_differences':diffs,'source_text_spans_owners_order_unchanged':True,
        'sources_sha256_before':before['ontology_review']['sources_sha256'],
        'sources_sha256_after':after['ontology_review']['sources_sha256'],
        'code_location':'02_BACKEND/semantic_runtime/legal_agent/ontology_review.py:236-241',
        'propagation':['law_navigation.execute_tool:1829', 'evidence_inventory.acknowledge:294-299',
            'evidence_inventory.confirmed_pages:57-68', 'decision_projection.retain_requested:858-870',
            'ontology_review.reconcile:236-241'],
        'native_journal_receipts':[
            {'seq':290,'role':'previous ontology page receipt','payload_sha256':'3b28e712219da9359a978bb3c147604bf865f109bc8b131c433c5d6c8871606a'},
            {'seq':328,'role':'next successful delivery','payload_sha256':'deb78712a64368c09debf4f6fdec82cc7c723bcad35fb6ea7672c01389fc310a'},
            {'seq':334,'role':'blocked transition','payload_sha256':'c94c607c0bcb0ccce086f5a96e8afd416d2a9a26c6a3498e0e2f7491f0b19d7c'}],
        'cause':'Same stable ontology page ID collides with a full source-card hash that includes changing presentation metadata.'}
    value={'schema_version':'adr1066-read-only-live-diagnosis-v1','at':datetime.now(timezone.utc).isoformat(),
        'status':'STOPPED_PARTIAL','planned_cells':9,'attempted_cells':3,'limited_answers':2,'fatal_stops':1,'not_run':6,
        'product_calls':total_calls,'offline_judge_calls':0,'observed_cost_usd':cost,'product_seconds':seconds,
        'navigation_calls':navigation_calls,'maximum_request_chars':maximum_chars,'cells':cells,
        'runtime_receipt_collision':proof,
        'separate_audit_error':{'error':'WireAuditError: WIRE_DOCUMENT_ID_MISSING',
            'first_occurrence':'001-fsc-hard-005-A0/call-004-service exact_evidence[0], block390, 0..22',
            'cause':'Legacy gate.explicit_spans demands parent document_id on evidence-ID-bound cards; frozen delivery_spans verifies ownership through native evidence receipts.',
            'gate_result_unchanged':True,'quality_certified':False},
        'a0_timing':{'total_seconds':320.6685692829924,'transport_seconds':67.31851485402149,
            'navigation_view_event_intervals_seconds':[24.466,26.868,24.611,24.509,24.692,23.895,37.467,24.825],
            'interval_sum_seconds':211.333,'unattributed_remainder_seconds':42.0170544289709,
            'limitation':'Intervals cover whole view construction. Fine-grained query timers are no-op; no attribution to one hash/query/validator is proven.'},
        'a0_selection':{'read_target_available':'T915d5f1ccb33e30c86ff51f2553b (제20조②)',
            'observation':'FOLLOW_CONNECTION selected other 제24조 ranges while its reason requested 제20조②; six directory openings did not read more originals.',
            'terminal':'NO_PROGRESS count5/recovery3; 9/40 calls before ASSESS/COMPOSE, not exhaustion of40-call budget'},
        'interpretation':'Required action-field omission was not observed in these19 navigation responses. This is one known question across3 arms, not evidence of general compatibility or legal correctness.',
        'input_artifacts':inputs,'design_freeze_sha256':sha(ART/'design-freeze.json'),
        'model_calls_by_diagnosis':0,'database_loads_by_diagnosis':0,'candidate_changed':False,
        'main_changed':False,'genos_changed':False,'regrade_performed':False}
    write(ART/'POST_RUN_DIAGNOSIS.json',value)
    (ART/'POST_RUN_DIAGNOSIS.md').write_text(f'''# ADR1066 실모델 중단 진단

**수정은 일부 효과가 있었지만 정상 동작 완료는 아니다.** 계획9셀 중 첫 질문의 A0/A1은 제한 답변, A2는 시스템 오류로 중단했다. 나머지6셀은 미실행이다. 제품{total_calls}호출, 관찰 비용 ${cost:.8f}, 제품 실행 합계 {seconds:.2f}초. 평가기준상 완료된3조건 묶음이 없어 채점 모델은0회다.

## 확인된 개선

관찰한 행동 선택 {navigation_calls}회에서는 이전의 행동 이름만 반환하는 필수 항목 누락이 재현되지 않았다. 원문 읽기·판단·관련 목록 탐색과 A0/A1의 ASSESS/COMPOSE 발행이 연결됐다. A1/A2에서 승인 묶음 확보와 실제 모델 전달도 관찰했다. 최대 요청 {maximum_chars:,}자까지 앱 입력 한도로 차단되지 않았다. 각 셀의 원문 대조 불일치는0건이다. 정답률이나 전체 질문의 성공률로 확대하지 않는다.

## A2 중단의 직접 원인

같은 승인 묶음 페이지를 다시 전달했을 때 source 카드12개의 원문·span·소유자·순서는 같았다. 단1개 카드의 `presentation_id`만 새 화면 ID로 바뀌었다. 페이지 ID는 같았지만 전체 카드의 `sources_sha256`이 달라졌고 `ontology_review.reconcile`이 이를 ‘ontology delivery receipt changed’로 거부했다. 최상위 표시 ID는 비교에서 제외하면서 원문 카드 내부 표시 ID가 들어간 전체 hash는 계속 비교하는 동일성 계약의 결함이다. 원문 변조·모델 필수 필드 누락과 구분한다. 요청005/006의 정확 경로·해시·차이는 [기계 진단](POST_RUN_DIAGNOSIS.json)에 있다.

합성80검사는 단일 승인 범위의 전달과 문서ID 보존 등을 확인했지만, 여러 원문과 이전 화면의 범위를 함께 재표시하며 페이지가 반복되는 이 전이는 포함하지 못했다. 검사 통과가 실모델의 전체 실행 성공을 보장하지 않았다.

## 별도의 선택·속도 문제

A0에서 제20조② READ 카드가 실제로 있었지만 모델은 그 조문을 확인하겠다는 이유와 다른 제24조 하위 범위의 연결 목록을 선택했다. 연결 목록 조회6회 동안 새 원문을 읽지 못했고 NO_PROGRESS5·복구 선택3회로 제한 답변이 됐다. 전체40호출 한도는 남아 있었다.

A0 전체320.67초 중 실제 모델 응답은67.32초, 다음 선택 화면 구성8구간은 약211.33초다. 전체 메뉴를 만든 뒤 현재 작업으로 축소하는 경로이며, 세부 타이머가 비활성이라 특정 조회·hash·검사 하나의 비용으로 단정하지 않는다. 출력 오류에 따른 반복 보완이 지연 원인이라는 증거는 없다.

## 감사기의 별도 호환 문제

최종 gate도 `WIRE_DOCUMENT_ID_MISSING`으로 미확인 종료했다. 일부 exact_evidence 카드는 원장 evidence ID로 문서에 결속되는데, 구형 helper가 카드의 직접 document_id만 요구했다. 별도의 native 원문 감사가 검증한 결과와 이 감사기 실패를 구분한다. 원 gate 결과를 고치거나 다시 채점하지 않았다.

## 상태와 후속 방향

실행은 STOPPED_PARTIAL이며 원래9셀 범위를 축소하거나 미실행을 성공·실패 점수로 채우지 않는다. 후속 수정은 원문 내용/판본/권한의 불변 결속과 표시 메타데이터의 동일성 분리, 실제 대상과 이유의 연결, 전체 화면 구성 비용을 다뤄야 한다. 원문 검증 자체를 끄는 해결책은 아니다. 현재 후보·실행·과거1065·MAIN103은 변경하지 않았다. 법률 정확도·온톨로지 효과·GENOS 현장 성능은 미확인이다.

[라이브 원집계](LIVE_RESULT.md) · [질문별 원문 기록](../실험/README.md) · [동결 계획](live-implementation-plan.json)
''')
    print(json.dumps({k:value[k] for k in ('status','product_calls','observed_cost_usd','product_seconds','navigation_calls','maximum_request_chars')}))

if __name__=='__main__':main()
