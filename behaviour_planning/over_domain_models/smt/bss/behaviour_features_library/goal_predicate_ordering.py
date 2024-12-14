from collections import defaultdict

import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT

class GoalPredicatesOrderingSMT(DimensionConstructorSMT):
    
    def __init__(self, encoder, additional_information):
        self.goal_predciates_vars = []
        self.dummy_goal_variable = z3.Bool('dummy-goal-variable', ctx=encoder.ctx)
        self.dummy_goal_expression = self.dummy_goal_variable == z3.BoolVal(False, ctx=encoder.ctx)
        super().__init__('goal-predicates-ordering', encoder, additional_information)

    def __encode__(self, encoder):
        """!
        This function should return the encoding of the dimension.
        """
        _sgo_z3_vars = []
        for _, sgo_vars_list in encoder.goal_predicates_vars.items():
            sgnoname = str(sgo_vars_list[0])[:str(sgo_vars_list[0]).rfind('_')]
            subgoal_z3_var = z3.Int(f'sgo-{sgnoname}', ctx=encoder.ctx)
            _sgo_z3_vars.append(subgoal_z3_var)
            for idx, sgo in enumerate(sgo_vars_list):
                expr  = [sgo] + [z3.Not(sgo, ctx=encoder.ctx) for sgo in sgo_vars_list[:idx]]
                self.encodings.append(z3.And(expr) == (subgoal_z3_var == z3.IntVal(idx+1, ctx=encoder.ctx)))
            self.encodings.append(z3.And([z3.Not(sgo, ctx=encoder.ctx) for sgo in sgo_vars_list]) == (subgoal_z3_var == z3.IntVal(-100, ctx=encoder.ctx)))

        uf_gt = z3.Function('GoalPredicateOrderingFn', z3.IntSort(ctx=encoder.ctx), z3.IntSort(ctx=encoder.ctx), z3.BoolSort(ctx=encoder.ctx)) 
        for i, sgoi in enumerate(_sgo_z3_vars):
            for j, sgoj in enumerate(_sgo_z3_vars[i+1:]):
                self.encodings.append((sgoi >= sgoj) == (uf_gt(sgoi, sgoj) == z3.BoolVal(True,  ctx=encoder.ctx)))
                self.encodings.append((sgoi < sgoj)  == (uf_gt(sgoi, sgoj) == z3.BoolVal(False, ctx=encoder.ctx)))
                # now create a variable to hold this ordering.
                ordering_var = z3.Int(f'goal-predicate-ordering-{str(sgoi)}>{str(sgoj)}', ctx=encoder.ctx)
                self.encodings.append(ordering_var == uf_gt(sgoi, sgoj))
                self.goal_predciates_vars.append(ordering_var)

    def value(self, plan):
        ret_value = []
        ret_value_str = []
        if isinstance(plan, ModelRef):
            for predicate in self.goal_predciates_vars:
                predicate_value = plan.evaluate(predicate, model_completion = True)
                ret_value.append(predicate == predicate_value)
                ret_value_str.append(str(predicate_value.as_long()))
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        self.var_domain.add(''.join(ret_value_str))
        if len(ret_value) == 0: ret_value.append(self.dummy_goal_expression)
        return z3.And(ret_value)

    def discretize(self, value):
        """!
        This function should return the discretized value of the dimension.
        """
        return value
    
    def behaviour_expression(self, plan):
        return self.discretize(self.value(plan))
