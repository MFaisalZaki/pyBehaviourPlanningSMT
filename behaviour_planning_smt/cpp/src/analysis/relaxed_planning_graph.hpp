// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include "../problem/problem.hpp"
#include "../problem/action.hpp"
#include "../problem/expression.hpp"
#include "../problem/goal.hpp"
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <chrono>

namespace bp {

/**
 * @brief RelaxedPlanningGraph
 *
 * Layer-by-layer relaxed planning graph implementation using traditional fixpoint computation.
 *
 * Features:
 * - Syntactic achievability check for Boolean fluents
 * - Simplified numeric handling: any modification of a numeric variable enables any condition containing it
 * - Layer-by-layer construction until fixpoint is reached (always runs to fixpoint for soundness)
 * - Independent from ARPG and current achievers analysis
 *
 * The relaxed planning graph ignores delete effects and negative interactions,
 * providing an optimistic view of what's achievable for heuristic computation.
 *
 * Note: This Boolean RPG always runs to fixpoint (no early termination) for soundness.
 * The more precise NumericRelaxedPlanningGraph can use early termination safely.
 */
class RelaxedPlanningGraph {
public:
    explicit RelaxedPlanningGraph(Problem& problem);

    /**
     * Build the relaxed planning graph from initial state until fixpoint.
     * @return true if all goals are reachable, false otherwise
     */
    bool build();

    /**
     * Check if a specific condition expression is achievable.
     * @param condition The condition to check (can be Boolean or numeric)
     * @return true if the condition is achievable in the relaxed graph
     */
    bool is_achievable(const Expression& condition) const;

    /**
     * Get the first layer where a condition becomes achievable.
     * @param condition The condition to check
     * @return layer number (0-based), or -1 if not achievable
     */
    int get_achievability_layer(const Expression& condition) const;

    /**
     * Get all actions that become applicable in a given layer.
     * @param layer The layer number (0-based)
     * @return reference to vector of actions, empty if layer doesn't exist
     */
    const std::vector<const Action*>& get_actions_in_layer(int layer) const;

    /**
     * Get all conditions that become true in a given layer.
     * @param layer The layer number (0-based)
     * @return reference to set of condition IDs, empty if layer doesn't exist
     */
    const std::unordered_set<int>& get_conditions_in_layer(int layer) const;

    /**
     * Get the total number of layers in the graph.
     * @return number of layers, 0 if graph hasn't been built
     */
    size_t get_layer_count() const { return fact_layers_.size(); }

    /**
     * Check if all goal conditions are achievable.
     * @return true if all goals are reachable
     */
    bool are_goals_achievable() const;

    /**
     * Reset the graph for recomputation.
     */
    void reset();

    /**
     * Print debugging information about the graph structure.
     */
    void print_debug_info() const;

    /**
     * Print reachability analysis comparing reached vs total fluents/actions.
     */
    void print_reachability_analysis() const;

    /**
     * Get the minimum number of steps (transitions) needed to achieve the goals.
     * This provides a lower bound for planning based on the RPG structure.
     * @return minimum steps needed, or -1 if goals are not achievable
     * Note: 1 layer = 0 steps, 2 layers = 1 step, etc.
     */
    int get_minimum_steps_lower_bound() const;

    /**
     * Get actions that never appear in any RPG layer after fixpoint analysis.
     * These actions are safe to remove because:
     * - Actions with only numeric preconditions would appear immediately
     * - Actions that never appear have unsatisfiable Boolean preconditions
     * @return vector of pointers to actions that never become applicable
     */
    std::vector<const Action*> get_removable_actions() const;

    /**
     * Remove unreachable actions from the problem after RPG analysis.
     * This method modifies the problem by removing actions that never appear
     * in any RPG layer, reducing the SAT encoding size.
     * @return number of actions removed
     * @warning This modifies the problem and invalidates existing action pointers
     */
    size_t remove_unreachable_actions();


private:
    Problem& problem_;

    // Layer-based storage using grounded fluent IDs for efficiency
    // Fact encoding: positive facts use fluent_id (0, 1, 2, ...),
    // negative facts use -(fluent_id + 1) (-1, -2, -3, ...)
    std::vector<std::unordered_set<int>> fact_layers_;                   // IDs of facts (positive and negative) true at each layer
    std::vector<std::vector<const Action*>> action_layers_;               // Pointers to actions applicable at each layer

