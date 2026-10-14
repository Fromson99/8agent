from pathlib import Path
import ast
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0772/provider-display/snapshot';p=S/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
s=p.read_text();assert 'source-provider-20261013-r2' not in s
s=s.replace('source-cards-20261013-r1','source-provider-20261013-r2')
s=s.replace('        self.source_read_rows = []\n','        self.source_candidate_rows = []\n        self.source_candidate_context = None\n        self.source_candidate_label = ""\n        self.source_read_rows = []\n',1)
start=s.index('    def _card_rationale(');end=s.index('    async def _append_source_card',start)
s=s[:start]+'''    @staticmethod
    def _source_label(row):
        # Korean headwords verified in the selected glossary. Provenance is
        # frozen in ADR-0772/provider-label-evidence.json, not inferred by LLM.
        providers = {'krx': '한국거래소', 'kofia': '한국금융투자협회',
                     'law': '법제처', 'moleg': '법제처'}
        parts = [p.strip() for p in re.split(r"\\s*>\\s*" if ">" in row else r"/", row)]
        if len(parts) < 2 or parts[0].lower() not in {'external', 'internal'}:
            return None, row
        if parts[0].lower() == 'internal':
            return '내부규정', parts[-1] or '문서명 미확인'
        # external / provider / title, or external / team / provider / title.
        offset = 2 if len(parts) >= 4 and parts[1].lower() not in providers else 1
        provider = parts[offset].lower() if len(parts) > offset + 1 else ''
        title = ' / '.join(parts[offset+1:]) if provider else parts[-1]
        return '외부법률 / ' + providers.get(provider, '기타 출처'), title or '문서명 미확인'

    def _card_rationale(self, label, details):
        # Markdown list items create real line breaks in Visible Reasoner.
        groups = {}
        plain = []
        for row in details:
            heading, title = self._source_label(row)
            if heading:
                groups.setdefault(heading, []).append(title)
            else:
                plain.append(row)
        blocks = [self._plain(label)]
        if plain:
            blocks.append('\\n\\n'.join('- ' + self._plain(row) for row in plain))
        for heading, titles in groups.items():
            blocks.append(self._plain(heading) + '\\n\\n' + '\\n'.join(
                str(i) + '. ' + self._plain(title) for i, title in enumerate(titles, 1)))
        return '\\n\\n'.join(blocks)

    async def _flush_source_candidates(self):
        if not self.source_candidate_rows:
            return
        rows, label = self.source_candidate_rows, self.source_candidate_label
        self.source_candidate_rows = []
        self.source_candidate_context = None
        self.source_candidate_label = ''
        await self._append_source_card(label, rows)

'''+s[end:]
s=s.replace('    async def _flush_source_reads(self):\n','    async def _flush_source_reads(self):\n        await self._flush_source_candidates()\n',1)
start=s.index('    async def _source_progress(');end=s.index('    @staticmethod\n    def _plain',start)
s=s[:start]+'''    async def _source_progress(self, event):
        """One card per contiguous result/read group, never an LLM-call claim."""
        if not isinstance(event, dict) or event.get('schema_version') != 'rag-progress-v1':
            return False
        if event.get('kind') == 'heartbeat':
            return True
        basis = event.get('basis') or {}
        rows = event.get('details')
        rows = [" ".join(row.split()) for row in rows
                if isinstance(row, str) and row.strip() and len(row) <= 300] if isinstance(rows, list) else []
        if (event.get('kind') == 'reading' and basis.get('kind') == 'UNIT_READ_STARTED'
                and basis.get('detail_mode') == 'activity' and rows):
            await self._flush_source_candidates()
            context = (event.get('request_id'), event.get('run_id'))
            if self.source_read_rows and context != self.source_read_context:
                await self._flush_source_reads()
            self.source_read_context = context
            for row in rows:
                if row not in self.source_read_rows:
                    self.source_read_rows.append(row)
            return True
        if event.get('kind') == 'candidate' and basis.get('kind') in {
                'LAW_FULLTEXT_DIRECTORY', 'SOURCE_FULLTEXT_RESULTS'}:
            label = event.get('label')
            if isinstance(label, str) and 0 < len(label) <= 140:
                if self.source_read_rows:
                    await self._flush_source_reads()
                context = (event.get('request_id'), event.get('run_id'), basis.get('kind'),
                           basis.get('journal_seq'), label)
                if context != self.source_candidate_context:
                    await self._flush_source_candidates()
                if not rows:
                    await self._flush_source_candidates()
                    await self._append_source_card(label, [])
                    return True
                self.source_candidate_context, self.source_candidate_label = context, label
                for row in rows:
                    if row not in self.source_candidate_rows:
                        self.source_candidate_rows.append(row)
                return True
        await self._flush_source_reads()
        return False

'''+s[end:]
s=s.replace("    basis = event.get('basis') or {}\n    if basis.get('detail_mode') == 'full_error':", "    basis = event.get('basis') or {}\n    if not isinstance(basis, dict):\n        return None\n    if basis.get('detail_mode') in {'full_error', 'error', 'diagnostic'}:")
compile(s,str(p),'exec');p.write_text(s)
print('Candidate workflow updated; backend/search/model untouched')
