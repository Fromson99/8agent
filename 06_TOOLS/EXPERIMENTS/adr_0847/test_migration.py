from contextlib import ExitStack,closing
from copy import deepcopy
import json,sqlite3
import pytest
from test_document_release import source
from semantic_runtime.storage import Store,publish
from semantic_runtime.basis_links.sources import SourcePort
from semantic_runtime.basis_links.repository import Repository
from semantic_runtime.basis_links.service import Service
from semantic_runtime.basis_links.migration import migrate
from semantic_runtime.basis_links.contracts import BasisError
from lawrag.pipeline.basis_lifecycle import prepare,verify
from test_authority import WHO,BODY,review_body


def make(tmp_path,name,texts):
    path=source(tmp_path/(name+'.sqlite'),[('inside','모의내규',['승인은 외규에 따른다.']),('outside-'+name,'모의외규',texts)])
    with sqlite3.connect(path) as db:
        for did, in db.execute('SELECT document_id FROM document').fetchall():
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({'document_category':'internal' if did=='inside' else 'external'}),did))
    publish(tmp_path,path,tmp_path/name)
    return Store(tmp_path/name)


@pytest.mark.parametrize('texts,status',[
    (['서론','승인 기한은 10일이다.'],'current'),
    (['승인 기한은 11일이다.'],'review_needed'),
    (['승인 기한은 10일이다.','승인 기한은 10일이다.'],'unresolved'),
    (['승인하지 않는다.'],'review_needed'),
])
def test_migration_preserves_human_event(tmp_path,texts,status):
    with ExitStack() as stack:
        old=SourcePort(stack.enter_context(closing(make(tmp_path,'old',['승인 기한은 10일이다.']))))
        new=SourcePort(stack.enter_context(closing(make(tmp_path,'new',texts))))
        repo=stack.enter_context(closing(Repository(tmp_path/'authority.sqlite')))
        service=Service(repo,old);who={**WHO,'document_ids':['inside','outside-old','outside-new']}
        p=service.propose(who,{**BODY,'external':[{'document_id':'outside-old','unit_id':'0'}]});service.review(who,review_body(p))
        original=repo.history(p['link']['link_id'])['events']
        lineage=[{'version_id':did,'family_id':'law:1','source_artifact_hash':port.document_hash(did),'provenance':{'official_id':'1'}} for port,did in ((old,'outside-old'),(new,'outside-new'))]
        result=prepare(repo,old,new,who,{'outside-old':'outside-new'},lineage)
        assert result['items'][0]['status']==status,result
        assert repo.history(p['link']['link_id'])['events']==original
        assert prepare(repo,old,new,who,{'outside-old':'outside-new'},lineage)==result
        assert verify(repo,new,who,result['migration_id'])['verified']
        assert repo.binding(p['link']['link_id'],2,old.generation)['external'][0]['document_id']=='outside-old'
        current_only=Service(repo,new).list({**who,'document_ids':['inside','outside-new']})['items']
        assert bool(current_only)==(status!='unresolved')
        if current_only:assert 'outside-old' not in json.dumps(current_only)
        assert Service(repo,new).list(who)['items']


def test_lineage_and_helper_version_fail_closed(tmp_path):
    with ExitStack() as stack:
        old=SourcePort(stack.enter_context(closing(make(tmp_path,'old',['旧']))));new=SourcePort(stack.enter_context(closing(make(tmp_path,'new',['新']))))
        repo=stack.enter_context(closing(Repository(tmp_path/'authority.sqlite')));who={**WHO,'document_ids':['inside','outside-old','outside-new']}
        with pytest.raises(BasisError):migrate(Service(repo,old),new,who,{'outside-old':'outside-new'})
