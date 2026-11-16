"""States application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class States:
    def __init__(self,store): self.s=store
    def observe(self,name,value,unit,evidence,ttl=60):
        from digital_life.application.services.goals import Goals
        if not math.isfinite(value): raise ContractError('nonfinite state')
        with self.s.tx():
            found=self.s.db.execute('SELECT id FROM state_definitions WHERE instance_id=? AND name=?',(self.s.instance_id,name)).fetchone()
            definition=found[0] if found else self.s.insert('state_definitions',name=name,unit=unit,direction='higher',measurement_kind='observed',ttl=ttl,range_rule=Goals(self.s).rule())
            return self.s.insert('state_observations',definition_id=definition,value=value,observed_at=utc(),source_ref=evidence,quality='valid')
    def snapshot(self,names=None):
        output={}
        parameters=[self.s.instance_id]
        sql='SELECT o.* FROM state_definitions d JOIN state_observations o ON o.rowid=(SELECT n.rowid FROM state_observations n WHERE n.instance_id=d.instance_id AND n.definition_id=d.id ORDER BY n.observed_at DESC,n.rowid DESC LIMIT 1) WHERE d.instance_id=? ORDER BY o.observed_at,o.rowid'
        if names is not None:
            names=list(names)
            if not names:return {}
            sql=sql.replace(' ORDER BY o.observed_at,o.rowid',' AND d.name IN ('+','.join('?' for _ in names)+') ORDER BY o.observed_at,o.rowid');parameters.extend(names)
        for row in self.s.db.execute(sql,parameters):
            definition=self.s.row('state_definitions',row['definition_id'])
            from datetime import datetime,timedelta
            expires=(datetime.fromisoformat(row['observed_at'].replace('Z','+00:00'))+timedelta(seconds=definition['ttl'])).isoformat().replace('+00:00','Z')
            output[definition['name']]={'value':row['value'],'fresh':expires>utc() and row['quality']=='valid','ref':row['id'],'observed_at':row['observed_at'],'expires_at':expires,'source_ref':row['source_ref'],'unit':definition['unit']}
        return output

