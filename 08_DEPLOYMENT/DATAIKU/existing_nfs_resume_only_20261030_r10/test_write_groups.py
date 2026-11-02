import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import sys
import zipfile

import pytest

HERE=Path(__file__).resolve().parent
CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from lawrag.pipeline import oracle_deferred_import as d
from semantic_runtime import oracle_query_catalog as q


def frames():
    for asset,size in [('a',53),('b',1237),('c',4)]:
        for i in range(0,size,20):
            yield asset,[q.record('test.kind',{'i':j,'asset':asset},key=[asset,j]) for j in range(i,min(i+20,size))]


@pytest.mark.parametrize('after',[0,1,2,3,12,25,66])
def test_groups_preserve_exact_legacy_cursor_and_rows(after):
    original=list(frames())
    with patch.object(d,'batches',side_effect=lambda *a:iter(original)):
        groups=list(d.write_groups(None,None,None,after=after))
    previous=after
    for asset,rows,through in groups:
        assert len(rows)<=500
        assert rows==[r for a,b in original[previous:through] for r in b]
        assert all(a==asset for a,b in original[previous:through])
        previous=through
    assert [r for a,b,n in groups for r in b]==[r for a,b in original[after:] for r in b]
    assert previous==len(original)


def test_lost_ack_replays_same_whole_group_then_advances_cursor():
    original=list(frames())
    with patch.object(d,'batches',side_effect=lambda *a:iter(original)):
        group=list(d.write_groups(None,None,None,after=3))[0]
        # Simulated failed ACK leaves the old cursor at3, including unknown commit.
        replay=list(d.write_groups(None,None,None,after=3))[0]
        assert replay==group
        after_ack=list(d.write_groups(None,None,None,after=group[2]))
    assert [r for a,b,n in after_ack for r in b]==[r for a,b in original[group[2]:] for r in b]


def test_combined_byte_bound_kept():
    records=[q.record('large',{'body':'a'*1900000},key=i) for i in range(4)]
    original=[('a',records[:2]),('a',records[2:])]
    with patch.object(d,'batches',side_effect=lambda *a:iter(original)):
        groups=list(d.write_groups(None,None,None,after=0))
    assert [len(x[1]) for x in groups]==[2,2]
    assert [x[2] for x in groups]==[1,2]


@pytest.mark.parametrize('after',[-1,True,999])
def test_invalid_cursor_rejected(after):
    with patch.object(d,'batches',side_effect=lambda *a:frames()):
        with pytest.raises(d.io.DPError,match='CURSOR'):list(d.write_groups(None,None,None,after=after))


@pytest.mark.parametrize('executor',[d.R8_DESCRIPTOR_EXECUTOR,d.R9_DESCRIPTOR_EXECUTOR])
def test_completed_r8_descriptor_reused_without_describe(tmp_path,executor):
    original=d.io.file_sha
    result=({}, {'x':'sha'}, {'test':{'rows':1,'chain':'same'}})
    with patch.object(d.query,'describe',return_value=result) as describe:
        with patch.object(d.io,'file_sha',side_effect=lambda p:executor if str(p)==d.__file__ else original(p)):
            first=d.prepared_descriptor(tmp_path,{'id':'same'},{'x':'sha'},tmp_path)
        assert d.prepared_descriptor(tmp_path,{'id':'same'},{'x':'sha'},tmp_path)==first
        assert describe.call_count==1


@pytest.mark.parametrize('size',[20,100,500])
def test_selectable_write_size_keeps_cursor_meaning(size):
    original=list(frames())
    with patch.object(d,'batches',side_effect=lambda *a:iter(original)):
        groups=list(d.write_groups(None,None,None,after=2,max_rows=size))
    assert all(len(b)<=size for _,b,_ in groups)
    assert [r for _,b,_ in groups for r in b]==[r for _,b in original[2:] for r in b]


def test_publisher_and_projection_functions_unchanged_from_r8():
    import ast
    with zipfile.ZipFile(HERE.parent/'existing_nfs_progress_20261030_r8/DATAIKU_EXISTING_NFS_CLIENT_20261030_R8.zip') as z:
        for name in ('oracle_query_publish.py','oracle_query_package.py','oracle_query_navigation_publish.py','oracle_full_package.py','oracle_migration.py'):
            rel='client/02_BACKEND/lawrag/pipeline/'+name
            assert z.read(rel)==(CODE/rel).read_bytes()
        rel='client/02_BACKEND/semantic_runtime/oracle_query_catalog.py'
        old,new=[ast.parse(t) for t in (z.read(rel),(CODE/rel).read_bytes())]
        def projection(tree):
            return {n.name:ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name!='insert_records'}
        assert projection(old)==projection(new)