    // Achievability tracking using fluent IDs (same encoding as fact_layers_)
    std::unordered_map<int, int> achievability_layer_;                   // Maps fact_id -> first layer it's achievable


    // Goal tracking - we'll extract condition IDs during goal processing
    std::vector<int> goal_condition_ids_;                               // IDs of goal conditions

    // Timing and statistics
    mutable std::chrono::high_resolution_clock::time_point build_start_time_;
    mutable double build_time_ms_;

    // Static empty containers for safe returns
    static const std::vector<const Action*> empty_action_vector_;
    static const std::unordered_set<int> empty_condition_set_;

    /**
     * Initialize the first fact layer with the initial state.
     */
    void initialize_fact_layer();

    /**
     * Extract all goal conditions from the problem goals.
     */
    void extract_goal_conditions();

    /**
     * Extract conditions from CNF expressions (based on AchieversAnalysis pattern).
     * @param expr The expression to extract from
     * @param conditions Output vector for pointers to extracted conditions
     */
    void extract_cnf_conditions(const Expression& expr, std::vector<const Expression*>& conditions) const;

    /**
     * Compute which actions become applicable at the current layer.
     * @param layer_index The current layer index
     * @return vector of newly applicable actions
     */
    std::vector<const Action*> compute_applicable_actions(int layer_index) const;

    /**
     * Check if all preconditions of an action are satisfied at a given layer.
     * @param action The action to check
     * @param layer_index The layer to check against
     * @return true if all preconditions are satisfied
     */
    bool are_preconditions_satisfied(const Action& action, int layer_index) const;

    /**
     * Check if a single condition is satisfied at a given layer.
     * Handles both positive and negated conditions.
     * @param condition The condition to check (may be negated)
     * @param layer_index The layer to check against
     * @return true if the condition is satisfied
     */
    bool is_condition_satisfied(const Expression& condition, int layer_index) const;

    /**
     * Add effects of an action to the next fact layer.
     * @param action The action whose effects to add
     * @param target_layer_index The layer index to add effects to
     */
    void add_effects_to_layer(const Action& action, int target_layer_index);

    /**
     * Add a simple atomic effect to the target layer.
     * @param effect The simple effect to add
     * @param target_layer_index The layer index to add effect to
     */
    void add_simple_effect_to_layer(const Effect& effect, int target_layer_index);


    /**
     * Check if a fixpoint has been reached (no new facts in the last layer).
     * @return true if no progress was made in the last iteration
     */
    bool is_fixpoint_reached() const;

    /**
     * Check if a fact (positive or negative) exists in the given layer.
     * @param condition The condition to check (can be positive or negative)
     * @param layer_index The layer to check against
     * @return true if the fact exists in the layer
     */
    bool is_fact_in_layer(const Expression& condition, int layer_index) const;


    /**
     * Extract the inner condition from a negated condition.
     * @param negated_condition The negated condition (must be negated)
     * @return reference to the inner positive condition
     */
    const Expression& get_inner_condition(const Expression& negated_condition) const;


    /**
     * Find the grounded fluent ID for a given expression.
     * For positive expressions: returns fluent_id (0, 1, 2, ...)
     * For negative expressions: returns -(fluent_id + 1) (-1, -2, -3, ...)
     * @param expr The expression to find ID for (can be positive or negative)
     * @return encoded fact ID, or -1 if not found
     */
    int find_grounded_fluent_id(const Expression& expr) const;

    /**
     * Helper to decode fact ID and get string representation for debugging.
     * @param fact_id The encoded fact ID
     * @return string representation of the fact (with "not" prefix for negative facts)
     */
    std::string fact_id_to_string(int fact_id) const;

    /**
     * Encode a positive fluent ID as a negative fact ID.
     * @param fluent_id The positive fluent ID (0, 1, 2, ...)
     * @return negative fact ID (-(fluent_id + 1))
     */
    static int encode_negative_fact_id(int fluent_id) { return -(fluent_id + 1); }

    /**
     * Decode a negative fact ID to get the original positive fluent ID.
     * @param negative_fact_id The negative fact ID (-1, -2, -3, ...)
     * @return original positive fluent ID
     */
    static int decode_negative_fact_id(int negative_fact_id) { return -(negative_fact_id + 1); }
};

} // namespace bp