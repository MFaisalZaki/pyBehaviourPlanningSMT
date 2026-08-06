// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "expression.hpp"
#include "problem.hpp"
#include <sstream>
#include <functional>

namespace bp {

Expression::Expression(const pb::Expression& pb_expression, const Problem* problem) {
    // Set type from protobuf and resolve using Problem context
    const Type* resolved_type = resolve_type(pb_expression.type(), problem);
    type_ = resolved_type;

    // Convert kind
    kind_ = static_cast<Kind>(pb_expression.kind());
    
    // Handle atom vs list based on the protobuf content
    if (pb_expression.has_atom()) {
        // This is an atom expression
        Atom original_atom(pb_expression.atom());
        
        // If this is a symbol and it's a function symbol, apply UP operator mapping
        if (original_atom.is_symbol() && 
            (kind_ == Kind::FUNCTION_SYMBOL || kind_ == Kind::FLUENT_SYMBOL)) {
            std::string mapped_symbol = Expression::map_up_operator(original_atom.symbol());
            // Create a new atom with the mapped symbol
            pb::Atom mapped_pb_atom;
            mapped_pb_atom.set_symbol(mapped_symbol);
            atom_ = Atom(mapped_pb_atom);
        } else {
            atom_ = original_atom;
        }
    }
    
    // Handle list (for function applications, etc.)
    if (pb_expression.list_size() > 0) {
        list_.clear();
        for (int i = 0; i < pb_expression.list_size(); ++i) {
            const auto& pb_expr = pb_expression.list(i);
            
            // For the first element in function applications, apply operator mapping.
            // The oneof case check works on every protobuf version, unlike the
            // has_symbol() accessor, which older protoc releases do not generate
            // for oneof members.
            if (i == 0 && kind_ == Kind::FUNCTION_APPLICATION && pb_expr.has_atom() &&
                pb_expr.atom().content_case() == pb::Atom::kSymbol) {
                // Create a modified protobuf expression with mapped operator
                pb::Expression modified_pb_expr = pb_expr;
                std::string original_symbol = pb_expr.atom().symbol();
                std::string mapped_symbol = Expression::map_up_operator(original_symbol);
                modified_pb_expr.mutable_atom()->set_symbol(mapped_symbol);
                list_.emplace_back(modified_pb_expr, problem);
            } else {
                // Recursively process other elements
                list_.emplace_back(pb_expr, problem);
            }
        }
    }
}

// this method is used only during the initialization of the Expression object
// to resolve a type expressed as a string, to the type instantiation
// basically, 
const Type* Expression::resolve_type(const std::string& type_str, const Problem* problem) const {
    if (type_str.empty()) {
        return nullptr;
    }
    
    // If we have a Problem context, try to find the type
    if (problem) {
        // First try the exact type name
        const Type* found_type = problem->find_type(type_str);
        if (found_type) {
            return found_type;
        }
        
        // Handle type name mappings for compatibility
        std::string mapped_type = type_str;
        if (type_str == "up:integer") {
            mapped_type = "up:int";
        } else if (type_str == "up:boolean") {
            mapped_type = "up:bool";
        }
        
        if (mapped_type != type_str) {
            found_type = problem->find_type(mapped_type);
            if (found_type) {
                return found_type;
            }
        }
    }
    
    // For primitive types, we might need to create/find them in a global registry
    // For now, return nullptr if not found in problem context
    return nullptr;
}

std::string Expression::to_string() const {
    std::ostringstream oss;
    
    if (is_atom()) {
        if (atom_.has_value()) {
            oss << atom_->to_string();
        } else {
            oss << "ATOM_NO_VALUE";
        }
    } else if (is_list()) {
        if (list_.empty()) {
            oss << "()";
        } else {
            oss << "(";
            for (size_t i = 0; i < list_.size(); ++i) {
                if (i > 0) oss << " ";
                oss << list_[i].to_string();
            }
            oss << ")";
        }
    } else {
        oss << "EMPTY";
    }
    
    return oss.str();
}

bool Expression::operator==(const Expression& other) const {
    if (kind_ != other.kind_ || type_ != other.type_) {
        return false;
    }
    
    if (is_atom() && other.is_atom()) {
        return atom_ == other.atom_;
    } else if (is_list() && other.is_list()) {
        return list_ == other.list_;
    }
    
    return false;
}

bool Expression::is_and() const {
    // Handle list case: (and ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::AND;
    }
    // Handle atom case: expression is literally "and" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::AND;
    }
    return false;
}

