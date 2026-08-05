// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "parameter.hpp"

namespace bp {

Parameter::Parameter(const pb::Parameter& pb_param, const Type* type)
    : name_(pb_param.name()), type_(type) {}

} // namespace bp
