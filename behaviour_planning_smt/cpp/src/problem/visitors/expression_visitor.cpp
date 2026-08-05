// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "expression_visitor.hpp"
#include <span>

namespace bp {

void accept_visitor(const Expression& expr, ExpressionVisitor& visitor) {
    if (expr.is_atom()) {
        const Atom& atom = expr.value();
        
        if (atom.is_symbol()) {
            visitor.visit_symbol(atom.symbol(), expr.kind(), expr.type());
        } else if (atom.is_integer()) {
            visitor.visit_integer(atom.integer(), expr.kind());
        } else if (atom.is_real()) {
            visitor.visit_real(atom.real(), expr.kind());
        } else if (atom.is_boolean()) {
            visitor.visit_boolean(atom.boolean(), expr.kind());
        }
    } 
    else if (expr.is_list()) {
        const auto& list = expr.list();
        
        if (expr.is_function_application() && !list.empty() && list[0].is_atom()) {
            // Function application: first element is the function name
            const std::string& function_name = list[0].value().symbol();
            std::span<const Expression> args{list.data() + 1, list.size() - 1};
            visitor.visit_function_application(function_name, args, expr.kind());
        } else if (expr.is_state_variable() && !list.empty() && list[0].is_atom()) {
            // Fluent application: first element is the fluent name
            const std::string& fluent_name = list[0].value().symbol();
            std::span<const Expression> args{list.data() + 1, list.size() - 1};
            visitor.visit_fluent_application(fluent_name, args, expr.kind());
        } else {
            // Generic list
            visitor.visit_list(list, expr.kind());
        }
    }
}

} // namespace bp
