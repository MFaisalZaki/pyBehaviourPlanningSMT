// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "expression_visitor.hpp"
#include <unordered_set>
#include <unordered_map>
#include <string>
#include <vector>

namespace bp {

/**
 * @brief Visitor that collects fluents with their polarity information
 * 
 * Traverses the expression tree and collects all fluent applications
 * with their polarity (positive/negative) in boolean contexts.
 * For numeric fluents, polarity is not relevant.
 */
class FluentPolarityCollector : public BaseExpressionVisitor {
public:
    enum class Polarity {
        POSITIVE,   // Fluent appears positively (e.g., (at robot loc))
        NEGATIVE    // Fluent appears negatively (e.g., (not (at robot loc)))
    };

private:
    std::unordered_map<Expression, Polarity> boolean_fluents_;
    std::unordered_set<Expression> numeric_fluents_;
    bool in_negation_context_ = false;
    
    /**
     * @brief Collects a fluent expression with its polarity
     */
    void collect_fluent(const Expression& fluent_expr) {
        if (fluent_expr.type() && fluent_expr.type()->is_bool()) {
            // Boolean fluent - record polarity
            Polarity polarity = in_negation_context_ ? Polarity::NEGATIVE : Polarity::POSITIVE;
            boolean_fluents_[fluent_expr] = polarity;
        } else {
            // Numeric fluent - no polarity
            numeric_fluents_.insert(fluent_expr);
        }
    }
    
public:
    void visit_symbol(const std::string& symbol, Expression::Kind kind, const Type* type) override {
        // Single fluent symbols (no arguments) - handled by collect_from_expression
    }
    
    void visit_function_application(const std::string& function_name,
                                  std::span<const Expression> args,
                                  Expression::Kind kind) override {
        // For other functions, recursively visit all arguments
        for (const auto& arg : args) {
            accept_visitor(arg, *this);
        }
    }
    
    void visit_fluent_application(const std::string& fluent_name,
                                std::span<const Expression> args,
                                Expression::Kind kind) override {
        // Note: This method is not used anymore since we handle fluent applications
        // directly in collect_from_expression by checking for STATE_VARIABLE kind
        
        // Recursively visit arguments in case they contain nested fluents
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
    
    /**
     * @brief Main entry point to collect fluents from an expression
     * 
     * Call this method to collect all fluents from a complete expression.
     * This handles the full expression context that individual visit methods lack.
     */
    void collect_from_expression(const Expression& expr) {
        // Handle negation expressions like (not ...)
        if (expr.is_not()) {
            // Enter negation context and process the negated content
            bool old_negation = in_negation_context_;
            in_negation_context_ = !in_negation_context_;
            
            // Process everything after the "not" operator
            const auto& list = expr.list();
            for (size_t i = 1; i < list.size(); ++i) {
                collect_from_expression(list[i]);
            }
            
            in_negation_context_ = old_negation;
            return;
        }
        
        // Check if this expression itself is a fluent
        if (expr.kind() == Expression::Kind::FLUENT_SYMBOL || 
            expr.kind() == Expression::Kind::STATE_VARIABLE) {
            collect_fluent(expr);
        } else if (expr.is_list()) {
            // For other list expressions, recursively process each element
            for (const auto& element : expr.list()) {
                collect_from_expression(element);
            }
        }
    } 
    
    // Accessors for boolean fluents
    const std::unordered_map<Expression, Polarity>& get_boolean_fluents() const { 
        return boolean_fluents_; 
    }
    
    // Accessors for numeric fluents
    const std::unordered_set<Expression>& get_numeric_fluents() const { 
        return numeric_fluents_; 
    }
    
    // Utility methods
    bool has_boolean_fluents() const { return !boolean_fluents_.empty(); }
    bool has_numeric_fluents() const { return !numeric_fluents_.empty(); }
    size_t boolean_fluent_count() const { return boolean_fluents_.size(); }
    size_t numeric_fluent_count() const { return numeric_fluents_.size(); }
    
    // Clear all collected fluents
    void clear() { 
        boolean_fluents_.clear(); 
        numeric_fluents_.clear();
        in_negation_context_ = false;
    }
    
    // Get string representation of all collected fluents
    std::string to_string() const {
        std::string result = "Collected fluents:\n";
        result += "Boolean fluents:\n";
        for (const auto& [fluent, polarity] : boolean_fluents_) {
            result += "  " + fluent.to_string() + " [" + 
                     (polarity == Polarity::POSITIVE ? "POSITIVE" : "NEGATIVE") + "]\n";
        }
        result += "Numeric fluents:\n";
        for (const auto& fluent : numeric_fluents_) {
            result += "  " + fluent.to_string() + "\n";
        }
        return result;
    }
};

} // namespace bp
