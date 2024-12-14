
from pypmt.planner.plan.smt_sequential_plan import SMTSequentialPlan

def __init__(self, plan, task, z3_plan=None):
    self.behaviour  = None
    self.isvalid    = None
    self.cost_value = None
    self.id        = None
    self._z3_plan  = z3_plan
    self.validation_fail_reason = None
    self.plan = plan
    self.task = task
    self._plan_str = None

setattr(SMTSequentialPlan, '__init__', __init__)