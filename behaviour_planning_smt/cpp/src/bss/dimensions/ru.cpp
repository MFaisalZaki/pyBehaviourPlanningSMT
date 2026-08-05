#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

namespace bp {

namespace {

/**
 * @brief Resource usage count ('ru').
 *
 * A resource is used when any grounded action whose name contains the resource
 * name appears in the plan; the behaviour is the number of used resources.
 * The argument is the path to a resources file with
 * `(:resource NAME MIN MAX DELTA)` entries — only the names are read.
 *
 * Encoder support: only needs per-step action variables, currently provided
 * by the "seq" encoder.
 */
class ResourceCountDimension : public Dimension {
public:
    ResourceCountDimension(const Encoder& encoder, const std::vector<RangeEntry>& resources)
        : Dimension("ru") {
        require_encoder(encoder, "ru", {"seq"});
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

static DimensionPlugin _ru_plugin(
    "ru",
    [](const Encoder& encoder, const std::string& argument, const DimensionContext&)
        -> std::unique_ptr<Dimension> {
        return std::make_unique<ResourceCountDimension>(
            encoder, parse_range_file(argument, "resource"));
    },
    "resource usage count: how many resources from the file ARG the plan uses "
    "(names matched as substrings of grounded action names)");

} // namespace bp
