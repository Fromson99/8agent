"""Render validated observations, never regenerate a legal answer at publication."""
from ..contracts import digest
from copy import deepcopy
import html
import re

RELATIONS={'DIRECT':'직접 명시','INDIRECT':'상위 내규·위임 경유','CONTENT_ONLY':'내용 대응만',
           'UNKNOWN':'미확인','UNRELATED':'무관'}
VERDICTS={'CONFORMS':'부합','ADDITIONAL_INTERNAL':'내부 추가기준','CONFLICT':'상충',
          'POSSIBLE_GAP':'미비 후보','DEFERRED':'판정 보류'}
GAP_STATES={'PARTIAL_PROVISION':'필요한 원문 전체 범위의 확인 미완료',
    'MISSING_REFERENCE':'참조 원문 확인 미완료','EXTERNAL_SCOPE':'외규 조사 범위 확인 미완료',
    'INTERNAL_SCOPE':'내규 조사 범위 확인 미완료','QUERY_SCOPE':'질문 조사 범위 확인 미완료',
    'NOT_REGISTERED':'조사 대상 등록 확인 미완료','TOOL_FAILURE':'원문 조사 도구 실행 미완료',
    'MISSING_NUMERIC':'수치·산식 근거 확인 미완료','UNKNOWN_VERSION':'선택 판본의 기준일 유효성 확인 미완료'}


def gap_observation(gap,issues,sources):
    """State and bound source locations are displayable without legal inference."""
    issue=next(i for i in issues if i['id']==gap['issue_id'])
    action=gap.get('action') or {}
    locations=[]
    for ident in action.get('context_evidence',[]):
        if ident in sources:
            metadata=sources[ident]['metadata']
            location=metadata['document_name']+' '+metadata.get('heading','')
            if location not in locations:locations.append(location)
    return (issue['label']+' — '+GAP_STATES[gap['kind']]+
        ('. 관련 확인 원문: '+'; '.join(locations) if locations else ''))


def cell(value):
    return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n','<br>')


def literal(value):
    return re.sub(r'([\\`*_{}\[\]()!|])',r'\\\1',html.escape(str(value),quote=False))


