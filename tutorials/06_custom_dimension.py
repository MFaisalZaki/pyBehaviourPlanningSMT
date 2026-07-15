"""
Tutorial 6: Writing your own dimension.

The five built-in dimensions are not special: each is a class implementing a two
method contract, registered under a short name. This tutorial adds a sixth that
counts how many navigate actions a plan uses, so that plans driving around a lot
and plans driving as little as possible count as different behaviours.

Run with: python tutorials/06_custom_dimension.py
"""

import os
import z3
from unified_planning.io import PDDLReader
from behaviour_planning_smt.bss.features.base import DimensionConstructorSMT
from behaviour_planning_smt.bss.behaviour_space import features_map
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner


# 1. Subclass DimensionConstructorSMT.
#
#    The base class stores name/task/addinfo, exposes the encoder as
#    self.encoder, prepares an empty self.formula and an empty self.var_domain,
#    and then calls __encode__ for you. Because __encode__ runs from inside
#    super().__init__, anything __encode__ needs must be set up *before* that
#    call -- which is why the built-in dimensions call super().__init__ last.
class ActionCountSMT(DimensionConstructorSMT):

    # The behaviour space builds dimensions as features_map[name](task, addinfo),
    # so a dimension takes exactly two arguments and picks its own short name.
    # The task handed over is the grounded, compiled one, so the action names
    # here are grounded names like 'navigate_rover0_waypoint3_waypoint1'.
    def __init__(self, task, additional_information):
        super().__init__('ac', task, additional_information)

    def __encode__(self, encoder):
        """Constrain a z3 variable to the number of matching actions in a plan."""
        prefix = self.addinfo['action-prefix']

        # encoder.up_actions_to_z3 maps each grounded action name to one boolean
        # per step, true when the plan takes that action then. Other useful
        # handles are encoder.up_fluent_to_z3 (a fluent's value per step),
        # encoder.get_actions_vars(t), encoder.horizon_var and len(encoder) for
        # the number of steps.
        step_vars = [var for action_name, vars_per_step in encoder.up_actions_to_z3.items()
                          if action_name.startswith(prefix)
                          for var in vars_per_step]
        assert len(step_vars) > 0, f'No grounded action starts with {prefix!r}.'

        # Every z3 term must be built in the encoder's context. Mixing contexts
        # is the usual cause of a baffling z3 error here.
        self.var = z3.Int(self.name, ctx=encoder.ctx)
        as_ints  = [z3.If(var, z3.IntVal(1, ctx=encoder.ctx),
                               z3.IntVal(0, ctx=encoder.ctx)) for var in step_vars]

        # Whatever you append to self.formula is added to the solver alongside
        # the planning task's own encoding.
        self.formula.append(self.var == z3.Sum(as_ints))

    def expr(self, model):
        """Pin this dimension to the value it takes in a given plan's model."""
        # This expression is what makes a behaviour: the planner ANDs one per
        # dimension, then forbids that conjunction to force the next plan into a
        # different part of the space. So it has to *identify* the behaviour, not
        # merely describe it.
        value = model.evaluate(self.var, model_completion=True)
        # var_domain records the values seen so far. The planner does not read
        # it, but the built-in dimensions maintain it and it is handy to inspect.
        self.var_domain.add(str(value))
        return self.var == value


# 2. Register it. features_map is read when the behaviour space is built, so
#    assigning to it is enough -- the library needs no edit.
features_map['ac'] = ActionCountSMT


# 3. Use it like any built-in dimension: a [name, additional-info] pair, where
#    additional-info is whatever your class expects to find in self.addinfo.
pddls_dir   = os.path.join(os.path.dirname(__file__), 'pddls', 'classical-rovers')
task = PDDLReader().parse_problem(os.path.join(pddls_dir, 'domain.pddl'),
                                  os.path.join(pddls_dir, 'p03.pddl'))

dims  = []
dims += [['ac', {"action-prefix": "navigate"}]]
dims += [['cb', {"quality-bound": 1.5}]]

planner = ForbiddenBehaviorSMTPlanner(task, dims)
plans   = planner.plan(4)
print(f'\nGot {len(plans)} plans.')

for i, plan in enumerate(plans):
    navigations = next(a.as_long() for a in plan.behaviour_attr['ac'].children()
                       if z3.is_int_value(a))
    print(f'Plan {i+1}: {len(plan.actions)} actions | navigate actions: {navigations}')

print(f'\nValues this dimension took: {sorted(planner.behaviour_space.features["ac"].var_domain)}')

# A dimension does not have to be an integer count. 'go' pins a vector of
# ordering variables and 'fn' pins one box per numeric fluent, both returning a
# z3.And(...) from expr(). Anything the encoder can talk about and expr() can
# pin down works as a dimension.
#
# This dimension is all the planner needs. Inferring the behaviour of plans that
# are already written -- replaying them against the task rather than reading them
# off a z3 model -- is a separate job, and a separate package:
# https://github.com/MFaisalZaki/BehaviourDiversityCounter. A dimension there is
# a different contract, so a new dimension that both sides should agree on has to
# be written once for each.
