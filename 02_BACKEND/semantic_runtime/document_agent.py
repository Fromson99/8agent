"""Request-local serving adapter for document tools and reviewed multi-source answers."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from .document_navigation import MappedAgent, EntityRegistry
from .folder_navigation import FolderNavigator, load_origin_projection
from .multi_entry_navigation import bind_structure
from .navigation_agent import ServingNavigationAgent, glossary_assets
from .navigation_match import ReverseMatcher

IMPLEMENTATION = 'document-navigation-v1'


class ServingDocumentAgent(ServingNavigationAgent):
    @contextmanager
    def resources(self, scope):
        index = self.get_index()
        tools = index.tools(scope)
        glossary = None
        try:
            glossary = glossary_assets(self.pipeline.store.path, self.config)
            projection = load_origin_projection(self.pipeline.contracts.root, self.config,
                                                self.pipeline.store)
            manifest = self.pipeline.store.manifest
            cache_key = (manifest['generation_id'], manifest['store_sha256'],
                         glossary.binding['manifest_sha256'], glossary.binding['dictionary_sha256'])
            matcher = bind_structure(ReverseMatcher(self.pipeline.store.db, tools, glossary, cache_key=cache_key),
                                     self.pipeline.store, projection)
            matcher.navigation_store = self.pipeline.store
            yield index, tools, glossary, matcher
            glossary.check_unchanged()
        finally:
            tools.db.close()
            if glossary is not None:
                glossary.close()

    def retrieve(self, plan, use_llm=True):
        scope = plan['scope']['document_version_ids']
        with self.resources(scope) as (index, tools, glossary, matcher):
            # The current HTTP contract has no authenticated user/session identity.
            # Keep interpretation proposals inside this request; never share aliases.
            with TemporaryDirectory(prefix='rag-document-request-') as folder:
                agent = MappedAgent(self.pipeline, glossary, index, matcher,
                                    self.config.get('limits'),
                                    ledger=Path(folder)/'mappings.sqlite', actor=plan['id'],
                                    mapping_persistence='REQUEST_ONLY')
                agent.navigator = FolderNavigator(matcher, self.pipeline.store)
                if use_llm:
                    result = agent.retrieve(plan, True)
                else:
                    registry = EntityRegistry(matcher, scope, plan['question'], [])
                    data = {'keyword_types': registry.matches(plan['question']),
                            'scope_menu': registry.menu(), 'content_read': False}
                    result = agent.local_result(plan, data,
                        '모델 미사용: 등록된 문서·폴더·용어 시작점입니다. 문서 목록과 원문 조회 API를 사용할 수 있습니다.',
                        'METADATA_ONLY', {})
                    result['term_agent'].update(status='METADATA_ONLY', use_llm=False)
                result['term_agent'].update(implementation=IMPLEMENTATION,
                    mapping_persistence='REQUEST_ONLY', quality_certified=False)
                return result
