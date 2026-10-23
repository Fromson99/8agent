"""Re-entry inside the existing Pipeline, preserving query and request-local work."""
from .errors import ContractError


def system_request(question):
    """Compatibility hook: natural language never authorizes a model bypass."""
    return False


def run_case(pipeline,body,principal,options,lease):
    from .unified_runtime import run as unified_run
    return unified_run(pipeline,body,principal,options,lease)


def run(pipeline, session, runner):
    profile = pipeline.contracts.pipeline['profiles'][pipeline.profile_id]
    steps = {step['id']: step for step in profile['nodes']}
    if set(steps) != {'retrieve', 'select', 'assemble', 'answer'}:
        raise ContractError('legal-agent stage graph mismatch')
    values = {'$input.request': session.context.request}
    research = True
    while True:
        if research:
            for stage in ('retrieve', 'select', 'assemble'):
                runner.execute(steps[stage], values, legal_session=session)
        else:
            session.work.assert_assembly_current()
        runner.execute(steps['answer'], values, legal_session=session)
        control = values['answer.control']
        if control['decision'] == 'FINAL':
            return values[profile['outputs']['result']]
        if session.cycles >= session.profile['max_cycles']:
            raise ContractError('coordinator attempted to exceed cycle limit')
        research = control['decision'] == 'RESEARCH'
