// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include "protobuf_aliases.hpp"
#include "type.hpp"

namespace bp {

/**
 * @brief Parameter
 * 
 * Represents a typed parameter for actions or fluents.
 */
class Parameter {
public:
    // Constructors
    Parameter() = default;
    Parameter(const std::string& name, const Type* type) : name_(name), type_(type) {}
    Parameter(const pb::Parameter& pb_param, const Type* type);
    
    // Accessors
    const std::string& name() const { return name_; }
    const Type* type() const { return type_; }
    
    // Setters
    void set_name(const std::string& name) { name_ = name; }
    void set_type(const Type* type) { type_ = type; }
    
    // String representation
    std::string to_string() const { return name_ + " : " + (type_ ? type_->name() : ""); }
    
    // Operators
    bool operator==(const Parameter& other) const {
        return name_ == other.name_ && type_ == other.type_;
    }
    bool operator!=(const Parameter& other) const { return !(*this == other); }

private:
    std::string name_;
    const Type* type_ = nullptr;
};

} // namespace bp
