// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "../problem/visitors/expression_visitor.hpp"
#include "../problem/problem.hpp"
#include "../problem/object.hpp"
#include "z3_variable_factory.hpp"
#include <z3++.h>
#include <optional>
#include <string>
#include <vector>
#include <functional>

namespace bp {

// Forward declarations
class Fluent;

/**
 * @brief Visitor that converts expressions to Z3 formulas using grounded variables
 * 
 * Unlike LiftedEncodingVisitor which creates uninterpreted functions, this visitor
 * creates individual Z3 variables for each grounded fluent at specific timesteps.
 * It works in conjunction with GroundedEncoder to maintain consistency in variable
 * naming and creation.
 * 
 * Key differences from LiftedEncodingVisitor:
 * - Fluent applications become individual variables (e.g., "located_plane1_city0_5") 
 *   instead of function calls (e.g., "(located plane1 city0 5)")
 * - Proper type support for Boolean, Integer, Real, and Object fluents
 * - Uses Z3VariableFactory for consistent variable creation and naming
 * - Supports temporal encoding through timestep parameters
 */
class GroundedEncodingVisitor : public BaseExpressionVisitor {
private:
    z3::context& ctx_;
    const Problem* problem_;
    int current_timestep_;
    std::optional<z3::expr> result_;
    Z3VariableFactory* variable_factory_;
    
public:
    // Constructor
    GroundedEncodingVisitor(z3::context& ctx, const Problem* problem, 
                           Z3VariableFactory* factory);
    
    // BaseExpressionVisitor interface methods
    void visit_symbol(const std::string& symbol, Expression::Kind kind, const Type* type) override;
    void visit_integer(int64_t value, Expression::Kind kind) override;
    void visit_real(const Real& value, Expression::Kind kind) override;
    void visit_boolean(bool value, Expression::Kind kind) override;
    void visit_function_application(const std::string& function_name,
                                  std::span<const Expression> args,
                                  Expression::Kind kind) override;
    void visit_fluent_application(const std::string& fluent_name,
                                std::span<const Expression> args,
                                Expression::Kind kind) override;
    void visit_list(const std::vector<Expression>& elements, 
                   Expression::Kind kind) override;
    
    // Result access
    std::optional<z3::expr> get_result() const { return result_; }
    bool has_result() const { return result_.has_value(); }
    z3::expr get_expression() const { return result_.value(); }
    
    // Utility methods
    void clear() { 
        result_.reset();
    }
    
    // Temporal encoding methods
    void set_timestep(int timestep) { current_timestep_ = timestep; }
    int get_timestep() const { return current_timestep_; }
    void clear_timestep() { current_timestep_ = -1; }

private:
    // Helper methods for specific Z3 operations
    std::optional<z3::expr> handle_and(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_or(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_not(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_equals(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_less_than(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_less_equal(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_greater_than(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_greater_equal(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_plus(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_minus(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_multiply(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_divide(const std::vector<z3::expr>& args);
    std::optional<z3::expr> handle_implies(const std::vector<z3::expr>& args);
};

} // namespace bp
