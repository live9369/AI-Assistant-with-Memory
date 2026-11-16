"""Rules application service."""
import json
import math
from digital_life.domain.contracts import utc,identifier,dumps,sha,probability,text,ContractError,Conflict,Forbidden

class Rules:
    """Bounded three-valued AST interpreter. None means unknown."""
    def evaluate(self,expression,variables,depth=0):
        if depth>16: raise ContractError('rule nesting limit')
        if not isinstance(expression,dict): return expression
        if 'var' in expression: return variables.get(expression['var'])
        op=expression.get('op')
        if op=='literal': return expression.get('value')
        if op in ('and','or'):
            values=[self.evaluate(v,variables,depth+1) for v in expression.get('args',[])]
            if len(values)>64: raise ContractError('rule width limit')
            if op=='and': return False if False in values else None if None in values else all(values)
            return True if True in values else None if None in values else any(values)
        if op=='not':
            value=self.evaluate(expression['arg'],variables,depth+1); return None if value is None else not value
        a=self.evaluate(expression.get('left'),variables,depth+1); b=self.evaluate(expression.get('right'),variables,depth+1)
        if a is None or b is None: return None
        operations={'eq':lambda:a==b,'ne':lambda:a!=b,'lt':lambda:a<b,'le':lambda:a<=b,'gt':lambda:a>b,'ge':lambda:a>=b,'in':lambda:a in b}
        if op not in operations: raise ContractError('unsupported rule operator')
        try: return operations[op]()
        except TypeError: return None

