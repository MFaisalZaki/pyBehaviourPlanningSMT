// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "protobuf_aliases.hpp"
#include "expression.hpp"

namespace bp {

/**
 * @brief Assignment
 * 
 * Represents an assignment of a value to a fluent. Used to represent states, such as the initial state.
 */
class Assignment {
public:
    // Constructors
    Assignment() = default;
    Assignment(const Expression& fluent, const Expression& value)
        : fluent_(fluent), value_(value) {}
    Assignment(const pb::Assignment& pb_assignment, const Problem* problem);
    
    // Accessors
    const Expression& fluent() const { return fluent_; }
    const Expression& value() const { return value_; }
    
    // Setters
    void set_fluent(const Expression& fluent) { fluent_ = fluent; }
    void set_value(const Expression& value) { value_ = value; }
    
    // String representation
    std::string to_string() const;
    
    // Operators
    bool operator==(const Assignment& other) const {
        return fluent_ == other.fluent_ && value_ == other.value_;
    }
    bool operator!=(const Assignment& other) const { return !(*this == other); }

private:
    Expression fluent_;
    Expression value_;
};

} // namespace bp
