#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

#include <stdexcept>

namespace bp {

namespace {

/**
 * @brief Utility value ('uv').
 *
 * Requires an oversubscription task: sums the weights of the metric goals that
 * hold in the final state and requires the total to be positive.
 *
 * Encoder support: relies on the weighted goals evaluated at the last state
 * layer (utility_goals), provided by the "seq" encoder.
 */
class UtilityValueDimension : public Dimension {
public:
    explicit UtilityValueDimension(const Encoder& encoder) : Dimension("uv") {
        require_encoder(encoder, "uv", {"seq"});
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

    BehaviourValue evaluate(const z3::model& model) const override {
        z3::expr utility_value = model.eval(*utility_var_, true);
        return {*utility_var_ == utility_value, utility_value.get_decimal_string(0)};
    }

private:
    std::optional<z3::expr> utility_var_;
};

} // namespace

static DimensionPlugin _uv_plugin(
    "uv",
    [](const Encoder& encoder, const std::string&, const DimensionContext&)
        -> std::unique_ptr<Dimension> {
        return std::make_unique<UtilityValueDimension>(encoder);
    },
    "utility value: the total utility the plan collects (oversubscription tasks only)");

} // namespace bp
