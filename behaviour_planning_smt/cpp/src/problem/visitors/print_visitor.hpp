// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "expression_visitor.hpp"
#include <iostream>

namespace bp {

/**
 * @brief Visitor that prints the expression tree structure
 * 
 * Provides a hierarchical view of expressions with indentation
 * to show the tree structure.
 */
class PrintVisitor : public BaseExpressionVisitor {
private:
    int depth_ = 0;
    std::ostream& out_;
    
    void print_indent() const {
        for (int i = 0; i < depth_; ++i) {
            out_ << "  ";
        }
    }
    
    const char* kind_to_string(Expression::Kind kind) const {
        switch (kind) {
            case Expression::Kind::UNKNOWN: return "UNKNOWN";
            case Expression::Kind::CONSTANT: return "CONSTANT";
            case Expression::Kind::PARAMETER: return "PARAMETER";
            case Expression::Kind::VARIABLE: return "VARIABLE";
            case Expression::Kind::FLUENT_SYMBOL: return "FLUENT_SYMBOL";
            case Expression::Kind::FUNCTION_SYMBOL: return "FUNCTION_SYMBOL";
            case Expression::Kind::STATE_VARIABLE: return "STATE_VARIABLE";
            case Expression::Kind::FUNCTION_APPLICATION: return "FUNCTION_APPLICATION";
            default: return "UNKNOWN";
        }
    }
    
    const char* type_to_string(const Type* type) const {
        if (!type) return "UNKNOWN";
        
        if (type->is_bool()) return "BOOLEAN";
        if (type->is_int()) return "INTEGER";
        if (type->is_real()) return "REAL";
        if (type->is_object()) return "OBJECT";
        return "OBJECT"; // Default for user-defined types
    }
    
public:
    explicit PrintVisitor(std::ostream& out = std::cout) : out_(out) {}
    
    void visit_symbol(const std::string& symbol, Expression::Kind kind, const Type* type) override {
        print_indent();
        out_ << "Symbol: \"" << symbol << "\" (" << kind_to_string(kind) << ", " << type_to_string(type) << ")\n";
    }
    
    void visit_integer(int64_t value, Expression::Kind kind) override {
        print_indent();
        out_ << "Integer: " << value << " (" << kind_to_string(kind) << ")\n";
    }
    
    void visit_real(const Real& value, Expression::Kind kind) override {
        print_indent();
        out_ << "Real: " << value.to_string() << " (" << kind_to_string(kind) << ")\n";
    }
    
    void visit_boolean(bool value, Expression::Kind kind) override {
        print_indent();
        out_ << "Boolean: " << (value ? "true" : "false") << " (" << kind_to_string(kind) << ")\n";
    }
    
    void visit_function_application(const std::string& function_name,
                                  std::span<const Expression> args,
                                  Expression::Kind kind) override {
        print_indent();
        out_ << "Function: \"" << function_name << "\" with " << args.size() 
             << " args (" << kind_to_string(kind) << ")\n";
        depth_++;
        for (const auto& arg : args) {
            accept_visitor(arg, *this);
        }
        depth_--;
    }
    
    void visit_fluent_application(const std::string& fluent_name,
                                std::span<const Expression> args,
                                Expression::Kind kind) override {
        print_indent();
        out_ << "Fluent: \"" << fluent_name << "\" with " << args.size() 
             << " args (" << kind_to_string(kind) << ")\n";
        depth_++;
        for (const auto& arg : args) {
            accept_visitor(arg, *this);
        }
        depth_--;
    }
    
    void visit_list(const std::vector<Expression>& elements, 
                   Expression::Kind kind) override {
        print_indent();
        out_ << "List with " << elements.size() << " elements (" << kind_to_string(kind) << ")\n";
        depth_++;
        for (const auto& element : elements) {
            accept_visitor(element, *this);
        }
        depth_--;
    }
};

} // namespace bp
