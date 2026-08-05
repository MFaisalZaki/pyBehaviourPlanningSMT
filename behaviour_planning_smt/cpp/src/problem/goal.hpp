// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "protobuf_aliases.hpp"
#include "expression.hpp"

namespace bp {

/**
 * @brief Goal
 * 
 * Represents a goal condition in the planning problem.
 */
class Goal {
public:
    // Constructors
    Goal() = default;
    Goal(const Expression& goal_expr) : goal_expr_(goal_expr) {}
    Goal(const pb::Goal& pb_goal, const Problem* problem);
    
    // Accessors
    const Expression& goal_expression() const { return goal_expr_; }
    
    // Setters
    void set_goal_expression(const Expression& goal_expr) { goal_expr_ = goal_expr; }
    
    // String representation
    std::string to_string() const { return goal_expr_.to_string(); }
    
    // Operators
    bool operator==(const Goal& other) const { return goal_expr_ == other.goal_expr_; }
    bool operator!=(const Goal& other) const { return !(*this == other); }

private:
    Expression goal_expr_;
};

} // namespace bp
