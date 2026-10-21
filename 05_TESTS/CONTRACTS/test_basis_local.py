"""Same-runtime fixed links: review boundary, SQLite consumer and recovery."""
import fcntl
import json

import pytest

import basis_local as local
from lawrag.pipeline import basis_batch_artifacts as art
from semantic_runtime.basis_links.contracts import BasisError
from semantic_runtime.basis_links.resolver import snapshot, targets
from semantic_runtime.basis_links.service import Service
from test_risk_basis_staging import pilot, PHOTO, run as stage, add


@pytest.fixture
def prepared(pilot):
    stage(pilot)
    return pilot


def call(p, action, **kwargs):
    return local.run(action,p.job,p.root/'review',PHOTO,p.runtime,None,
                     local_validation=True,**kwargs)


def test_report_and_apply_only_reviewed_fixed_four_then_replay_and_revoke(prepared):
    p=prepared
    extra=add(p,kind='RELATED')
    assert call(p,'report')['links']==4
    assert not (p.runtime/'basis-links').exists()
    assert call(p,'status')['status']=='not_applied'
    html=(p.root/'review/LINKS.html').read_text()
    assert html.count('<tr><td class="number">')==4
    assert '위험관리기준시행세칙' in html and '금융투자업규정' in html
    assert extra not in html
    assert call(p,'check')['status']=='SOURCE_READY'
    assert not (p.root/'review/REVIEW.json').exists()
    before=(p.root/'review/RELATIONS.json').read_bytes()
    stage(p)  # A reused staging receipt must remain verifiable.
    assert call(p,'report')['status']=='HTML_READY'
    assert (p.root/'review/RELATIONS.json').read_bytes()==before
    assert len(call(p,'apply')['inserted'])==4
    assert call(p,'apply')['status']=='already_applied'
    state=call(p,'status')
    assert state['marker_enabled'] and set(state['live'].values())=={'APPROVED'}
    value=art.read_json(p.root/'review/RELATIONS.json')
    with art.authority(p.runtime/'basis-links/authority.sqlite') as repo, art.source(PHOTO,value['source'],value['principal']) as (sources,who):
        assert len(repo.links('risk_team'))==4 and repo.head(extra) is None
        service=Service(repo,sources)
        assert len(targets(service,who,snapshot(service,who,[p.selected['internal_document_id']])))==7
    assert call(p,'rollback')['status']=='rolled_back'
    assert call(p,'rollback')['status']=='already_rolled_back'
    with pytest.raises(BasisError):
        call(p,'apply')
    assert not list(p.root.rglob('*.zip'))


@pytest.mark.parametrize('phase',['before_commit','after_commit'])
def test_commit_failure_and_response_loss_resume_exact_input(prepared,phase):
    p=prepared
    call(p,'report')
    def fail(actual):
        if actual==phase: raise OSError('injected response/transaction loss')
    with pytest.raises(OSError): call(p,'apply',hook=fail)
    result=call(p,'apply')
    assert result['status']==('applied' if phase=='before_commit' else 'already_applied')
    assert len(result['inserted'])==4


@pytest.mark.parametrize('what',['html','receipt','context','snapshot'])
def test_tampering_refused_without_sqlite(prepared,what):
    p=prepared
    call(p,'report')
    if what=='html':
        path=p.root/'review/LINKS.html'
        path.write_text(path.read_text()+'changed')
    elif what=='receipt':
        path=next(p.job.glob('RISK_FIXED_*.json'))
        data=art.read_json(path); data['actions'][0]['head_hash']='changed'; art.atomic(path,data)
    elif what=='context':
        path=p.root/'review/LOCAL_CONTEXT.json'
        data=art.read_json(path); data['runtime']='other'; art.atomic(path,data)
    else:
        path=p.root/'review/RELATIONS.json'
        data=art.read_json(path); data['items'].pop(); art.atomic(path,data)
    with pytest.raises(BasisError): call(p,'apply')
    assert not (p.runtime/'basis-links').exists()


def test_interrupted_html_generation_resumes_without_replacing_snapshot(prepared,monkeypatch):
    p=prepared
    original=art.atomic
    def fail(path,value):
        if path.name=='RELATIONS.json': raise OSError('disk interruption')
        return original(path,value)
    monkeypatch.setattr(art,'atomic',fail)
    with pytest.raises(OSError): call(p,'report')
    monkeypatch.setattr(art,'atomic',original)
    assert call(p,'report')['status']=='HTML_READY'
    assert call(p,'check')['status']=='SOURCE_READY'


def test_source_change_lock_and_unreviewed_apply_refused(prepared,monkeypatch):
    p=prepared
    with pytest.raises(BasisError): call(p,'apply')
    with (p.job/'CANDIDATES.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): call(p,'report')
    call(p,'report')
    original=local.fixed_snapshot
    def changed(*a,**k):
        value=original(*a,**k); value['source']['selection_sha256']='changed'; return value
    monkeypatch.setattr(local,'fixed_snapshot',changed)
    with pytest.raises(BasisError): call(p,'apply')
    assert not (p.runtime/'basis-links').exists()


def test_field_apply_requires_shared_runtime(prepared):
    p=prepared
    call(p,'report')
    with pytest.raises(BasisError,match='공유 runtime'):
        local.run('apply',p.job,p.root/'review',PHOTO,p.runtime,None)
    assert not (p.runtime/'basis-links').exists()
