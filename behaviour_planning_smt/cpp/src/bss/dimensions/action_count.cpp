#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

#include <stdexcept>

namespace bp {

namespace {

/**
 * @brief Action count ('ac') — the example plugin dimension.
 *
 * Counts how many actions whose grounded name contains the argument the plan
 * uses, so plans that, say, drive around a lot and plans that drive as little
 * as possible count as different behaviours:
 *
 *     --dim ac:navigate
 *
 * This file is the template for writing your own dimension (see
 * tutorials/06_custom_dimension.py): a class implementing the two-method
 * contract plus a DimensionPlugin registrar, compiled into the planner by one
 * CMakeLists.txt entry. Nothing else in the code base mentions it.
 */
class ActionCountDimension : public Dimension {
public:
    ActionCountDimension(const Encoder& encoder, const std::string& name_fragment)
        : Dimension("ac") {
        // It is the dimension's responsibility to know the encoders it
        // supports: counting per-step booleans is how "seq" counts actions.
        require_encoder(encoder, "ac", {"seq"});
        if (name_fragment.empty()) {
            throw std::invalid_argument(
                "The 'ac' dimension needs an action-name fragment, e.g. --dim ac:navigate");
        }
        z3::context& ctx = encoder.ctx();

        std::vector<z3::expr> flags;
        for (const z3::expr& action_var : encoder.action_vars_matching(name_fragment)) {
            flags.push_back(z3::ite(action_var, ctx.int_val(1), ctx.int_val(0)));
        }
        if (flags.empty()) {
            throw std::invalid_argument("No grounded action name contains '" + name_fragment +
                                        "' for the 'ac' dimension.");
        }

        z3::expr count = ctx.int_const(("ac-" + name_fragment).c_str());
        count_var_ = count;
        formula_.push_back(count == sum_vec(ctx, flags));
    }

    BehaviourValue evaluate(const z3::model& model) const override {
        z3::expr count_value = model.eval(*count_var_, true);
        return {*count_var_ == count_value, count_value.get_decimal_string(0)};
    }

    // Counts compare by absolute difference.
    double distance(const std::string& a, const std::string& b) const override {
        return numeric_distance(a, b);
    }

private:
    std::optional<z3::expr> count_var_;
};

} // namespace

static DimensionPlugin _ac_plugin(
    "ac",
    [](const Encoder& encoder, const std::string& argument, const DimensionContext&)
        -> std::unique_ptr<Dimension> {
        return std::make_unique<ActionCountDimension>(encoder, argument);
    },
    "action count (example plugin): how many actions whose grounded name contains ARG "
    "the plan uses");

} // namespace bp
