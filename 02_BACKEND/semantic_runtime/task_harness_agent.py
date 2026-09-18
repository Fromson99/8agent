"""Explicit candidate adapter for the existing retrieve/select/assemble/answer path."""
from pathlib import Path

from .contracts import sha
from .navigation_agent import ServingNavigationAgent, glossary_assets
from .navigation_match import ReverseMatcher
from .task_harness import TaskSession
from .task_policy import load_bound_definition


class ServingTaskHarnessAgent(ServingNavigationAgent):
    def retrieve(self, plan, use_llm=True):
        binding = self.config['task_policy']
        definition = load_bound_definition(self.pipeline.store.path, binding)
        if self.config.get('learning', {}).get('bundle') is not None:
            raise ValueError('task harness cannot execute navigation recipes')
        index = self.get_index()
        tools = index.tools(plan['scope']['document_version_ids'])
        glossary = None
        try:
            glossary = glossary_assets(self.pipeline.store.path, self.config)
            matcher = ReverseMatcher(self.pipeline.store.db, tools, glossary)
            provenance = {'query_id': plan['id'], 'generation_id': plan['generation_id'],
                          'source_store_sha256': self.pipeline.store.manifest['store_sha256'],
                          'index_manifest': index.manifest,
                          'glossary_binding': self.pipeline.store.manifest.get('glossary') or self.config['glossary'],
                          'controller_sha256': sha(Path(__file__).with_name('task_harness.py')),
                          'policy_loader_sha256': sha(Path(__file__).with_name('task_policy.py'))}
            journal = getattr(self.pipeline, 'task_harness_journal', None)
            if use_llm and journal is None:
                raise ValueError('task harness requires a local execution journal')
            session = TaskSession(matcher, tools, glossary, plan['question'],
                                  plan['scope']['document_version_ids'], definition, binding,
                                  provenance, self.config.get('limits'), journal)
            if use_llm:
                state = session.run(self.pipeline.provider)
            else:
                state = session.result()
                state.update(status='METADATA_ONLY', initial=session.initial)
            selected = sorted({j['source_id'] for j in state['adopted']})
            state.update(use_llm=use_llm, selected_ids=selected, final={
                'findings': [{'text': j['claim'], 'source_ids': [j['source_id']]} for j in state['adopted']],
                'evidence_ids': selected,
                'open_questions': [{'kind': 'EVIDENCE', 'text': x} for x in state['stop']['unresolved']],
                'question_for_user': state['question_for_user'], 'next_action': state['status']})
            state['matched_question_spans'] = [span for kind in ('terms', 'structures')
                                               for row in session.seed[kind] for span in row['question_spans']]
            candidates = [{**tools.sources[sid], 'ancestors': [], 'routes': ['task_harness'], 'score': 0}
                          for sid in state['read_source_ids']]
            glossary.check_unchanged()
            return {'candidates': candidates, 'routes': {'task_harness': len(candidates)},
                    'vector_status': 'NOT_USED', 'generation_id': plan['generation_id'], 'term_agent': state}
        finally:
            tools.db.close()
            if glossary is not None:
                glossary.close()
