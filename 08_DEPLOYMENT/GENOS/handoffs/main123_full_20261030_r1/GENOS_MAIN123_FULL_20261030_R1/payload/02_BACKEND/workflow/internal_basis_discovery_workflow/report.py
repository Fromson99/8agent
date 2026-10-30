from ..contracts import digest


def view(ctx,state):
    return {'input':ctx.request['input'],'as_of':ctx.request['as_of'],'stage':state['stage']}


def build(ctx,state,status=None,code=None):
    from ..risk_team_compare_workflow.report import cell
    inventory=state.get('inventory',[]);units=state.get('units',{})
    coverage={'total':len(inventory),'read':sum(bool(u['internal']) for u in units.values()),
              'reviewed':sum(u['status']=='reviewed' for u in units.values()),
              'with_candidates':sum(bool(u.get('proposals')) for u in units.values())}
    coverage['unprocessed']=coverage['total']-coverage['reviewed']
    coverage['skipped']=sum(u['status']=='skipped' for u in units.values())
    coverage['pending']=coverage['unprocessed']-coverage['skipped']
    coverage['research_incomplete']=sum(u.get('research_status') in ('failed','partial') for u in units.values())
    coverage['not_found']=sum(u['status']=='reviewed' and not u.get('proposals') for u in units.values())
    lines=['내규 전체 근거 조사','',f"전체 {coverage['total']}개 범위 중 {coverage['reviewed']}개 검토, {coverage['skipped']}개 오류 건너뜀, {coverage['pending']}개 미처리.",
           '검토 완료는 모든 외규 발견이나 관계 승인을 뜻하지 않습니다.','','| 내규 범위 | 처리 상태 | 후보 관계 | 미확보·의견 |','|---|---|---|---|']
    for item in inventory:
        unit=units.get(item['inventory_id'],{})
        lines.append('| '+' | '.join(cell(v) for v in [item['title'],unit.get('status','pending'),', '.join(unit.get('proposals',[])), '; '.join(unit.get('notes',[]))])+' |')
    result={'response_schema':'workflow-result-v1','workflow_id':ctx.request['workflow_id'],'workflow_version':ctx.request['workflow_version'],
            'run_id':ctx.context.run_id,'request_id':ctx.request['request_id'],'status':status or 'partial',
            'answer':{'text':'\n'.join(lines),'claims':[],'unresolved':[{'reason':g} for g in state.get('gaps',[])],
                      'answer_status':'COMPLETE' if coverage['unprocessed']==0 and not coverage['research_incomplete'] else 'PARTIAL'},
            'coverage':coverage,'basis_link_ids':state.get('basis_proposals',[]),'units':units,'inventory':inventory,
            'research_failures':[{'scope_id':key,**u['failure']} for key,u in units.items() if u.get('failure')],
            'resume_available':False,'continuation_available':coverage['unprocessed']>0,'return_to':ctx.request['return_to'],
            'usage':ctx.repo.work.budget(),'previous_usage':state.get('cumulative_usage'),
            'binding':ctx.context.binding,'quality_certified':False}
    if code:result['error_code']=code
    return result
