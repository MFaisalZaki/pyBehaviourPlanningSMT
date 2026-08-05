// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "assignment.hpp"

namespace bp {

Assignment::Assignment(const pb::Assignment& pb_assignment, const Problem* problem) 
    : fluent_(pb_assignment.fluent(), problem), value_(pb_assignment.value(), problem) {
}

std::string Assignment::to_string() const {
    return fluent_.to_string() + " := " + value_.to_string();
}

} // namespace bp
