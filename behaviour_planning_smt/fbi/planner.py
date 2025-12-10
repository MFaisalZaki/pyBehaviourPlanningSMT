import z3
from behaviour_planning_smt.bss.behaviour_space import BehaviourSpaceSMT

class ForbiddenBehaviorSMTPlanner:
    def __init__(self, task, features):
        self.solver_timeout     =  300000
        self.solver_memorylimit = 16000
        self.plan_set           = set()
        self.behaviour_space    = BehaviourSpaceSMT(task, features)
        self.ctx                = self.behaviour_space.encoder.ctx

    def __behaviour_generator__(self, planset):
        behaviours_list = [plan.behaviour_expr for plan in planset if plan.behaviour_expr is not None]
        assumptions     = []
        if len(behaviours_list) > 0: assumptions.append(z3.Not(z3.Or(behaviours_list), ctx=self.ctx))
        return self.behaviour_space.check(assumptions, self.solver_timeout, self.solver_memorylimit)

    def __plan_generator__(self, planset):
        assumptions     = []
        behaviours_list = [plan.behaviour_expr for plan in planset if plan.behaviour_expr is not None]
        plans_list      = [z3.And(plan.z3_actions_vars) for plan in planset if plan.z3_actions_vars is not None]
        if len(behaviours_list) > 0: assumptions.append(z3.Or(behaviours_list))
        if len(plans_list) > 0:      assumptions.append(z3.Not(z3.Or(plans_list), ctx=self.ctx))
        return self.behaviour_space.check(assumptions, self.solver_timeout, self.solver_memorylimit)

    def plan(self, k):
        behaviour_count = 0
        while len(self.plan_set) < k :
            plan = self.__behaviour_generator__(self.plan_set)
            if plan is None: break
            self.plan_set.add(plan)
            behaviour_count += 1
        
        while len(self.plan_set) < k :
            plan = self.__plan_generator__(self.plan_set)
            if plan is None: break
            self.plan_set.add(plan)

        return self.plan_set