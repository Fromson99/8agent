"""Small relevance decision, independent of optional v3 legal assessments."""
from copy import deepcopy
from jsonschema import Draft202012Validator, ValidationError
from . import relations_protocol as v3
from .protocol import obj, arr, enum, S, ID
from .errors import ProposalError
ITEM = obj({'evidence_id':ID,'tier':enum('CORE','SUPPLEMENTAL'),
    'basis_span_ids':arr(ID,1,24),'relevance_reason':{'type':'string','minLength':1,'maxLength':400},
    'relation_refs':arr(ID,0,24),'interpretation_status':enum('UNASSESSED','UNCERTAIN','REVIEWED')})
DECISION = obj({'goal_id':ID,'question_revision':{'type':'integer','minimum':1},'view_id':ID,
    'selections':arr(ITEM,0,20), 'pending':arr(obj({'evidence_id':ID,'reason':S}),0,40),
    'rejected':arr(obj({'evidence_id':ID,'reason':S}),0,40)})
DEFINITIONS = deepcopy(v3.DEFINITIONS)
DEFINITIONS['SourceSelectionDecision']=DECISION
DEFINITIONS['TurnDecision']=obj({'actions':arr(v3.TOOL,0,8),'source_selection':{'anyOf':[DECISION,{'type':'null'}]},
    'assessments':arr(v3.ASSESSMENT),'relation_assessments':arr(v3.RELATION_ASSESSMENT),
    'intent':enum('CONTINUE','DRAFT','CLARIFY'),'reason':S})
SCHEMA={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:8-agent:source-tiers-v4','$defs':DEFINITIONS}
def schema(name): return deepcopy(DEFINITIONS[name])
def validate(name,value):
    try: Draft202012Validator(DEFINITIONS[name]).validate(value)
    except ValidationError as exc: raise ProposalError(f'{name} at /{"/".join(map(str,exc.absolute_path))}: {exc.message}') from exc
    def check(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in ('reason','relevance_reason') and not x.strip(): raise ProposalError('blank '+k)
                check(x)
        elif isinstance(v,list):
            for x in v: check(x)
    check(value)
    return value

# Public projection is closed independently from the extensible term_agent envelope.
N={'type':'integer','minimum':0}
H={'type':'string','pattern':'^[a-f0-9]{64}$'}
SPAN_CARD=obj({'span_id':ID,'evidence_id':ID,'block_id':ID,'start_cp':N,'end_cp':N,
    'block_hash':H,'text':S,'span_hash':H})
CARD=obj({'coordinate_label':S,'open_url':S,'selection_id':ID,'selection_version':N,
    'goal_id':ID,'question_revision':N,'view_id':ID,'evidence_id':ID,'tier':enum('CORE','SUPPLEMENTAL'),
    'relevance_reason':S,'relation_refs':arr(ID),'interpretation_status':enum('UNASSESSED','UNCERTAIN','REVIEWED'),
    'document_id':ID,'document_name':S,'coordinate':{'type':'object'},'generation_id':ID,
    'source_store_sha256':H,'source_artifact_hash':H,'source_id':ID,'spans':arr(SPAN_CARD,1,24),
    'excerpt':S,'coverage':enum('PARTIAL','COMPLETE'),'remaining_range':S,
    'open_target':obj({'generation_id':ID,'document_id':ID,'unit_id':{'type':['string','null']},'source_artifact_hash':H})})
DEFINITIONS['FinalSourceBundle']=obj({'schema_version':enum('source-tiers-v4'),'goal_id':ID,'question_revision':N,
    'selection_revision':H,'binding_hash':H,'status':enum('SOURCE_SELECTED','NO_SELECTION'),
    'sources':arr(CARD,0,20),'excluded':arr(obj({'selection_id':ID,'version':N,'reason':S})),
    'candidates_url':S,'candidate_counts':obj({'pending':N,'rejected':N,'unselected':N}),'bundle_hash':H})

# Candidate wire contract: relevance decisions refer to the card that carries the text.
LEGACY_DECISION = deepcopy(DECISION)
CHOICE = obj({'source':ID, 'decision':enum('KEEP_CORE','KEEP_SUPPLEMENTAL','DEFER','REJECT'),
              'reason':{'type':'string','minLength':1,'maxLength':400}})
DECISION = obj({'choices':arr(CHOICE,0,20)})
DEFINITIONS['SourceSelectionDecision']=DECISION
DEFINITIONS['TurnDecision']['properties']['source_selection']={'anyOf':[DECISION,{'type':'null'}]}
# Whole delivered sources are retained; the card display cap is not a selection cap.
DEFINITIONS['FinalSourceBundle']['properties']['sources']['items']['properties']['spans'].pop('maxItems',None)
# ADR0517 selects at most24 originals; paged originals can have more evidence
# cards. Output serialization must not silently drop selected pages.
DEFINITIONS['FinalSourceBundle']['properties']['sources'].pop('maxItems',None)
def validate_wire(name,value):
    if name not in ('TurnDecision','SourceSelectionDecision'):
        return validate(name,value)
    envelope=deepcopy(DEFINITIONS[name])
    if name=='TurnDecision':
        for key in ('actions','assessments','relation_assessments'):
            envelope['properties'][key]['items']={}
        envelope['properties']['source_selection']={'type':['object','null']}
    else: envelope['properties']['choices']['items']={}
    try: Draft202012Validator(envelope).validate(value)
    except ValidationError as exc: raise ProposalError(f'{name} envelope: {exc.message}') from exc
    return value
