"""Exact navigation semantics and recovery; deliberately no timing assertions."""
from collections import Counter
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import sqlite3
import pytest

from semantic_runtime import reference_build as rb
from semantic_runtime import term_references,term_references_legacy
from semantic_runtime.navigation_storage import AUDIT_TABLES,verify_build
from semantic_runtime.contracts import sha
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.term_serving_bundle import verify_assets
from test_provision_references import SCHEMA,article
from test_navigation_storage import original_source

ROOT=Path(__file__).resolve().parents[2]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0633-genos-reference-build-contract'

def logical(db,table):
    def cell(value):
        if isinstance(value,str) and value[:1] in ('{','['):
            try:return json.dumps(json.loads(value),sort_keys=True,ensure_ascii=False)
            except ValueError:pass
        return value
    return Counter(tuple(cell(v) for v in row) for row in db.execute('SELECT * FROM '+table))


def test_suffix_exact_regex_equivalence_and_title_count_independent():
    rng=random.Random(634)
    keys=['법','A[법]','규정(별)','가 법',' > 법','', ' ', '법 ', '법\n','법\t ', '\t']
    keys += [''.join(rng.choices('가힣Az09 ()[]>·\n\t',k=rng.randrange(1,14))) for _ in range(120)]
    index=rb.LiteralSuffixIndex(keys)
    prefixes=['','법','앞법','앞 법\n','é법','법\t \n','法법','한A[법]','(A[법])', ' 법 \n']
    prefixes += [rng.choice(['가','Z','9','é','·',' ','\n',''])+rng.choice(keys)+rng.choice(['','\n',' \t']) for _ in range(300)]
    for prefix in prefixes:
        hits=[k for k in keys if re.search(r'(?<![가-힣A-Za-z0-9])'+re.escape(k)+r'\s*$',prefix)]
        assert index.match(prefix)==(max(hits,key=len) if hits else None),repr(prefix)
    small=rb.LiteralSuffixIndex(['가상 법'])
    large=rb.LiteralSuffixIndex(['가상 법']+[f'별개 {i} 법령' for i in range(10000)])
    assert small.match('앞 가상 법  ')==large.match('앞 가상 법  ')
    assert small.visits==large.visits


def reference_fixture(db,scope=False):
    db.executescript(SCHEMA)
    if scope:db.execute('CREATE TABLE structure_anchor(source_id TEXT,unit_id TEXT,json TEXT,PRIMARY KEY(source_id,unit_id))')
    rows=[('a1','a','RAW > A[가상] 법','제1조', [('1','제1조(정의) 금융자금')]),
          ('a2','a','RAW > A[가상] 법','제2조', [('2','제2조(정의) 금융자금')]),
          ('ax','a','RAW > A[가상] 법','별표 1',[('3','별표 1 금융자금')]),
          ('d1','d','A[가상] 법 시행령','제1조',[('d','제1조(적용) 법 제1조에 따른다.')]),
          ('dup','old','RAW > old > A[가상] 법','제1조',[('old','제1조(구 버전)')]),
          ('r1','r','가상 규정','제1조',[('4','제1조(인용) 「A[가상] 법」(이하 "가법"이라 한다).'),('5','같은 법 시행령(이하 "령"이라 한다).')]),
          ('r2','r','가상 규정','제2조',[('6','제2조(적용) 가법 제1조 및 제2조, 령 제1조, 등록명 제1조, 이 규정 제1조를 준용한다. A[가상] 법 별표 1과 없는법 별표 99를 따른다.')])]
    for sid,did,name,heading,blocks in rows:article(db,sid,did,name,heading,None,blocks,[])
    db.commit()


