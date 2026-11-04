"""Explicit checkpointed transitions; business logic belongs only to this package."""
from . import query_scope, retrieval, basis, recovery, compare, report


def execute(ctx):
    if ctx.definition.manifest.get('research_contract')=='comparison-research-v1':
        from .task_board import execute
        return execute(ctx)
    state=ctx.repo.state()['checkpoint']
    while True:
        ctx.context.remaining()
        stage=state['stage']
        if stage=='INTAKE':
            state['scope']=query_scope.prepare(ctx)
            state['stage']='FIND_INTERNAL'
        elif stage=='FIND_INTERNAL':
            retrieval.discover(ctx,state,'internal')
            state['stage']='FIND_EXTERNAL'
        elif stage=='FIND_EXTERNAL':
            retrieval.discover(ctx,state,'external')
            state['stage']='VERIFY_BASIS'
        elif stage=='VERIFY_BASIS':
            retrieval.restore_context(ctx,state)
            value=basis.assess(ctx,state)
            if state.get('retained_pairs'):
                retained={p['issue_id'] for p in state['retained_pairs']}
                value['pairs']=state['retained_pairs']+[p for p in value['pairs'] if p['issue_id'] not in retained]
            state['basis']=value
            state['stage']='REPAIR_SCOPE'
        elif stage=='REPAIR_SCOPE':
            if ctx.request['use_llm'] and recovery.recover(ctx,state):
                state['stage']='VERIFY_BASIS'
            else:state['stage']='COMPARE'
        elif stage=='COMPARE':
            state['comparison']=compare.compare(ctx,state)
            state['stage']='REPORT'
        elif stage=='REPORT':
            result=report.build(ctx,state)
            ctx.rag.port.verify_all()
            state['stage']='END'
            return ctx.repo.save(state,status=result['status'],result=result)
        elif stage=='END':
            return ctx.repo.state()['result']
        else:raise ValueError('unknown workflow stage')
        ctx.repo.save(state)
