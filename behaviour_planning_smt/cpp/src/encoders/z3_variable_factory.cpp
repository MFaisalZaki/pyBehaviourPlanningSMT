// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "z3_variable_factory.hpp"
#include "../problem/action.hpp"
#include <iostream>

namespace bp {

Z3VariableFactory::Z3VariableFactory(z3::context& ctx)
    : ctx_(ctx) {
    state_vars_.clear();
    action_vars_.clear();
    state_var_name_to_fluent_.clear();
    action_var_name_to_action_.clear();
}

z3::expr Z3VariableFactory::create_bool_variable(const std::string& name) {
    return ctx_.bool_const(name.c_str());
}

z3::expr Z3VariableFactory::create_int_variable(const std::string& name) {
    return ctx_.int_const(name.c_str());
}

z3::expr Z3VariableFactory::create_real_variable(const std::string& name) {
    return ctx_.real_const(name.c_str());
}

z3::expr Z3VariableFactory::create_object_variable(const std::string& name) {
    // Objects are typically mapped to integers in SMT encoding for distinctness
    return ctx_.int_const(name.c_str());
}

z3::expr Z3VariableFactory::create_symbol_variable(const std::string& name, const Type* type) {
    if (!type) {
        // For unknown types, default to integer
        return create_int_variable(name);
    }
    
    if (type->is_bool()) {
        return create_bool_variable(name);
    } else if (type->is_int()) {
        return create_int_variable(name);
    } else if (type->is_real()) {
        return create_real_variable(name);
    } else if (type->is_object()) {
        return create_object_variable(name);
    } else {
        // For unknown types, default to integer
        return create_int_variable(name);
    }
}

const z3::expr& Z3VariableFactory::get_fluent_variable(const Fluent& fluent, int timestep) {
    std::string var_name = get_fluent_var_name(fluent, timestep);

    // Ensure we have enough timesteps allocated
    ensure_timestep_capacity(timestep);

    auto& timestep_vars = state_vars_[timestep];
    auto it = timestep_vars.find(var_name);
    if (it == timestep_vars.end()) {
        // Create new variable
        z3::expr new_var = create_new_fluent_variable(fluent, var_name);
        timestep_vars[var_name] = std::make_shared<z3::expr>(new_var);

        // Store reverse mapping
        state_var_name_to_fluent_[var_name] = {std::make_shared<Fluent>(fluent), timestep};

        return *(timestep_vars[var_name]);
    }
    return *(it->second);
}

const z3::expr& Z3VariableFactory::get_action_variable(const Action& action, int timestep) {
    std::string var_name = get_action_var_name(action, timestep);

    // Ensure we have enough timesteps allocated
    ensure_timestep_capacity(timestep);

    auto& timestep_vars = action_vars_[timestep];
    auto it = timestep_vars.find(var_name);
    if (it == timestep_vars.end()) {
        // Actions are always boolean variables
        z3::expr new_var = create_bool_variable(var_name);
        timestep_vars[var_name] = std::make_shared<z3::expr>(new_var);

        // Store reverse mapping
        action_var_name_to_action_[var_name] = {std::make_shared<Action>(action), timestep};

        return *(timestep_vars[var_name]);
    }
    return *(it->second);
}

std::string Z3VariableFactory::get_fluent_var_name(const Fluent& fluent) const {
    std::string name = fluent.name();
    // Add parameter values from the fluent's embedded parameters
    for (const auto& param : fluent.parameters()) {
        name += "_" + param.name();
    }
    return name;
}

std::string Z3VariableFactory::get_fluent_var_name(const Fluent& fluent, int timestep) const {
    return get_fluent_var_name(fluent) + "_" + std::to_string(timestep);
}

std::string Z3VariableFactory::get_action_var_name(const Action& action) const {
    std::string name = action.name();
    // Add parameter values from the action's embedded parameters
    for (const auto& param : action.parameters()) {
        name += "_" + param.name();
    }
    return name;
}

std::string Z3VariableFactory::get_action_var_name(const Action& action, int timestep) const {
    return get_action_var_name(action) + "_" + std::to_string(timestep);
}

void Z3VariableFactory::ensure_timestep_capacity(int timestep) {
    while (static_cast<int>(state_vars_.size()) <= timestep) {
        state_vars_.emplace_back();
    }
    while (static_cast<int>(action_vars_.size()) <= timestep) {
        action_vars_.emplace_back();
    }
}

z3::expr Z3VariableFactory::create_new_fluent_variable(const Fluent& fluent, const std::string& var_name) {
    if (fluent.is_bool_fluent()) {
        return create_bool_variable(var_name);
    } else if (fluent.is_int_fluent() || fluent.is_real_fluent()) {
        // Force all numeric fluents to be real to avoid mixed int/real type issues
        return create_real_variable(var_name);
    } else if (fluent.is_object_fluent()) {
        return create_object_variable(var_name);
    } else {
        // For unknown types, default to real (safer than integer for mixed arithmetic)
        std::cerr << "Warning: Unknown fluent type for " << var_name << ", defaulting to real" << std::endl;
        return create_real_variable(var_name);
    }
}

std::optional<std::pair<const Fluent&, int>> Z3VariableFactory::get_fluent_from_variable(const z3::expr& var) const {
    std::string var_name = var.decl().name().str();
    auto it = state_var_name_to_fluent_.find(var_name);
    if (it != state_var_name_to_fluent_.end()) {
        return std::make_pair(std::cref(*(it->second.first)), it->second.second);
    }
    return std::nullopt;
}

std::optional<std::pair<const Action&, int>> Z3VariableFactory::get_action_from_variable(const z3::expr& var) const {
    std::string var_name = var.decl().name().str();
    auto it = action_var_name_to_action_.find(var_name);
    if (it != action_var_name_to_action_.end()) {
        return std::make_pair(std::cref(*(it->second.first)), it->second.second);
    }
    return std::nullopt;
}

bool Z3VariableFactory::is_fluent_variable(const z3::expr& var) const {
    std::string var_name = var.decl().name().str();
    return state_var_name_to_fluent_.find(var_name) != state_var_name_to_fluent_.end();
}

bool Z3VariableFactory::is_action_variable(const z3::expr& var) const {
    std::string var_name = var.decl().name().str();
    return action_var_name_to_action_.find(var_name) != action_var_name_to_action_.end();
}

// Const versions for read-only access
const z3::expr& Z3VariableFactory::get_fluent_variable(const Fluent& fluent, int timestep) const {
    std::string var_name = get_fluent_var_name(fluent, timestep);

    if (timestep >= static_cast<int>(state_vars_.size())) {
        throw std::runtime_error("Timestep " + std::to_string(timestep) + " not allocated yet");
    }

    const auto& timestep_vars = state_vars_[timestep];
    auto it = timestep_vars.find(var_name);
    if (it == timestep_vars.end()) {
        throw std::runtime_error("Fluent variable " + var_name + " not found for timestep " + std::to_string(timestep));
    }
    return *(it->second);
}

const z3::expr& Z3VariableFactory::get_action_variable(const Action& action, int timestep) const {
    std::string var_name = get_action_var_name(action, timestep);

    if (timestep >= static_cast<int>(action_vars_.size())) {
        throw std::runtime_error("Timestep " + std::to_string(timestep) + " not allocated yet");
    }

    const auto& timestep_vars = action_vars_[timestep];
    auto it = timestep_vars.find(var_name);
    if (it == timestep_vars.end()) {
        throw std::runtime_error("Action variable " + var_name + " not found for timestep " + std::to_string(timestep));
    }
    return *(it->second);
}

// Variable enumeration methods for propagators
std::vector<std::shared_ptr<z3::expr>> Z3VariableFactory::get_all_fluent_variables(int timestep) const {
    std::vector<std::shared_ptr<z3::expr>> variables;

    if (timestep >= static_cast<int>(state_vars_.size())) {
        return variables; // Empty vector if timestep not allocated
    }

    const auto& timestep_vars = state_vars_[timestep];
    variables.reserve(timestep_vars.size());

    for (const auto& pair : timestep_vars) {
        variables.push_back(pair.second);
    }

    return variables;
}

std::vector<std::shared_ptr<z3::expr>> Z3VariableFactory::get_all_action_variables(int timestep) const {
    std::vector<std::shared_ptr<z3::expr>> variables;

    if (timestep >= static_cast<int>(action_vars_.size())) {
        return variables; // Empty vector if timestep not allocated
    }

    const auto& timestep_vars = action_vars_[timestep];
    variables.reserve(timestep_vars.size());

    for (const auto& pair : timestep_vars) {
        variables.push_back(pair.second);
    }

    return variables;
}

std::vector<std::pair<std::shared_ptr<z3::expr>, int>> Z3VariableFactory::get_all_fluent_variables() const {
    std::vector<std::pair<std::shared_ptr<z3::expr>, int>> variables;

    for (int timestep = 0; timestep < static_cast<int>(state_vars_.size()); ++timestep) {
        const auto& timestep_vars = state_vars_[timestep];
        for (const auto& pair : timestep_vars) {
            variables.emplace_back(pair.second, timestep);
        }
    }

    return variables;
}

std::vector<std::pair<std::shared_ptr<z3::expr>, int>> Z3VariableFactory::get_all_action_variables() const {
    std::vector<std::pair<std::shared_ptr<z3::expr>, int>> variables;

    for (int timestep = 0; timestep < static_cast<int>(action_vars_.size()); ++timestep) {
        const auto& timestep_vars = action_vars_[timestep];
        for (const auto& pair : timestep_vars) {
            variables.emplace_back(pair.second, timestep);
        }
    }

    return variables;
}

// Timestep management queries
int Z3VariableFactory::get_max_timestep() const {
    int max_state = static_cast<int>(state_vars_.size()) - 1;
    int max_action = static_cast<int>(action_vars_.size()) - 1;
    return std::max(max_state, max_action);
}

bool Z3VariableFactory::has_variables_for_timestep(int timestep) const {
    bool has_state_vars = timestep < static_cast<int>(state_vars_.size()) && !state_vars_[timestep].empty();
    bool has_action_vars = timestep < static_cast<int>(action_vars_.size()) && !action_vars_[timestep].empty();
    return has_state_vars || has_action_vars;
}

} // namespace bp
