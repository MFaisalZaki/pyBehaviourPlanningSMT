"""
Tutorial 3: The resource usage dimension.

'ru' counts how many distinct resources a plan uses, so it tells apart plans
that solve the same task with different amounts of the fleet. That only means
something when the task has several resources to choose between, so this
tutorial uses the classical rovers instance 3, which has two rovers.

Run with: python tutorials/03_resource_usage.py
"""

import os
import z3
from unified_planning.io import PDDLReader
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir     = os.path.join(os.path.dirname(__file__), 'pddls', 'classical-rovers')
domainfile    = os.path.join(pddls_dir, 'domain.pddl')
problemfile   = os.path.join(pddls_dir, 'p03.pddl')
resourcesfile = os.path.join(pddls_dir, 'resources.txt')

# The resources file lists one resource per line:
#
#   (:resource rover0 0 100 5)
#   (:resource rover1 0 100 5)
#
# NAME is matched as a *substring* against the grounded action names, so
# 'rover0' picks up every grounded action mentioning rover0. Resources matching
# no action are dropped. Unlike the 'fn' dimension, 'ru' only ever reads the
# name: the three numbers are required by the parser but never used, which is
# why the repository's own resource data under
# paper_experiments/data/classical-domains-ru-info carries them in a different
# order and still works.

task = PDDLReader().parse_problem(domainfile, problemfile)

# A quality bound above 1.0 is what makes this dimension interesting. Optimal
# plans tend to agree on how many rovers to use, so allowing plans of up to 1.5x
# the optimal cost leaves room for a plan that spreads the work differently.
dims  = []
dims += [['ru', resourcesfile]]
dims += [['cb', {"quality-bound": 1.5}]]

planner = ForbiddenBehaviorSMTPlanner(task, dims)
print(f'Optimal plan length: {planner.behaviour_space.optimal_plan_length}')

plans = planner.plan(4)
print(f'Got {len(plans)} plans.\n')

# behaviour_attr holds one z3 equality per dimension rather than a plain value,
# and z3 prints those with the number first, as '2 == ru'. Pick the numeral out
# of the equality's children to recover the count itself.
def dimension_value(behaviour_expr):
    return next(a.as_long() for a in behaviour_expr.children() if z3.is_int_value(a))

# The 'ru' value is the number of rovers the plan touched. Plans sharing a value
# have the same behaviour along this dimension: the planner returns them only
# once the behaviour space has no unseen behaviour left to offer, which is why
# asking for 4 plans yields repeats of a value here.
for i, plan in enumerate(plans):
    rovers_used = dimension_value(plan.behaviour_attr['ru'])
    print(f'Plan {i+1}: {len(plan.actions)} actions | rovers used: {rovers_used}')
