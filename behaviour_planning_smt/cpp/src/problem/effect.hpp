// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "protobuf_aliases.hpp"
#include "effect_expression.hpp"

namespace bp {

/**
 * @brief Effect
 * 
 * Wraps an EffectExpression, to represent an effect in a planning problem.
 * Supports conditional and quantified effects.
 */
class Effect {
public:
    // Constructors
    Effect() = default;
    Effect(const EffectExpression& effect_expr) : effect_expr_(effect_expr) {}
    Effect(const pb::Effect& pb_effect, const Problem* problem);
    
    // Accessors
    const EffectExpression& effect_expression() const { return effect_expr_; }
    
    // Setters
    void set_effect_expression(const EffectExpression& effect_expr) { effect_expr_ = effect_expr; }
    
    // Convenience methods that delegate to the effect expression
    EffectExpression::Kind kind() const { return effect_expr_.kind(); }
    const Expression& fluent() const { return effect_expr_.fluent(); }
    const Expression& value() const { return effect_expr_.value(); }
    bool is_conditional() const { return effect_expr_.is_conditional(); }
    const Expression& condition() const { return effect_expr_.condition(); }
    bool is_quantified() const { return effect_expr_.is_quantified(); }
    
    // String representation
    std::string to_string() const { return effect_expr_.to_string(); }
    
    // Operators
    bool operator==(const Effect& other) const { return effect_expr_ == other.effect_expr_; }
    bool operator!=(const Effect& other) const { return !(*this == other); }

private:
    EffectExpression effect_expr_;
};

} // namespace bp
