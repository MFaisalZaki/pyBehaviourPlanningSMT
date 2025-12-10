import z3
import re
import time 
import unified_planning.engines.results as UPResults


from unified_planning.model.metrics import Oversubscription
from unified_planning.shortcuts import OneshotPlanner, Compiler, CompilationKind
from pypmt.apis import initialize_fluents

from itertools import chain
from behaviour_planning_smt.bss.encodings.seq import EncoderSequential, EncoderForall
from behaviour_planning_smt.bss.encodings.r2e import EncoderRelaxed2Exists
from behaviour_planning_smt.bss.encodings.qfuf import EncoderSequentialQFUF

from behaviour_planning_smt.bss.features.goal_predicate_ordering import GoalPredicatesOrderingSMT
from behaviour_planning_smt.bss.features.cost_bound_makespan_optimal import MakespanOptimalCostSMT
from behaviour_planning_smt.bss.features.resources import ResourceCountSMT
from behaviour_planning_smt.bss.features.utility_value import UtilityValueSMT

encoder_map = {
    'seq':    EncoderSequential,
    'forall': EncoderForall,
    'r2e':    EncoderRelaxed2Exists,
    'qfuf':   EncoderSequentialQFUF
}

features_map = {
    'go': GoalPredicatesOrderingSMT,
    'cb': MakespanOptimalCostSMT,
    'ru': ResourceCountSMT,
    'uv': UtilityValueSMT,
}

class BehaviourSpaceSMT:
    def __init__(self, task, f):
        
        # This is required by pypmt to deal with numeric planning.
        initialize_fluents(task)

        self.encoder        = None
        self.compiled_task  = None
        self.task           = task
        self.optimal_plan_length = self.__infer_formula_length__(task)
        self.quality_bound  = next(filter(lambda e: e[0] == 'cb', f), ['cb', {'quality-bound': 1.0}])[1]['quality-bound']
        self.formula        = self.__encode_formula__(int(self.optimal_plan_length * self.quality_bound)) 
        self.features       = {feat_name: features_map[feat_name](self.compiled_task.problem, addinfo) for feat_name, addinfo in self.__update_addinfo__(f[:])}
        self.solver         = self.__create_smt_solver__(self.formula)

        self.log      = []
        self.sat_time = []

    def __infer_formula_length__(self, task):
        # This should solve the planning task using up.
        # if the planning task is oversubscription planning, then we need to remove the oversubscription metric.
        # to make sure that the planner solves get the formula len.
        oversubscription_metrics = list(filter(lambda metric: isinstance(metric, Oversubscription), task.quality_metrics))
        other_metrics            = list(filter(lambda metric: not isinstance(metric, Oversubscription), task.quality_metrics))
        self._is_oversubscription = len(oversubscription_metrics) > 0
        # remove the oversubscription metric from the task.
        task.clear_quality_metrics()
        for metric in other_metrics: task.add_quality_metric(metric)
        seedplan      = None
        with OneshotPlanner() as planner:
            result   = planner.solve(task)
            seedplan = result.plan if result.status in UPResults.POSITIVE_OUTCOMES else None
        # add the oversubscription metric back to the task.
        for metric in oversubscription_metrics: task.add_quality_metric(metric)
        return 0 if seedplan is None else len(seedplan.actions)

    def __encode_formula__(self, n):
        is_numeric_checker  = [self.task.kind.has_fluents_in_numeric_assignments()]
        is_numeric_checker += [self.task.kind.has_numeric_fluents()]
        is_numeric_checker += [self.task.kind.has_numbers()]
        is_numeric_checker += [self.task.kind.has_simple_numeric_planning()]

        is_oversubscription = self.task.kind.has_oversubscription() or self.task.kind.has_oversubscription_kind()

        compilation_list  = []
        compilation_list += [["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING]]
        compilation_list += [["up_disjunctive_conditions_remover", CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING]]
        compilation_list += [["up_grounder", CompilationKind.GROUNDING]] if any(is_numeric_checker) or is_oversubscription  else [["fast-downward-reachability-grounder", CompilationKind.GROUNDING]]

        with Compiler(names=list(map(lambda e: e[0], compilation_list)), compilation_kinds=list(map(lambda e: e[1], compilation_list))) as compiler:
            self.compiled_task = compiler.compile(self.task)

        self.encoder = encoder_map['seq'](self.compiled_task.problem)

        args = {
            'formula_length': n, 
            'disable_after_goal_state_actions': False,
            'horizon_planning': False,
            'skip_actions' : False
        }

        formula = self.encoder.encode_n(**args)
        setattr(self.compiled_task.problem, 'encoder', self.encoder)
        return formula
    
    def __update_addinfo__(self, features):
        ret_features = []
        for idx, (feat_name, addinfo) in enumerate(features):
            match feat_name:
                case 'cb':
                    # is_oversubscription = len(list(filter(lambda metric: isinstance(metric, Oversubscription), self.task.quality_metrics))) > 0 
                    is_oversubscription = self.compiled_task.problem.kind.has_oversubscription() or self.compiled_task.problem.kind.has_oversubscription_kind()
                    ret_features.append((feat_name, addinfo | {'optimal-plan-length': self.optimal_plan_length, 'is-oversubscription': is_oversubscription}))
                case _:
                    ret_features.append((feat_name, addinfo))
        return ret_features
    
    def __create_smt_solver__(self, formula):
        solver = z3.Solver(ctx=self.encoder.ctx)
        # Append the encodings for the planning task.
        solver.add(formula)
        # Append the behaviour space dimensions.
        solver.add(list(chain.from_iterable(f.formula for f in self.features.values())))
        return solver
    
    def check(self, assumption=[], timeout=None, memorylimit=None):
        if timeout is not None: self.solver.set('timeout', timeout)
        if memorylimit is not None and not isinstance(self.solver, z3.Optimize): self.solver.set('max_memory', memorylimit)
        start_time = time.time()
        is_formula_satisfiable = None
        try:
            is_formula_satisfiable = self.solver.check(assumption) == z3.sat
        except Exception as e:
            is_formula_satisfiable = False
            self.log.append(f'An error occured while checking the satisfiability of the formula: {e}')
        finally:
            end_time = time.time()
            time_taken = round(end_time - start_time, 2)
            # self.sat_time.append(f'{is_formula_satisfiable}, {time_taken}, {self.compute_behaviour_count()}')
            assert is_formula_satisfiable is not None, 'The satisfiability of the formula is not determined.'
            if not is_formula_satisfiable: return None
            model = self.solver.model()
            # extract the plan
            plan = self.encoder.extract_plan(model, model.evaluate(self.encoder.horizon_var, model_completion = True).as_long())
            # infer behaviour 
            behaviour_vars = {name : dim.expr(model) for name, dim in self.features.items()}
            lifted_plan = plan.replace_action_instances(self.compiled_task.map_back_action_instance)
            setattr(lifted_plan, 'behaviour_expr', z3.And(list(filter(lambda e: e is not  None, behaviour_vars.values()))) if len(behaviour_vars) > 0 else None)
            setattr(lifted_plan, 'behaviour_attr', behaviour_vars if len(behaviour_vars) > 0 else None)
            setattr(lifted_plan, 'behaviour_str', re.sub(r' {2,}', '  ', str(lifted_plan.behaviour_expr)).replace('\n', ''))
            setattr(lifted_plan, 'z3_actions_vars', plan.z3_actions_vars)
            return lifted_plan

    def reset(self):
        self.solver = self.__create_smt_solver__()
        self.log.append('The solver has been reset.')
        