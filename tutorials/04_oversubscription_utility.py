"""
Tutorial 4: The utility value dimension.

'uv' scores the utility a plan collects, which tells apart plans that chase
different subsets of the goals. It needs an oversubscription task: one that
attaches a utility to each goal predicate and asks for as much of it as it can
afford, rather than demanding every goal be met.

The classical rovers instance is not one of those, so this tutorial turns it
into one the same way the paper experiments do -- see add_utility_values() in
paper_experiments/utilities.py.

Run with: python tutorials/04_oversubscription_utility.py
"""

import os
import z3
import unified_planning as up
from unified_planning.io import PDDLReader
from unified_planning.model.walkers.free_vars import FreeVarsExtractor
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir   = os.path.join(os.path.dirname(__file__), 'pddls', 'classical-rovers')
domainfile  = os.path.join(pddls_dir, 'domain.pddl')
problemfile = os.path.join(pddls_dir, 'p03.pddl')

task = PDDLReader().parse_problem(domainfile, problemfile)

# 1. Turn the hard goals into utilities. A parsed task states its goal as one
#    conjunction, so pull the individual predicates out of it, price them, and
#    hand them to an Oversubscription metric.
def add_utility_values(task):
    goal_predicates = next(map(lambda expr: FreeVarsExtractor().get(expr), task.goals), None)
    if goal_predicates is None: return {}
    # Any pricing will do. The experiments use 2, 4, 6, ... in goal order.
    utilities = {g: (i+1)*2 for i, g in enumerate(goal_predicates)}
    task.add_quality_metric(up.model.metrics.Oversubscription(utilities, task.environment))
    # Clearing the goals is the point: nothing is mandatory any more, so a plan
    # is free to skip an expensive goal and still be a plan.
    task.goals.clear()
    return utilities

utilities = add_utility_values(task)
print('Goal utilities:')
for goal, utility in utilities.items():
    print(f'  {goal}: {utility}')
print(f'Total available utility: {sum(utilities.values())}\n')

# 2. 'uv' reads the utilities off the metric attached above, so it needs no
#    additional information of its own. Without that metric it raises an
#    assertion error rather than quietly scoring nothing.
#
#    'cb' behaves differently on an oversubscription task: instead of forcing
#    plans to be at least optimal length, it caps them at quality-bound * the
#    inferred length, which is the budget a plan gets to spend on utility.
dims  = []
dims += [['uv', {}]]
dims += [['cb', {"quality-bound": 0.5}]]

planner = ForbiddenBehaviorSMTPlanner(task, dims)
print(f'Inferred plan length: {planner.behaviour_space.optimal_plan_length}')

plans = planner.plan(4)
print(f'Got {len(plans)} plans.\n')

def dimension_value(behaviour_expr):
    return next(a.as_long() for a in behaviour_expr.children() if z3.is_int_value(a))

# Each plan collects a different amount of utility: that is its behaviour. A
# cheap plan settling for one goal and a longer one collecting several are both
# valid answers here, which is exactly what a hard-goal task cannot express.
for i, plan in enumerate(plans):
    print(f'Plan {i+1}: {len(plan.actions)} actions | utility: {dimension_value(plan.behaviour_attr["uv"])}')
