# pyBehaviourPlanningSMT
Implementation for the `Behaviour Planning: A Toolbox for Diverse Planning` paper.

# Installation
Installation is easy; just run `python -m venv venv && source venv/bin/activate && pip install .`
Afterwards, install the UP wrapper:`pip install git+https://github.com/MFaisalZaki/up-behaviour-planning.git `

# How to use
```
import unified_planning as up
from copy import deepcopy
from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner
from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, ResourceCountSMT
from behaviour_planning.over_domain_models.smt.shortcuts import ForbidBehaviourIterativeSMT
from up_behaviour_planning.FBIPlannerUp import FBIPlanner

env = up.environment.get_environment()
env.factory.add_engine('FBIPlanner', __name__, 'FBIPlanner')

# 1. Construct the planner's parameters:
# - define the behaviour space's dimensions 
dims  = []
dims += [(GoalPredicatesOrderingSMT, None)]
dims += [(MakespanOptimalCostSMT, {"cost-bound-factor": 1.0})]
# In case of the resource dimension, pass the additional information as path to the file.
# The format for the resource file is:
# (:resource NAME MAX MIN STEP)
# For example the rovers domain instance 4 where this dimension distinguish between plans based on the used rovers:
# (:resource rover0 100 0 5)
# (:resource rover1 100 0 5)
# dims += [(ResourceCountSMT, <Path to resource utilisation file>)]


planner_params = {
  "fbi-planner-type": "ForbidBehaviourIterativeSMT",
  "base-planner-cfg": {
    "planner-name": "symk-opt",
    "symk_search_time_limit": "900s",
    "k": 5 # The number of plans to be generated
  },
  "bspace-cfg": {
    "solver-timeout-ms": 600000,
    "solver-memorylimit-mb": 16000,
    "dims": dims,
    "run-plan-validation": True,
    "encoder": "forall",
    "disable-after-goal-state-actions": False
  }
}

domain  = <path to domain file>
problem = <path to instance file>

task = PDDLReader().parse_problem(domain, problem)
with OneshotPlanner(name='FBIPlanner',  params=deepcopy(planner_params)) as planner:
  result = planner.solve(task)
planlist = [] if len(result[0]) <= 1 else [r.plan for r in result[0]]
planlist = list(filter(lambda p: not p is None, planlist))
logmsgs  = result[1]
```

# Citation
```
@article{abdelwahed2024behaviour,
  title={Behaviour Planning: A Toolbox for Diverse Planning},
  author={Abdelwahed, Mustafa F and Espasa, Joan and Toniolo, Alice and Gent, Ian P},
  journal={arXiv preprint arXiv:2405.04300},
  year={2024}
}
```