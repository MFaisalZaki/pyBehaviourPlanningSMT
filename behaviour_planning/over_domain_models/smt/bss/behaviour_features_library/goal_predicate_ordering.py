from collections import defaultdict

import z3
from z3 import ModelRef
from unified_planning.plans import SequentialPlan

from behaviour_planning.over_domain_models.smt.bss.behaviour_features_library.landmark_predicate_ordering import LandmarkPredicatesOrderingSMT

class GoalPredicatesOrderingSMT(LandmarkPredicatesOrderingSMT):
    
    def __init__(self, encoder, additional_information):
        super().__init__('subgoal', 
                         encoder, 
                         {'landmark_vars_dict': encoder.goal_predicates_vars})