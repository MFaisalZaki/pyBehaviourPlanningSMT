from collections import defaultdict
import z3

from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.cost_bound_dims import CostBoundSMT

class MakespanOptimalCostSMT(CostBoundSMT):
    def __init__(self, encoder, additional_information):
        super().__init__('makespan-optimal-cost', encoder, lambda a: 1, additional_information)

    def __encode__(self, encoder):

        # A better way to do this is to count how many steps are enabled rather than summing up the actions.
        selected_actions_vars = []
        for t in range(0, len(encoder)):
            var = z3.Int(f'step_{t}_cost', ctx=encoder.ctx)
            selected_actions_vars.append(var)
            self.encodings.append(var == z3.If(z3.Or(encoder.get_actions_vars(t)), z3.IntVal(1, ctx=encoder.ctx), z3.IntVal(0, ctx=encoder.ctx)))
        
        self.actions_cost = z3.Int(self.name, ctx=encoder.ctx)
        self.var          = self.actions_cost
        self.encodings.append(self.actions_cost == z3.Sum(selected_actions_vars))

        # bound the plan length variable to the makespan.
        self.encodings.append(self.actions_cost < z3.IntVal(len(encoder), ctx=encoder.ctx))

        # if the planning problem is not oversubscription, then we can add the optimal plan length constraint.
        if not self.is_oversubscription:
            self.encodings.append(self.actions_cost >= z3.IntVal(self.optimal_plan_length, ctx=encoder.ctx))
        else:
            # this means that the planning problem is an oversubscription planning problem.
            # so we need to set the actions_cost to be less the the bound factor * len(encoder).
            cost_bound_step = int(self.cost_bound_factor * len(encoder))
            self.encodings.append(self.actions_cost <= z3.IntVal(cost_bound_step, ctx=encoder.ctx))
            # limit the horizon variable to the cost bound value.
            self.encodings.append(encoder.horizon_var <= z3.IntVal(cost_bound_step, encoder.ctx))
            # disable all the actions after the cost bound step.
            for t in range(cost_bound_step, len(encoder)):
                self.encodings.append(z3.And(encoder.disable_actions_at_t(t)))

    def value(self, plan):
        retvalue = None
        if isinstance(plan, ModelRef):
            retvalue = plan.evaluate(self.var, model_completion = True)
        elif isinstance(plan, SequentialPlan):
            assert False, 'Value function is not implemented for this dimension for a plan.'
        else:
            raise TypeError(f"Unknown type for plan: {type(plan)}")
        # Update domain value.
        self.var_domain.add(str(retvalue))
        return retvalue

    def discretize(self, value):
        return value.as_long()