@pytest.mark.parametrize('scope',[False,True])
def test_frozen_previous_compiler_exact_rows(scope):
    name='term_references.py' if scope else 'term_references_legacy.py'
    path=ADR/'artifacts/baseline/02_BACKEND/semantic_runtime'/name
    pins=json.loads((ADR/'artifacts/upstream-pins.json').read_text())
    assert sha(path)==pins['02_BACKEND/semantic_runtime/'+name]
    spec=importlib.util.spec_from_file_location('semantic_runtime._frozen633',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    current=term_references if scope else term_references_legacy
    delegations=[{'src':{'name':'가상 규정','jo':'제1조'},'dst':{'name':'A[가상] 법 시행령','jo':'제1조'}}]
    with closing(sqlite3.connect(':memory:')) as a, closing(sqlite3.connect(':memory:')) as b:
        for db in (a,b):reference_fixture(db,scope)
        assert old.compile_references(a,{'등록명':'가상 규정'},delegations)==current.compile_references(b,{'등록명':'가상 규정'},delegations)
        for table in ('reference','reference_end','reference_target','reference_candidate','reference_candidate_end'):
            assert logical(a,table)==logical(b,table),table


def test_bounded_body_cache_and_shared_writable_sql():
    with closing(sqlite3.connect(':memory:')) as db:
        reference_fixture(db)
        cache=rb.BuildSources(db,max_bytes=1300,max_entries=2)
        for (sid,) in db.execute('SELECT id FROM source'):
            assert cache[sid]['id']==sid
            assert cache.bytes<=1300 and len(cache.cache)<=2
        large={'id':'oversize','blocks':[{'text':'가'*3000}]}
        db.execute('INSERT INTO source VALUES (?,?,?,?)',('oversize','r',None,json.dumps(large)))
        assert cache['oversize']==large and 'oversize' not in cache.cache
        rb.shared_reference_schema(db)
        text='동일 원문 별표 1 제1조 제2조';digest=hashlib.sha256(text.encode()).hexdigest()
        for i in range(3):
            value={'id':str(i),'source_text':text,'source_text_sha256':digest,'reason':None}
            db.execute('INSERT INTO reference VALUES (?,?,?)',(str(i),'r',json.dumps(value)))
        assert db.execute('SELECT count(*) FROM reference_body').fetchone()[0]==1
        assert all('source_text' not in json.loads(r[0]) for r in db.execute('SELECT json FROM reference_payload'))
        value['reason']='REVIEWED';db.execute('UPDATE reference SET json=? WHERE id=?',(json.dumps(value),'2'))
        assert json.loads(db.execute("SELECT json FROM reference WHERE id='2'").fetchone()[0])==value
        bad=dict(value,source_text='다른 원문')
        with pytest.raises(sqlite3.IntegrityError,match='collision'):db.execute('UPDATE reference SET json=? WHERE id=?',(json.dumps(bad),'2'))
        db.execute("DELETE FROM reference WHERE id='1'")
        assert db.execute('SELECT count(*) FROM reference').fetchone()[0]==2


def corpus(path,documents=3):
    original_source(path)
    with sqlite3.connect(path) as db:
        for i in range(documents):
            did=f'doc-{i:03}'
            db.execute('INSERT INTO document VALUES (?,?,?,?)',(did,'가상법 '+str(i),'fixture-hash','{}'))
            for n in (1,2):
                uid=f'u{n}';unit={'family':'kr_article','surface':f'제{n}조','title':'영업일','span':[0,1]}
                db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(did,uid,None,json.dumps(unit)))
                text=f'제{n}조(영업일) 영업일 영업일 Business Day 자금지원. 제{3-n}조와 제{3-n}조를 준용한다. 가상법 별표 1.'
                db.execute('INSERT INTO source_block VALUES (?,?,?,?,?,?)',(did,str(n),uid,text,'fixture-hash','{}'))
    return path


