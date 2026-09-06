import copy
import unittest
from map_demand_v01.joint_validation_v01 import evaluate,evaluate_growth


class JointValidationTests(unittest.TestCase):
    def setUp(self):
        self.c=dict(numeric=[dict(key='a',axis='flow_aim',kind='interval',lower=6.,upper=7.),
            dict(key='a',axis='aim_control',kind='approximate',reference=5.)],
            relations=[dict(id='order',left=dict(key='a',axis='flow_aim'),right=dict(key='a',axis='aim_control'),relation='greater')],
            qualitative=[])
    def test_missing_is_unknown_not_zero(self):
        r=evaluate({},self.c)
        self.assertTrue(all(x['status']=='UNKNOWN_MISSING_PREDICTION' for x in r['numeric']))
        self.assertEqual(r['readiness'],'NOT_ESTABLISHED')
    def test_interval_violation_and_opposite_dominance_both_count(self):
        p={'a':dict(flow_aim=4.,aim_control=8.)};old=copy.deepcopy(p)
        r=evaluate(p,self.c)
        self.assertEqual(r['known_failure_count'],2)
        self.assertEqual(p,old)
    def test_approximate_reference_never_becomes_invented_pass_band(self):
        r=evaluate({'a':dict(flow_aim=7.,aim_control=5.)},self.c)
        self.assertEqual(r['numeric'][1]['status'],'REVIEW_APPROXIMATE_REFERENCE')
        self.assertEqual(r['relations'][0]['status'],'ORDER_ONLY_MATCHES_MARGIN_UNVALIDATED')
        self.assertEqual(r['readiness'],'NOT_ESTABLISHED')
    def test_nonfinite_is_missing_and_bounds_inclusive(self):
        r=evaluate({'a':dict(flow_aim=6.,aim_control=float('nan'))},self.c)
        self.assertEqual(r['numeric'][0]['status'],'WITHIN_STATED_BOUND')
        self.assertEqual(r['numeric'][1]['status'],'UNKNOWN_MISSING_PREDICTION')

    def test_flat_length_response_is_a_failure_even_with_roundoff(self):
        rows=[dict(distance_px=60.,interval_ms=100.,movement_count=n,turn_deg=45.,cs=4.,
                   flow_aim=value,aim_control=4.) for n,value in ((16,4.),(32,4.+1e-12),(64,3.9))]
        original=copy.deepcopy(rows)
        result=evaluate_growth(rows)
        self.assertEqual(result['known_failure_count'],2)
        self.assertEqual(result['readiness'],'REJECTED_REQUIRED_GROWTH')
        self.assertEqual(rows,original)

    def test_observed_cs_increase_does_not_certify_human_gain_or_missing_cases(self):
        rows=[dict(distance_px=60.,interval_ms=100.,movement_count=64,turn_deg=45.,cs=cs,
                   flow_aim=4.,aim_control=value) for cs,value in ((3,3.),(4,4.),(6,None))]
        result=evaluate_growth(rows)
        self.assertEqual(result['checks'][0]['status'],'INCREASE_OBSERVED_MAGNITUDE_UNVALIDATED')
        self.assertEqual(result['checks'][1]['status'],'UNKNOWN_MISSING_PREDICTION')
        self.assertEqual(result['readiness'],'NOT_ESTABLISHED')

    def test_geometry_changes_are_not_mislabeled_as_length_effects(self):
        rows=[dict(distance_px=d,interval_ms=100.,movement_count=n,turn_deg=45.,cs=4.,
                   flow_aim=v,aim_control=4.) for d,n,v in ((24.,16,1.),(100.,64,7.))]
        self.assertEqual(evaluate_growth(rows)['checks'],[])


if __name__=='__main__':unittest.main()
