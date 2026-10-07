"""Re-entry inside the existing Pipeline, preserving query and request-local work."""
from .errors import ContractError


def system_request(question):
    import re
    from ..pipeline import route_question
    from .tools_policy import metadata_only_request
    text=route_question(question)[0]
    return metadata_only_request(text) or bool(re.fullmatch(
        r'\s*(안녕(?:하세요)?|반갑습니다|고마워(?:요)?|감사합니다|hello|hi|사용법|도움말)[.!?！？\s]*',text,re.IGNORECASE))


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
