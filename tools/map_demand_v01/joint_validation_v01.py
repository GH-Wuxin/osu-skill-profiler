"""Read-only cross-map/cross-axis constraint evaluation, never a scorer.

Approximate human points are reported with residuals, not silently expanded
into arbitrary acceptance bands. Unlabelled cases cannot establish validity.
"""
import math
from collections import defaultdict


def _value(predictions, key, axis):
    value=predictions.get(key,{}).get(axis)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):return None
    return float(value)


def evaluate(predictions, constraints):
    numeric=[]
    for c in constraints['numeric']:
        value=_value(predictions,c['key'],c['axis'])
        item={**c,'observed':value}
        if value is None:item.update(status='UNKNOWN_MISSING_PREDICTION')
        elif c['kind']=='approximate':item.update(status='REVIEW_APPROXIMATE_REFERENCE',residual=value-c['reference'])
        elif c['kind'] in ('upper','interval'):
            lo=c.get('lower',-math.inf);hi=c['upper']
            violation=max(lo-value,value-hi,0.)
            item.update(status='WITHIN_STATED_BOUND' if violation==0 else 'VIOLATES_STATED_BOUND',violation=violation)
        else:raise ValueError('Unsupported human constraint kind')
        numeric.append(item)
    relations=[]
    for c in constraints['relations']:
        if c['relation']!='greater':raise ValueError('Unsupported relation')
        left=_value(predictions,**c['left']);right=_value(predictions,**c['right'])
        gap=None if left is None or right is None else left-right
        relations.append({**c,'left_value':left,'right_value':right,'gap':gap,
            'status':'UNKNOWN_MISSING_PREDICTION' if gap is None else
                'ORDER_ONLY_MATCHES_MARGIN_UNVALIDATED' if gap>0 else 'VIOLATES_STATED_ORDER'})
    failures=sum(item['status'].startswith('VIOLATES') for item in [*numeric,*relations])
    return dict(numeric=numeric,relations=relations,qualitative_pending=constraints['qualitative'],
        known_failure_count=failures,readiness='REJECTED_KNOWN_CONSTRAINTS' if failures else 'NOT_ESTABLISHED',
        cross_band_human_validation='NOT_ESTABLISHED',
        approximate_points_are_pass_fail=False,unlabelled_predictions_are_validation=False)


def evaluate_growth(stimuli):
    """Check required responses without inventing human-sized score margins.

    A flat length response must remain a visible failure even when all named
    map bounds match. Numerical tolerance distinguishes roundoff from change;
    an observed increase does not establish its perceptual size or accuracy.
    """
    dimensions=('distance_px','interval_ms','movement_count','turn_deg','cs')
    checks=[]
    for axis,parameter in (('flow_aim','movement_count'),('aim_control','cs')):
        fixed=tuple(key for key in dimensions if key!=parameter)
        groups=defaultdict(list)
        for row in stimuli:groups[tuple(row[key] for key in fixed)].append(row)
        for conditions,rows in sorted(groups.items()):
            ordered=sorted(rows,key=lambda row:row[parameter])
            for first,second in zip(ordered,ordered[1:]):
                if first[parameter]==second[parameter]:raise ValueError('Duplicate controlled stimulus')
                a=_value({0:first},0,axis);b=_value({0:second},0,axis)
                change=None if a is None or b is None else b-a
                status='UNKNOWN_MISSING_PREDICTION'
                if change is not None:
                    tolerance=1e-9*max(1.,abs(a),abs(b))
                    status='INCREASE_OBSERVED_MAGNITUDE_UNVALIDATED' if change>tolerance else 'VIOLATES_REQUIRED_GROWTH'
                checks.append(dict(axis=axis,parameter=parameter,fixed=dict(zip(fixed,conditions)),
                    from_parameter=first[parameter],to_parameter=second[parameter],
                    from_value=a,to_value=b,change=change,status=status))
    failures=sum(row['status'].startswith('VIOLATES') for row in checks)
    return dict(checks=checks,known_failure_count=failures,
        readiness='REJECTED_REQUIRED_GROWTH' if failures else 'NOT_ESTABLISHED',
        response_magnitude_validation='NOT_ESTABLISHED',numerical_tolerance_is_human_margin=False)
