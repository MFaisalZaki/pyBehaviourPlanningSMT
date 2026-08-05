// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "type.hpp"

namespace bp {

Type::Type(const std::string& name) : name_(name) {}

const std::string& Type::name() const { return name_; }
void Type::set_name(const std::string& name) { name_ = name; }

const Type* Type::parent() const { return parent_; }
void Type::set_parent(const Type* parent) { parent_ = parent; }

void Type::set_parent_name(const std::string& parent_name) { parent_name_ = parent_name; }
const std::string& Type::parent_name() const { return parent_name_; }

bool Type::is_subtype_of(const Type* supertype) const {
    const Type* current = this;
    while (current) {
        if (current == supertype) return true;
        current = current->parent();
    }
    return false;
}

} // namespace bp