bool Expression::is_or() const {
    // Handle list case: (or ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::OR;
    }
    // Handle atom case: expression is literally "or" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::OR;
    }
    return false;
}

bool Expression::is_not() const {
    // Handle list case: (not ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::NOT;
    }
    // Handle atom case: expression is literally "not" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::NOT;
    }
    return false;
}

bool Expression::is_implies() const {
    // Handle list case: (implies ...) or (=> ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::IMPLIES;
    }
    // Handle atom case: expression is literally "implies" or "=>" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::IMPLIES;
    }
    return false;
}

bool Expression::is_iff() const {
    // Handle list case: (iff ...) or (<=> ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::IFF;
    }
    // Handle atom case: expression is literally "iff" or "<=>" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::IFF;
    }
    return false;
}

bool Expression::is_equals() const {
    // Handle list case: (= ...) or (== ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::EQUALS;
    }
    // Handle atom case: expression is literally "=" or "==" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::EQUALS;
    }
    return false;
}

bool Expression::is_plus() const {
    // Handle list case: (+ ...) or (up:plus ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::PLUS;
    }
    // Handle atom case: expression is literally "+" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::PLUS;
    }
    return false;
}

bool Expression::is_minus() const {
    // Handle list case: (- ...) or (up:minus ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::MINUS;
    }
    // Handle atom case: expression is literally "-" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::MINUS;
    }
    return false;
}

bool Expression::is_multiply() const {
    // Handle list case: (* ...) or (up:times ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::MULTIPLY;
    }
    // Handle atom case: expression is literally "*" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::MULTIPLY;
    }
    return false;
}

bool Expression::is_divide() const {
    // Handle list case: (/ ...) or (up:div ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::DIVIDE;
    }
    // Handle atom case: expression is literally "/" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::DIVIDE;
    }
    return false;
}

bool Expression::is_less_than() const {
    // Handle list case: (< ...) or (up:lt ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::LESS_THAN;
    }
    // Handle atom case: expression is literally "<" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::LESS_THAN;
    }
    return false;
}

bool Expression::is_less_equal() const {
    // Handle list case: (<= ...) or (up:le ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::LESS_EQUAL;
    }
    // Handle atom case: expression is literally "<=" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::LESS_EQUAL;
    }
    return false;
}

bool Expression::is_greater_than() const {
    // Handle list case: (> ...) or (up:gt ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::GREATER_THAN;
    }
    // Handle atom case: expression is literally ">" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::GREATER_THAN;
    }
    return false;
}

bool Expression::is_greater_equal() const {
    // Handle list case: (>= ...) or (up:ge ...) - this is the common case in PDDL
    if (is_list() && !list_.empty() && list_[0].is_atom() && list_[0].value().is_symbol()) {
        return string_to_operator(list_[0].value().symbol()) == Operator::GREATER_EQUAL;
    }
    // Handle atom case: expression is literally ">=" (rare, but for completeness)
    if (is_atom() && atom_.has_value() && atom_->is_symbol()) {
        return string_to_operator(atom_->symbol()) == Operator::GREATER_EQUAL;
    }
    return false;
}

bool Expression::is_boolean_true() const {
    return is_atom() && atom_.has_value() && atom_->is_boolean() && atom_->boolean();
}

bool Expression::is_boolean_false() const {
    return is_atom() && atom_.has_value() && atom_->is_boolean() && !atom_->boolean();
}

} // namespace bp
