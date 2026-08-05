#pragma once

#include <z3++.h>
#include <vector>

namespace bp {

/// Or over a plain vector; false when empty.
inline z3::expr mk_or_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(false);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_or(vec);
}

/// And over a plain vector; true when empty.
inline z3::expr mk_and_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(true);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_and(vec);
}

/// Integer sum over a plain vector; 0 when empty.
inline z3::expr sum_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.int_val(0);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::sum(vec);
}

/// Pseudo-boolean equality: exactly one of `exprs` is true.
inline z3::expr exactly_one(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    std::vector<int> coeffs(exprs.size(), 1);
    return z3::pbeq(vec, coeffs.data(), 1);
}

/// At most one of `exprs` is true.
inline z3::expr at_most_one(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::atmost(vec, 1);
}

/// Numeral of `value` in the sort of `var` (int or real), so comparisons stay
/// well-sorted regardless of how a fluent was typed.
inline z3::expr numeral_like(const z3::expr& var, long value) {
    z3::context& ctx = var.ctx();
    if (var.is_real()) return ctx.real_val(static_cast<int64_t>(value));
    return ctx.int_val(static_cast<int64_t>(value));
}

} // namespace bp
