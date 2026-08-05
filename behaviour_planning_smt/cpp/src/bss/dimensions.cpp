#include "dimension.hpp"
#include "../util/logger.hpp"

#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace bp {

namespace {

z3::expr mk_or_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(false);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_or(vec);
}

z3::expr mk_and_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.bool_val(true);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::mk_and(vec);
}

z3::expr sum_vec(z3::context& ctx, const std::vector<z3::expr>& exprs) {
    if (exprs.empty()) return ctx.int_val(0);
    z3::expr_vector vec(ctx);
    for (const auto& e : exprs) vec.push_back(e);
    return z3::sum(vec);
}

// Numeral of `value` in the sort of `var` (int or real), so comparisons stay
// well-sorted regardless of how the fluent was typed.
z3::expr numeral_like(const z3::expr& var, long value) {
    z3::context& ctx = var.ctx();
    if (var.is_real()) return ctx.real_val(static_cast<int64_t>(value));
    return ctx.int_val(static_cast<int64_t>(value));
}

} // namespace

// ---------------------------------------------------------------------------
// Goal predicate ordering ('go')
// ---------------------------------------------------------------------------

GoalOrderingDimension::GoalOrderingDimension(const BoundedSeqEncoder& encoder)
    : Dimension("go") {
    z3::context& ctx = encoder.ctx();
    const auto& predicate_vars = encoder.goal_predicate_vars();
    const auto& predicate_names = encoder.goal_predicate_names();

    // One landmark variable per goal conjunct: the first state layer at which
    // the conjunct holds, or -100 when it never does.
    std::vector<z3::expr> landmark_vars;
    for (size_t i = 0; i < predicate_vars.size(); ++i) {
        const auto& states = predicate_vars[i];
        std::string label = i < predicate_names.size() ? predicate_names[i] : "conjunct";
        z3::expr landmark = ctx.int_const(("go-" + std::to_string(i) + "-" + label).c_str());
        landmark_vars.push_back(landmark);

        for (size_t idx = 0; idx < states.size(); ++idx) {
            std::vector<z3::expr> first_here;
            first_here.push_back(states[idx]);
            for (size_t j = 0; j < idx; ++j) {
                first_here.push_back(!states[j]);
            }
            formula_.push_back(mk_and_vec(ctx, first_here) ==
                               (landmark == ctx.int_val(static_cast<int>(idx) + 1)));
        }
        std::vector<z3::expr> never;
        for (const auto& state : states) never.push_back(!state);
        formula_.push_back(mk_and_vec(ctx, never) == (landmark == ctx.int_val(-100)));
    }

    // Pairwise orderings reified through an uninterpreted function, then
    // materialized as 0/1 integers that form the behaviour.
    z3::sort int_sort = ctx.int_sort();
    z3::func_decl uf_gt = z3::function("goPredicateOrderingFn", int_sort, int_sort, ctx.bool_sort());
    for (size_t i = 0; i < landmark_vars.size(); ++i) {
        for (size_t j = i + 1; j < landmark_vars.size(); ++j) {
            const z3::expr& li = landmark_vars[i];
            const z3::expr& lj = landmark_vars[j];
            formula_.push_back((li >= lj) == (uf_gt(li, lj) == ctx.bool_val(true)));
            formula_.push_back((li < lj) == (uf_gt(li, lj) == ctx.bool_val(false)));

            std::string ordering_name = "go-ordering-" + std::to_string(i) + "__after__" + std::to_string(j);
            z3::expr ordering_var = ctx.int_const(ordering_name.c_str());
            formula_.push_back(ordering_var ==
                               z3::ite(uf_gt(li, lj), ctx.int_val(1), ctx.int_val(0)));
            ordering_vars_.push_back(ordering_var);
        }
    }
}

Dimension::BehaviourValue GoalOrderingDimension::evaluate(const z3::model& model) const {
    if (ordering_vars_.empty()) {
        return {std::nullopt, ""};
    }
    z3::context& ctx = ordering_vars_.front().ctx();
    std::vector<z3::expr> pinned;
    std::string value;
    for (const auto& ordering_var : ordering_vars_) {
        z3::expr ordering_value = model.eval(ordering_var, true);
        pinned.push_back(ordering_var == ordering_value);
        value += ordering_value.get_decimal_string(0);
    }
    return {mk_and_vec(ctx, pinned), value};
}

// ---------------------------------------------------------------------------
// Makespan-optimal cost bound ('cb')
// ---------------------------------------------------------------------------

