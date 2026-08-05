// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "expression_visitor.hpp"
#include <unordered_set>
#include <string>

namespace bp {

/**
 * @brief Visitor that collects all variables and parameters in an expression
 * 
 * Traverses the expression tree and collects all symbols that are marked
 * as variables or parameters. Useful for dependency analysis.
 */
class VariableCollector : public BaseExpressionVisitor {
private:
    std::unordered_set<std::string> variables_;
    std::unordered_set<std::string> parameters_;
    
public:
    void visit_symbol(const std::string& symbol, Expression::Kind kind) override {
        if (kind == Expression::Kind::VARIABLE) {
            variables_.insert(symbol);
        } else if (kind == Expression::Kind::PARAMETER) {
            parameters_.insert(symbol);
        }
    }
    
    void visit_function_application(const std::string& function_name,
                                  std::span<const Expression> args,
                                  Expression::Kind kind) override {
        // Recursively visit all arguments
        for (const auto& arg : args) {
            accept_visitor(arg, *this);
        }
    }
    
    void visit_fluent_application(const std::string& fluent_name,
                                std::span<const Expression> args,
                                Expression::Kind kind) override {
        // Recursively visit all arguments
        for (const auto& arg : args) {
            accept_visitor(arg, *this);
        }
    }
    
    void visit_list(const std::vector<Expression>& elements, 
                   Expression::Kind kind) override {
        // Recursively visit all elements
        for (const auto& element : elements) {
            accept_visitor(element, *this);
        }
    }
    
    // Accessors
    const std::unordered_set<std::string>& get_variables() const { return variables_; }
    const std::unordered_set<std::string>& get_parameters() const { return parameters_; }
    
    // Utility methods
    bool has_variables() const { return !variables_.empty(); }
    bool has_parameters() const { return !parameters_.empty(); }
    size_t variable_count() const { return variables_.size(); }
    size_t parameter_count() const { return parameters_.size(); }
    
    void clear() { 
        variables_.clear(); 
        parameters_.clear();
    }
};

} // namespace bp
