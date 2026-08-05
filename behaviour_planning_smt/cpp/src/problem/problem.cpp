// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "problem.hpp"
#include <sstream>

namespace bp {

Problem::Problem(const pb::Problem& pb_problem) {
    load_types(pb_problem.types());
    resolve_type_hierarchy();
    
    // Load objects
    load_objects(pb_problem.objects());
    
    // Load fluents
    load_fluents(pb_problem.fluents());
    
    // Load actions
    load_actions(pb_problem.actions());
    
    // Load initial state
    for (const auto& pb_assignment : pb_problem.initial_state()) {
        initial_state_.emplace_back(pb_assignment, this);
    }
    
    // Load goals
    for (const auto& pb_goal : pb_problem.goals()) {
        goals_.emplace_back(pb_goal, this);
    }

    // Collect all grounded fluents systematically
    collect_all_grounded_fluents();
}

bool Problem::has_object(const std::string& name) const {
    return object_name_to_index_.find(name) != object_name_to_index_.end();
}

const Object* Problem::find_object(const std::string& name) const {
    auto it = object_name_to_index_.find(name);
    if (it != object_name_to_index_.end()) {
        return &objects_[it->second];
    }
    return nullptr;
}

bool Problem::has_fluent(const std::string& name) const {
    return fluent_name_to_index_.find(name) != fluent_name_to_index_.end();
}

const Fluent* Problem::find_fluent(const std::string& name) const {
    auto it = fluent_name_to_index_.find(name);
    if (it != fluent_name_to_index_.end()) {
        return &fluents_[it->second];
    }
    return nullptr;
}

bool Problem::has_action(const std::string& name) const {
    return action_name_to_index_.find(name) != action_name_to_index_.end();
}

const Action* Problem::find_action(const std::string& name) const {
    auto it = action_name_to_index_.find(name);
    if (it != action_name_to_index_.end()) {
        return &actions_[it->second];
    }
    return nullptr;
}

const Type* Problem::find_type(const std::string& name) const {
    auto it = type_name_to_ptr_.find(name);
    if (it != type_name_to_ptr_.end()) return it->second;
    return nullptr;
}

void Problem::add_object(const Object& object) {
    objects_.push_back(object);
    build_object_mappings();
}

void Problem::set_objects(const std::vector<Object>& objects) {
    objects_ = objects;
    build_object_mappings();
}

void Problem::add_fluent(const Fluent& fluent) {
    fluents_.push_back(fluent);
    // Set the ID to match the vector index
    fluents_.back().set_id(fluents_.size() - 1);
    build_fluent_mappings();
}

void Problem::set_fluents(const std::vector<Fluent>& fluents) {
    fluents_ = fluents;
    // Set IDs to match vector indices
    for (size_t i = 0; i < fluents_.size(); ++i) {
        fluents_[i].set_id(static_cast<int>(i));
    }
    build_fluent_mappings();
}

void Problem::add_action(const Action& action) {
    actions_.push_back(action);
    // Set the ID to match the vector index
    actions_.back().set_id(actions_.size() - 1);
    build_action_mappings();
}

void Problem::set_actions(const std::vector<Action>& actions) {
    actions_ = actions;
    // Set IDs to match vector indices
    for (size_t i = 0; i < actions_.size(); ++i) {
        actions_[i].set_id(static_cast<int>(i));
    }
    build_action_mappings();
}

bool Problem::remove_action(size_t index) {
    if (index >= actions_.size()) {
        return false;
    }

    // Remove the action from the vector
    actions_.erase(actions_.begin() + index);

    // Update IDs for all remaining actions to maintain index == ID invariant
    for (size_t i = index; i < actions_.size(); ++i) {
        actions_[i].set_id(static_cast<int>(i));
    }

    // Rebuild the name-to-index mapping
    build_action_mappings();

    return true;
}

bool Problem::remove_action(const Action* action) {
    // Find the action index
    for (size_t i = 0; i < actions_.size(); ++i) {
        if (&actions_[i] == action) {
            return remove_action(i);
        }
    }
    return false;
}

void Problem::add_grounded_fluent(const Expression& fluent) {
    grounded_fluents_.push_back(fluent);
    build_grounded_fluent_mappings();
}

void Problem::set_grounded_fluents(const std::vector<Expression>& fluents) {
    grounded_fluents_ = fluents;
    build_grounded_fluent_mappings();
}

void Problem::clear_all() {
    objects_.clear();
    fluents_.clear();
    actions_.clear();
    grounded_fluents_.clear();
    initial_state_.clear();
    goals_.clear();
    object_name_to_index_.clear();
    fluent_name_to_index_.clear();
    action_name_to_index_.clear();
    grounded_fluent_to_index_.clear();
}

bool Problem::is_empty() const {
    return objects_.empty() && fluents_.empty() && actions_.empty() &&
           grounded_fluents_.empty() && initial_state_.empty() && goals_.empty();
}

std::string Problem::to_string() const {
    std::ostringstream oss;
    oss << "Problem: " << problem_name_ << " (Domain: " << domain_name_ << ")\n";
    
    oss << "\nObjects (" << objects_.size() << "):";
    for (const auto& obj : objects_) {
        oss << "\n  " << obj.to_string();
    }
    
    oss << "\n\nFluents (" << fluents_.size() << "):";
    for (const auto& fluent : fluents_) {
        oss << "\n  " << fluent.to_string();
    }
    
    oss << "\n\nActions (" << actions_.size() << "):";
    for (const auto& action : actions_) {
        oss << "\n  " << action.to_string();
    }

    oss << "\n\nGrounded Fluents (" << grounded_fluents_.size() << "):";
    for (const auto& fluent : grounded_fluents_) {
        oss << "\n  " << fluent.to_string();
    }
    
    oss << "\n\nInitial State (" << initial_state_.size() << " assignments):";
    for (const auto& assignment : initial_state_) {
        oss << "\n  " << assignment.to_string();
    }
    
    oss << "\n\nGoals (" << goals_.size() << "):";
    for (const auto& goal : goals_) {
        oss << "\n  " << goal.to_string();
    }
    
    return oss.str();
}

bool Problem::operator==(const Problem& other) const {
    return domain_name_ == other.domain_name_ &&
           problem_name_ == other.problem_name_ &&
           objects_ == other.objects_ &&
           fluents_ == other.fluents_ &&
           actions_ == other.actions_ &&
           initial_state_ == other.initial_state_ &&
           goals_ == other.goals_;
}

void Problem::build_object_mappings() {
    object_name_to_index_.clear();
    for (size_t i = 0; i < objects_.size(); ++i) {
        object_name_to_index_[objects_[i].name()] = i;
    }
}

void Problem::build_fluent_mappings() {
    fluent_name_to_index_.clear();
    for (size_t i = 0; i < fluents_.size(); ++i) {
        fluent_name_to_index_[fluents_[i].name()] = i;
    }
}

void Problem::build_action_mappings() {
    action_name_to_index_.clear();
    for (size_t i = 0; i < actions_.size(); ++i) {
        action_name_to_index_[actions_[i].name()] = i;
    }
}

void Problem::build_grounded_fluent_mappings() {
    grounded_fluent_to_index_.clear();
    for (size_t i = 0; i < grounded_fluents_.size(); ++i) {
        grounded_fluent_to_index_[grounded_fluents_[i]] = i;
    }
}

void Problem::load_types(const pb::RepeatedTypeDeclaration& pb_types) {
    types_.clear();
    type_name_to_ptr_.clear();

    // ensure basic types are present
    types_.emplace_back("up:bool");
    types_.emplace_back("up:int");
    types_.emplace_back("up:real");

    for (const auto& pb_type : pb_types) {
        types_.emplace_back(pb_type.type_name());
        types_.back().set_parent_name(pb_type.parent_type());
    }
    
    // Build the name to pointer mapping
    for (auto& type : types_) {
        type_name_to_ptr_[type.name()] = &type;
    }
}

void Problem::resolve_type_hierarchy() {
    for (auto& type : types_) {
        if (!type.parent_name().empty()) {
            auto it = type_name_to_ptr_.find(type.parent_name());
            if (it != type_name_to_ptr_.end()) {
                type.set_parent(it->second);
            }
        }
    }
}

void Problem::load_objects(const pb::RepeatedObjectDeclaration& pb_objects) {
    objects_.clear();
    for (const auto& pb_obj : pb_objects) {
        const Type* type = find_type(pb_obj.type());
        objects_.emplace_back(pb_obj.name(), type);
    }
    build_object_mappings();
}

void Problem::load_fluents(const pb::RepeatedFluent& pb_fluents) {
    fluents_.clear();
    for (const auto& pb_fluent : pb_fluents) {
        std::vector<Parameter> params;
        // Collect parameters for the fluent
        for (const auto& pb_param : pb_fluent.parameters()) {
            const Type* param_type = find_type(pb_param.type());
            params.emplace_back(pb_param.name(), param_type);
        }

        // Find the value type for the fluent
        const Type* value_type = find_type(pb_fluent.value_type());
        if (!value_type) {
            std::cerr << "ERROR: Could not find type '" << pb_fluent.value_type() 
                << "' for fluent '" << pb_fluent.name() << "'" << std::endl;
        }
        fluents_.emplace_back(pb_fluent.name(), value_type, params);
    }
    build_fluent_mappings();
}

void Problem::load_actions(const pb::RepeatedAction& pb_actions) {
    actions_.clear();
    for (const auto& pb_action : pb_actions) {
        std::vector<Parameter> params;
        for (const auto& pb_param : pb_action.parameters()) {
            const Type* param_type = find_type(pb_param.type());
            params.emplace_back(pb_param.name(), param_type);
        }
        actions_.emplace_back(pb_action, params, this);
        // Set the ID to match the vector index
        actions_.back().set_id(actions_.size() - 1);
    }
    build_action_mappings();
}

void Problem::collect_all_grounded_fluents() {
    grounded_fluents_.clear();
    std::unordered_set<Expression> unique_fluents;

    // Helper function to add a fluent if it's not already present
    auto add_unique_fluent = [&](const Expression& fluent) {
        if (unique_fluents.find(fluent) == unique_fluents.end()) {
            unique_fluents.insert(fluent);
            grounded_fluents_.push_back(fluent);
        }
    };

    // Collect grounded fluents from initial state
    for (const auto& assignment : initial_state_) {
        add_unique_fluent(assignment.fluent());
    }

    // Build the lookup mappings
    build_grounded_fluent_mappings();
}

int Problem::find_grounded_fluent_index(const Expression& fluent) const {
    auto it = grounded_fluent_to_index_.find(fluent);
    return (it != grounded_fluent_to_index_.end()) ? static_cast<int>(it->second) : -1;
}

} // namespace bp
