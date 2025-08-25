from collections import defaultdict

import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class LandmarkPredicatesOrderingSMT(DimensionConstructorSMT):
    
    def __init__(self, name, encoder, additional_information):
        self.landmark_predciates_vars = []
        self.dummy_landmark_variable = z3.Bool(f'dummy-{name}-variable', ctx=encoder.ctx)
        self.dummy_landmark_expression = self.dummy_landmark_variable == z3.BoolVal(False, ctx=encoder.ctx)
        super().__init__(name, encoder, additional_information)

    def __encode__(self, encoder):
        """!
        This function should return the encoding of the dimension.
        """
        landmark_vars_dict = self.additional_information.get('landmark_vars_dict', [])
        assert len(landmark_vars_dict) > 0, 'LandmarkPredicatesOrderingSMT requires the landmark_vars_list to be provided in the additional_information.'
        _landmark_z3_vars = []
        for _, landmark_vars_list in landmark_vars_dict.items():
            landmark_name = str(landmark_vars_list[0])[:str(landmark_vars_list[0]).rfind('_')]
            landmark_z3_var = z3.Int(f'{self.name}-{landmark_name}', ctx=encoder.ctx)
            _landmark_z3_vars.append(landmark_z3_var)
            for idx, predicate in enumerate(landmark_vars_list):
                expr  = [predicate] + [z3.Not(predicate, ctx=encoder.ctx) for predicate in landmark_vars_list[:idx]]
                self.encodings.append(z3.And(expr) == (landmark_z3_var == z3.IntVal(idx+1, ctx=encoder.ctx)))
            self.encodings.append(z3.And([z3.Not(predicate, ctx=encoder.ctx) for predicate in landmark_vars_list]) == (landmark_z3_var == z3.IntVal(-100, ctx=encoder.ctx)))

        uf_gt = z3.Function(f'{self.name}PredicateOrderingFn', z3.IntSort(ctx=encoder.ctx), z3.IntSort(ctx=encoder.ctx), z3.BoolSort(ctx=encoder.ctx)) 
        for i, landmark_i in enumerate(_landmark_z3_vars):
            for j, landmark_j in enumerate(_landmark_z3_vars[i+1:]):
                self.encodings.append((landmark_i >= landmark_j) == (uf_gt(landmark_i, landmark_j) == z3.BoolVal(True,  ctx=encoder.ctx)))
                self.encodings.append((landmark_i < landmark_j)  == (uf_gt(landmark_i, landmark_j) == z3.BoolVal(False, ctx=encoder.ctx)))
                # now create a variable to hold this ordering.
                ordering_var = z3.Int(f'{self.name}-predicate-ordering-{str(landmark_i)}__after__{str(landmark_j)}'.replace('(','_').replace(')',''), ctx=encoder.ctx)
                self.encodings.append(ordering_var == uf_gt(landmark_i, landmark_j))
                self.landmark_predciates_vars.append(ordering_var)

    def value(self, plan):
        ret_value = []
        ret_value_str = []
        if isinstance(plan, ModelRef):
            for predicate in self.landmark_predciates_vars:
                predicate_value = plan.evaluate(predicate, model_completion = True)
                ret_value.append(predicate == predicate_value)
                ret_value_str.append(str(predicate_value.as_long()))
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        self.var_domain.add(''.join(ret_value_str))
        if len(ret_value) == 0: ret_value.append(self.dummy_landmark_expression)
        return z3.And(ret_value)

    def discretize(self, value):
        """!
        This function should return the discretized value of the dimension.
        """
        return value
    
    def behaviour_expression(self, plan):
        return self.discretize(self.value(plan))