CostBoundDimension::CostBoundDimension(const BoundedSeqEncoder& encoder, double quality_bound,
                                       int optimal_plan_length)
    : Dimension("cb") {
    z3::context& ctx = encoder.ctx();
    const int layers = encoder.size(); // formula_length + 1, mirrors len(encoder)

    std::vector<z3::expr> step_costs;
    for (int t = 0; t < layers; ++t) {
        z3::expr step_cost = ctx.int_const(("step_" + std::to_string(t) + "_cost").c_str());
        step_costs.push_back(step_cost);
        formula_.push_back(step_cost == z3::ite(mk_or_vec(ctx, encoder.action_vars_at(t)),
                                                ctx.int_val(1), ctx.int_val(0)));
    }

    z3::expr cost = ctx.int_const("makespan-optimal-cost");
    cost_var_ = cost;
    formula_.push_back(cost == sum_vec(ctx, step_costs));

    // Bound the plan cost by the number of layers.
    formula_.push_back(cost < ctx.int_val(layers));

    if (!encoder.is_oversubscription()) {
        formula_.push_back(cost >= ctx.int_val(optimal_plan_length));
    } else {
        // Oversubscription: the quality bound becomes a budget on the number
        // of actions the plan may spend collecting utility.
        const int cost_bound_step = static_cast<int>(quality_bound * optimal_plan_length);
        formula_.push_back(cost <= ctx.int_val(cost_bound_step));
        formula_.push_back(encoder.horizon_expr() <= ctx.int_val(cost_bound_step));
        for (int t = cost_bound_step; t < layers; ++t) {
            formula_.push_back(!mk_or_vec(ctx, encoder.action_vars_at(t)));
        }
    }
}

Dimension::BehaviourValue CostBoundDimension::evaluate(const z3::model& model) const {
    z3::expr cost_value = model.eval(*cost_var_, true);
    return {*cost_var_ == cost_value, cost_value.get_decimal_string(0)};
}

// ---------------------------------------------------------------------------
// Resource usage count ('ru')
// ---------------------------------------------------------------------------

ResourceCountDimension::ResourceCountDimension(const BoundedSeqEncoder& encoder,
                                               const std::vector<RangeEntry>& resources)
    : Dimension("ru") {
    z3::context& ctx = encoder.ctx();

    std::vector<z3::expr> per_resource;
    for (const auto& resource : resources) {
        std::vector<z3::expr> action_vars = encoder.action_vars_matching(resource.name);
        if (action_vars.empty()) continue; // resources matching no action are dropped

        z3::expr used = ctx.int_const(("ru-" + resource.name).c_str());
        formula_.push_back(used == z3::ite(mk_or_vec(ctx, action_vars),
                                           ctx.int_val(1), ctx.int_val(0)));
        per_resource.push_back(used);
    }

    z3::expr count = ctx.int_const("ru");
    count_var_ = count;
    formula_.push_back(count == sum_vec(ctx, per_resource));
}

Dimension::BehaviourValue ResourceCountDimension::evaluate(const z3::model& model) const {
    z3::expr count_value = model.eval(*count_var_, true);
    return {*count_var_ == count_value, count_value.get_decimal_string(0)};
}

// ---------------------------------------------------------------------------
// Utility value ('uv')
// ---------------------------------------------------------------------------

UtilityValueDimension::UtilityValueDimension(const BoundedSeqEncoder& encoder)
    : Dimension("uv") {
    if (!encoder.is_oversubscription() || encoder.utility_goals().empty()) {
        throw std::invalid_argument(
            "The 'uv' dimension requires an oversubscription task whose metric assigns a utility per goal.");
    }
    z3::context& ctx = encoder.ctx();

    std::vector<z3::expr> per_goal;
    for (const auto& goal : encoder.utility_goals()) {
        z3::expr utility = ctx.int_const(("utility-" + goal.name).c_str());
        z3::expr weight = goal.weight.denominator() == 1
                              ? ctx.int_val(static_cast<int64_t>(goal.weight.numerator()))
                              : ctx.real_val(static_cast<int64_t>(goal.weight.numerator()),
                                             static_cast<int64_t>(goal.weight.denominator()));
        formula_.push_back(utility == z3::ite(goal.at_last_state, weight, ctx.int_val(0)));
        per_goal.push_back(utility);
    }

    z3::expr total = ctx.int_const("utility");
    utility_var_ = total;
    formula_.push_back(total == sum_vec(ctx, per_goal));
    formula_.push_back(total > ctx.int_val(0));
}

Dimension::BehaviourValue UtilityValueDimension::evaluate(const z3::model& model) const {
    z3::expr utility_value = model.eval(*utility_var_, true);
    return {*utility_var_ == utility_value, utility_value.get_decimal_string(0)};
}

// ---------------------------------------------------------------------------
// Numeric function values ('fn')
// ---------------------------------------------------------------------------

