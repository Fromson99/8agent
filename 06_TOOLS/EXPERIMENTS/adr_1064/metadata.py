"""Prepare/finalize only ADR1064 metadata; original experiments stay immutable."""
import sys
from common import ROOT,ADR,ART,SOURCE,TOOLS,read,save,sha,rel

SECTIONS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성',
    '결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']


def document(result=None):
    front=(ADR/'README.md').read_text(encoding='utf-8').split('---',2)[1]
    outcome=('코드와 합성 검사를 준비했다. 실제 입력 동결과 보정 집계는 아직 실행하지 않았다.' if result is None else
        f"첫 9셀의 기계적 전달 감사를 완료했다. 모든 호출 확인 여부: {result['all_calls_verified']}. 미확인은 개별 기록에 보존한다.")
    bodies=[
        outcome+' 제품·모델·법률 의미 점수·ADR1063 공식 게이트는 변경하지 않는다.',
        '부모 text_ref를 공유하는 exact_evidence의 하위 span과 ASSESS의 id/text 전용 evidence_options를 기존 감사기가 추적하지 못했다. 기존 결과와 오류는 그대로 보존한다.',
        '[사전 규칙](artifacts/implementation-plan.json). 실제 사전·원래 view·근거 ID·좌표·텍스트 hash·권한·버전을 모두 결속한다. 변조는 거부하고 확인할 수 없는 범위는 UNKNOWN이다.',
        'ADR1060/wire-audit의 감사 방식이 부모다. ADR1063은 informed_by 입력 원본이다. baseline은 원집계, delivery-audit는 별도 기계적 참조 집계다. 전체 첫 9셀을 선택하며 추가 모델·제품 실행·법률 재채점은 없다.',
        '[동결](artifacts/design-freeze.json)은 도구·규칙과 9셀의 개별 원시 기록 해시를 고정한다. 제품의 실제 전송 사전을 원래 frozen codec으로 복원한다. 원문 DB·색인을 열지 않고 원래 원문 검증 receipt 및 native evidence에 결속한다.',
        outcome+' [별도 결과](artifacts/result.json). 원집계는 각 셀 보고서 baseline에 원래 값으로 표시한다.',
        '부모의 원문 slice와 자식의 순서·범위가 정확히 일치하는 경우만 중복 결측을 제거한다. ASSESS 옵션은 현재 요청의 원래 ID와 확보 근거로만 연결한다. 미전달 원문을 채우거나 품질 실패를 지우지 않는다.',
        '추가 모델 호출·토큰·비용은 0이다. 원문 확보·검색·선택·gold recall·정답률을 새로 측정하지 않는다. 발생 횟수와 source별 범위 union은 서로 구분한다.',
        '기계적 참조 추적 오류와 실제 원문 미전달은 별개다. 원문 전달 확인은 법률 적용의 타당성·답변의 정답 여부를 인증하지 않는다.',
        '첫 9셀의 저장된 기록만 대상으로 한다. 원문 DB를 재조회한 독립 법령 원본 재검증이 아니다. 기존 source_integrity 검사 기록과 native evidence의 정확한 결속 범위만 확인한다.',
        'MAIN103·GENOS·ADR1063 제품과 원집계·공식 게이트를 유지한다. 첫 9셀 게이트 재승인이나 나머지 102셀 실행 허가가 아니다. 잘못된 보정이면 이 새 감사 결과만 사용하지 않고 원결과를 보존한다.',
        '`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1064/test_delivery_spans.py` → root의 실행 종료 확인 후 `freeze.py` → `run.py` → `metadata.py --finish`. 완료 산출물은 덮어쓰지 않는다. 최종 표준 검사는 root가 수행한다.'
    ]
    (ADR/'README.md').write_text('---'+front+'---\n# 실제 원문 전달 참조 감사\n\n'+
        '\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(zip(SECTIONS,bodies),1))+'\n',encoding='utf-8')
    (ADR/'실험/README.md').write_text('# ADR1064 기계적 전달 감사\n\n질문 단위 법률 평가가 아닌 저장된 참조 표현의 구조 감사다. questions=[]이며 첫 9셀 전체는 동결·결과의 cell 목록으로 연결한다.\n\n[규칙](../artifacts/implementation-plan.json) · [동결](../artifacts/design-freeze.json) · [결과](../artifacts/result.json)\n',encoding='utf-8')


def prepare():
    assert not (ART/'design-freeze.json').exists()
    plan={'schema_version':'delivery-reference-audit-plan-v1','model_calls':0,'source_database_access':False,
        'source_selection':'Exactly all first nine closed ADR1063 cells, in frozen execution order; no outcome sampling.',
        'hypothesis':'Parent source-text references and exact ASSESS option IDs can account for delivered native spans without guessing coordinates or changing original results.',
        'primary_metric':'Verified reference occurrences and source/version/block interval union; original missing counts remain separately reported.',
        'success':'Every accepted occurrence binds actual request, frozen codec, native view, prior verified acquired evidence, original coordinates, text/hash/version and ACL. Unknown is explicit; all synthetic tamper cases reject.',
        'failure':'Hash/version/ACL/ID/offset/parent body/order mismatch is REJECTED. Missing proof is UNKNOWN. No model correction, silent fallback or source inference.',
        'parent_reference_rule':'Resolve exact text_ref owner/id/start/end. Parent body must equal native parent text and the exact newline-joined native child sequence. Check every child extent and acquired evidence; never search for a substring.',
        'assessment_rule':'Restore actual request-local aliases. Bind each option id to same native-view option, exact text, native source/document/evidence ID and acquired enclosing span. Every source evidence_refs entry must resolve and retain its owner.',
        'overlap_rule':'Verify every occurrence and all overlapping text before per-source/version/block interval union; duplicate occurrences remain in the audit.',
        'preservation':'ADR1063 product code, source files, requests, responses, usage, original metrics and official gate stay unchanged. No first9 reapproval, no remaining102 execution and no semantic regrade.',
        'failure_owner':'This isolated audit reports VERIFIED/UNKNOWN/REJECTED; no retries or state repair.',
        'standards_read':['04_EXPERIMENTS/LEGACY_ADR/EXPERIMENT_AGENT_PROMPT.md','04_EXPERIMENTS/LEGACY_ADR/STANDARD.md','07_DOCS/REFERENCE/OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md']}
    save(ART/'implementation-plan.json',plan)
    m=read(ADR/'실험/manifest.json')
    m['lineage']['hypothesis_delta']=plan['hypothesis']
    m['design'].update(hypothesis=plan['hypothesis'],primary_metric=plan['primary_metric'],
        success_criteria=plan['success'],failure_criteria=plan['failure'],criteria_frozen_before_run=True,operational_audit=True)
    m['design']['criteria_record']={'path':rel(ART/'implementation-plan.json'),'sha256':sha(ART/'implementation-plan.json')}
    m['design']['code_isolation']['reason']='Isolated read-only reference accounting tools only. Frozen product codecs are imported by hash; no product behavior or runtime registry changes.'
    m['design']['arms'][0].update(changes='Immutable ADR1063 first-nine original metrics; no baseline rerun',controls=plan['preservation'])
    m['design']['arms'][1].update(changes='Strict parent text_ref and ASSESS native-option accounting only',controls=plan['preservation'])
    m['runs'][0].update(purpose='regrade',arm_ids=['delivery-audit'],selection_rule=plan['source_selection'],artifact_path=rel(ART/'result.json'))
    m['llm_policy']['llm_calls']=[]
    m['dataset'].update(name='Nine frozen ADR1063 source-delivery records',version='native-reference-audit-v1',
        frozen_source=rel(SOURCE/'design-freeze.json'),sha256=sha(SOURCE/'design-freeze.json'),
        legal_version_checked=False,reference_version_checked=False)
    reason='Structural reference-integrity audit only; no retrieval policy, canonical article-stage metrics, gold recall, source acquisition or legal scoring is changed or newly measured.'
    m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason)
    m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason=reason)
    save(ADR/'실험/manifest.json',m,exclusive=False);document()


