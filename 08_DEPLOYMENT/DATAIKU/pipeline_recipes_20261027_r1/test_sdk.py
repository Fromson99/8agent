"""Real public Dataiku SDK against a local in-memory REST adapter, not a DSS server."""
import copy
import json
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0,os.environ.get('A8_DATAIKU_SDK_SOURCE','/tmp/a8-recipe-sdk/dataiku_api_client-15.2.0'))
from dataikuapi.dss.project import DSSProject
import install_flow


class Backend:
    def get_project(self,key): return DSSProject(self,key)
    def __init__(self):
        self.items={'managedfolders':{'ehA8dpVm':{'id':'ehA8dpVm','name':'LEGAL_PIPELINE_WORKSPACE','type':'S3',
            'params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture-bucket','path':'/${projectKey}/${odbId}'}}},
            'datasets':{},'recipes':{}}
        self.calls=[]
    def _perform_json(self,method,path,body=None,**kwargs):
        self.calls.append((method,path,copy.deepcopy(body)))
        parts=path.strip('/').split('/');assert parts[:2]==['projects','LEGAL_RAG']
        kind=parts[2];values=self.items[kind]
        if len(parts)==3:
            if method=='GET':
                return copy.deepcopy([v['recipe'] if kind=='recipes' else v for v in values.values()])
            assert method=='POST'
            if kind=='recipes':
                proto=copy.deepcopy(body['recipePrototype']);proto.setdefault('params',{'envSelection':{'envMode':'INHERIT'}})
                name=proto['name'];values[name]={'recipe':proto,'payload':body['creationSettings']['script']}
                return {'name':name}
            value=copy.deepcopy(body)
            name=value['name'] if kind=='datasets' else 'Folder%02d'%len(values)
            if kind=='managedfolders':value['id']=name
            else:value.setdefault('schema',{'columns':[]});value.setdefault('managed',False)
            values[name]=value
            return {'id':name}
        name=parts[3]
        if len(parts)==5:
            assert kind=='datasets' and parts[4]=='schema'
            if method=='GET':return copy.deepcopy(values[name]['schema'])
            assert method=='PUT';values[name]['schema']=copy.deepcopy(body);return {}
        if method=='GET':return copy.deepcopy(values[name])
        assert method=='PUT'
        values[name]=copy.deepcopy(body);return {}
    _perform_empty=_perform_json


def test_actual_sdk_creates_flow_and_reinstall_is_read_only():
    backend=Backend();project=DSSProject(backend,'LEGAL_RAG')
    cfg=install_flow.install(project,'# bootstrap fixture\n','ehA8dpVm')
    assert len(backend.items['recipes'])==4 and len(backend.items['datasets'])==7
    assert len(backend.items['managedfolders'])==5
    for role in install_flow.ROLES:
        raw=backend.items['managedfolders'][cfg[role]]
        assert raw['params']['bucket']=='fixture-bucket'
        assert raw['params']['path'].endswith('/'+role)
    recipes=backend.items['recipes']
    structure=recipes['LEGAL_02_STRUCTURE_GENOS_R1']['recipe']
    assert {v['ref'] for v in structure['inputs']['main']['items']}=={cfg['landing'],cfg['raw'],cfg['connection']}
    load=recipes['LEGAL_03_LOAD_SILVER_R1']['recipe']
    assert len(load['outputs']['main']['items'])==8
    assert all(v['appendMode'] for v in load['outputs']['main']['items'])
    assert all(not d['managed'] for d in backend.items['datasets'].values())
    before=copy.deepcopy(backend.items);backend.calls=[]
    assert install_flow.install(project,'# bootstrap fixture\n','ehA8dpVm')==cfg
    assert backend.items==before
    assert all(method=='GET' for method,_,_ in backend.calls)


def test_changed_object_refused_without_overwrite():
    backend=Backend();project=DSSProject(backend,'LEGAL_RAG')
    install_flow.install(project,'# a\n','ehA8dpVm')
    original=copy.deepcopy(backend.items)
    with pytest.raises(ValueError,match='EXISTING_RECIPE_CONFLICT'):
        install_flow.install(project,'# different code\n','ehA8dpVm')
    assert backend.items==original
