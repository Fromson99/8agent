"""V4 journal uses immutable versioned selections and the existing atomic outbox."""
from .relations_repository import RelationsRepository
from ..contracts import digest
class TiersRepository(RelationsRepository):
    VERSION=4
    DDL='journal-v4.sql'
    def dependency_hash(self):
        return digest({'v3':super().dependency_hash(),'selections':self.heads('source_selection')})

    def save_view(self,phase,body,evidence_ids):
        from .repository import encoded
        from .errors import ContractError
        for fragment in body.get('relation_details',[]):
            raw=encoded(self.notice(fragment['relation_id']))
            if (fragment['detail_hash']!=self.notice(fragment['relation_id'])['notice_hash'] or
                fragment['total_chars']!=len(raw) or
                raw[fragment['start_cp']:fragment['end_cp']]!=fragment['fragment']):
                raise ContractError('relation detail fragment mismatch')
        with self.transaction():
            view=super().save_view(phase,body,evidence_ids)
            for f in body.get('relation_details',[]):
                self.db.execute('INSERT OR IGNORE INTO item_presentation VALUES(?,?,?,?)',
                    (view['view_id'],'relation_fragment',f['relation_id']+':'+str(f['start_cp']),digest(f)))
            return view
