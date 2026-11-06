"""Prepare the fixed glossary/catalog archive once on a host with the R10 resources."""
from pathlib import Path
import argparse
import transport as t


def build(data, output):
    data=data.resolve(strict=True)
    policy_file=Path(__file__).resolve().parent/'00_SYSTEM/GLOSSARY_PIPELINE.json'
    policy=t.read(policy_file)
    draft=policy['draft_assembly'].get('current_draft',policy['current_draft'])
    bundle=policy['knowledge_bundle']
    if any(x.get('root_id','data')!='data' for x in (draft,bundle)):
        raise ValueError('SUPPORT_ROOT')
    if t.sha(t.checked(data,bundle['path'])/'manifest.json')!=bundle['manifest_sha256']:
        raise ValueError('SUPPORT_KNOWLEDGE_MANIFEST_CHANGED')
    files={}
    for rel in (draft['path'],bundle['path'],'CATALOG'):
        directory=t.checked(data,rel)
        if not directory.is_dir() or output.resolve().is_relative_to(directory):
            raise ValueError('SUPPORT_DIRECTORY:'+rel)
        for file in t.files(directory):
            files['01_DATA/'+file.relative_to(data).as_posix()]=file
    if not {'01_DATA/CATALOG/TEAM_LAYOUT.json','01_DATA/'+draft['path']+'/dictionary.sqlite'} <= files.keys():
        raise ValueError('SUPPORT_DEPENDENCY_MISSING')
    receipt=t.pack(files,output,metadata={'glossary_config_sha256':t.sha(policy_file)})
    print('AGENT_PIPELINE_SUPPORT_ZIP='+str(output.resolve()))
    print('AGENT_PIPELINE_SUPPORT_SHA256='+receipt['sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('data_root',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    build(a.data_root,a.output)
