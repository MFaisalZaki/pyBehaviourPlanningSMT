#include "problem_normalizer.hpp"

namespace bp {

size_t normalize_delete_then_set(Problem& problem) {
    size_t removed = 0;
    std::vector<Action> normalized_actions;
    normalized_actions.reserve(problem.action_count());

    for (const Action& action : problem.actions()) {
        auto has_positive_effect = [&](const Expression& fluent) {
            for (const Effect& other : action.effects()) {
                const EffectExpression& other_expr = other.effect_expression();
                if (other_expr.kind() == EffectExpression::Kind::ASSIGN &&
                    other_expr.value().is_boolean_true() &&
                    other_expr.fluent() == fluent) {
                    return true;
                }
            }
            return false;
        };

        std::vector<Effect> clean_effects;
        clean_effects.reserve(action.effect_count());
        for (const Effect& effect : action.effects()) {
            const EffectExpression& effect_expr = effect.effect_expression();
            const bool is_delete_then_set =
                effect_expr.kind() == EffectExpression::Kind::ASSIGN &&
                effect_expr.value().is_boolean_false() &&
                has_positive_effect(effect_expr.fluent());
            if (is_delete_then_set) {
                ++removed;
            } else {
                clean_effects.push_back(effect);
            }
        }

        Action normalized = action;
        normalized.set_effects(clean_effects);
        normalized_actions.push_back(std::move(normalized));
    }

    if (removed > 0) {
        problem.set_actions(normalized_actions);
    }
    return removed;
}

} // namespace bp