def build(ctx,state,status=None,code=None):
    if state.get('task_board'):
        from .task_board import report
        return report(ctx,state,status,code)
    from ..presentation import evidence as current_evidence,active_ids
    active=active_ids(state)
    derived={i for i,origin in state.get('packet_evidence',{}).items() if origin in active}
    evidence=current_evidence(ctx,state,active|derived);sources={e['evidence_id']:e for e in evidence}
    basis=state.get('basis',{'pairs':[],'gaps':[],'summary':'근거 관계 미확인'})
    compared=state.get('comparison',{'rows':[],'unresolved':[]})
    pairs={p['pair_id']:p for p in basis['pairs']}
    basis_summary='; '.join(p['pair_id']+': '+RELATIONS[p['basis_relation']] for p in basis['pairs']) or '근거 관계 미확인'
    issues=state.get('scope',{}).get('issues',[])
    display_basis=deepcopy(basis)
    for gap in display_basis['gaps']:
        gap['reason']=gap_observation(gap,issues,sources)
        # The unaccepted proposed followup remains in the audit basis. It is
        # not a finding about whether an unsearched rule exists.
        gap['action']=None
    # Keep the model's explanation even when it defers. Exact source cards and
    # immutable proposals make that review inspectable without regenerating it.
    display_basis['summary']=basis_summary
    unresolved=list(dict.fromkeys(state.get('gaps',[])+[g['reason'] for g in display_basis['gaps']]+compared['unresolved']))
    unresolved.extend('사용자 사실 확인 필요: '+fact for fact in state.get('scope',{}).get('missing_user_facts',[]))
    covered={pairs[r['pair_id']]['issue_id'] for r in compared['rows'] if r['verdict']!='DEFERRED'}
    for issue in state.get('scope',{}).get('issues',[]):
        if issue['id'] not in covered:
            unresolved.append(issue['label']+' — 확인된 범위만으로 판정할 수 없습니다.')
    unresolved=list(dict.fromkeys(unresolved))
    status=status or ('completed' if compared['rows'] and not unresolved and
                      all(r['verdict']!='DEFERRED' for r in compared['rows']) else 'partial')
    confirmed=len(compared['rows'])
    lines=[('LLM이 검토한 '+str(confirmed)+'개 비교 항목의 결과입니다.' if confirmed else
            '확보한 자료만으로는 내규와 외규의 근거 관계 및 부합 여부를 확정할 수 없습니다.'),
           '', '질문: '+literal(ctx.request['question']),
           '기준일: '+str(ctx.request['as_of'] or '미지정 — 현재 유효성 미확인'), '',
           '근거 관계: '+basis_summary, '',
           '| 비교 항목 | 외규 문서·조문 | 내규 문서·조문 | 근거 관계 | 차이·판정 | 미확인 사항 |',
           '|---|---|---|---|---|---|']
    def location(ids):
        return '; '.join(sources[i]['metadata']['document_name']+' '+sources[i]['metadata'].get('heading','')+
                         ' ['+i+']' for i in ids)
    for row in compared['rows']:
        pair=pairs[row['pair_id']]
        used={c['evidence'] for c in row['citations']} | {c['evidence'] for d in row['dimensions'] for c in d['citations']}
        locations=lambda ids:location([i for i in ids if i in used]) or '결정 근거 미확인'
        lines.append('| '+' | '.join(map(cell,[next((i['label'] for i in issues if i['id']==pair['issue_id']),row['item']),locations(pair['external']),locations(pair['internal']),
            RELATIONS[pair['basis_relation']],VERDICTS[row['verdict']]+' — '+row['difference']+' '+row['reason'],
            '; '.join(row['unresolved'])]))+' |')
    if not compared['rows']:lines.append('| 판정 보류 | 미확인 | 미확인 | 미확인 | 양측 관계·적용 검토 미완료 | 아래 참조 |')
    lines.extend(['','추가 확인 사항'])
    lines.extend('- '+literal(u) for u in unresolved or ['기록된 추가 확인 사항 없음. 의미 판단의 정확도는 별도 검증 대상입니다.'])
    cited=set()
    for row in compared['rows']:
        pair=pairs[row['pair_id']]
        cited.update(c['evidence'] for c in row['citations'])
        cited.update(c['evidence'] for d in row['dimensions'] for c in d['citations'])
        cited.update(c['evidence'] for c in pair['applicability']['citations'])
        cited.update(edge[k] for edge in pair['basis_path'] for k in ('from_evidence','to_evidence'))
    evidence=[e for e in evidence if e['evidence_id'] in cited]
    cards=[]
    for e in evidence:
        cards.append({'selection_id':e['evidence_id'],'document_id':e['document_id'],
            'document_name':e['metadata']['document_name'],'coordinate_label':e['metadata'].get('heading',''),
            'generation_id':e['generation_id'],'source_artifact_hash':e['source_artifact_hash'],
            'spans':e['spans'],'excerpt':e['text'],'side':e['side'],'content_read':True,
            'interpretation_status':'UNVERIFIED','coverage':'READ_SPANS_ONLY'})
    bundle={'schema_version':'workflow-source-v1','sources':cards,'binding_hash':ctx.context.binding_hash}
    bundle['bundle_hash']=digest(bundle)
    # Inline exact excerpts are also available to consumers without source cards.
    if evidence:
        lines.extend(['','확인한 원문'])
        for e in evidence:
            lines.extend(['',literal(e['metadata']['document_name']+' '+e['metadata'].get('heading',''))+' ['+e['evidence_id']+']',
                          '> '+literal(e['text']).replace('\n','\n> ')])
    result={'response_schema':'workflow-result-v1','workflow_id':ctx.request['workflow_id'],
        'workflow_version':ctx.request['workflow_version'],'status':status,'run_id':ctx.context.run_id,
        'request_id':ctx.request['request_id'],'revision':ctx.repo.state()['revision'],
        'answer':{'text':'\n'.join(lines),'unresolved':[{'reason':u} for u in unresolved],
                  'claims':[],'answer_status':'COMPLETE' if status=='completed' else 'PARTIAL'},
        'rag_results':state.get('rag_results',{}),
        'evidence_summary':{'active_adopted':len({i for r in state.get('rag_results',{}).values() for i in r.get('evidence_ids',[])}),
            'current_context':len(sources),'reported':len(evidence),'exploration_in_child_journals':True},
        'report':{'basis':basis,'basis_status':'AUDIT_MODEL_PROPOSALS','judgment_authority':'LLM_REVIEW',
                  'display_basis':display_basis,'rows':compared['rows'],'scope':state.get('scope')},
        'assembly':{'term_agent':{'source_bundle':bundle}},
        'evidence_refs':[e['evidence_id'] for e in evidence],'unresolved':unresolved,
        'resume_available':False,'usage':ctx.repo.work.budget(),'return_to':ctx.request['return_to'],
        'binding':ctx.context.binding,'quality_certified':False}
    if code:result['error_code']=code
    return result
