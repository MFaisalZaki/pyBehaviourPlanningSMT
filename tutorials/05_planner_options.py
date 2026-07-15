"""
Tutorial 3: Controlling the horizon.

Before it can encode anything, the planner needs a formula length. By default it
finds one by solving the task once and taking the optimal plan's length. That
first solve can be the slowest part of a run, and the options below let you
skip it or override what it produced.

Run with: python tutorials/03_planner_options.py
"""

import os
from unified_planning.io import PDDLReader
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir   = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers')
domainfile  = os.path.join(pddls_dir, 'domain.pddl')
problemfile = os.path.join(pddls_dir, 'pfile1.pddl')

task = PDDLReader().parse_problem(domainfile, problemfile)
dims = [['go', {}]]

# Any keyword argument is forwarded to the underlying behaviour space.

# 1. The default: solve the task first to infer the optimal plan length. The
#    formula length is that value scaled by cb's quality bound, or by 1.0 when
#    there is no cb dimension.
planner = ForbiddenBehaviorSMTPlanner(task, dims)
plans   = planner.plan(2)
print(f'[default] inferred length: {planner.behaviour_space.optimal_plan_length}, '
      f'plan lengths: {[len(p.actions) for p in plans]}')

# 2. horizon_length skips that solve and uses the value you give. Nothing checks
#    it against the task: too short and the goal is unreachable and you get no
#    plans back, too long and the formula is bigger than it needs to be.
planner = ForbiddenBehaviorSMTPlanner(task, dims, horizon_length=12)
plans   = planner.plan(2)
print(f'[horizon_length=12] length: {planner.behaviour_space.optimal_plan_length}, '
      f'plan lengths: {[len(p.actions) for p in plans]}')

# 3. horizon_planning_mode pins the horizon to the formula's last step instead of
#    binding it to the first step at which the goal holds, so plans are read from
#    the whole formula rather than truncated at the goal.
#
#    The effect on plan length is task dependent, and on this task the two modes
#    often agree: steps where no action was selected are skipped when the plan is
#    read back, so a plan is not obliged to fill its horizon either way.
planner = ForbiddenBehaviorSMTPlanner(task, dims, horizon_length=12, horizon_planning_mode=True)
plans   = planner.plan(2)
print(f'[horizon_planning_mode=True] plan lengths: {[len(p.actions) for p in plans]}')

# 4. use_pypmt forces the SMT planner for the inference step in 1. Numeric and
#    oversubscription tasks use it regardless -- this rovers task is numeric, so
#    the flag changes nothing here. It matters for classical tasks, which
#    otherwise infer their length with symk.
planner = ForbiddenBehaviorSMTPlanner(task, dims, use_pypmt=True)
print(f'[use_pypmt=True] inferred length: {planner.behaviour_space.optimal_plan_length}')
