

from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT

class CostBoundSMT(DimensionConstructorSMT):
    def __init__(self, name, task, action_cost_fn, additional_information):
        self.action_cost_fn       = action_cost_fn
        self.cost_bound_factor    = additional_information.get('quality-bound', None)
        self.optimal_plan_length  = additional_information.get('optimal-plan-length', None)
        self.is_oversubscription  = additional_information.get('is-oversubscription', False)

        assert self.cost_bound_factor is not None, f"Cost bound factor is not provided for the dimension {name}."
        assert self.optimal_plan_length is not None, f"Optimal plan length is not provided for the dimension {name}."

        super().__init__(name, task, additional_information)    