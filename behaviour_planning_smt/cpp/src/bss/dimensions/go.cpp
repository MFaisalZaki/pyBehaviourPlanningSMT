#include "../dimension.hpp"
#include "../../util/z3_utils.hpp"

namespace bp {

namespace {

/**
 * @brief Goal predicate ordering ('go').
 *
 * Each goal conjunct gets an integer landmark variable holding the first state
 * layer at which the conjunct becomes true (-100 when it never does). Pairwise
 * orderings of those landmarks, reified through an uninterpreted function into
 * 0/1 integers, form the behaviour.
 *
 * Encoder support: relies on per-conjunct goal layers (goal_predicate_vars),
 * which the "seq" encoder provides.
 */
class GoalOrderingDimension : public Dimension {
public:
    explicit GoalOrderingDimension(const Encoder& encoder) : Dimension("go") {
        require_encoder(encoder, "go", {"seq"});
        z3::context& ctx = encoder.ctx();
        const auto& predicate_vars = encoder.goal_predicate_vars();
        const auto& predicate_names = encoder.goal_predicate_names();

        // One landmark variable per goal conjunct: the first state layer at
        // which the conjunct holds, or -100 when it never does.
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
        z3::func_decl uf_gt =
            z3::function("goPredicateOrderingFn", int_sort, int_sort, ctx.bool_sort());
        for (size_t i = 0; i < landmark_vars.size(); ++i) {
            for (size_t j = i + 1; j < landmark_vars.size(); ++j) {
                const z3::expr& li = landmark_vars[i];
                const z3::expr& lj = landmark_vars[j];
                formula_.push_back((li >= lj) == (uf_gt(li, lj) == ctx.bool_val(true)));
                formula_.push_back((li < lj) == (uf_gt(li, lj) == ctx.bool_val(false)));

                std::string ordering_name =
                    "go-ordering-" + std::to_string(i) + "__after__" + std::to_string(j);
                z3::expr ordering_var = ctx.int_const(ordering_name.c_str());
                formula_.push_back(ordering_var ==
                                   z3::ite(uf_gt(li, lj), ctx.int_val(1), ctx.int_val(0)));
                ordering_vars_.push_back(ordering_var);
            }
        }
    }

    BehaviourValue evaluate(const z3::model& model) const override {
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

    // Hamming distance over the ordering vector: how many pairwise goal
    // orderings the two plans disagree on.
    double distance(const std::string& a, const std::string& b) const override {
        const size_t shared = std::min(a.size(), b.size());
        double differing = static_cast<double>(a.size() - shared + b.size() - shared);
        for (size_t i = 0; i < shared; ++i) {
            if (a[i] != b[i]) differing += 1.0;
        }
        return differing;
    }

private:
    std::vector<z3::expr> ordering_vars_;
};

} // namespace

static DimensionPlugin _go_plugin(
    "go",
    [](const Encoder& encoder, const std::string&, const DimensionContext&)
        -> std::unique_ptr<Dimension> {
        return std::make_unique<GoalOrderingDimension>(encoder);
    },
    "goal predicate ordering: in which order the goal conjuncts are achieved");

} // namespace bp
