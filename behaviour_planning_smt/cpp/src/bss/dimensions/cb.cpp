#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

#include <stdexcept>

namespace bp {

namespace {

/**
 * @brief Makespan-optimal cost bound ('cb').
 *
 * The plan cost is the number of non-empty steps. For regular tasks the cost
 * is bounded below by the optimal plan length; for oversubscription tasks it
 * is instead capped by quality_bound * optimal_plan_length, which also caps
 * the horizon and disables all later steps.
 *
 * Encoder support: how "cost" is counted depends on the encoder's execution
 * semantics, so this dimension branches on encoder.name(). Under "seq" every
 * step holds at most one action, so counting non-empty steps counts actions.
 * A parallel encoder would need its own branch here that sums action
 * variables instead of steps.
 */
class CostBoundDimension : public Dimension {
public:
    CostBoundDimension(const Encoder& encoder, double quality_bound, int optimal_plan_length)
        : Dimension("cb") {
        if (encoder.name() == "seq") {
            encode_for_seq(encoder, quality_bound, optimal_plan_length);
        } else {
            // Reached only when a new encoder plugin exists but this dimension
            // has not been taught its execution semantics yet.
            require_encoder(encoder, "cb", {"seq"});
        }
    }

    BehaviourValue evaluate(const z3::model& model) const override {
        z3::expr cost_value = model.eval(*cost_var_, true);
        return {*cost_var_ == cost_value, cost_value.get_decimal_string(0)};
    }

private:
    void encode_for_seq(const Encoder& encoder, double quality_bound, int optimal_plan_length) {
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
            // Oversubscription: the quality bound becomes a budget on the
            // number of actions the plan may spend collecting utility.
            const int cost_bound_step = static_cast<int>(quality_bound * optimal_plan_length);
            formula_.push_back(cost <= ctx.int_val(cost_bound_step));
            formula_.push_back(encoder.horizon_expr() <= ctx.int_val(cost_bound_step));
            for (int t = cost_bound_step; t < layers; ++t) {
                formula_.push_back(!mk_or_vec(ctx, encoder.action_vars_at(t)));
            }
        }
    }

    std::optional<z3::expr> cost_var_;
};

} // namespace

static DimensionPlugin _cb_plugin(
    "cb",
    [](const Encoder& encoder, const std::string& argument, const DimensionContext& context)
        -> std::unique_ptr<Dimension> {
        // The argument is the quality bound; it also reaches the planner as
        // context.quality_bound because it scales the formula length.
        double quality_bound = context.quality_bound;
        if (!argument.empty()) {
            try {
                quality_bound = std::stod(argument);
            } catch (const std::exception&) {
                throw std::invalid_argument("The 'cb' dimension expects a numeric quality "
                                            "bound, got '" + argument + "'");
            }
        }
        return std::make_unique<CostBoundDimension>(encoder, quality_bound,
                                                    context.optimal_plan_length);
    },
    "makespan-optimal cost bound: the plan cost, bounded by ARG * optimal length "
    "(ARG is the quality bound, default 1.0)");

} // namespace bp
