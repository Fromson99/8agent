from pathlib import Path
import json
R=Path(__file__).resolve().parents[3]
S=R/'02_BACKEND/lawrag/research/candidates/adr_0924/bridged/snapshot'
def edit(name,old,new,count=1):
    p=S/name;s=p.read_text();assert s.count(old)==count,(name,s.count(old),old)
    p.write_text(s.replace(old,new))
L='02_BACKEND/semantic_runtime/legal_agent/'
edit(L+'source_investigation.py',"    view=inv.bounded_model_view(data)","""    from . import investigation_leads as leads
    catalogue=leads.capture(inv,data)
    shown=deepcopy(data)
    shown['investigation_leads']=leads.projection(catalogue)
    shown.pop('document_term_candidates',None)
    view=inv.bounded_model_view(shown)""")
edit(L+'source_investigation.py'," '후보는 원문 확보나 적용 확정이 아니다. 모든 후보를 읽어야 종료하는 것은 아니다. '",""" 'investigation_leads는 실제 읽지 않은 위치를 포함한다. 미리보기의 수치·조건을 확인한 원문으로 세지 않는다. '
 '질문의 남은 내용과 연결된 후보의 원문을 읽을지 선택한다. 반환 시 미열람 단서도 부모에게 전달된다. '
 '후보는 원문 확보나 적용 확정이 아니다. 모든 후보를 읽어야 종료하는 것은 아니다. '""")
edit(L+'source_handoff.py',"    evidence=inv.s.repo.evidence()","    from .investigation_leads import export\n    leads=export(inv)\n    evidence=inv.s.repo.evidence()")
edit(L+'source_handoff.py',"'source_return':{'schema_version':'source-investigation-v1',","'source_return':{'schema_version':'source-investigation-v2','leads':leads,")
edit(L+'source_handoff.py',"envelope={'response_schema':'workflow-investigation-return-v1'","envelope={'response_schema':('workflow-investigation-return-v2' if selected['source_return']['schema_version']=='source-investigation-v2' else 'workflow-investigation-return-v1')")
edit(L+'source_handoff.py',"    rows=child.db.execute(\"SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'\").fetchall()","    if envelope['handoff'].get('schema_version')=='source-investigation-v2':\n        from .investigation_leads import validate as validate_leads\n        validate_leads(envelope['handoff']['leads'])\n    rows=child.db.execute(\"SELECT payload_json,payload_hash FROM event WHERE kind='WORKFLOW_PARENT_TASK_BOUND'\").fetchall()")
edit(L+'source_handoff.py',"    return obj(status={'const':'sources_returned'}","    original=obj(status={'const':'sources_returned'}")
p=S/L/'source_handoff.py'
p.write_text(p.read_text()+"\n    current=deepcopy(original)\n    contract=current['properties']['source_return']\n    contract['properties']['schema_version']={'const':'source-investigation-v2'}\n    contract['properties']['leads']={'type':'object'}\n    contract['required'].append('leads')\n    return {'anyOf':[original,current]}\n")
edit('02_BACKEND/workflow/risk_team_compare_workflow/retrieval.py',"ctx.definition.manifest.get('source_return_contract')=='source-investigation-v1'","ctx.definition.manifest.get('source_return_contract') in ('source-investigation-v1','source-investigation-v2')")
edit('02_BACKEND/semantic_runtime/workflow_evidence.py',"bundle.update(schema_version='workflow-comparison-bundle-v2',export_mode='SOURCE_HANDOFF',","bundle.update(schema_version=('workflow-comparison-bundle-v3' if envelope['handoff'].get('schema_version')=='source-investigation-v2' else 'workflow-comparison-bundle-v2'),export_mode='SOURCE_HANDOFF',")
edit('02_BACKEND/semantic_runtime/workflow_evidence.py',"'source_investigation':{\n            'reason':", "'source_investigation':{\n            'leads':bundle.get('investigation_return',{}).get('leads'),\n            'reason':")
edit('02_BACKEND/semantic_runtime/comparison_research_bridge.py','def locators(port,evidence):','def locators(port,evidence,leads=None):')
edit('02_BACKEND/semantic_runtime/comparison_research_bridge.py','    return out\n\n\ndef compile_task',"""    from .legal_agent.investigation_leads import lead_locator
    for lead in (leads or {}).get('items',[]):
        value=lead_locator(port,lead)
        out['L'+digest(value)[:24]]=value
    return out


def investigation_leads(port,state):
    from .legal_agent.investigation_leads import parent_catalogue
    from workflow.presentation import valid_results
    return parent_catalogue(port,list(reversed(valid_results(state))))


def compile_task""")
edit('02_BACKEND/semantic_runtime/comparison_research_bridge.py',"        if locator not in locators(port,known).values():raise ContractError('research target is not a current verified locator')", """        if locator.get('lead_ref'):
            from .legal_agent.investigation_leads import validate_locator
            validate_locator(port,locator)
        elif locator not in locators(port,known).values():raise ContractError('research target is not a current verified locator')""")
