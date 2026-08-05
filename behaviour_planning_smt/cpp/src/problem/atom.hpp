// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <variant>
#include "protobuf_aliases.hpp"
#include "real.hpp"

namespace bp {

/**
 * @brief Atom
 * 
 * Can hold a symbol, integer, real number, or boolean value.
 */
class Atom {
public:
    // Value types that an atom can hold
    using Value = std::variant<std::string, int64_t, Real, bool>;
    
    // Constructors
    Atom() : value_(std::string("")) {}
    Atom(const std::string& symbol) : value_(symbol) {}
    Atom(const char* symbol) : value_(std::string(symbol)) {}
    Atom(int64_t integer) : value_(integer) {}
    Atom(int integer) : value_(static_cast<int64_t>(integer)) {}
    Atom(const Real& real) : value_(real) {}
    Atom(double real) : value_(Real(real)) {}
    Atom(bool boolean) : value_(boolean) {}
    Atom(const pb::Atom& pb_atom);
    
    // Type checkers
    bool is_symbol() const { return std::holds_alternative<std::string>(value_); }
    bool is_integer() const { return std::holds_alternative<int64_t>(value_); }
    bool is_real() const { return std::holds_alternative<Real>(value_); }
    bool is_boolean() const { return std::holds_alternative<bool>(value_); }

    // Boolean value checkers
    bool is_true() const { return is_boolean() && boolean(); }
    bool is_false() const { return is_boolean() && !boolean(); }
    
    // Value getters
    const std::string& symbol() const { return std::get<std::string>(value_); }
    int64_t integer() const { return std::get<int64_t>(value_); }
    const Real& real() const { return std::get<Real>(value_); }
    bool boolean() const { return std::get<bool>(value_); }
    
    // String representation
    std::string to_string() const;
    
    // Operators
    bool operator==(const Atom& other) const { return value_ == other.value_; }
    bool operator!=(const Atom& other) const { return !(*this == other); }

private:
    Value value_;
};

} // namespace bp
