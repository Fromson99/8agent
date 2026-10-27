from copy import deepcopy
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('adr1079_transition_audit',Path(__file__).with_name('transition_audit.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture():
    return {'events':[
        {'journal':'j','seq':10,'kind':'NAVIGATION_TASK_PROJECTED','payload':{
            'departure':{'judgment_refs':['J1','J2']},'retained_source_count':2,
            'context_hash':'h','task':'REVIEW'}},
        {'journal':'j','seq':12,'kind':'NAVIGATION_TASK_CHOICE_CONTRACT','payload':{
            'presentation_id':'p','canonical_validation_required':True,'semantic_defaults_created':False}}],
        'calls':[{'presentation_id':'p','successful_native_attempts':[{'journal':'j'}],
                  'task_navigation':{'context_hash':'h'},'request_path':'request.json','request_sha256':'r'}]}


def test_exact_next_screen_transmitted():
    assert module.check_transition(fixture())['status']=='OBSERVED'


def test_failed_prior_projection_alone_does_not_pass():
    value=fixture();value['calls']=[]
    assert module.check_transition(value)['status']=='NOT_OBSERVED'


def test_later_unrelated_screen_not_a_repair_witness():
    value=fixture();value['events'].insert(1,{'journal':'j','seq':11,'kind':'NAVIGATION_TASK_PROJECTED','payload':{}})
    assert module.check_transition(value)['status']=='NOT_OBSERVED'


def test_one_group_or_wrong_presentation_not_a_multi_original_witness():
    for change in ('group','presentation','journal','context'):
        value=fixture()
        if change=='group':value['events'][0]['payload']['retained_source_count']=1
        if change=='presentation':value['calls'][0]['presentation_id']='other'
        if change=='journal':value['calls'][0]['successful_native_attempts'][0]['journal']='other'
        if change=='context':value['calls'][0]['task_navigation']['context_hash']='other'
        assert module.check_transition(value)['status']=='NOT_OBSERVED'
