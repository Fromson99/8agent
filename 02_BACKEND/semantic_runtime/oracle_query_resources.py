"""Open the existing source tools against one Oracle request pin."""
from contextlib import contextmanager


@contextmanager
def resources(agent,scope):
    from .oracle_query_glossary import Glossary
    from .oracle_query_matcher import Matcher
    from .oracle_query_fulltext import UnitIndex
    from .oracle_query_store import Store
    from .folder_navigation import load_origin_projection
    from .document_aliases import load as load_aliases
    index=agent.get_index();tools=index.tools(scope)
    store=Store(tools.request)
    glossary=None
    try:
        glossary=Glossary(tools.request,agent.config)
        root=agent.pipeline.contracts.root
        aliases=load_aliases(root,agent.config,store)
        projection=load_origin_projection(root,agent.config,store)
        matcher=Matcher(store,tools,glossary,document_aliases=aliases,origin_projection=projection)
        matcher.fulltext=matcher.unit_fulltext=UnitIndex(tools.request)
        matcher.fulltext_db=matcher.unit_fulltext_db=matcher.fulltext
        from .initial_vector import Retriever,mode
        if mode()!='keyword':matcher.initial_vector=Retriever(tools.request)
        yield index,tools,glossary,matcher
        store.check_unchanged();glossary.check_unchanged()
    finally:
        tools.db.close();store.close()
        if glossary is not None: glossary.close()
