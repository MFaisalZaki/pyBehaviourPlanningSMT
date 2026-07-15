from behaviour_planning_smt.bss.features.landmark_predicate_ordering import LandmarkPredicatesOrderingSMT

class GoalPredicatesOrderingSMT(LandmarkPredicatesOrderingSMT):
    def __init__(self, task, additional_information):
        super().__init__('go', task, {'landmark_vars_dict': task.encoder.goal_predicates_vars})