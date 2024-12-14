import os
import unified_planning as up
from copy import deepcopy
from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner
from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, FunctionsSMT
from up_behaviour_planning.FBIPlannerUp import FBIPlanner

env = up.environment.get_environment()
env.factory.add_engine('FBIPlanner', __name__, 'FBIPlanner')

domain   = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers', 'domain.pddl')
problem  = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers', 'pfile1.pddl')
resource = os.path.join(os.path.dirname(__file__), 'pddls', 'numeric-rovers', 'resources.txt')

# 1. Construct the planner's parameters:
# - define the behaviour space's dimensions 
dims  = []
# dims += [(GoalPredicatesOrderingSMT, None)]
# dims += [(MakespanOptimalCostSMT, {"cost-bound-factor": 2.0})]
dims += [(FunctionsSMT, resource)]

compilationlist = []
compilationlist += [["up_quantifiers_remover", "QUANTIFIERS_REMOVING"]]
compilationlist += [["up_disjunctive_conditions_remover", "DISJUNCTIVE_CONDITIONS_REMOVING"]]
compilationlist += [["up_grounder", "GROUNDING"]]


planner_params = {
  "fbi-planner-type": "ForbidBehaviourIterativeSMT",
  "base-planner-cfg": {
    "planner-name": "SMTPlanner",
    "encoder": "EncoderForall", 
    "upper-bound": 100, 
    "search-strategy": "SMTSearch", 
    "configuration": "forall", 
    "run-validation": False,
    "compilationlist": compilationlist,
    "k": 5 # The number of plans to be generated
  },
  "bspace-cfg": {
    'quality-bound-factor': 2.0,
    "solver-timeout-ms": 600000,
    "solver-memorylimit-mb": 16000,
    "dims": dims,
    "compliation-list": compilationlist,
    "run-plan-validation": True,
    "disable-after-goal-state-actions": False
  }
}

task = PDDLReader().parse_problem(domain, problem)
with OneshotPlanner(name='FBIPlanner',  params=deepcopy(planner_params)) as planner:
  result = planner.solve(task)

planlist = [] if len(result[0]) <= 1 else [r.plan for r in result[0]]
planlist = list(filter(lambda p: not p is None, planlist))
logmsgs  = result[1]