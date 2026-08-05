// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include "protobuf_aliases.hpp"
#include "parameter.hpp"
#include "expression.hpp"
#include "effect.hpp"

namespace bp {

/**
 * @brief Action
 * 
 * Represents a planning action with parameters, preconditions, and effects.
 */
class Action {
public:
    // Constructors
    Action() = default;
    Action(const std::string& name) : name_(name), id_(-1) {}
    Action(const pb::Action& pb_action, const std::vector<Parameter>& parameters, const Problem* problem);
    
    // Basic accessors
    const std::string& name() const { return name_; }
    int id() const { return id_; }
    
    // Parameter access
    const std::vector<Parameter>& parameters() const { return parameters_; }
    size_t parameter_count() const { return parameters_.size(); }
    const Parameter& parameter(size_t index) const { return parameters_[index]; }
    bool has_parameter(const std::string& name) const;
    const Parameter* find_parameter(const std::string& name) const;
    
    // Precondition access
    const Expression& precondition() const { return precondition_; }
    bool has_precondition() const { 
        return !(precondition_.is_constant() && precondition_.is_atom() && 
                 precondition_.value().is_boolean() && precondition_.value().boolean() == true); 
    }
    
    // Effect access
    const std::vector<Effect>& effects() const { return effects_; }
    size_t effect_count() const { return effects_.size(); }
    const Effect& effect(size_t index) const { return effects_[index]; }
    
    // Setters
    void set_name(const std::string& name) { name_ = name; }
    void set_id(int id) { id_ = id; }
    void add_parameter(const Parameter& param);
    void set_parameters(const std::vector<Parameter>& parameters);
    void set_precondition(const Expression& precond) { precondition_ = precond; }
    void add_effect(const Effect& effect) { effects_.push_back(effect); }
    void set_effects(const std::vector<Effect>& effects) { effects_ = effects; }
    
    // String representation
    std::string to_string() const;
    
    // Operators
    bool operator==(const Action& other) const;
    bool operator!=(const Action& other) const { return !(*this == other); }
    bool operator<(const Action& other) const;

private:
    std::string name_;
    int id_;
    std::vector<Parameter> parameters_;
    Expression precondition_;
    std::vector<Effect> effects_;
    
    // Quick lookup for parameters
    std::unordered_map<std::string, size_t> parameter_name_to_index_;
    
    void build_parameter_mappings();
};

} // namespace bp

// specialising std::hash for Action by using its ID
// note that for this to work we need to be in the std namespace
namespace std {
    template<>
    struct hash<bp::Action> {
        std::size_t operator()(const bp::Action& action) const {
            return std::hash<int>()(action.id());
        }
    };
}