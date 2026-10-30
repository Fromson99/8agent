from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
S=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1227/source-first/snapshot'
p=S/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py';s=p.read_text()
s=s.replace('from .assembly_ir import validate_originals','from .assembly_ir import validate_originals\nfrom . import recorded_fields, authoring_semantics as semantics')
s=s.replace("output_schema = obs.normalization_schema(raw, profile)","output_schema = recorded_fields.request_schema(obs.normalization_schema(raw, profile), raw)")
s=s.replace('obs.restore_normalization(proposal, raw)','recorded_fields.restore(proposal, raw, output_schema, obs.restore_normalization)')
s=s.replace("profile['prompt'] + obs.NORMALIZATION_INSTRUCTIONS, output_schema, validate,","profile['prompt'] + obs.NORMALIZATION_INSTRUCTIONS + recorded_fields.INSTRUCTIONS, output_schema, validate,")
old="""        matching = self.match(observations, kwargs['originals'])
        context = {'profile': profile['effective'], 'profile_hash': profile['profile_hash'],"""
new="""        source_schema = semantics.source_schema(profile, kwargs['originals'])
        # This independent call deliberately cannot see observations or the base.
        source_context = {'operation': 'SOURCE_ANALYSIS', 'originals': kwargs['originals'],
                          'profile_hash': profile['profile_hash']}
        analysis, source_receipt = self._job('SOURCE_ANALYSIS', source_context,
            semantics.SOURCE_PROMPT, source_schema,
            lambda p: semantics.validate_source(p, source_schema, kwargs['originals']),
            lambda: self._originals(kwargs['originals']))
        matching = self.match(observations, kwargs['originals'])
        context = {'source_analysis': analysis,
                   'profile': profile['effective'], 'profile_hash': profile['profile_hash'],"""
assert old in s;s=s.replace(old,new)
old="""        proposal, receipt = self._job('ACCUMULATE', context, acc.PROMPT, acc.accumulation_schema(profile, observations, base, kwargs['originals']),
            lambda p: acc.validate_proposal(p, profile, kwargs['originals'], observations, base),
            lambda:(self._originals(kwargs['originals']),self._observations(kwargs['observation_ids'],profile)))
        return self.save_accumulation(**kwargs, proposal=proposal, model_receipt=receipt, matching_receipt=matching)"""
new="""        output_schema = semantics.request_schema(
            acc.accumulation_schema(profile, observations, base, kwargs['originals']), analysis)
        def validate(proposal):
            canonical, _ = semantics.restore(proposal, output_schema, analysis, kwargs['originals'])
            acc.validate_proposal(canonical, profile, kwargs['originals'], observations, base)
        proposal, receipt = self._job('ACCUMULATE', context, acc.PROMPT + semantics.ACCUMULATION_PROMPT,
            output_schema, validate,
            lambda:(self._originals(kwargs['originals']),self._observations(kwargs['observation_ids'],profile)))
        canonical, assembly = semantics.restore(proposal, output_schema, analysis, kwargs['originals'])
        receipt = {**receipt, 'semantic_assembly': assembly,
                   'source_analysis': deepcopy(analysis), 'source_analysis_receipt': source_receipt}
        return self.save_accumulation(**kwargs, proposal=canonical, model_receipt=receipt, matching_receipt=matching)"""
assert old in s;s=s.replace(old,new)
s=s.replace("'instruction': '같은 입력과 의미를 유지하고 나열한 형식·참조 오류만 한 번 보완한다.'", "'instruction': ('원본 입력을 유지하고 나열한 오류를 한 번 보완한다. 원문 분석·비교의 불일치도 고치되 원래 관찰 기록은 고쳐 쓰지 않는다.'\n+                                        if stage in ('SOURCE_ANALYSIS','ACCUMULATE') else\n+                                        '같은 입력과 의미를 유지하고 나열한 형식·참조 오류만 한 번 보완한다.')")
p.write_text(s)
