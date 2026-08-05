// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "goal.hpp"

namespace bp {

Goal::Goal(const pb::Goal& pb_goal, const Problem* problem) 
    : goal_expr_(pb_goal.goal(), problem) {
}

} // namespace bp
