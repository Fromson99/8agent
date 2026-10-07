"""Meaningful read-boundary regressions against the generated native fixture."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parent))
import run


@pytest.fixture
def native(tmp_path):
    rev=run.verify()
    frozen=run.CANDIDATE/'revisions'/rev['revision_id']/'snapshot'
    gm=run.load('native_audit_graph',frozen/'02_BACKEND/lawrag/core/investigation_graph.py')
    fixture=run.ADR/'artifacts/native-contracts'
    return gm,fixture,run.read(fixture/'source-catalogue.json'),tmp_path


def action(s,cat,did,index=0,ancestor=False):
    sid=next(sid for sid,c in cat.items() if c['document_id']==did and c['unit_id']==str(index))
    target=s.sources.handle('D' if ancestor else 'P',
        {'document_id':did} if ancestor else {'document_id':did,'unit_id':str(index),'source_id':sid})
    return {'tool':'read','args':{'target':target,'extent':'article','cursor':None},
            'reason':'native ontology access regression','question_refs':['Q1'],
            'expected_information':'검증한 현재 원문 근거'},sid


def policy_session(native,purpose,case_index=0):
    gm,fixture,cat,out=native
    case=run.read(run.DESIGN/'cases.json')['cases'][case_index]
    return gm,fixture,cat,out,case,{'purpose':purpose,'confidence':'HIGH','reason':'native contract'}


@pytest.mark.parametrize('ancestor',[False,True])
def test_excluded_current_source_and_document_denied_before_evidence(native,ancestor):
    gm,f,cat,out,case,decision=policy_session(native,'APPLICABILITY')
    with run.session(out,f/'fixture/built/generation',case,False) as s:
        graph=gm.Graph(f/'ontology.sqlite')
        try:policy=run.apply_policy(s,graph,gm,decision,cat)
        finally:graph.close()
        a,sid=action(s,cat,'mock-performance:v1',ancestor=ancestor)
        before=s.sources.repo.evidence()
        with pytest.raises(gm.AccessDenied):s.sources.execute(a,'blocked-read',actor='SYSTEM_POLICY')
        assert s.sources.repo.evidence()==before
        assert sid in policy['excluded_node_ids']


def test_allowed_native_read_still_executes_and_preserves_original(native):
    gm,f,cat,out,case,decision=policy_session(native,'APPLICABILITY')
    with run.session(out,f/'fixture/built/generation',case,False) as s:
        graph=gm.Graph(f/'ontology.sqlite')
        try:run.apply_policy(s,graph,gm,decision,cat)
        finally:graph.close()
        a,sid=action(s,cat,'mock-regulation:v1')
        value=s.sources.execute(a,'allowed-read',actor='SYSTEM_POLICY')
        assert value['status']=='OK'
        assert sid in {e['source_id'] for e in s.sources.repo.evidence()}


@pytest.mark.parametrize('purpose',['INVENTORY','PERFORMANCE','MIXED','UNKNOWN'])
def test_other_purpose_preserves_c_native_read(native,purpose):
    gm,f,cat,out,case,decision=policy_session(native,purpose)
    with run.session(out,f/'fixture/built/generation',case,False) as s:
        graph=gm.Graph(f/'ontology.sqlite')
        try:policy=run.apply_policy(s,graph,gm,decision,cat)
        finally:graph.close()
        a,sid=action(s,cat,'mock-performance:v1')
        assert not policy['excluded_node_ids']
        value=s.sources.execute(a,'other-purpose-read',actor='SYSTEM_POLICY')
        assert value['status']=='OK'
        assert sid in {e['source_id'] for e in s.sources.repo.evidence()}


def test_stale_classification_reverts_to_original_scope_before_native_read(native):
    gm,f,cat,out,case,decision=policy_session(native,'APPLICABILITY',6)
    with run.session(out,f/'fixture/built/generation',case,False) as s:
        graph=gm.Graph(f/'ontology.sqlite')
        try:policy=run.apply_policy(s,graph,gm,decision,cat)
        finally:graph.close()
        assert 'source version changed' in policy['fallback_reason']
        assert not policy['excluded_node_ids']
        a,sid=action(s,cat,'mock-drift:v2')
        value=s.sources.execute(a,'drift-read',actor='SYSTEM_POLICY')
        assert value['status']=='OK'
        assert sid in {e['source_id'] for e in s.sources.repo.evidence()}
