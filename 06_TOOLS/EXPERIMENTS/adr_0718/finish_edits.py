from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=L/name;s=p.read_text();assert old in s,(name,old[:60]);p.write_text(s.replace(old,new))
edit('law_navigation.py',"result['completion_contract']=cc.CONTRACT","result['completion_contract']=cc.version(self.s.profile)")
edit('law_navigation.py',"'no_progress','stop_reason','progress_gap_signature')", "'no_progress','stop_reason','progress_gap_signature','request_progress','investigation_epoch','decision_retry_history')")
edit('request_repair.py','当前原文已覆盖所选范围','현재 제시한 원문이 선택 범위를 이미 포함합니다')
edit('request_entry.py',"        intent=intent_schema(intent)","        intent=intent_schema(intent)\n        del intent['properties']['background_quotes']\n        intent['required'].remove('background_quotes')")
edit('request_entry.py',"            if intent['background_quotes']!=quotes:raise ProposalError('entry background projections disagree')", "            intent['background_quotes']=deepcopy(quotes)")
edit('request_entry.py',"SCOPE_PROMPT+' background_quotes는 context_quotes와 같은 목록이다.'", "SCOPE_PROMPT+' 이번 통합 입력에서는 배경을 context_quotes에만 작성한다.'")
edit('completion_v5.py',"    errors=cc.assessment_errors(legacy,cc.assessment_schema(issues,[],options,contract=cc.CONTRACT,facts=facts),issues)\n", "")
# An explicit source index with exact span IDs avoids sending the same body twice.
edit('completion_execution.py',"        feedback = None", "        model_sources=sources\n        if modern:\n            context,model_sources=v5.project_assessment(context,sources,options)\n            self.s.work.event('ASSESSMENT_SOURCE_PROJECTION',{'sources':len(sources),'spans':len(options),\n                'source_hash':digest(sources),'evidence_hash':digest(options),'contract':contract})\n        feedback = None")
edit('completion_execution.py',"'issues': self.issues, 'sources': sources, 'evidence_options': options", "'issues': self.issues, 'sources': model_sources, 'evidence_options': options")
edit('unified_rag.py',"'completion_contracts.py','completion_execution.py'", "'completion_contracts.py','completion_execution.py','completion_v5.py','request_repair.py'")
edit('unified_runtime.py',"            text_integrity='ACCEPTED_CLAIMS_RENDERED',citation_integrity='ORIGINAL_SPANS')", "            text_integrity='ACCEPTED_CLAIMS_RENDERED',citation_integrity='ORIGINAL_SPANS')\n        assessment=parts['ASSESS']['payload']\n        meta['accepted_outcome']={'schema_version':'accepted-outcome-v1',\n            'basis':'committed-ASSESS-and-verified-COMPOSE','assessment_hash':digest(assessment),\n            'answer_coverage':assessment['answer_coverage'],'disposition':assessment['disposition'],\n            'stop_reason':assessment.get('stop_reason'),'semantic_quality_certified':False}")
# Sampling is request-window process RSS, never attributed exclusive request memory.
p=C/'02_BACKEND/semantic_runtime/execution_metrics.py';s=p.read_text();s=s.replace('import time\n','import time\nfrom pathlib import Path\n')
s=s.replace("class Metrics:",'''def resident_bytes():
    try:
        pages=int(Path('/proc/self/statm').read_text().split()[1])
        import os
        return pages*os.sysconf('SC_PAGE_SIZE')
    except (OSError,ValueError,IndexError):return None

class Metrics:''')
s=s.replace('        self.lock = threading.Lock()', '''        self.lock = threading.Lock()
        self.rss_start=resident_bytes();self.rss_peak=self.rss_start;self.rss_last=self.rss_start
        self.rss_samples=1 if self.rss_start is not None else 0
        self.stop_sampling=threading.Event();self.sampler=None

    def sample_memory(self):
        value=resident_bytes()
        if value is None:return
        with self.lock:
            self.rss_peak=max(self.rss_peak or 0,value);self.rss_last=value;self.rss_samples+=1

    def start_sampling(self):
        def sample():
            while not self.stop_sampling.wait(0.1):self.sample_memory()
        self.sampler=threading.Thread(target=sample,name='rag-rss-sample',daemon=True)
        self.sampler.start()

    def close_sampling(self):
        self.stop_sampling.set()
        if self.sampler:self.sampler.join(timeout=1)
        self.sample_memory()''')
s=s.replace("        with self.lock: calls = [dict(row) for row in self.calls]", "        self.sample_memory()\n        with self.lock:\n            calls = [dict(row) for row in self.calls]\n            memory={'basis':'process-rss-sampled-during-request','interval_ms':100,\n                'start_bytes':self.rss_start,'peak_observed_bytes':self.rss_peak,'latest_bytes':self.rss_last,\n                'samples':self.rss_samples,'exclusive_request_allocation':False}")
s=s.replace("'llm_calls': len(calls), 'calls': calls,", "'llm_calls': len(calls), 'calls': calls, 'memory':memory,")
s=s.replace("    metrics = Metrics(); token = _CURRENT.set(metrics)","    metrics = Metrics(); token = _CURRENT.set(metrics)\n    metrics.start_sampling()")
s=s.replace("        _CURRENT.reset(token)","        metrics.close_sampling()\n        _CURRENT.reset(token)");p.write_text(s)
print('completion, source projection, accepted outcome and sampling connected')