def finish():
    from run import verify_freeze
    frozen=read(ART/'design-freeze.json');verify_freeze(frozen);result=read(ART/'result.json')
    assert result['design_freeze_sha256']==sha(ART/'design-freeze.json') and result['status']=='complete'
    m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
    m['results']={'status':'complete','by_arm':{
        'baseline':{'status':'complete','total':0,'correct':None,'accuracy':None,'original_cells':9},
        'delivery-audit':{'status':'complete','total':0,'correct':None,'accuracy':None,'audited_cells':len(result['cells'])}},
        'comparisons':[],'judge_disagreements':None,'usage':{'model_calls':0},'latency':{},'error_taxonomy':[]}
    save(ADR/'실험/manifest.json',m,exclusive=False);document(result)
    save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1064',
        'created_at':m['reservation']['created_at'],'files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size,
            'description':'Isolated reference audit artifact or tool; no product record overwritten',
            'contains_raw_prompts_and_outputs':False} for p in sorted([*ART.rglob('*'),*TOOLS.glob('*.py')])
            if p.is_file() and p!=ART/'manifest.json']},exclusive=False)
    print('Audit metadata ready; root must run status/hash/final validation/graph before completion claim.')


if __name__=='__main__':
    if '--finish' in sys.argv:finish()
    else:prepare()
