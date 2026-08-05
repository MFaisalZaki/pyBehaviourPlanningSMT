// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "fluent.hpp"
#include <sstream>

namespace bp {

Fluent::Fluent(const pb::Fluent& pb_fluent, const Type* value_type, const std::vector<Parameter>& parameters)
    : name_(pb_fluent.name()), value_type_(value_type), parameters_(parameters) {}

std::string Fluent::to_string() const {
    std::ostringstream oss;
    oss << name_;
    if (!parameters_.empty()) {
        oss << "(";
        for (size_t i = 0; i < parameters_.size(); ++i) {
            if (i > 0) oss << ", ";
            oss << parameters_[i].to_string();
        }
        oss << ")";
    }
    oss << " : " << (value_type_ ? value_type_->name() : "null");
    if (has_default_value()) {
        oss << " = " << default_value_->to_string();
    }
    return oss.str();
}

bool Fluent::operator==(const Fluent& other) const {
    return name_ == other.name_ &&
           value_type_ == other.value_type_ &&
           parameters_ == other.parameters_ &&
           default_value_ == other.default_value_;
}

} // namespace bp
