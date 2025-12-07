import sys
import unified_planning as up
import z3

from collections import defaultdict
from copy import deepcopy
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.shortcuts import Compiler, CompilationKind, OperatorKind
from unified_planning.plans import ActionInstance
from unified_planning.plans import SequentialPlan

from pypmt.apis import initialize_fluents
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.space_encoders.basic import BehaviourSpaceSMT

class BehaviourCountSMT:
    def __init__(self, domain, problem, bspace_cfg, planlist, is_oversubscription_planning=False, compilationlist=[['up_quantifiers_remover', CompilationKind.QUANTIFIERS_REMOVING], ['fast-downward-reachability-grounder', CompilationKind.GROUNDING]]):
        
        self.compilationlist = compilationlist

        # read the planning task.
        planningtask = PDDLReader().parse_problem(domain, problem)
        
        # compiled task.
        self.gr_result = self._prepare_task(planningtask, is_oversubscription_planning)
        self.task = self.gr_result.problem

        # update the behaviour space configuration parameters.
        self._update_bspace_cfg(bspace_cfg, is_oversubscription_planning)
        
        # recompile the plans to the grounded problem.
        # recheck this if the results of fi planner are not as expected.
        # TODO: We need to find a better way to get the plans.
        updated_planlist = list(map(lambda p: PDDLReader().parse_plan_string(self.task,  PDDLWriter(self.task).get_plan(PDDLReader().parse_plan_string(planningtask, p)).replace(' ', '_')), planlist))
        # updated_planlist = list(map(lambda p: PDDLReader().parse_plan_string(self.task, p), planlist))
        
        # compute the maximum plan length
        bspace_cfg['upper-bound'] = max(map(lambda p: len(p.actions), updated_planlist))
        # disable after goal state actions check to allow loops.
        bspace_cfg['disable-after-goal-state-actions'] = True
        # disable plan validation.
        bspace_cfg['run-plan-validation'] = False

        # initialize the behaviour space.
        self.bspace = BehaviourSpaceSMT(self.gr_result, bspace_cfg)
        # check if we are optimising on behaviour count.
        select_k = bspace_cfg.get('select-k', sys.maxsize)
        # compute behaviour count.
        self.colleted_behaviours = set()
        self.selected_plans_list = defaultdict(list)
        for i, plan in enumerate(updated_planlist):
            ret = self.bspace.plan_behaviour(plan, i=i, return_plan=False)
            if ret is None: 
                self.bspace.log_msg.append(f'Plan {i} is not satisfiable.')
                continue
            setattr(plan, 'behaviour', ' ^ '.join(list(map(lambda s : f'({str(s)})', self._flatten_expr(ret)))))
            self.selected_plans_list[ret].append(plan)
            self.colleted_behaviours.add(ret)
            if self.count() >= select_k: break

    def _flatten_expr(self, expr): 
        return [expr] if not (z3.is_and(expr) or z3.is_or(expr)) else [arg for child in expr.children() for arg in self._flatten_expr(child)]

    def _prepare_task(self, planningtask, is_oversubscription_planning):
        # initialize the fluents.        
        initialize_fluents(planningtask)
        compiler_names = list(map(lambda e: e[0], self.compilationlist))
        compilation_kinds = list(map(lambda e: e[1], self.compilationlist))

        # ground the problem.
        with Compiler(names = compiler_names, compilation_kinds = compilation_kinds) as grounder:
            gr_result = grounder.compile(planningtask)
       
        # add the utility mertic if the planning task is oversubscription.
        if is_oversubscription_planning:
            goals = {}
            for i, goal in enumerate(gr_result.problem.goals):
                i = i + 1
                if OperatorKind.AND == goal.node_type:
                    for j, g in enumerate(goal.args):
                        j = j + 1
                        goals[g] = i * j
                else:
                    goals[goal] = i * 2
            gr_result.problem.add_quality_metric(up.model.metrics.Oversubscription(goals))
        return gr_result

    def _update_bspace_cfg(self, bspace_cfg, is_oversubscription_planning):
        # update the behaviour space configuration parameters.
        additional_information_updates = []
        for idx, (dim_class, dim_additional_information) in enumerate(bspace_cfg['dims']):
            extra_info = {}
            if dim_class.__name__ in ['MakespanOptimalCostSMT', 'CostBoundSMT']:
                extra_info.update({
                    # 'optimal-plan-length': 0,
                    'cost-bound-factor' : 1.0,
                    'is-oversubscription': is_oversubscription_planning})
                additional_information_updates.append((idx, dim_additional_information | extra_info))
        
        for idx, dim_additional_information in additional_information_updates:
            bspace_cfg['dims'][idx][1] = dim_additional_information

    def count(self):
        return len(self.colleted_behaviours)
    
    def selected_plans(self, k):
        ret_plans = []
        cpy_plans_list = deepcopy(self.selected_plans_list)
        while len(ret_plans) < k and not all([len(v) == 0 for v in cpy_plans_list.values()]):
            for key in cpy_plans_list.keys():
                if len(ret_plans) >= k: break
                if len(cpy_plans_list[key]) == 0: continue
                ret_plans.append(cpy_plans_list[key].pop())
        return ret_plans

    def logs(self):
        return self.bspace.log_msg

