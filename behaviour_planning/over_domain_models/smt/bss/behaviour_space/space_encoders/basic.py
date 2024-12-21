import time
from collections import defaultdict

import z3

from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.seq_encoder import EncoderSequential, EncoderForall
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.r2e_encoder import EncoderRelaxed2Exists
from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.qfuf_encoder import EncoderSequentialQFUF

from behaviour_planning.over_domain_models.smt.bss.behaviour_space.formula_encoders.smt_sequential_plan import SMTSequentialPlan
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.cost_bound_makespan_optimal import MakespanOptimalCostSMT


encoder_map = {
    'seq': EncoderSequential,
    'forall': EncoderForall,
    'r2e': EncoderRelaxed2Exists,
    'qfuf': EncoderSequentialQFUF
}

class BehaviourSpaceSMT:

    def __init__(self, task, cfg=defaultdict(dict)) -> None:
        self.task    = task.problem
        self.encodername = cfg.get('encoder', 'seq')
        self.encoder = encoder_map[self.encodername](self.task)
        self.run_plan_validation    = cfg.get('run-plan-validation', False)
        
        self._behaviour_frequency = defaultdict(dict)
        self._plans = []

        args = {
            'formula_length': cfg.get('upper-bound', 50), 
            'disable_after_goal_state_actions': cfg.get('disable-after-goal-state-actions', False),
            'horizon_planning': cfg.get('horizon-planning', False),
        }

        self.encoder.encode_n(**args)
        
        self.dims  = cfg.get('dims', [])
        
        self.dims  = [d(self.encoder, additional_information) for d, additional_information in self.dims]

        # convert the list to dict with keys as the names of the dimensions.
        self.dims = {d.__class__.__name__: d for d in self.dims}
        # add the dimensions encodings
        for name, _dim in self.dims.items():
            self.encoder.extend(_dim.encodings)
        
        # Create the solver.
        self.solver = z3.Solver(ctx=self.encoder.ctx)
        self.solver.add(self.encoder.assertions)

        # Logged messages.
        self.log_msg  = []
        self.sat_time = []

        # Solver state.
        self.solver_push_cnt = 0

    def __len__(self) -> list:
        return [(name, len(dim)) for name, dim in self.dims.items()]
    
    @property
    def ctx(self):
        return self.encoder.ctx
    
    def _push(self):
        self.solver_push_cnt += 1
        self.solver.push()
    
    def _pop(self):
        if self.solver_push_cnt > 0:
            self.solver.pop()
            self.solver_push_cnt -= 1

    def reset(self):
        self.solver = z3.Solver(ctx=self.encoder.ctx)
        self.solver.add(self.encoder.assertions)
        self.log_msg.append('The solver has been reset.')

    def extract_plan(self):
        """!
        This function should update the plan with its behaviour and any extra information 
        extracted from the model.
        """
        model = self.solver.model()
        # Evaluate the horizon.
        horizon = model.evaluate(self.encoder.horizon_var, model_completion = True).as_long()
        # Extract the plan.
        plan = self.encoder.extract_plan(model, horizon)
        # We need to extract the behaviour from the model.
        behaviour = self.infer_behaviour(model)
        # Update the plan with its behaviour.
        setattr(plan, "behaviour", behaviour)
        # Update its id.
        setattr(plan, "id", len(self._plans)+1)
        # Run validation if enabled.
        is_plan_valid = True
        if self.run_plan_validation and not self.encoder.task_is_oversubscription_planning: is_plan_valid = plan.validate()
        else: setattr(plan, "isvalid", True), setattr(plan, "reason", 'Task is oversubscription' if self.encoder.task_is_oversubscription_planning else 'Validation skipped')
        
        if not is_plan_valid:
            self.log_msg.append(f'Plan {plan.id} is invalid. Reason: {plan.validation_fail_reason}')
            return None
        
        # Count the frequency of the behaviour.
        behaviour_str = str(behaviour)
        if not behaviour_str in self._behaviour_frequency: self._behaviour_frequency[behaviour_str] = 0
        self._behaviour_frequency[behaviour_str] += 1
        
        # Append the plan to the list of plans.
        self._plans.append(plan)
        
        return plan

    def is_satisfiable(self, assumption=[], timeout=None, memorylimit=None) -> bool:
        if timeout is not None: 
            self.solver.set('timeout', timeout)
        
        if memorylimit is not None and not isinstance(self.solver, z3.Optimize):
            self.solver.set('max_memory', memorylimit)
        
        start_time = time.time()
        is_formula_satisfiable = None
        try:
            is_formula_satisfiable = self.solver.check(assumption) == z3.sat
        except Exception as e:
            is_formula_satisfiable = False
            self.log_msg.append(f'An error occured while checking the satisfiability of the formula: {e}')
        finally:
            end_time = time.time()
            time_taken = round(end_time - start_time, 2)
            self.sat_time.append(f'{is_formula_satisfiable}, {time_taken}, {self.compute_behaviour_count()}')
            assert is_formula_satisfiable is not None, 'The satisfiability of the formula is not determined.'
            return is_formula_satisfiable
    
    def infer_behaviour(self, model):
        behaviour_vars = []
        for dimname, dim in self.dims.items():
            behaviour_vars.append(dim.behaviour_expression(model))
        return z3.And(behaviour_vars) if len(behaviour_vars) > 0 else None

    def plan_behaviour(self, plan:SequentialPlan, i=1, return_plan=True):
        """!
        Add the plan to the behaviour space and return a its number in the behaviour space besides
        its behaviour.
        """
        assert isinstance(plan, SequentialPlan), 'The plan is not of type SequentialPlan.'
        # Get the plan's behaviour before returning its number.
        satres = self.solver.check(self.encoder.convert(plan)) == z3.sat
        if not satres:
            self.log_msg.append(f'The behaviour space is not satisfiable after appending plan {i}')
            return None
        # self.log_msg.append(f'Plan {i} has been added to the behaviour space.')
        if return_plan: return self.extract_plan()
        # this is the case when we don't want to return the plan but the behaviour itself.
        return self.infer_behaviour(self.solver.model())
    
    def compute_behaviour_count(self):
        return len(self._behaviour_frequency.keys())
    
    def compute_dimensions_count(self):
        retdetails = defaultdict(dict)
        for dim, dimsize in len(self):
            retdetails[dim] = dimsize
        return retdetails
    
    def logs(self):
        # collect the dimensions' logs.
        for _, dim in self.dims.items():
            self.log_msg.extend(dim.logs)
        return self.log_msg
    
