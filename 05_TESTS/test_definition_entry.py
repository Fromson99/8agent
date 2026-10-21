from copy import deepcopy
from types import SimpleNamespace as NS
import sqlite3,json
import pytest
from semantic_runtime.legal_agent import definition_entry as de
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.repository import text_hash

def sample(question='유동성 비율의 기준은?',count=1):
    text='제2조 제3조에 따른 비율(이하 유동성비율이라 한다)';key='유동성비율';start=text.index(key)
    d=dict(id='d0',key=key,label=key,document_id='allowed',source_id='a',unit_id='1',block_id='b',source_text=text,source_text_sha256=text_hash(text),source_artifact_sha256='hash',term_start=start,term_end=start+len(key),scope_status='UNRESOLVED')
    sources={'a':dict(document_id='allowed',document_name='정의규정',source_artifact_sha256='hash',unit_id='1',blocks=[{'block_id':'b'}]),'z':dict(document_id='target',document_name='대상규정',source_artifact_sha256='target-hash',unit_id='2',blocks=[{'block_id':'c'}])}
    defs={'d'+str(i):dict(d,id='d'+str(i)) for i in range(count)}
    ref=dict(id='r',source_id='a',document_id='allowed',block_id='b',source_text=text,source_text_sha256=text_hash(text),mention_start=4,mention_end=7,mention_text='제3조',locator='제3조',resolution='EXACT_NAMED_DOCUMENT_ARTICLE',target_source_ids=['z'],targets=[{'source_id':'z','unit_id':'2','block_ids':['c'],'target_level':'provision'}])
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE definition_reference(definition_id TEXT,reference_id TEXT)');db.execute("INSERT INTO definition_reference VALUES('d0','r')");db.execute('CREATE TABLE reference(id TEXT PRIMARY KEY,json TEXT)');db.execute('INSERT INTO reference VALUES(?,?)',('r',json.dumps(ref)))
    return NS(tools=NS(definitions=defs,sources=sources,references={'r':ref},db=db),scope=['allowed','target'],store=NS(source=lambda did,bid:{'text':text,'unit_id':'1'}),context=NS(request={'question':question}),matcher=NS(units={('allowed','1'):{'surface':'제2조'},('target','2'):{'surface':'제3조'}},_unit_sources=lambda did,uid:['a'] if did=='allowed' else ['z']))

def test_initial_definition_and_exact_reference_locations():
    s=sample();p=de.page(s,de.matches(s));r=p['items'][0]
    assert p['total']==1 and r['question_span']['text']=='유동성 비율'
    assert r['definition']['source_id']=='a' and not r['citation_eligible']
    assert r['connections'][0]['targets'][0]['source_id']=='z' and r['scope_status']=='UNRESOLVED'

@pytest.mark.parametrize('question,count',[('유동성비율은?',1),('비유동성비율은?',0),('다른 비율 기준',0),('「유동성비율」',1)])
def test_word_boundary_and_particle(question,count):assert len(de.matches(sample(question)))==count

def test_longest_label_and_multiple_definitions_preserved():
    s=sample('단기금융업무 유동성비율',2);d=deepcopy(s.tools.definitions['d0']);d.update(id='long',key='단기금융업무유동성비율',label='단기금융업무 유동성비율');s.tools.definitions['long']=d
    assert [r['definition_id'] for r in de.matches(s)]==['long']
    assert len(de.matches(sample(count=2)))==2

def test_scope_blocks_origin_and_hides_destination():
    s=sample();s.scope=['target'];assert not de.matches(s)
    s.scope=['allowed'];r=de.page(s,de.matches(s))['items'][0]
    assert r['connections'][0]['targets']==[] and r['connections'][0]['scope_limited'] and '대상규정' not in str(r)

@pytest.mark.parametrize('field,value',[('source_text_sha256','wrong'),('source_artifact_sha256','wrong'),('term_start',0),('unit_id','9')])
def test_definition_corruption_fails_closed(field,value):
    s=sample();s.tools.definitions['d0'][field]=value
    with pytest.raises(ContractError):de.page(s,de.matches(s))

@pytest.mark.parametrize('field,value',[('source_text_sha256','wrong'),('mention_end',8),('source_id','z')])
def test_reference_corruption_fails_closed(field,value):
    s=sample();s.tools.references['r'][field]=value;s.tools.db.execute('UPDATE reference SET json=?',(json.dumps(s.tools.references['r']),))
    with pytest.raises(ContractError):de.page(s,de.matches(s))

def test_unresolved_target_stays_unresolved():
    s=sample();s.tools.references['r']['resolution']='UNRESOLVED';s.tools.db.execute('UPDATE reference SET json=?',(json.dumps(s.tools.references['r']),));r=de.page(s,de.matches(s))['items'][0]['connections'][0]
    assert r['resolution']=='UNRESOLVED' and not r['targets']

def test_all_pages_and_durable_offsets():
    s=sample(count=19);rows=de.matches(s);seen=[];offset=0
    while True:
        p=de.page(s,rows,offset);seen.extend(r['definition_id'] for r in p['items'])
        if p['next_offset'] is None:break
        offset=p['next_offset']
    assert len(set(seen))==19 and de.page(s,deepcopy(rows),8)==de.page(s,rows,8)
    for invalid in [-1,1,24,True]:
        with pytest.raises(ContractError):de.page(s,rows,invalid)


def test_empty_lazy_cache_still_resolves_stored_definition():
    s=sample();s.tools.references.clear()
    assert de.page(s,de.matches(s))['items'][0]['connections'][0]['targets'][0]['source_id']=='z'
    assert not s.tools.references  # no fictitious read or cached navigation

def test_older_generation_without_link_table_keeps_definition():
    s=sample();s.tools.db.execute('DROP TABLE definition_reference')
    r=de.page(s,de.matches(s))['items'][0]
    assert r['definition']['source_id']=='a' and not r['connections']

@pytest.mark.parametrize('fault',['dangling','identity','unit','blocks'])
def test_stored_link_boundaries(fault):
    s=sample();r=s.tools.references['r']
    if fault=='dangling':s.tools.db.execute('DELETE FROM reference')
    else:
        if fault=='identity':r['id']='other'
        if fault=='unit':r['targets'][0]['unit_id']='999'
        if fault=='blocks':r['targets'][0]['block_ids']=['outside']
        s.tools.db.execute('UPDATE reference SET json=?',(json.dumps(r),))
    with pytest.raises(ContractError):de.page(s,de.matches(s))

def test_navigation_registry_adds_definition_page_to_legacy_contract():
    from semantic_runtime.legal_agent import tool_policy
    from pathlib import Path
    import os
    root=Path(os.environ['LAWRAG_WORKSPACE_ROOT'])
    design=json.loads((root/'07_DOCS/REFERENCE/REPORTS/TOOL_FAILURE_RECOVERY_DESIGN_20261014/POLICY_DESIGN.json').read_text())
    original={(c['surface'],c['name']) for c in design['choices']}
    assert set(tool_policy.REGISTRY)==original|{('navigation','NEXT_DEFINITIONS')}
