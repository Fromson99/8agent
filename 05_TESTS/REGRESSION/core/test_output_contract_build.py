"""Actual build adapter completion/schema boundaries; synthetic provider only."""
import pytest
from .test_recipe_runtime import isolated_env, install_transport, response
from lawrag.core.structure import recipe_runtime as runtime
from lawrag.core.structure.recipe_output import ResponseError


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path,monkeypatch):
    raw=response({});raw['choices'][0]['message']['content']='{"value":1,"value":2}'
    install_transport(monkeypatch,lambda *args:raw)
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'duplicates'),[])
    with pytest.raises(ResponseError):provider('review','test',{}, {'type':'object'},False)
    exchange=provider.client.log[-1]
    assert provider.calls==exchange.physical_calls==1
    assert exchange.output_contract['issues'][0]['code']=='DUPLICATE_JSON_KEY'


def test_build_stream_needs_completion_marker_even_if_json_is_valid(tmp_path,monkeypatch):
    sessions=install_transport(monkeypatch,lambda *args:response({'ok':True}))
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'interrupted'),[])
    post=sessions[0].post
    def incomplete(*args,**kwargs):
        reply=post(*args,**kwargs);lines=reply.iter_lines
        reply.iter_lines=lambda: (line for line in lines() if b'[DONE]' not in line if isinstance(line,bytes))
        return reply
    monkeypatch.setattr(sessions[0],'post',incomplete)
    with pytest.raises(runtime.NeedsReview):provider('review','test',{}, {'type':'object'},False)
    assert provider.calls==1 and provider.client.log[-1].output_contract['category']=='OUTPUT_INCOMPLETE'


def test_build_model_binding_failure_is_not_repaired(tmp_path,monkeypatch):
    raw=response({'ok':True});raw['model']='unapproved-model'
    install_transport(monkeypatch,lambda *args:raw)
    provider=runtime.GenosCalls(runtime.Journal(tmp_path,'wrong-model'),[])
    with pytest.raises(runtime.NeedsReview):provider('review','test',{}, {'type':'object'},False)
    assert provider.calls==1
    assert provider.client.log[-1].output_contract['category']=='STATE_OR_BINDING_INVALID'


def test_build_resume_reuses_proposals_and_keeps_total_budget(tmp_path,monkeypatch):
    calls=[]
    install_transport(monkeypatch,lambda *args:calls.append(1) or response({'ok':True}))
    checkpoint=tmp_path/'checkpoints'/'document.json';binding={'source':'synthetic','model':'test-qwen-vl'}
    first=runtime.GenosCalls(runtime.Journal(tmp_path,'first'),[],max_calls=2)
    first.bind_recovery(checkpoint,binding)
    assert first('a','test',{}, {'type':'object'},False)=={'ok':True}
    resumed=runtime.GenosCalls(runtime.Journal(tmp_path,'resumed'),[],max_calls=2)
    resumed.bind_recovery(checkpoint,binding)
    assert resumed('a','test',{}, {'type':'object'},False)=={'ok':True}
    assert resumed.calls==len(calls)==1
    resumed('b','test',{}, {'type':'object'},False)
    with pytest.raises(runtime.NeedsReview,match='budget'):resumed('c','test',{}, {'type':'object'},False)
    assert resumed.calls==len(calls)==2


def test_build_unknown_send_is_not_replayed_on_restart(tmp_path,monkeypatch):
    install_transport(monkeypatch,lambda *args:response({'ok':True}))
    checkpoint=tmp_path/'checkpoints'/'document.json';binding={'source':'synthetic'}
    first=runtime.GenosCalls(runtime.Journal(tmp_path,'first'),[]);first.bind_recovery(checkpoint,binding)
    def interrupted(*args):raise KeyboardInterrupt()
    monkeypatch.setattr(first,'_send_request',interrupted)
    with pytest.raises(KeyboardInterrupt):first('a','test',{}, {'type':'object'},False)
    resumed=runtime.GenosCalls(runtime.Journal(tmp_path,'resumed'),[]);resumed.bind_recovery(checkpoint,binding)
    with pytest.raises(runtime.NeedsReview,match='unknown'):resumed('a','test',{}, {'type':'object'},False)
    assert resumed.calls==1 and not resumed.client.log


def test_build_internal_typeerror_never_requests_model_repair(tmp_path):
    from lawrag.core.structure.recipe_compact import ask
    calls=[]
    def broken(*args):calls.append(1);raise TypeError('injected implementation failure')
    with pytest.raises(TypeError):ask(broken,runtime.Journal(tmp_path,'bug'),'review','test',{}, {},False)
    assert len(calls)==1
