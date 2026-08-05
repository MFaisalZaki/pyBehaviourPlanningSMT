// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <vector>
#include <string>
#include "action.hpp"
#include "protobuf_aliases.hpp"

namespace bp {

/**
 * @brief Plan representation
 * 
 * Represents a plan as a simple sequence of actions.
 */
class Plan {
public:
    // Constructors
    Plan() = default;
    
    // Add an action to the end of the plan
    void add_action(const Action* action);
    
    // Access actions
    const std::vector<const Action*>& actions() const { return actions_; }
    
    // Basic properties
    size_t length() const { return actions_.size(); }
    bool is_empty() const { return actions_.empty(); }
    
    // Convert to protobuf for communication with Python
    pb::Plan to_protobuf() const;
    
    // String representation for debugging
    std::string to_string() const;
    
    // Clear the plan
    void clear() { actions_.clear(); }

private:
    // A simple sequence of actions
    std::vector<const Action*> actions_;
};

} // namespace bp