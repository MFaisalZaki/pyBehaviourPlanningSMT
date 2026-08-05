#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

namespace bp {

namespace {

/**
 * @brief Numeric function values ('fn').
 *
 * Slices the final-state value of each listed numeric fluent into boxes of
 * width delta; the box index a plan ends in is its behaviour along that
 * fluent. The argument is the path to a functions file with
 * `(:function NAME MIN MAX DELTA)` entries.
 *
 * Encoder support: relies on final-state fluent variables
 * (fluent_var_at_last_state), provided by the "seq" encoder.
 */
class FunctionsDimension : public Dimension {
public:
    FunctionsDimension(const Encoder& encoder, const std::vector<RangeEntry>& functions)
        : Dimension("fn") {
        require_encoder(encoder, "fn", {"seq"});
        z3::context& ctx = encoder.ctx();

        for (const auto& function : functions) {
            auto fluent_var = encoder.fluent_var_at_last_state(function.name);
            if (!fluent_var) continue; // silently skip names that match no fluent

            const z3::expr& value = *fluent_var;
            std::vector<z3::expr> boxes;
            for (long low = function.min; low < function.max - function.delta;
                 low += function.delta) {
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

    BehaviourValue evaluate(const z3::model& model) const override {
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

private:
    std::vector<std::pair<std::string, z3::expr>> function_vars_;
};

} // namespace

static DimensionPlugin _fn_plugin(
    "fn",
    [](const Encoder& encoder, const std::string& argument, const DimensionContext&)
        -> std::unique_ptr<Dimension> {
        return std::make_unique<FunctionsDimension>(
            encoder, parse_range_file(argument, "function"));
    },
    "numeric function values: which value box each fluent from the file ARG ends in");

} // namespace bp