def compare_builds(a,b):
    with closing(sqlite3.connect(a/'generation/navigation/navigation.sqlite')) as x, closing(sqlite3.connect(b/'generation/navigation/navigation.sqlite')) as y:
        tables=[r[0] for r in x.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            if table in {'occurrence_keys','reference_payload','reference_body','navigation_checkpoint'}:continue
            assert logical(x,table)==logical(y,table),table
    with closing(sqlite3.connect(a/'audit/navigation/navigation.sqlite')) as x, closing(sqlite3.connect(b/'audit/navigation/navigation.sqlite')) as y:
        for table in AUDIT_TABLES:assert logical(x,table)==logical(y,table),table


@pytest.mark.parametrize('scope',['0','1'])
def test_compact_v2_full_build_exact_and_readable(tmp_path,term_glossary,monkeypatch,scope):
    monkeypatch.setenv('GENOS_REFERENCE_SCOPE_V2',scope)
    source=corpus(tmp_path/'source.sqlite');before=sha(source)
    for profile,folder in [('compact-v1','old'),('compact-v2','new')]:
        build_generation(source,term_glossary,tmp_path/folder,serving=True,storage_profile=profile,fulltext_granularity='unit')
    compare_builds(tmp_path/'old',tmp_path/'new')
    assert verify_assets(tmp_path/'new/generation')['verified']
    verify_build(tmp_path/'new')
    assert sha(source)==before
    with closing(sqlite3.connect(tmp_path/'new/generation/navigation/navigation.sqlite')) as db:
        assert not set(AUDIT_TABLES)&{r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert db.execute('SELECT count(*) FROM reference_body').fetchone()[0]<db.execute('SELECT count(*) FROM reference').fetchone()[0]
    from semantic_runtime.fulltext import open_index
    indexes=[]
    for folder in ('old','new'):
        nav=json.loads((tmp_path/folder/'generation/navigation/manifest.json').read_text())
        indexes.append(open_index(tmp_path/folder/'generation/fulltext',nav))
    with closing(indexes[0].connect()) as x,closing(indexes[1].connect()) as y:
        assert indexes[0].rank(x,['영업'])==indexes[1].rank(y,['영업'])


@pytest.mark.parametrize('interruption',['documents','references','evidence','audit'])
def test_substage_resume_is_exact(tmp_path,term_glossary,monkeypatch,interruption):
    from semantic_runtime import term_index,term_links,navigation_build
    source=corpus(tmp_path/'source.sqlite',70)
    out=tmp_path/'resumed'
    def stop(*a,**kw):raise RuntimeError('controlled interruption')
    with monkeypatch.context() as patch:
        if interruption=='documents':
            def progress(**kw):
                if kw.get('task')=='document-navigation' and kw.get('completed')==65:stop()
            patch.setattr(term_index,'_BUILD_PROGRESS',progress,raising=False)
        elif interruption=='references':
            original=rb.ReferenceWriter.insert;calls=0
            def insert(self,*a,**kw):
                nonlocal calls
                calls+=1
                if calls==205:stop()
                return original(self,*a,**kw)
            patch.setattr(rb.ReferenceWriter,'insert',insert)
        elif interruption=='evidence':patch.setattr(term_links.LinkProjector,'finish',stop)
        else:patch.setattr(navigation_build,'finish_audit',stop)
        with pytest.raises(RuntimeError,match='controlled'):
            build_generation(source,term_glossary,out,serving=True,storage_profile='compact-v2',fulltext_granularity='unit')
    partial=tmp_path/'.resumed.building/generation/navigation/navigation.sqlite'
    with closing(sqlite3.connect(partial)) as db:
        assert db.execute("SELECT count(*) FROM navigation_checkpoint WHERE stage='document'").fetchone()[0]>0
        if interruption=='references':
            assert db.execute("SELECT count(*) FROM navigation_checkpoint WHERE stage='reference-source'").fetchone()[0]>=64
    build_generation(source,term_glossary,out,serving=True,storage_profile='compact-v2',fulltext_granularity='unit')
    build_generation(source,term_glossary,tmp_path/'fresh',serving=True,storage_profile='compact-v2',fulltext_granularity='unit')
    compare_builds(tmp_path/'fresh',out);verify_build(out)


def test_shared_reference_review_apply(tmp_path,term_glossary,monkeypatch):
    import test_reference_resolution as cases
    original=cases.build_generation
    def compact(*args,**kwargs):
        return original(*args,**kwargs,storage_profile='compact-v2')
    monkeypatch.setattr(cases,'build_generation',compact)
    cases.test_prepare_review_and_apply_builds_a_new_generation(tmp_path,term_glossary)


def test_resume_refuses_changed_input(tmp_path,term_glossary,monkeypatch):
    from semantic_runtime import term_links
    source=corpus(tmp_path/'source.sqlite')
    with monkeypatch.context() as patch:
        def stop(*args,**kwargs):raise RuntimeError('interrupted')
        patch.setattr(term_links.LinkProjector,'finish',stop)
        with pytest.raises(RuntimeError):build_generation(source,term_glossary,tmp_path/'built',storage_profile='compact-v2')
    with sqlite3.connect(source) as db:db.execute("UPDATE source_block SET text=text||' changed'")
    with pytest.raises(ValueError,match='resume inputs/code changed'):
        build_generation(source,term_glossary,tmp_path/'built',storage_profile='compact-v2')


def test_process_crash_recovers_joint_audit_transaction(tmp_path,term_glossary):
    import os,subprocess,sys
    source=corpus(tmp_path/'source.sqlite',70);out=tmp_path/'crashed'
    runner=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0634/compact/runner.py'
    script=tmp_path/'crash.py'
    script.write_text('import runpy,os\nrunpy.run_path('+repr(str(runner))+')\n'
        'from semantic_runtime import term_index\nfrom lawrag.pipeline.term_generation import build_generation\n'
        'def progress(**kw):\n'
        '    if kw.get("task")=="document-navigation" and kw.get("completed")==65:os._exit(91)\n'
        'term_index._BUILD_PROGRESS=progress\n'
        'build_generation('+','.join(repr(str(p)) for p in (source,term_glossary,out))+',storage_profile="compact-v2")\n')
    result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,
                          env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==91,result.stdout+result.stderr
    build_generation(source,term_glossary,out,storage_profile='compact-v2')
    build_generation(source,term_glossary,tmp_path/'fresh',storage_profile='compact-v2')
    compare_builds(tmp_path/'fresh',out)