FunctionsDimension::FunctionsDimension(const BoundedSeqEncoder& encoder,
                                       const std::vector<RangeEntry>& functions)
    : Dimension("fn") {
    z3::context& ctx = encoder.ctx();

    for (const auto& function : functions) {
        auto fluent_var = encoder.fluent_var_at_last_state(function.name);
        if (!fluent_var) continue; // silently skip names that match no fluent

        const z3::expr& value = *fluent_var;
        std::vector<z3::expr> boxes;
        for (long low = function.min; low < function.max - function.delta; low += function.delta) {
            boxes.push_back(value >= numeral_like(value, low) &&
                            value < numeral_like(value, low + function.delta));
        }
        boxes.push_back(value >= numeral_like(value, function.max - function.delta) &&
                        value <= numeral_like(value, function.max));

        z3::expr box_var = ctx.int_const(("fn-box-" + function.name).c_str());
        for (size_t idx = 0; idx < boxes.size(); ++idx) {
            formula_.push_back(boxes[idx] == (box_var == ctx.int_val(static_cast<int>(idx))));
        }
        formula_.push_back(box_var >= ctx.int_val(static_cast<int64_t>(function.min)));
        formula_.push_back(box_var <= ctx.int_val(static_cast<int64_t>(function.max)));

        function_vars_.emplace_back(function.name, box_var);
    }
}

Dimension::BehaviourValue FunctionsDimension::evaluate(const z3::model& model) const {
    if (function_vars_.empty()) {
        return {std::nullopt, ""};
    }
    z3::context& ctx = function_vars_.front().second.ctx();
    std::vector<z3::expr> pinned;
    std::string value;
    for (const auto& [fluent_name, box_var] : function_vars_) {
        z3::expr box_value = model.eval(box_var, true);
        pinned.push_back(box_var == box_value);
        if (!value.empty()) value += ";";
        value += fluent_name + "=" + box_value.get_decimal_string(0);
    }
    return {mk_and_vec(ctx, pinned), value};
}

// ---------------------------------------------------------------------------
// Resources / functions file parser
// ---------------------------------------------------------------------------

std::vector<RangeEntry> parse_range_file(const std::string& path, const std::string& keyword) {
    std::ifstream input(path);
    if (!input) {
        throw std::invalid_argument("Cannot open file: " + path);
    }
    std::stringstream buffer;
    buffer << input.rdbuf();
    const std::string content = buffer.str();

    std::vector<RangeEntry> entries;
    std::unordered_map<std::string, size_t> position_of;

    size_t pos = 0;
    auto skip_whitespace = [&]() {
        while (pos < content.size() && std::isspace(static_cast<unsigned char>(content[pos]))) ++pos;
    };
    auto expect = [&](char c) {
        skip_whitespace();
        if (pos >= content.size() || content[pos] != c) {
            throw std::invalid_argument("Malformed entry in " + path + ": expected '" +
                                        std::string(1, c) + "'");
        }
        ++pos;
    };
    auto read_token = [&]() -> std::string {
        skip_whitespace();
        size_t start = pos;
        int parenthesis_depth = 0;
        while (pos < content.size()) {
            char c = content[pos];
            if (c == '(') { ++parenthesis_depth; ++pos; continue; }
            if (c == ')') {
                if (parenthesis_depth == 0) break;
                --parenthesis_depth; ++pos; continue;
            }
            if (std::isspace(static_cast<unsigned char>(c)) && parenthesis_depth == 0) break;
            ++pos;
        }
        return content.substr(start, pos - start);
    };

    const std::string entry_keyword = ":" + keyword;
    while (true) {
        skip_whitespace();
        if (pos >= content.size()) break;
        expect('(');
        std::string head = read_token();
        if (head != entry_keyword) {
            throw std::invalid_argument("Malformed entry in " + path + ": expected '" +
                                        entry_keyword + "', found '" + head + "'");
        }
        RangeEntry entry;
        entry.name = read_token();
        try {
            entry.min = std::stol(read_token());
            entry.max = std::stol(read_token());
            entry.delta = std::stol(read_token());
        } catch (const std::exception&) {
            throw std::invalid_argument("Malformed numeric field in " + path + " for entry '" +
                                        entry.name + "'");
        }
        expect(')');

        auto seen = position_of.find(entry.name);
        if (seen != position_of.end()) {
            entries[seen->second] = entry; // keep the original position, take the latest values
        } else {
            position_of[entry.name] = entries.size();
            entries.push_back(entry);
        }
    }

    if (entries.empty()) {
        throw std::invalid_argument("No (" + entry_keyword + " ...) entries found in " + path);
    }
    return entries;
}

} // namespace bp
