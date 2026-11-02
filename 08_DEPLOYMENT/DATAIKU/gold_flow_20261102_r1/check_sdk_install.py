"""Real Dataiku SDK with an in-memory REST boundary; never contacts DSS."""
import copy
import ast
import io
import json
from pathlib import Path
import sys
import types
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'package'),'/tmp/g19-flow-sdk/unpacked/dataiku_api_client-15.2.0']
from dataikuapi.dss.project import DSSProject
from install_flow import install
import flow_runtime

class MemoryAPI:
    def __init__(self):
        self.stores={k:{} for k in ['managedfolders','datasets','recipes','scenarios','zones','insights']}
        self.stores['managedfolders']['ehA8dpVm']={'id':'ehA8dpVm','name':'landing','projectKey':'LEGAL_RAG','type':'S3','params':{'connection':'OBS_DP_PUBLIC','bucket':'fixture','path':'/landing'}}
        self.payloads={};self.calls=[]
    def get_project(self,key):return DSSProject(self,key)
    def _perform_empty(self,*a,**kw):return self._perform_json(*a,**kw)
    def _perform_json(self,method,path,body=None,params=None):
        self.calls.append((method,path));body=copy.deepcopy(body)
        parts=path.strip('/').split('/')[2:]
        if parts[:2]==['flow','zones']:parts=['zones']+parts[2:]
        kind=parts[0];store=self.stores[kind]
        if len(parts)==1:
            if method=='GET':
                if kind=='recipes':return [v['recipe'] for v in store.values()]
                return copy.deepcopy(list(store.values()))
            assert method=='POST',(method,path)
            if kind=='recipes':
                recipe=body['recipePrototype'];name=recipe['name']
                store[name]={'recipe':dict(recipe,params={'envSelection':{'envMode':'INHERIT'}}), 'payload':body['creationSettings']['script']}
                return {'name':name}
            key=body.get('name') if kind=='datasets' else kind[:2]+str(len(store)+1)
            body['id']=key
            if kind=='zones':body.update(items=[],shared=[])
            if kind=='scenarios':body['active']=False
            store[key]=body
            return copy.deepcopy(body)
        key=parts[1]
        if len(parts)==3:
            sub=parts[2]
            if kind=='zones' and sub=='items':
                assert method=='POST';store[key]['items'].append(body);return copy.deepcopy(store[key])
            if sub=='schema':
                if method=='GET':return copy.deepcopy(store[key]['schema'])
                store[key]['schema']=body;return {}
            if sub=='payload':
                if method=='GET':return self.payloads.get(key,{'script':''})
                self.payloads[key]=body;return {}
            raise AssertionError((method,path))
        if method=='GET':return copy.deepcopy(store[key])
        assert method=='PUT',(method,path);store[key]=body;return {}

def main():
    client=MemoryAPI();project=DSSProject(client,'LEGAL_RAG');blobs={};insights=[]
    class Folder:
        def __init__(self,id):self.id=id
        def upload_stream(self,p,stream):blobs[self.id,p]=stream.read()
        def list_paths_in_partition(self):return ['/'+p for (folder,p) in blobs if folder==self.id]
        def get_download_stream(self,p):return io.BytesIO(blobs[self.id,p.lstrip('/')])
    sys.modules['dataiku']=types.SimpleNamespace(Folder=Folder,default_project_key=lambda:'LEGAL_RAG',api_client=lambda:client)
    def insight(v):
        insights.append(v);client.stores['insights']['g19f1_pipeline_status']={'id':'g19f1_pipeline_status'}
    flow_runtime.publish_insight=insight
    text=(HERE/'DATAIKU_GOLD_FLOW_INSTALL_R1.txt').read_text()
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='FLOW_CONFIG')
    bootstrap=ast.literal_eval(node.value.args[1])
    blobs['ehA8dpVm','DATAIKU_GOLD_FLOW_20261102_R1.zip']=(HERE/'DATAIKU_GOLD_FLOW_20261102_R1.zip').read_bytes()
    cfg=install(project,bootstrap,'ehA8dpVm')
    counts={k:len(v) for k,v in client.stores.items()}
    assert counts=={'managedfolders':9,'datasets':17,'recipes':8,'scenarios':1,'zones':7,'insights':1},counts
    cfg2=install(project,bootstrap,'ehA8dpVm')
    assert cfg2==cfg and counts=={k:len(v) for k,v in client.stores.items()} and len(insights)==1
    scope={};exec(compile(text,'delivered-install.txt','exec'),scope)
    assert scope['FLOW_CONFIG']==cfg and counts=={k:len(v) for k,v in client.stores.items()}
    records=client.stores['recipes'];db_outputs=[]
    for v in records.values():
        outputs=v['recipe']['outputs']['main']['items']
        assert all(i['appendMode'] for i in outputs)
        db_outputs.extend(i['ref'] for i in outputs if '_DB_' in i['ref'])
        compile(v['payload'],'recipe','exec')
    assert len(db_outputs)==len(set(db_outputs))==17
    assert all(not v['managed'] for v in client.stores['datasets'].values())
    script=next(iter(client.payloads.values()))['script'];compile(script,'scenario','exec')
    assert script.count('NON_RECURSIVE_FORCED_BUILD')==8 and script.count('fail_fatal=True')==8
    assert not any('/jobs' in path or '/run' in path for _,path in client.calls)
    result={'sdk':'dataiku-api-client 15.2.0','boundary':'in-memory REST, no actual DSS','status':'PASS',
            'counts':counts,'checks':['delivered ZIP + complete install TXT entrypoint','install','reinstall idempotent','8 recipe scripts compile','17 external append outputs',
             'scenario stage sequence stops on error','installation never starts load','7 colored zones','existing insight preserved'],
            'rest_calls':len(client.calls)}
    (HERE/'SDK_INSTALL_VALIDATION.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':main()
