// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "object.hpp"

namespace bp {

Object::Object(const pb::ObjectDeclaration& pb_object, const Type* type)
    : name_(pb_object.name()), type_(type) {}

} // namespace bp