W='02_BACKEND/workflow/risk_team_compare_workflow/task_board.py'
edit(W,"        values=sources_for_issue(ctx,state,issue['id']);ids=[e['evidence_id'] for e in values]", """        values=sources_for_issue(ctx,state,issue['id']);ids=[e['evidence_id'] for e in values]
        lead_catalogue=native.investigation_leads(ctx.rag.port,state)
        # Bound extra locations independently of originals; preserve omission.
        all_leads=lead_catalogue['items']
        visible_leads=[];lead_chars=0
        import json
        for lead in all_leads:
            size=len(json.dumps(lead,ensure_ascii=False))
            if len(visible_leads)>=16 or lead_chars+size>6000:continue
            visible_leads.append(lead);lead_chars+=size
        lead_view={**lead_catalogue,'items':visible_leads,
                   'omitted_count':lead_catalogue['omitted_count']+len(all_leads)-len(visible_leads)}""")
edit(W,'            locators=native.locators(ctx.rag.port,visible)','            locators=native.locators(ctx.rag.port,visible,lead_view)')
edit(W,"            data.update(issue=issue,fields=", "            data.update(investigation_leads=lead_view,issue=issue,fields=")
edit(W,"input_key=digest([issue['id'],data['sources'],data['attempt_status']])","input_key=digest([issue['id'],data['sources'],data['attempt_status'],lead_view])")
edit(W,"                '정말 필요한 추가 원문만 next_tasks에 넣는다.","""                'investigation_leads는 자식이 발견한 조사 위치다. 미리보기는 인용 근거가 아니다. 필요한 후보는 locator_id로 read_node를 선택한다. '
                '연결된 B를 읽고 새 원문이 들어오면 기존 A의 판단도 함께 재검토한다. 미열람·불확실성은 설명하되 이미 확보한 원문은 활용한다. '
                '정말 필요한 추가 원문만 next_tasks에 넣는다.""")
edit(L+'law_navigation.py',"cards.append({'reference_id':c['reference_id'],'anchor_excerpt':c['witness'],","cards.append({'reference_id':c['reference_id'],'anchor':deepcopy(g['anchor']),'anchor_excerpt':c['witness'],")
edit(L+'law_navigation.py',"""            value['references'] = {**{k: v for k, v in value['references'].items() if k != 'dependency_cards'},
                                   'dependency_cards_omitted': True}
            steps.append('reference_dependency_cards_omitted')""","""            value['references']['dependency_cards'] = [
                {k:deepcopy(c[k]) for k in ('reference_id','anchor','target','direction','already_read','read_action') if k in c}
                for c in value['references']['dependency_cards']]
            steps.append('reference_dependency_cards_minimized')""")
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json';v=json.loads(p.read_text());v.update(version='1.11.0',source_return_contract='source-investigation-v2');p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Wired v2 source return, verified parent locators, existing ITEMS/research and preserved minimum reference cards.')
