// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include "protobuf_aliases.hpp"
#include "real.hpp"
#include "atom.hpp"
#include "parameter.hpp"
#include "expression.hpp"
#include "effect_expression.hpp"
#include "effect.hpp"
#include "object.hpp"
#include "fluent.hpp"
#include "goal.hpp"
#include "assignment.hpp"
#include "action.hpp"
#include "type.hpp"

namespace bp {

/**
 * @brief Main problem representation class
 * 
 * This is the central class that represents a complete planning problem.
 * It contains all objects, fluents, actions, initial state, and goals.
 * 
 * Note that this class is the only one that has qualified objects. That is,
 * Fluent objects for example represent the schema of a fluent, not a grounded
 * instance. The grounded instances are represented by the Expression class.
 * The Expression class then has utility methods to check the type of an Expression,
 * such as whether it is a fluent application, function application, or an atom.
 */
class Problem {
public:
    // Constructors
    Problem() = default;
    Problem(const std::string& domain_name, const std::string& problem_name)
        : domain_name_(domain_name), problem_name_(problem_name) {}
    Problem(const pb::Problem& pb_problem);
    
    // Basic accessors
    const std::string& domain_name() const { return domain_name_; }
    const std::string& problem_name() const { return problem_name_; }
    
    // Object access
    const std::vector<Object>& objects() const { return objects_; }
    size_t object_count() const { return objects_.size(); }
    const Object& object(size_t index) const { return objects_[index]; }
    bool has_object(const std::string& name) const;
    const Object* find_object(const std::string& name) const;
    
    // Fluent access
    const std::vector<Fluent>& fluents() const { return fluents_; }
    size_t fluent_count() const { return fluents_.size(); }
    const Fluent& fluent(size_t index) const { return fluents_[index]; }
    const Fluent& fluent_by_id(int id) const { return fluents_[id]; }
    bool has_fluent(const std::string& name) const;
    const Fluent* find_fluent(const std::string& name) const;

    // Fluent modification
    // NOTE: Fluent IDs are automatically set to match their position in the fluents_ vector.
    // This provides a stable ID system where fluent.id() == index in fluents() vector.
    // IDs are maintained across add_fluent(), set_fluents(), and load_fluents() operations.
    void add_fluent(const Fluent& fluent);
    void set_fluents(const std::vector<Fluent>& fluents);

    // Grounded fluent access
    // NOTE: Grounded fluents are stored with IDs matching their position in the grounded_fluents_ vector.
    // This provides a stable ID system where grounded_fluent_id == index in grounded_fluents() vector.
    const std::vector<Expression>& grounded_fluents() const { return grounded_fluents_; }
    size_t grounded_fluent_count() const { return grounded_fluents_.size(); }
    const Expression& grounded_fluent(int id) const { return grounded_fluents_[id]; }

    // Grounded fluent modification
    void add_grounded_fluent(const Expression& fluent);
    void set_grounded_fluents(const std::vector<Expression>& fluents);

    // Grounded fluent lookup
    /**
     * Find the index of a grounded fluent expression using O(1) hash map lookup.
     * @param fluent The fluent expression to find
     * @return fluent index (0-based), or -1 if not found
     */
    int find_grounded_fluent_index(const Expression& fluent) const;

    // Action access
    const std::vector<Action>& actions() const { return actions_; }
    size_t action_count() const { return actions_.size(); }
    const Action& action(size_t index) const { return actions_[index]; }
    bool has_action(const std::string& name) const;
    const Action* find_action(const std::string& name) const;
    
    // Action modification
    // NOTE: Action IDs are automatically set to match their position in the actions_ vector.
    // This provides a stable ID system where action.id() == index in actions() vector.
    // IDs are maintained across add_action(), set_actions(), and load_actions() operations.
    void add_action(const Action& action);
    void set_actions(const std::vector<Action>& actions);

    /**
     * Remove an action by index and maintain ID system consistency.
     * All actions after the removed index will have their IDs decremented by 1.
     * This ensures action.id() continues to match the vector index.
     * @param index The index of the action to remove (0-based)
     * @return true if removal successful, false if index out of bounds
     * @warning This invalidates any existing pointers/references to actions with index >= removed index
     */
    bool remove_action(size_t index);

    /**
     * Remove an action by pointer and maintain ID system consistency.
     * @param action Pointer to the action to remove
     * @return true if removal successful, false if action not found
     * @warning This invalidates any existing pointers/references to actions after the removed action
     */
    bool remove_action(const Action* action);
    
    // Initial state access
    const std::vector<Assignment>& initial_state() const { return initial_state_; }
    size_t initial_assignment_count() const { return initial_state_.size(); }
    const Assignment& initial_assignment(size_t index) const { return initial_state_[index]; }
    
    // Goal access
    const std::vector<Goal>& goals() const { return goals_; }
    size_t goal_count() const { return goals_.size(); }
    const Goal& goal(size_t index) const { return goals_[index]; }
    
    // Type access
    const std::vector<Type>& types() const { return types_; }
    const Type* find_type(const std::string& name) const;
    
    // Setters
    void set_domain_name(const std::string& domain_name) { domain_name_ = domain_name; }
    void set_problem_name(const std::string& problem_name) { problem_name_ = problem_name; }
    
    void add_object(const Object& object);
    void set_objects(const std::vector<Object>& objects);
    
    void add_initial_assignment(const Assignment& assignment) { initial_state_.push_back(assignment); }
    void set_initial_state(const std::vector<Assignment>& initial_state) { initial_state_ = initial_state; }
    
    void add_goal(const Goal& goal) { goals_.push_back(goal); }
    void set_goals(const std::vector<Goal>& goals) { goals_ = goals; }
    
    // Convenience methods
    void clear_all();
    bool is_empty() const;
    
    // String representation
    std::string to_string() const;
    
    // Operators
    bool operator==(const Problem& other) const;
    bool operator!=(const Problem& other) const { return !(*this == other); }

private:
    std::string domain_name_;
    std::string problem_name_;
    
    std::vector<Object> objects_;
    std::vector<Fluent> fluents_;
    std::vector<Action> actions_;
    std::vector<Expression> grounded_fluents_;
    std::vector<Assignment> initial_state_;
    std::vector<Goal> goals_;
    std::vector<Type> types_;
    
    // Quick lookup mappings
    std::unordered_map<std::string, size_t> object_name_to_index_;
    std::unordered_map<std::string, size_t> fluent_name_to_index_;
    std::unordered_map<std::string, size_t> action_name_to_index_;
    std::unordered_map<Expression, size_t> grounded_fluent_to_index_;
    std::unordered_map<std::string, const Type*> type_name_to_ptr_;
    
    void build_object_mappings();
    void build_fluent_mappings();
    void build_action_mappings();
    void build_grounded_fluent_mappings();
    void collect_all_grounded_fluents();
    void load_types(const pb::RepeatedTypeDeclaration& pb_types);
    void resolve_type_hierarchy();
    void load_objects(const pb::RepeatedObjectDeclaration& pb_objects);
    void load_fluents(const pb::RepeatedFluent& pb_fluents);
    void load_actions(const pb::RepeatedAction& pb_actions);
};

} // namespace bp
