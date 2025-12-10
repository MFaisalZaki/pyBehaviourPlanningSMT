import json

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.base import DimensionConstructorSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.goal_predicate_ordering import GoalPredicatesOrderingSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.cost_bound_dims import CostBoundSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.cost_bound_makespan_optimal import MakespanOptimalCostSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.resource_count import ResourceCountSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.functions import FunctionsSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.utility_value import UtilityValueSMT
from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.utility_set import UtilitySetSMT


def process_args(args):

    # Read the planner's configuration file.
    with open(args.plannercfg, 'r') as f:
        cfg = json.load(f)

    planner_cfg = cfg['base-planner-cfg']
    bspace_cfg  = cfg['bspace-cfg']

    # process the arguments.
    dims = []
    if args.add_goal_ordering:
        dims += [(GoalPredicatesOrderingSMT, None)]

    if args.add_resource_count:
        assert args.resource_file, "Resource file is required when adding resource count to the plan."
        dims += [(ResourceCountSMT, args.resource_file)]

    if args.add_makespan:
        dims += [(MakespanOptimalCostSMT, {"disable_action_check": args.disable_action_check})]
    
    # Update the bspace configuration to include the parsed resource file
    bspace_cfg['dims'] = dims
    
    # Update the planner's quality bound factor
    if args.q: bspace_cfg['quality-bound-factor'] = args.q

    return bspace_cfg, planner_cfg