import sys
import math
from enum import Enum

from unified_planning.model.metrics import Oversubscription
from unified_planning.shortcuts import OneshotPlanner, Compiler, CompilationKind
import unified_planning.engines.results as UPResults
from unified_planning.engines.results import CompilerResult

import z3

# Register planners.
import up_symk
import up_pypmt

from pypmt.apis import initialize_fluents

from behaviour_planning.over_domain_models.smt.bss.behaviour_space.space_encoders.basic import BehaviourSpaceSMT
from behaviour_planning.over_domain_models.smt.bss.utilities import compute_behaviour_space_statistics_smt

class ForbidMode(Enum):
    BEHAVIOUR = 1
    PLAN      = 2

class ForbidBehaviourIterativeSMT:
    def __init__(self, task, bspace_cfg, planner_cfg):
        self.basic_task               = task
        self.base_planner             = planner_cfg
        self.solver_timeout           = bspace_cfg.get('solver-timeout-ms', 300000)
        self.solver_memorylimit       = bspace_cfg.get('solver-memorylimit-mb', 16000)
        self.compilationlist          = bspace_cfg.get('compliation-list', [["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING], ["fast-downward-reachability-grounder", CompilationKind.GROUNDING]])
        self.behaviour_only           = bspace_cfg.get('behaviours-only', False)
        self.ignore_seed_plan         = bspace_cfg.get('ignore-seed-plan', False)
        self.use_fixed_length_formula = bspace_cfg.get('use_fixed_length_formula', False)
        self._is_oversubscription     = False
        
        # initialise fluents.
        initialize_fluents(task)

        # compile the task before solving it.
        self.compiled_task = self._compile(task, self.compilationlist)

        self.bspace = None

        self.log_msg = []
        self.diverse_plans = []
        self.diverse_plans_actions_sequence = set()

        if self.use_fixed_length_formula: self._init_using_fixed_length(self.compiled_task, bspace_cfg)
        else: self._init_using_planner(self.compiled_task, bspace_cfg)
            
    def plan(self, required_plancount = sys.maxsize):
        # Try to generate plans that are diverse in terms of behaviours.
        self.core(ForbidMode.BEHAVIOUR, required_plancount)
        # If we did not get enough diverse behaviours, then try to generate plans from those behaviours.
        if (len(self.diverse_plans) < required_plancount) and\
           (required_plancount != sys.maxsize) and\
           (not self.behaviour_only):
            self.core(ForbidMode.PLAN, required_plancount)
        # return the plans to the lifted task.
        return [self._lift_plan(p, p.behaviour) for p in self.diverse_plans]
        # return list(map(lambda p: p.plan.replace_action_instances(self.compiled_task.map_back_action_instance), self.diverse_plans))
    
    def core(self, forbid_mode, required_plancount):

        if self.bspace is None:
            self.log_msg.append('Behaviour space could not be constructed.')
            return

        if (forbid_mode == ForbidMode.BEHAVIOUR) and len(self.bspace.__len__()) == 0:
            # Cannot generate any behaviour for an empty space
            return

        if (len(self.diverse_plans) == 0) and (len(self.base_planner) != 0) and not self._is_oversubscription:
            self.log_msg.append('Seed plan invalidated the behaviour space.')

        behaviours_list = []
        plans_list      = []

        for plan in self.diverse_plans:
            if plan.behaviour is not None: behaviours_list.append(plan.behaviour)
            if plan._z3_plan is not None:  plans_list.append(z3.Not(z3.And(plan._z3_plan), ctx=self.ctx))

        assumptions = []
        if len(behaviours_list) > 0:
            assumptions.append(z3.Not(z3.Or(behaviours_list), ctx=self.ctx) if forbid_mode == ForbidMode.BEHAVIOUR else z3.Or(behaviours_list))
        
        if len(plans_list): assumptions.extend(plans_list)

        while self.bspace.is_satisfiable(assumptions, self.solver_timeout, self.solver_memorylimit) and (len(self.diverse_plans) < required_plancount):
            # Extract plan from the behaviour space.
            plan = self.bspace.extract_plan()
            if plan is None: break
            # Update the diverse plan list and check that we don't have repeated plans.
            self.update(plan)
            # Append the behaviour to the list of behaviours.
            if forbid_mode == ForbidMode.BEHAVIOUR and plan.behaviour is not None: behaviours_list.append(plan.behaviour)
            # Update the our assumptions.
            assumptions = []
            if len(behaviours_list) > 0:
                assumptions.append(z3.Not(z3.Or(behaviours_list), ctx=self.ctx) if forbid_mode == ForbidMode.BEHAVIOUR else z3.Or(behaviours_list))
            if len(plans_list): 
                plans_list.append(z3.Not(z3.And(plan._z3_plan), ctx=self.ctx))
            assumptions.extend(plans_list)
            print("Found {} till now: {}".format('behaviour(s)' if forbid_mode == ForbidMode.BEHAVIOUR else 'plan(s)', len(self.diverse_plans)))
    
    def update(self, plan):
        # Make sure that we did not get a repeated plan.
        if plan in self.diverse_plans_actions_sequence:
            self.log_msg.append('Repeated plan generated.')
            return
        self.diverse_plans_actions_sequence.add(plan)
        self.diverse_plans.append(plan)

    def logs(self):
        ret_logs = {}
        ret_logs['fbi-logs']     = self.log_msg
        ret_logs['bspace-logs']  = self.bspace.logs() if self.bspace is not None else 'bspace is None.'
        ret_logs['bspace-stats'] = compute_behaviour_space_statistics_smt(self.diverse_plans, self.bspace) if self.bspace is not None else 'bspace is None.'
        return ret_logs

    def _flatten_expr(self, expr): 
        return [expr] if not (z3.is_and(expr) or z3.is_or(expr)) else [arg for child in expr.children() for arg in self._flatten_expr(child)]

    def _lift_plan(self, plan, behaviour):
        plan = plan.plan.replace_action_instances(self.compiled_task.map_back_action_instance)
        setattr(plan, 'behaviour', ' ^ '.join(list(map(lambda s : f'({str(s)})', self._flatten_expr(behaviour)))))
        return plan

    def _compile(self, task, compilationlist):
        oversubscription_metrics = list(filter(lambda metric:     isinstance(metric, Oversubscription), task.quality_metrics))
        other_metrics            = list(filter(lambda metric: not isinstance(metric, Oversubscription), task.quality_metrics))

        task.clear_quality_metrics()
        for metric in other_metrics: task.add_quality_metric(metric)
        
        names = [name for name, _ in compilationlist]
        compilationkinds = [kind for _, kind in compilationlist]
        with Compiler(names=names, compilation_kinds=compilationkinds) as compiler:
            compiled_task = compiler.compile(task)

        assert len(compiled_task.problem.actions) > 0, 'No actions in the compiled task.'

        # add the oversubscription metric back to the task.
        for metric in oversubscription_metrics: compiled_task.problem.add_quality_metric(metric)

        return compiled_task

    def _solve(self, task):

        # if the planning task is oversubscription planning, then we need to remove the oversubscription metric.
        # to make sure that the planner solves get the formula len.

        oversubscription_metrics = list(filter(lambda metric: isinstance(metric, Oversubscription), task.quality_metrics))
        other_metrics            = list(filter(lambda metric: not isinstance(metric, Oversubscription), task.quality_metrics))

        self._is_oversubscription = len(oversubscription_metrics) > 0

        # remove the oversubscription metric from the task.
        task.clear_quality_metrics()
        for metric in other_metrics: task.add_quality_metric(metric)

        plannername   = self.base_planner.get('planner-name', None)
        plannerparams = self.base_planner
        seedplan      = None

        assert plannername in set(['symk-opt', 'SMTPlanner']), 'Unsupported planner is not defined.'        
        assert plannername is not None, 'Planner is not defined.'
        # remove the planner-name from the parameters.
        del plannerparams['planner-name']

        if 'compilationlist' in plannerparams:
            compilationlist = []
            for name, kind in plannerparams['compilationlist']:
                compilationlist.append([None if name == 'None' else name, eval(f'CompilationKind.{kind}')])
            plannerparams['compilationlist'] = compilationlist            

        with OneshotPlanner(name=plannername,  params=plannerparams) as planner:
            result   = planner.solve(task)
            seedplan = result.plan if result.status in UPResults.POSITIVE_OUTCOMES else None
        
        # add the oversubscription metric back to the task.
        for metric in oversubscription_metrics: task.add_quality_metric(metric)

        return seedplan

    def _init_using_planner(self, task, bspace_cfg):

        # run a planner to infer the formula length.
        seedplan = self._solve(task.problem)

        if seedplan is None or len(seedplan.actions) == 0:
            self.log_msg.append('Seed plan could not be generated.')
            return

        # based on the formula length the included dimensions we need to update the upper-bound for the 
        # behaviour space and update the dimensions' additional information. 

        # first infer the behaviour space upper bound based on the passed quality factor.
        quality_bound_factor      = bspace_cfg.get('quality-bound-factor', 1.0)
        bspace_cfg['upper-bound'] = int(math.floor(len(seedplan.actions)*quality_bound_factor))
        assert bspace_cfg['upper-bound'] >= 1, 'The upper bound is less than or equal to zero.'
        
        # check if the quality_bound_factor is 1.0 then there is no point of having the MakespanOptimalCostSMT dimension.
        if quality_bound_factor == 1.0 and not self._is_oversubscription:
            bspace_cfg['dims'] = list(filter(lambda x: x[0].__name__ != 'MakespanOptimalCostSMT', bspace_cfg['dims']))

        # now we need to update the following dimensions, if they are included in the behaviour space.
        # - Update the MakespanOptimalCostSMT with the optimal plan length and the cost bound value.

        additional_information_updates = []
        for idx, (dim_class, dim_additional_information) in enumerate(bspace_cfg['dims']):
            extra_info = {}
            if dim_class.__name__ in ['MakespanOptimalCostSMT', 'CostBoundSMT']:
                extra_info.update({'optimal-plan-length': len(seedplan.actions), 'is-oversubscription': self._is_oversubscription})
                additional_information_updates.append((idx, dim_additional_information | extra_info))
        
        for idx, dim_additional_information in additional_information_updates:
            bspace_cfg['dims'][idx][1] = dim_additional_information
        
        # Construct the behaviour space
        self.bspace = BehaviourSpaceSMT(task, bspace_cfg)
        # Add seed plan to the the list of generated behaviours if the planning task is not oversubscription planning.
        if not self._is_oversubscription:
            plan = self.bspace.plan_behaviour(seedplan)
            if plan is not None and not self.ignore_seed_plan: self.update(plan)
        # Get the same context as the behaviour space.
        self.ctx = self.bspace.ctx
    

    def _init_using_fixed_length(self, task, bspace_cfg):
        # assert False, 'Not implemented yet.'
        # Construct the behaviour space
        self.bspace = BehaviourSpaceSMT(task, bspace_cfg)
        # Get the same context as the behaviour space.
        self.ctx = self.bspace.ctx