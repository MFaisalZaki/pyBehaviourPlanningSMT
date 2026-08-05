// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "../expression.hpp"
#include "../atom.hpp"
#include <vector>
#include <span>

namespace bp {

/**
 * @brief Visitor interface for Expression traversal
 * 
 * Implement this interface to define operations on different expression types.
 * Uses the visitor pattern to dispatch based on expression content.
 */
class ExpressionVisitor {
public:
    virtual ~ExpressionVisitor() = default;
    
    // Visit different atom types
    virtual void visit_symbol(const std::string& symbol, Expression::Kind kind, const Type* type) = 0;
    virtual void visit_integer(int64_t value, Expression::Kind kind) = 0;
    virtual void visit_real(const Real& value, Expression::Kind kind) = 0;
    virtual void visit_boolean(bool value, Expression::Kind kind) = 0;
    
    // Visit function applications and lists
    virtual void visit_function_application(const std::string& function_name,
                                          std::span<const Expression> args,
                                          Expression::Kind kind) = 0;
    virtual void visit_list(const std::vector<Expression>& elements, 
                           Expression::Kind kind) = 0;
    
    // Visit fluent applications (special case of function application)
    virtual void visit_fluent_application(const std::string& fluent_name,
                                        std::span<const Expression> args,
                                        Expression::Kind kind) = 0;
};

/**
 * @brief Base visitor with default implementations
 * 
 * Inherit from this if you only want to override specific visit methods.
 * All methods have empty default implementations.
 */
class BaseExpressionVisitor : public ExpressionVisitor {
public:
    void visit_symbol(const std::string& symbol, Expression::Kind kind, const Type* type) override {}
    void visit_integer(int64_t value, Expression::Kind kind) override {}
    void visit_real(const Real& value, Expression::Kind kind) override {}
    void visit_boolean(bool value, Expression::Kind kind) override {}
    void visit_function_application(const std::string& function_name,
                                  std::span<const Expression> args,
                                  Expression::Kind kind) override {}
    void visit_list(const std::vector<Expression>& elements, 
                   Expression::Kind kind) override {}
    void visit_fluent_application(const std::string& fluent_name,
                                std::span<const Expression> args,
                                Expression::Kind kind) override {}
};

/**
 * @brief Utility function to accept visitors
 * 
 * This function dispatches to the appropriate visitor method based on
 * the expression's content and kind.
 */
void accept_visitor(const Expression& expr, ExpressionVisitor& visitor);

} // namespace bp
