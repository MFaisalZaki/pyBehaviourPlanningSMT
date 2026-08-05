// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT),
// trimmed to the parts the behaviour planner uses.
#pragma once

#include "../problem/fluent.hpp"
#include "../problem/action.hpp"
#include <z3++.h>
#include <string>
#include <unordered_map>
#include <memory>
#include <vector>

namespace bp {

/**
 * @brief Factory class responsible for creating and managing Z3 variables
 *
 * Encapsulates variable naming and creation, caching one variable per
 * fluent/action and timestep so the encoding stays consistent: asking twice
 * for the same fluent at the same layer returns the same Z3 constant.
 *
 * Naming scheme: name and parameters joined by '_', then the timestep,
 * e.g. `at_rover0_waypoint2_7`.
 */
class Z3VariableFactory {
private:
    z3::context& ctx_;

    // Storage for SMT variables - outer vector is indexed by timestep
    // state_vars_[0]["at_airplane1_city1"] -> z3::expr(bool variable for fluent at timestep 0)
    std::vector<std::unordered_map<std::string, std::shared_ptr<z3::expr>>> state_vars_;

    // action_vars_[0]["move_airplane1_city1_city2"] -> z3::expr(bool variable for action at timestep 0)
    std::vector<std::unordered_map<std::string, std::shared_ptr<z3::expr>>> action_vars_;

public:
    explicit Z3VariableFactory(z3::context& ctx);

    // Basic variable creation methods (create new variables without caching)
    z3::expr create_bool_variable(const std::string& name);
    z3::expr create_int_variable(const std::string& name);
    z3::expr create_real_variable(const std::string& name);
    z3::expr create_object_variable(const std::string& name);

    // Symbol-based variable creation (for visit_symbol)
    z3::expr create_symbol_variable(const std::string& name, const Type* type);

    // High-level variable management with caching
    const z3::expr& get_fluent_variable(const Fluent& fluent, int timestep);
    const z3::expr& get_action_variable(const Action& action, int timestep);

    // Variable naming methods
    std::string get_fluent_var_name(const Fluent& fluent) const;
    std::string get_fluent_var_name(const Fluent& fluent, int timestep) const;
    std::string get_action_var_name(const Action& action) const;
    std::string get_action_var_name(const Action& action, int timestep) const;

private:
    // Helper methods for variable creation and management
    void ensure_timestep_capacity(int timestep);
    z3::expr create_new_fluent_variable(const Fluent& fluent, const std::string& var_name);
};

} // namespace bp
