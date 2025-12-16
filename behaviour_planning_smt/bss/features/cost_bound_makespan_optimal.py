import z3

from behaviour_planning_smt.bss.features.cost_bound_dims import CostBoundSMT
from behaviour_planning_smt.bss.features.base import DimensionConstructorSimulator

class MakespanOptimalCostSMT(CostBoundSMT):
    def __init__(self, task, additional_information):
        super().__init__('makespan-optimal-cost', task, lambda a: 1, additional_information)

    def __encode__(self, encoder):
        # A better way to do this is to count how many steps are enabled rather than summing up the actions.
        selected_actions_vars = []
        for t in range(0, len(encoder)):
            var = z3.Int(f'step_{t}_cost', ctx=encoder.ctx)
            selected_actions_vars.append(var)
            self.formula.append(var == z3.If(z3.Or(encoder.get_actions_vars(t)), z3.IntVal(1, ctx=encoder.ctx), z3.IntVal(0, ctx=encoder.ctx)))
        
        self.actions_cost = z3.Int(self.name, ctx=encoder.ctx)
        self.var          = self.actions_cost
        self.formula.append(self.actions_cost == z3.Sum(selected_actions_vars))

        # bound the plan length variable to the makespan.
        self.formula.append(self.actions_cost < z3.IntVal(len(encoder), ctx=encoder.ctx))

        # if the planning problem is not oversubscription, then we can add the optimal plan length constraint.
        if not self.is_oversubscription:
            self.formula.append(self.actions_cost >= z3.IntVal(self.optimal_plan_length, ctx=encoder.ctx))
        else:
            # this means that the planning problem is an oversubscription planning problem.
            # so we need to set the actions_cost to be less the the bound factor * len(encoder).
            cost_bound_step = int(self.cost_bound_factor * self.optimal_plan_length)
            self.formula.append(self.actions_cost <= z3.IntVal(cost_bound_step, ctx=encoder.ctx))
            # limit the horizon variable to the cost bound value.
            self.formula.append(encoder.horizon_var <= z3.IntVal(cost_bound_step, encoder.ctx))
            # disable all the actions after the cost bound step.
            for t in range(cost_bound_step, len(encoder)):
                self.formula.append(z3.And(encoder.disable_actions_at_t(t)))

    def expr(self, model):
        """!
        This function should return the z3 expression of the dimension given the model.
        """
        retvalue = model.evaluate(self.var, model_completion = True)
        self.var_domain.add(str(retvalue))
        return self.var == retvalue


class MakespanOptimalCostSimulator(DimensionConstructorSimulator):
    def __init__(self, task, addinfo):
        super().__init__(task, 'cb', addinfo)
    
    def plan_behaviour(self, plan):
        self.domain.add(len(plan.actions))
        return f'{self.name}:' + str(len(plan.actions))
