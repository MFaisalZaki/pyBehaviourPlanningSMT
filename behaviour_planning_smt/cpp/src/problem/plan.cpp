// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "plan.hpp"
#include <sstream>

namespace bp {

void Plan::add_action(const Action* action) {
    if (action) {
        actions_.push_back(action);
    }
}

pb::Plan Plan::to_protobuf() const {
    pb::Plan pb_plan_msg;

    for (const Action* action : actions_) {
        pb::ActionInstance* pb_action_instance = pb_plan_msg.add_actions();
        pb_action_instance->set_action_name(action->name());

        for (const Parameter& param : action->parameters()) {
            pb::Atom* pb_param = pb_action_instance->add_parameters();
            pb_param->set_symbol(param.name());
        }
    }

    return pb_plan_msg;
}

std::string Plan::to_string() const {
    if (is_empty()) {
        return "Empty plan";
    }

    std::ostringstream oss;
    oss << "Plan with " << length() << " actions:\n";
    for (const Action* action : actions_) {
        oss << action->name() << "\n";
    }

    return oss.str();
}

} // namespace bp