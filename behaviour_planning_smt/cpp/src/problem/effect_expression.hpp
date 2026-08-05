// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <vector>
#include <optional>
#include "protobuf_aliases.hpp"
#include "expression.hpp"

namespace bp {

/**
 * @brief Effect expression
 * 
 * Represents an effect of the form "FLUENT OP VALUE" with optional condition.
 */
class EffectExpression {
public:
    // Effect kinds (simplified from protobuf)
    enum class Kind {
        ASSIGN = 0,   // fluent := value
        INCREASE = 1, // fluent += value
        DECREASE = 2  // fluent -= value
    };
    
    // Constructors
    EffectExpression() : kind_(Kind::ASSIGN) {}
    EffectExpression(Kind kind, const Expression& fluent, const Expression& value)
        : kind_(kind), fluent_(fluent), value_(value) {}
    EffectExpression(Kind kind, const Expression& fluent, const Expression& value, 
                    const Expression& condition)
        : kind_(kind), fluent_(fluent), value_(value), condition_(condition) {}
    EffectExpression(const pb::EffectExpression& pb_effect_expr, const Problem* problem);
    
    // Accessors
    Kind kind() const { return kind_; }
    const Expression& fluent() const { return fluent_; }
    const Expression& value() const { return value_; }
    bool is_conditional() const { 
        return condition_.has_value() && 
               !(condition_->is_constant() && condition_->is_atom() && 
                 condition_->value().is_boolean() && condition_->value().boolean() == true); 
    }
    const Expression& condition() const { return condition_.value(); }
    const std::vector<Expression>& forall_variables() const { return forall_variables_; }
    
    // Setters
    void set_kind(Kind kind) { kind_ = kind; }
    void set_fluent(const Expression& fluent) { fluent_ = fluent; }
    void set_value(const Expression& value) { value_ = value; }
    void set_condition(const Expression& condition) { condition_ = condition; }
    void clear_condition() { condition_.reset(); }
    void add_forall_variable(const Expression& variable) { forall_variables_.push_back(variable); }
    
    // Convenience methods
    bool is_assign() const { return kind_ == Kind::ASSIGN; }
    bool is_increase() const { return kind_ == Kind::INCREASE; }
    bool is_decrease() const { return kind_ == Kind::DECREASE; }
    bool is_quantified() const { return !forall_variables_.empty(); }
    
    // String representation
    std::string to_string() const;
    std::string kind_to_string() const;
    
    // Operators
    bool operator==(const EffectExpression& other) const;
    bool operator!=(const EffectExpression& other) const { return !(*this == other); }

private:
    Kind kind_;
    Expression fluent_;
    Expression value_;
    std::optional<Expression> condition_;
    std::vector<Expression> forall_variables_;
};

} // namespace bp
