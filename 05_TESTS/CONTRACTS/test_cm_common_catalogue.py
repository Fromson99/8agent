"""Common CM catalogue shares source entries while retaining private state and live ACL."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import time
import pytest
from lawrag.pipeline import shortcut_package as packages
from lawrag.pipeline.legal_wiki_compiler import rebuild
from semantic_runtime.storage import Store
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import MemoryError, digest, encoded
from semantic_runtime.legal_agent import core_evidence_route as core
from test_cm_shortcut_package import host, state

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def inputs():
    common = json.loads((ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_data_20261007_r2/CM51_SOURCE_PACKAGE.json').read_text())
    common.update(package_id='common-contract-fixture',visibility=packages.COMMON_VISIBILITY)
    store = Store(ROOT/'01_DATA/TERM_RELEASES/local-genos-parity-20261006-r1/generation')
    operator = packages.common_principal(store=store)
    reader = {'user_id':'alice','team_id':'risk_team','authenticated':True,
              'document_ids':operator['document_ids']}
    yield common,store,operator,reader
    store.close()


@pytest.fixture
def repo(tmp_path):
    repo=ShortcutRepository(tmp_path/'cases-v4.sqlite')
    yield repo
    repo.close()


def test_one_catalogue_shared_across_users_teams_and_tenants(inputs,repo,tmp_path):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store)
    assert receipt['scope']==packages.common_scope_id()
    assert len(receipt['records'])==51 and sum(r['sources'] for r in receipt['records'])==98
    for other in (reader,{**reader,'user_id':'bob'},{**reader,'user_id':'carol','team_id':'financial_team','tenant_id':'second'}):
        assert len(repo.search(other,limit=100)['pages'])==51
        path=core.lookup(host(repo,receipt['source_binding']),state(package,other),other)
        assert path and path['unit_id']==receipt['records'][0]['unit_id']
    assert packages.import_package(repo,operator,package,store)['already_imported']
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==51
    assert rebuild(repo,operator,tmp_path/'wiki')['pages']==51
    assert rebuild(repo,reader,tmp_path/'wiki')['pages']==0


def test_common_route_keeps_current_facts_and_literal_input(inputs,repo):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store)
    current={**state(package,reader),'task':'현재 모델 요약','facts':[{'name':'근무기간','value':'3개월'}]}
    question='벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'
    path=core.lookup(host(repo,receipt['source_binding']),current,reader,question=question)
    assert path['case_id']=='cm-016' and path['conditions']==core.conditions(current)


def test_common_acl_narrowing_hides_records_and_direct_reads(inputs,repo):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store)
    record=receipt['records'][0]
    denied={**reader,'document_ids':[]}
    assert repo.search(denied,limit=100)['pages']==[]
    with pytest.raises(MemoryError):repo.current(record['unit_id'],1,denied)
    assert core.lookup(host(repo,receipt['source_binding']),state(package,denied),denied) is None
    assert core.lookup(host(repo,receipt['source_binding']),{**state(package,reader),'document_ids':[]},reader) is None


def test_external_and_changed_source_binding_do_not_reuse_common(inputs,repo):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store)
    assert core.lookup(host(repo,receipt['source_binding'],'external'),state(package,reader),reader) is None
    bad={**receipt['source_binding'],'unit_index_sha256':'different'}
    assert core.lookup(host(repo,bad),state(package,reader),reader) is None


def test_private_catalogue_is_not_shared_or_automatically_promoted(inputs,repo):
    package,store,operator,reader=inputs
    private=deepcopy(package);private['visibility']='PRIVATE_OWNER_TEAM'
    receipt=packages.import_package(repo,reader,private,store)
    assert len(repo.search(reader,limit=100)['pages'])==51
    assert repo.search({**reader,'user_id':'bob'},limit=100)['pages']==[]
    assert repo.search({**reader,'team_id':'financial_team'},limit=100)['pages']==[]
    assert receipt['scope']!=packages.common_scope_id()
    with pytest.raises(MemoryError):packages.import_package(repo,operator,private,store)


def test_common_publication_requires_filesystem_operator(inputs,repo):
    package,store,operator,reader=inputs
    with pytest.raises(MemoryError):packages.import_package(repo,reader,package,store)
    forged={**reader,'user_id':packages.COMMON_OWNER,'team_id':packages.COMMON_TEAM,
            'tenant_id':packages.COMMON_TENANT,'_common_operator':True}
    with pytest.raises(MemoryError):repo.scope(forged)
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0


def test_reading_common_catalogue_grants_no_write_authority(inputs,repo):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store);unit=receipt['records'][0]['unit_id']
    assert repo.current(unit,1,reader)['visibility']=='COMMON'
    with pytest.raises(MemoryError):repo.publish(unit,1,reader,expected_head=1)
    with pytest.raises(MemoryError):repo.retire(unit,1,reader,reason='not operator')
    with pytest.raises(MemoryError):repo.verification(unit,1,reader,kind='SOURCE',result='PASS',policy='x',verifier='x',evidence=['x'],expires=time.time()+60)
    with pytest.raises(MemoryError):packages.retire_package(repo,reader,receipt)
    assert len(repo.search(reader,limit=100)['pages'])==51


def test_source_revocation_and_retirement_affect_all_readers(inputs,repo):
    package,store,operator,reader=inputs
    receipt=packages.import_package(repo,operator,package,store)
    unit=receipt['records'][0]['unit_id']
    ref=repo.db.execute('SELECT ref FROM sw_dependency WHERE unit=? LIMIT 1',(unit,)).fetchone()[0]
    repo.revoke_source(ref,operator)
    with pytest.raises(MemoryError):repo.current(unit,1,reader)
    assert core.lookup(host(repo,receipt['source_binding']),state(package,reader),reader) is None
    assert packages.retire_package(repo,operator,receipt)['records_preserved']
    assert repo.search(reader,limit=100)['pages']==[]
    assert repo.db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
    with pytest.raises(MemoryError):packages.import_package(repo,operator,package,store)


def test_bad_common_source_is_atomic_and_receipt_retirement_is_exact(inputs,repo):
    package,store,operator,reader=inputs
    bad=deepcopy(package);bad['cases'][-1]['entries'][-1]['section_text_sha256']='different'
    with pytest.raises(MemoryError):packages.import_package(repo,operator,bad,store)
    assert repo.db.execute('SELECT count(*) FROM sw_unit').fetchone()[0]==0
    receipt=packages.import_package(repo,operator,package,store)
    bad=deepcopy(receipt);bad['records']=bad['records'][:-1]
    with pytest.raises(MemoryError):packages.retire_package(repo,operator,bad)
    assert len(repo.search(reader,limit=100)['pages'])==51


def test_common_routes_do_not_starve_private_procedure_menu(inputs,repo):
    from semantic_runtime.legal_agent.wiki_execution import WikiExecution
    package,store,operator,reader=inputs
    packages.import_package(repo,operator,package,store)
    private=deepcopy(package);private['visibility']='PRIVATE_OWNER_TEAM'
    private['cases']=private['cases'][:1]
    receipt=packages.import_package(repo,reader,private,store)
    prior=receipt['records'][0]['unit_id']
    value=json.loads(repo.db.execute('SELECT payload FROM sw_knowledge WHERE unit=?',(prior,)).fetchone()[0])
    value.pop('core_evidence_route')
    unit='unit:zz-private-template';value['id']=unit;value['question']='private current question'
    for member in value['members']:member['unit']=unit
    with repo.transaction():
        repo.db.execute('INSERT INTO sw_unit VALUES(?,?,1)',(unit,repo.scope(reader)))
        repo.db.execute('INSERT INTO sw_knowledge VALUES(?,1,?,?,?,?)',(unit,'private-fixture',encoded(value),digest(value),'OPEN'))
        repo.db.execute("INSERT INTO sw_lifecycle VALUES(?,1,'PUBLISHED')",(unit,))
        repo.db.execute('INSERT INTO sw_dependency SELECT ?,1,ref,version,hash,role FROM sw_dependency WHERE unit=?',(unit,prior))
    execution=SimpleNamespace(host=SimpleNamespace(shortcut=repo,shortcut_flags={'hint':True}),
        principal=reader,state={'task':value['question'],'facts':[]},
        s=SimpleNamespace(context=SimpleNamespace(run_id='private-plan-test')),
        current_source=lambda member:True)
    plans=WikiExecution.plans(execution)
    assert len(plans)==1 and plans[0][0]['unit_id']==unit and plans[0][1]['mode']=='HINT'
