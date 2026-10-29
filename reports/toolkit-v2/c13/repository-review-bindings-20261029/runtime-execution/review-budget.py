"""Enforce the actual review ceiling before every assessment reservation."""
import math
from decimal import Decimal


def require_room(current,initial,limits,ceiling):
    if any(not math.isfinite(float(v)) or float(v)<0 for v in (*current[:3],*initial[:3])):
        raise RuntimeError('Nonfinite review accounting; stop without dispatch')
    checks=[(current[0],initial[0],limits.max_operations,ceiling['maximum_operations']),
            (current[1],initial[1],limits.max_model_turns,ceiling['maximum_model_turns']),
            (current[2],initial[2],limits.max_elapsed_seconds,ceiling['maximum_reserved_seconds'])]
    if any(now<start or now+extra>start+maximum for now,start,extra,maximum in checks):
        raise RuntimeError('Exact review operation/turn/time ceiling would be exceeded')
    if Decimal(str(current[3]))!=Decimal(str(initial[3])) or limits.max_cash_usd!=0:
        raise RuntimeError('This review permits zero cash only')


def install(repo,connection,initial,ceiling):
    original=repo.reserve
    def reserve(plan,operation,limits,**kwargs):
        current=connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()
        require_room(current,initial,limits,ceiling)
        return original(plan,operation,limits,**kwargs)
    repo.reserve=reserve
    return original


def self_check():
    from aeep.assessment.models import AssessmentLimits
    initial=(100,20,1000.,'0.0');ceilings={'maximum_operations':10,'maximum_model_turns':6,'maximum_reserved_seconds':400}
    limits=AssessmentLimits(max_operations=1,max_model_turns=1,max_elapsed_seconds=35)
    require_room((109,25,1365.,'0.0'),initial,limits,ceilings)
    count=1
    for current in [(110,25,1365.,'0'),(109,26,1365.,'0'),(109,25,1366.,'0'),(99,25,1300.,'0'),(109,25,float('nan'),'0'),(109,25,1300.,'1')]:
        try:require_room(current,initial,limits,ceilings)
        except RuntimeError:count+=1
        else:raise AssertionError('Budget guard accepted an out-of-scope reservation')
    return count


if __name__=='__main__':print(self_check())
