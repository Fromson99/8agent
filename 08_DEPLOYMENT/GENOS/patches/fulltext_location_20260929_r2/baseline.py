class RelationsTools:
    def search(self,args,offset):
        self._search_stage='execute'
        if args['mode']!='fulltext': return super().search(args,offset)
        from ..fulltext import question_terms, thread_snapshot, thread_delta, DIAGNOSTIC_REVISION
        self._search_stage='fulltext_tool.tokenize'
        with obs.step(search_log,'fulltext_tool.tokenize'):
            terms=question_terms(args['query'])
        self._search_stage='fulltext_tool.scope'
        with obs.step(search_log,'fulltext_tool.scope'):
            docs,bounds=self.docs_bounds(args['target'])
            allowed=set(self.sources_in(args['target']))
        self._search_stage='fulltext_tool.rank'
        with obs.step(search_log,'fulltext_tool.rank',term_count=len(terms),allowed_count=len(allowed)):
            db=self.matcher.fulltext_db
            # Slow NFS queries share the whole request budget. Do not abort a
            # valid FTS query after an independent 20-second local timer.
            db.set_progress_handler(lambda:int(time.monotonic()>=self.context.deadline),1000)
            ids=self.matcher.fulltext.rank(db,terms,allowed)
        self._search_stage='fulltext_tool.materialize'
        with obs.step(search_log,'fulltext_tool.location_mapping',result_count=len(ids)):
            measure=getattr(self.tools.sources,'measure_loads',None)
            with (measure() if measure else nullcontext(None)) as loads:
                before=thread_snapshot();locations={};completed=False;bounds_tokenize_ms=0.0
                route_handle_ms=0.0
                try:
                    t=time.perf_counter()
                    route=self.handle('L',{'kind':'search','query':args['query'],'target':args['target'],'mode':'fulltext'})
                    route_handle_ms=(time.perf_counter()-t)*1000
                    for sid in ids:
                        source=self.tools.sources[sid]
                        if bounds:
                            text=' '.join(b['text'] for b in source['blocks'] if bounds[0]<=int(b['block_id'])<bounds[1])
                            t=time.perf_counter()
                            try:matched=bool(set(terms).intersection(question_terms(text)))
                            finally:bounds_tokenize_ms+=(time.perf_counter()-t)*1000
                            if not matched: continue
                            n=self.resolve(args['target']);key=(n['document_id'],n['unit_id'],None)
                        else: key=(source['document_id'],source.get('unit_id'),sid)
                        locations[key]=None
                    completed=True
                finally:
                    obs.event(search_log,'fulltext.location.timings',
                              diagnostic_revision=DIAGNOSTIC_REVISION,
                              mapping_status='completed' if completed else 'failed',
                              result_count=len(ids),location_count=len(locations),bounds_enabled=bool(bounds),
                              route_handle_ms=round(route_handle_ms,3),bounds_tokenize_ms=round(bounds_tokenize_ms,3),
                              **thread_delta(before,thread_snapshot()),
                              **{k:round(v,3) if isinstance(v,float) else v for k,v in (loads or {}).items()})
        keys,nxt=self.page(list(locations),offset)
        with obs.step(search_log,'fulltext_tool.page_preview',result_count=len(keys)):
            # Previews, routes and candidate handles are materialized only for the returned page.
            items=[self.node_card(did,uid,source_id=sid,route=route) for did,uid,sid in keys]
        return items,nxt,[],{'search_receipt':{'mode':'fulltext','query':args['query'],
            'query_terms':terms,'searched_target':args['target'],'document_ids':docs,'bounds':bounds,
            'total_status':'exact','total':len(locations),'tokenizer':self.matcher.fulltext.manifest['tokenizer'],
            'ranking':self.matcher.fulltext.manifest['ranking']}}
