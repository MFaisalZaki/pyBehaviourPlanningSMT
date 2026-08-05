// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "relaxed_planning_graph.hpp"
#include "../config/config.hpp"
#include "../util/memory_tracker.hpp"
#include "../util/scoped_timer.hpp"
#include "../util/logger.hpp"
#include "../util/stats.hpp"
#include <iostream>
#include <iomanip>
#include <algorithm>
#include <sstream>

namespace bp {

// Static member definitions
const std::vector<const Action*> RelaxedPlanningGraph::empty_action_vector_;
const std::unordered_set<int> RelaxedPlanningGraph::empty_condition_set_;

RelaxedPlanningGraph::RelaxedPlanningGraph(Problem& problem)
    : problem_(problem), build_time_ms_(0.0) {
    extract_goal_conditions();
}

void RelaxedPlanningGraph::reset() {
    fact_layers_.clear();
    action_layers_.clear();
    achievability_layer_.clear();
}


bool RelaxedPlanningGraph::build() {
    auto& config = Config::instance();
    ScopedTimer timer("rpg.boolean.build_time_ms");
    double start_memory = MemoryTracker::instance().get_current_memory_mb();

    reset();
    initialize_fact_layer();

    // Boolean RPG must always run to fixpoint for soundness
    // (it uses syntactic relaxation which is less precise than numeric bounds)
    // Build layers until fixpoint (with safety limit)
    const int MAX_RPG_LAYERS = 100; // Prevent infinite expansion
    while (!is_fixpoint_reached() && fact_layers_.size() < MAX_RPG_LAYERS) {
        int current_layer = fact_layers_.size() - 1;

        // Compute applicable actions
        auto applicable_actions = compute_applicable_actions(current_layer);
        action_layers_.push_back(std::move(applicable_actions));

        // Early termination if no actions are applicable
        if (action_layers_[current_layer].empty()) {
            break; // Fixpoint reached - no new actions can be applied
        }

        // Create next fact layer - copy all facts from current layer
        fact_layers_.emplace_back(fact_layers_[current_layer]);
        int next_layer = fact_layers_.size() - 1;

        // Add effects of applicable actions
        for (const Action* action : action_layers_[current_layer]) {
            add_effects_to_layer(*action, next_layer);
        }

        // Boolean RPG continues to fixpoint - no early termination
        // (early termination is only sound for the more precise Numeric RPG)
    }

    build_time_ms_ = timer.elapsed_ms();
    double end_memory = MemoryTracker::instance().get_current_memory_mb();
    double memory_used = end_memory - start_memory;

    bool goals_reachable = are_goals_achievable();

    // Count reachable actions
    int total_actions = problem_.action_count();
    std::unordered_set<const Action*> reachable_action_set;
    for (const auto& layer : action_layers_) {
        for (const Action* action : layer) {
            reachable_action_set.insert(action);
        }
    }
    int reachable_actions = reachable_action_set.size();
    int removed_actions = total_actions - reachable_actions;

    // Record to Stats
    Stats::instance().set("rpg.boolean.total_layers", fact_layers_.size());
    Stats::instance().set("rpg.boolean.total_actions", total_actions);
    Stats::instance().set("rpg.boolean.reachable_actions", reachable_actions);
    Stats::instance().set("rpg.boolean.removed_actions", removed_actions);
    Stats::instance().set("rpg.boolean.memory_mb", memory_used);
    Stats::instance().set("rpg.boolean.goals_reachable", goals_reachable ? 1.0 : 0.0);

    // Structured visual output
    std::ostringstream actions_str;
    actions_str << total_actions << " (" << reachable_actions << " reachable, " << removed_actions << " removed)";

    Logger::instance().component(VerbosityLevel::INFO, "RPG.Boolean", {
        {"time", std::to_string(static_cast<int>(build_time_ms_)) + "ms"},
        {"layers", std::to_string(fact_layers_.size())},
        {"actions", actions_str.str()},
        {"mem", std::to_string(static_cast<int>(memory_used)) + "MB"},
        {"goals", goals_reachable ? "REACHABLE" : "UNREACHABLE"}
    });

    //print_debug_info();
    //print_reachability_analysis();

    return goals_reachable;
}

void RelaxedPlanningGraph::initialize_fact_layer() {
    fact_layers_.emplace_back();

    // Process all initial assignments (complete initial state)
    for (size_t i = 0; i < problem_.initial_assignment_count(); ++i) {
        const auto& assignment = problem_.initial_assignment(i);
        int fluent_id = find_grounded_fluent_id(assignment.fluent());

        if (fluent_id == -1) continue;

        const auto& value = assignment.value();
        assert(value.is_atom() && "Initial assignment value must be an atom");

        if (value.value().is_true()) {
            // Boolean fluent set to true: add positive fact
            fact_layers_[0].insert(fluent_id);
            achievability_layer_[fluent_id] = 0;
        } else if (value.value().is_false()) {
            // Boolean fluent set to false: add negative fact
            int negative_fluent_id = encode_negative_fact_id(fluent_id);
            fact_layers_[0].insert(negative_fluent_id);
            achievability_layer_[negative_fluent_id] = 0;
        } else {
            // Numeric fluent: always add as positive fact
            fact_layers_[0].insert(fluent_id);
            achievability_layer_[fluent_id] = 0;
        }
    }
}

bool RelaxedPlanningGraph::is_achievable(const Expression& condition) const {
    int fluent_id = find_grounded_fluent_id(condition); // already handles numeric and negated
    return fluent_id != -1 && achievability_layer_.contains(fluent_id);
}

int RelaxedPlanningGraph::get_achievability_layer(const Expression& condition) const {
    int fluent_id = find_grounded_fluent_id(condition);
    if (fluent_id == -1) return -1;
    return achievability_layer_.contains(fluent_id) ? achievability_layer_.at(fluent_id) : -1;
}

const std::vector<const Action*>& RelaxedPlanningGraph::get_actions_in_layer(int layer) const {
    return action_layers_[layer];
}

const std::unordered_set<int>& RelaxedPlanningGraph::get_conditions_in_layer(int layer) const {
    return fact_layers_[layer];
}

bool RelaxedPlanningGraph::are_goals_achievable() const {
    // Check Boolean goals
    for (int goal_id : goal_condition_ids_) {
        if (!achievability_layer_.contains(goal_id)) {
            return false;
        }
    }

    // For numeric goals: assume all are achievable (since we can't map them to fluent IDs)
    // This is consistent with the relaxed planning graph optimistic approach
    return true;
}

void RelaxedPlanningGraph::extract_goal_conditions() {
    goal_condition_ids_.clear();
    for (size_t i = 0; i < problem_.goal_count(); ++i) {
        std::vector<const Expression*> conditions;
        extract_cnf_conditions(problem_.goal(i).goal_expression(), conditions);

        // Convert expressions to IDs
        for (const Expression* condition : conditions) {
            int goal_id = find_grounded_fluent_id(*condition);
            if (goal_id != -1) {
                goal_condition_ids_.push_back(goal_id);
            }
            // Note: Numeric conditions (like >= comparisons) are not stored as goal IDs
            // since they can't be mapped to grounded fluents. RPG only handles Boolean goals.
        }
    }
}

void RelaxedPlanningGraph::extract_cnf_conditions(const Expression& expr, std::vector<const Expression*>& conditions) const {
    if (expr.is_and()) {
        for (size_t i = 0; i < expr.list_size(); ++i) {
            extract_cnf_conditions(expr.list_element(i), conditions);
        }
    } else {
        if (!expr.is_function_symbol()) {
            conditions.push_back(&expr);
        }
    }
}

std::vector<const Action*> RelaxedPlanningGraph::compute_applicable_actions(int layer_index) const {
    std::vector<const Action*> applicable;
    for (const auto & action : problem_.actions()) {
        if (are_preconditions_satisfied(action, layer_index)) {
            //     std::cout << "Action " << action.name() << ": " << (satisfied ? "APPLICABLE" : "NOT APPLICABLE") << std::endl;
            applicable.push_back(&action);
        }
    }
    return applicable;
}

bool RelaxedPlanningGraph::are_preconditions_satisfied(const Action& action, int layer_index) const {
    if (!action.has_precondition()) {
        return true;
    }

    std::vector<const Expression*> preconditions;
    extract_cnf_conditions(action.precondition(), preconditions);

    for (const Expression* precond : preconditions) {
        if (!is_condition_satisfied(*precond, layer_index)) {
            //     std::cout << "  Precondition '" << precond->to_string() << "': " << (satisfied ? "SATISFIED" : "NOT SATISFIED") << std::endl;
            return false;
        }
    }
    return true;
}

bool RelaxedPlanningGraph::is_condition_satisfied(const Expression& condition, int layer_index) const {
    // Handle Boolean conditions (positive and negative)
    if (condition.is_bool_type() || condition.is_not()) {
        return is_fact_in_layer(condition, layer_index);
    }

    // For numeric conditions: assume always satisfiable in relaxed planning graph
    return true;
}

void RelaxedPlanningGraph::add_effects_to_layer(const Action& action, int target_layer_index) {
    for (size_t i = 0; i < action.effect_count(); ++i) {
        const Effect& effect = action.effect(i);

        // For conditional and quantified effects in RPG: check conditions before applying
        if (effect.is_conditional()) {
            std::vector<const Expression*> conditions;
            extract_cnf_conditions(effect.condition(), conditions);

            // Check if all conditions are satisfied in the previous layer
            bool all_conditions_satisfied = true;
            for (const Expression* condition : conditions) {
                if (!is_condition_satisfied(*condition, target_layer_index - 1)) {
                    all_conditions_satisfied = false;
                    break;
                }
            }

            // Only apply the effect if all conditions are satisfied
            if (all_conditions_satisfied) {
                add_simple_effect_to_layer(effect, target_layer_index);
            }
        } else {
            // Handle simple atomic effects as before
            add_simple_effect_to_layer(effect, target_layer_index);
        }
    }
}

void RelaxedPlanningGraph::add_simple_effect_to_layer(const Effect& effect, int target_layer_index) {
    const Expression& fluent = effect.fluent();

    // Handle both positive and negative Boolean effects
    if (effect.value().is_atom() && effect.value().value().is_boolean()) {
        int fluent_id = find_grounded_fluent_id(fluent);
        assert(fluent_id != -1 && "Effect fluent not recognised");
        if (effect.value().value().boolean()) {
            // Positive effect: add the positive fact
            fact_layers_[target_layer_index].insert(fluent_id);
            if (achievability_layer_.find(fluent_id) == achievability_layer_.end()) {
                achievability_layer_[fluent_id] = target_layer_index;
            }
        } else {
            // Negative effect: add the negative fact
            int negative_fluent_id = encode_negative_fact_id(fluent_id);
            fact_layers_[target_layer_index].insert(negative_fluent_id);
            if (achievability_layer_.find(negative_fluent_id) == achievability_layer_.end()) {
                achievability_layer_[negative_fluent_id] = target_layer_index;
            }
        }
    } else if (effect.value().is_atom() && !effect.value().value().is_boolean()) {
        // Numeric effect - add the fluent as potentially modified
        int fluent_id = find_grounded_fluent_id(fluent);
        assert(fluent_id != -1 && "Effect fluent not recognised");
        fact_layers_[target_layer_index].insert(fluent_id);

            // Track achievability (first occurrence only)
            if (achievability_layer_.find(fluent_id) == achievability_layer_.end()) {
                achievability_layer_[fluent_id] = target_layer_index;
            }
        }
    }

bool RelaxedPlanningGraph::is_fixpoint_reached() const {
    if (fact_layers_.size() < 2) {
        return false;
    }

    // Check if last layer added any new facts (much simpler with IDs!)
    const auto& last_layer = fact_layers_.back();
    const auto& prev_layer = fact_layers_[fact_layers_.size() - 2];

    for (int fact_id : last_layer) {
        if (prev_layer.find(fact_id) == prev_layer.end()) {
            return false; // Found new fact
        }
    }

    return true; // No new facts added
}






int RelaxedPlanningGraph::find_grounded_fluent_id(const Expression& expr) const {
    // Handle negated expressions
    if (expr.is_not()) {
        const Expression& inner_condition = get_inner_condition(expr);
        // Use O(1) hash map lookup for the positive fluent ID and return the negative encoding
        int fluent_id = problem_.find_grounded_fluent_index(inner_condition);
        return (fluent_id != -1) ? encode_negative_fact_id(fluent_id) : -1;
    }

    // Handle positive expressions - use O(1) hash map lookup
    return problem_.find_grounded_fluent_index(expr);
}


const Expression& RelaxedPlanningGraph::get_inner_condition(const Expression& negated_condition) const {
    // For (not condition), return the condition being negated
    // The structure is: (not condition) where list_element(0) = 'not', list_element(1) = condition
    if (negated_condition.list_size() >= 2) {
        return negated_condition.list_element(1);
    } else {
        // Fallback to original behavior if structure is unexpected
        return negated_condition.list_element(0);
    }
}

bool RelaxedPlanningGraph::is_fact_in_layer(const Expression& condition, int layer_index) const {
    int fluent_id = find_grounded_fluent_id(condition);
    return fluent_id != -1 && fact_layers_[layer_index].contains(fluent_id);
}

int RelaxedPlanningGraph::get_minimum_steps_lower_bound() const {
    // Goals not achievable or RPG not built yet
    if (!are_goals_achievable() || fact_layers_.empty()) {
        return -1;
    }

    // Find the maximum layer where any goal condition first becomes achievable
    int max_goal_layer = 0;
    for (int goal_id : goal_condition_ids_) {
        auto it = achievability_layer_.find(goal_id);
        if (it != achievability_layer_.end()) {
            max_goal_layer = std::max(max_goal_layer, it->second);
        }
    }

    // Layer N means N steps are needed. i.e. Layer 0 = 0 steps, Layer 1 = 1 step, etc.
    return max_goal_layer;
}

std::vector<const Action*> RelaxedPlanningGraph::get_removable_actions() const {
    // Collect all actions that appear in any layer of the RPG
    std::unordered_set<const Action*> reachable_actions;
    for (const auto& layer : action_layers_) {
        for (const Action* action : layer) {
            reachable_actions.insert(action);
        }
    }

    // Find actions that never appear in any layer (safe to remove after fixpoint)
    // This is safe because:
    // 1. Actions with only numeric preconditions appear in layer 0 immediately
    // 2. Actions with mixed preconditions appear when Boolean parts are satisfied
    // 3. Actions that never appear have unsatisfiable Boolean preconditions
    std::vector<const Action*> removable_actions;
    for (size_t i = 0; i < problem_.action_count(); ++i) {
        const Action& action = problem_.action(i);
        if (reachable_actions.find(&action) == reachable_actions.end()) {
            removable_actions.push_back(&action);
        }
    }

    return removable_actions;
}

size_t RelaxedPlanningGraph::remove_unreachable_actions() {
    // Get actions that can be safely removed
    auto removable_actions = get_removable_actions();

    if (removable_actions.empty()) {
        return 0;
    }

    // Sort by index in descending order to maintain index validity during removal
    // We need to remove from highest index to lowest to avoid invalidating indices
    std::vector<size_t> indices_to_remove;
    for (const Action* action : removable_actions) {
        // Find the index of this action
        for (size_t i = 0; i < problem_.action_count(); ++i) {
            if (&problem_.action(i) == action) {
                indices_to_remove.push_back(i);
                break;
            }
        }
    }

    // Sort indices in descending order
    std::sort(indices_to_remove.begin(), indices_to_remove.end(), std::greater<size_t>());

    // Remove actions from highest index to lowest
    size_t removed_count = 0;
    for (size_t index : indices_to_remove) {
        if (problem_.remove_action(index)) {
            removed_count++;
        }
    }

    return removed_count;
}


void RelaxedPlanningGraph::print_debug_info() const {
    std::cout << "\n=== Relaxed Planning Graph Debug Info ===\n";
    std::cout << "Total layers: " << fact_layers_.size() << "\n";
    std::cout << "Goals achievable: " << (are_goals_achievable() ? "YES" : "NO") << "\n\n";

    for (size_t i = 0; i < fact_layers_.size(); ++i) {
        std::cout << "--- Layer " << i << " ---\n";
        std::cout << "Facts (" << fact_layers_[i].size() << "):\n";
        for (int fact_id : fact_layers_[i]) {
            std::cout << "  " << fact_id_to_string(fact_id) << "\n";
        }

        if (i < action_layers_.size()) {
            std::cout << "Actions (" << action_layers_[i].size() << "):\n";
            for (const Action* action : action_layers_[i]) {
                std::cout << "  " << action->name() << "\n";
            }
        }
        std::cout << "\n";
    }

    std::cout << "Goal conditions:\n";
    for (int goal_id : goal_condition_ids_) {
        auto it = achievability_layer_.find(goal_id);
        int layer = (it != achievability_layer_.end()) ? it->second : -1;
        std::cout << "  " << fact_id_to_string(goal_id) << " -> layer " << layer << "\n";
    }


    std::cout << "=========================================\n\n";
}

void RelaxedPlanningGraph::print_reachability_analysis() const {
    std::cout << "\n=== RPG Reachability Analysis ===\n";

    // Collect all reached fluent IDs from all layers
    std::unordered_set<int> all_reached_fluents;
    for (const auto& layer : fact_layers_) {
        for (int fact_id : layer) {
            // Only count positive fluent IDs (negative are encoded negations)
            if (fact_id >= 0) {
                all_reached_fluents.insert(fact_id);
            }
        }
    }

    // Collect all reached actions from all layers
    std::unordered_set<const Action*> all_reached_actions;
    for (const auto& layer : action_layers_) {
        for (const Action* action : layer) {
            all_reached_actions.insert(action);
        }
    }

    // Total counts
    size_t total_grounded_fluents = problem_.grounded_fluent_count();
    size_t total_actions = problem_.action_count();

    // Reachable counts
    size_t reachable_fluents = all_reached_fluents.size();
    size_t reachable_actions = all_reached_actions.size();

    // Calculate unreachable counts
    size_t unreachable_fluents = total_grounded_fluents - reachable_fluents;
    size_t unreachable_actions = total_actions - reachable_actions;

    std::cout << "Fluent Analysis:\n";
    std::cout << "  Total grounded fluents: " << total_grounded_fluents << "\n";
    std::cout << "  Reachable fluents: " << reachable_fluents << "\n";
    std::cout << "  Unreachable fluents: " << unreachable_fluents << "\n";
    if (total_grounded_fluents > 0) {
        double fluent_coverage = (double)reachable_fluents / total_grounded_fluents * 100.0;
        std::cout << "  Fluent coverage: " << std::fixed << std::setprecision(1) << fluent_coverage << "%\n";
    }

    std::cout << "\nAction Analysis:\n";
    std::cout << "  Total actions: " << total_actions << "\n";
    std::cout << "  Reachable actions: " << reachable_actions << "\n";
    std::cout << "  Unreachable actions: " << unreachable_actions << "\n";
    if (total_actions > 0) {
        double action_coverage = (double)reachable_actions / total_actions * 100.0;
        std::cout << "  Action coverage: " << std::fixed << std::setprecision(1) << action_coverage << "%\n";
    }

    // Show removable actions (safe to remove after fixpoint analysis)
    auto removable_actions = get_removable_actions();
    if (removable_actions.size() > 0) {
        double savings_percentage = (double)removable_actions.size() / total_actions * 100.0;
        std::cout << "  Removable actions: " << removable_actions.size() << " ("
                  << std::fixed << std::setprecision(1) << savings_percentage << "% potential SAT encoding savings)\n";
    }


    // List unreachable fluents (up to 10 for brevity)
    if (unreachable_fluents > 0) {
        std::cout << "\nUnreachable fluents (showing up to 10):\n";
        int count = 0;
        for (size_t i = 0; i < total_grounded_fluents && count < 10; ++i) {
            if (all_reached_fluents.find(static_cast<int>(i)) == all_reached_fluents.end()) {
                std::cout << "  " << problem_.grounded_fluent(i).to_string() << "\n";
                count++;
            }
        }
        if (unreachable_fluents > 10) {
            std::cout << "  ... and " << (unreachable_fluents - 10) << " more\n";
        }
    }

    // List unreachable actions (up to 10 for brevity)
    if (unreachable_actions > 0) {
        std::cout << "\nUnreachable actions (showing up to 10):\n";
        int count = 0;
        for (size_t i = 0; i < total_actions && count < 10; ++i) {
            const Action& action = problem_.action(i);
            if (all_reached_actions.find(&action) == all_reached_actions.end()) {
                std::cout << "  " << action.name() << "\n";
                count++;
            }
        }
        if (unreachable_actions > 10) {
            std::cout << "  ... and " << (unreachable_actions - 10) << " more\n";
        }
    }

    std::cout << "==================================\n\n";
}

std::string RelaxedPlanningGraph::fact_id_to_string(int fact_id) const {
    if (fact_id >= 0) {
        // Positive fact
        if (fact_id < static_cast<int>(problem_.grounded_fluent_count())) {
            return problem_.grounded_fluent(fact_id).to_string();
        }
    } else {
        // Negative fact: decode to get original fluent_id
        int original_fluent_id = decode_negative_fact_id(fact_id);
        if (original_fluent_id >= 0 && original_fluent_id < static_cast<int>(problem_.grounded_fluent_count())) {
            return "(not " + problem_.grounded_fluent(original_fluent_id).to_string() + ")";
        }
    }
    return "unknown_fact_" + std::to_string(fact_id);
}



} // namespace bp