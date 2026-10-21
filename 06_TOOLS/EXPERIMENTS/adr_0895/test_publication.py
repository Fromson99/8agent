from pathlib import Path
from copy import deepcopy
import importlib.util
import pytest
from semantic_runtime.legal_agent import completion_contracts as cc,unified_runtime as runtime

def gaps(count):
    return [{'kind':'MISSING_SOURCE','issue_id':'Q1','material':True,
             'material_id':'B'+str(i),'missing_target':'','reason':'별도 미확인 범위 '+str(i),
             'suggested_action':'RESEARCH'} for i in range(count)]

@pytest.mark.parametrize('count',[2,3,5])
def test_identical_display_text_is_single_but_every_gap_identity_survives(count):
    value={'gaps':gaps(count)};before=deepcopy(value['gaps'])
    out=cc.refresh_limitations(value,[{'id':'Q1','question':'기준은?'}])
    assert len(out['limitations'])==1 and len(out['limitation_items'])==count
    assert len({i['id'] for i in out['limitation_items']})==count
    assert out['gaps']==before
    old=deepcopy(out);assert cc.refresh_limitations(out,[{'id':'Q1','question':'기준은?'}])==old

@pytest.mark.parametrize('difference',['issue','missing_target'])
def test_distinct_visible_missing_information_is_not_collapsed(difference):
    value={'gaps':gaps(2)}
    if difference=='issue':value['gaps'][1]['issue_id']='Q2'
    else:value['gaps'][1]['missing_target']='제9조'
    out=cc.refresh_limitations(value,[{'id':'Q1','question':'기준은?'},{'id':'Q2','question':'예외는?'}])
    assert len(out['limitations'])==2 and len(out['limitation_items'])==2

def test_different_navigation_outcome_remains_visible_and_preserved():
    value={'gaps':gaps(2)};closed={cc.gap_key(value['gaps'][0]):'NOT_AVAILABLE'}
    out=cc.refresh_limitations(value,[{'id':'Q1','question':'기준은?'}],closed=closed)
    assert len(out['limitations'])==2
    assert out['limitation_items'][0]['navigation_status']=='NOT_AVAILABLE'
    assert '찾지 못했습니다' in out['limitations'][0]

P=Path(__file__).resolve().parents[1]/'adr_0892/test_focus.py'
spec=importlib.util.spec_from_file_location('current_compact_api_fixture',P)
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
tree=prior.tree

@pytest.mark.parametrize('legacy_duplicates',[False,True])
def test_actual_api_preserves_committed_limitations_on_publish_and_duplicate(tmp_path,tree,monkeypatch,legacy_duplicates):
    refresh=cc.refresh_limitations;ports=[];port=runtime.result_port
    # Fixture represents a committed partial assessment, including historical
    # duplicate display text. It does not edit a live response or model evidence.
    def saved_partial(value,issues,*args,**kwargs):
        out=refresh(value,issues,*args,**kwargs)
        text='격리 검사: 별도의 미확인 근거 범위가 남아 있습니다.'
        out['limitation_items']=[{'id':'L-fixture-'+str(i),'kind':'MISSING_SOURCE','issue_id':'Q1','text':text} for i in range(2)]
        out['limitations']=[text,text] if legacy_duplicates else [text]
        return out
    def checked(*args,**kwargs):
        result=port(*args,**kwargs);committed=args[3]['answer']['limitations']
        assert len(committed)==(2 if legacy_duplicates else 1)
        assert result['answer']['unresolved']==[{'reason':x} for x in committed]
        assert result['answer']['text']==args[3]['answer']['text']
        ports.append(result);return result
    monkeypatch.setattr(cc,'refresh_limitations',saved_partial)
    monkeypatch.setattr(runtime,'result_port',checked)
    prior.test_current_compact_api_publishes_and_reuses_verified_original(tmp_path,tree,monkeypatch)
    assert ports
