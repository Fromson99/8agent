from pathlib import Path
import importlib.util,numpy as np,pytest
ROOT=Path(__file__).resolve().parents[3]
file=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0970/dense-rerank/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/dense_rerank_probe.py'
s=importlib.util.spec_from_file_location('probe',file);p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
def test_max_descendant_and_stable_article_dedup():
    rows=[{'doc_id':'a','article':1},{'doc_id':'a','article':1},{'doc_id':'b','article':2}]
    out=p.rank_articles(rows,np.array([[.9,.1],[.95,.1],[.8,.2]]),np.array([1.,0.]))
    assert len(out)==2 and out[0]['doc_id']=='a' and out[0]['cosine']==.95
def test_nonfinite_cannot_become_success():
    with pytest.raises(ValueError):p.rank_articles([{'doc_id':'a','article':1}],np.array([[np.nan]]),np.array([1.]))
def test_valid_exact_quote():
    a={'answer':'답','citations':[{'source_id':'S1','quote':'원문'}],'limitations':[]}
    assert p.validate_answer(a,[{'id':'S1','text':'실제 원문 입니다'}])==a
@pytest.mark.parametrize('citation',[{'source_id':'S2','quote':'원문'},{'source_id':'S1','quote':'없는 내용'},{'source_id':'S1','quote':''}])
def test_bad_quote_or_unknown_source_rejected(citation):
    with pytest.raises(ValueError):p.validate_answer({'answer':'답','citations':[citation],'limitations':[]},[{'id':'S1','text':'원문'}])
def test_cycle_and_nonarticle_do_not_invent_article():
    assert p.article_root({'id':0,'parent':None},{}) is None
    u={'id':0,'parent':0}
    with pytest.raises(ValueError):p.article_root(u,{'0':u})

def test_compound_coordinate_must_resolve_to_true_article_root():
    root={'id':282,'parent':None,'family':'kr_article','legal_coordinate':{'unit':'조','chain':[]}}
    child={'id':283,'parent':282,'family':'circled','legal_coordinate':{'unit':'조','chain':[{'unit':'항','n':1}]}}
    assert p.article_root(child,{'282':root,'283':child})==282
