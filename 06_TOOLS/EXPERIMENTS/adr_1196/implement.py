from common import *
S=ROOT/read(DES/'candidate.json')['snapshot']
def edit(name,old,new):
 p=S/name;t=p.read_text();assert t.count(old)==1,(name,old);p.write_text(t.replace(old,new))
N='02_BACKEND/semantic_runtime/legal_agent/'
edit(N+'narrative_answer.py','from jsonschema import validate','from jsonschema import validate\nfrom ..contracts import digest')
edit(N+'narrative_answer.py',"VERSION = 'grounded-narrative-v1'", "VERSION = 'grounded-narrative-v1'\nPRESERVED_VERSION = 'accepted-content-v1'")
edit(N+'narrative_answer.py',"return profile.get('answer_presentation', 'structured') == VERSION", "return profile.get('answer_presentation', 'structured') in (VERSION, PRESERVED_VERSION)")
p=S/(N+'narrative_answer.py');p.write_text(p.read_text()+'''

def preserved(profile):
    return profile.get('answer_presentation') == PRESERVED_VERSION


def preserved_plan(assessment, requested_format=None, issues=None):
    """Choose layout only. Accepted text is the sole author of legal content."""
    from . import completion_contracts as cc
    value = cc.default_plan(assessment, requested_format, issues)
    if requested_format == 'bullets':
        value['layout'] = 'bullets'
    value.update(presentation=PRESERVED_VERSION,
                 accepted_assessment_hash=digest(assessment))
    verify_preserved_plan(assessment, value)
    return value


def verify_preserved_plan(assessment, value):
    from .completion_v5 import verify_content
    allowed = {'layout', 'claim_order', 'issue_sections', 'presentation',
               'accepted_assessment_hash', 'gap_reason_presentation'}
    if (value.get('presentation') != PRESERVED_VERSION or set(value) - allowed
            or value.get('accepted_assessment_hash') != digest(assessment)):
        raise ContractError('preserved answer plan differs from accepted assessment')
    for claim in assessment['claims']:
        # Recompile subject, scope, nested conditions, norms and exceptions; do
        # not trust a redundant text field that no longer matches its content.
        verify_content(claim)
''')
edit(N+'completion_contracts.py',"def render(assessment, plan):\n    claims", "def render(assessment, plan):\n    from .narrative_answer import PRESERVED_VERSION, verify_preserved_plan\n    if plan.get('presentation') == PRESERVED_VERSION:\n        verify_preserved_plan(assessment, plan)\n    claims")
edit(N+'completion_execution.py',"            # The source-backed judgment remains immutable; presentation is separate.\n            if rich:","""            preserve = (narrative.preserved(profile) and task is None
                and not assessment.get('source_excerpt_reply')
                and not assessment.get('assessment_basis', {}).get('scenario_choice'))
            rich = rich and not preserve
            # Accepted content is compiled once; layout must not rewrite it.
            if preserve:
                plan = narrative.preserved_plan(assessment, format, selection.get('issues'))
            elif rich:""")
edit(N+'completion_execution.py',"'presentation': narrative.VERSION if rich else 'structured'", "'presentation': plan.get('presentation', 'structured')")
edit(N+'workflow_tiers_policy.py',"('structured','grounded-narrative-v1')", "('structured','grounded-narrative-v1','accepted-content-v1')")
edit(N+'unified_runtime.py',"'streaming':'text-deltas-during-generation', 'semantic_quality_certified':False", "'streaming':('verified-complete-answer' if composition['composition_plan']['presentation'] == 'accepted-content-v1' else 'text-deltas-during-generation'), 'semantic_quality_certified':False")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p);v['answer_presentation']='accepted-content-v1';p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Six product/configuration files edited in isolated candidate only')
