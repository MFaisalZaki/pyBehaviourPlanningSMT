// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#pragma once

#include <string>
#include <memory>

namespace bp {

class Type {
public:
    Type() = default;
    explicit Type(const std::string& name);

    const std::string& name() const;
    void set_name(const std::string& name);

    // Parent type for hierarchy (nullptr if root)
    const Type* parent() const;
    void set_parent(const Type* parent);

    // For initial parsing, store parent name until resolved
    void set_parent_name(const std::string& parent_name);
    const std::string& parent_name() const;

    // Subtype check (traverse up the hierarchy)
    bool is_subtype_of(const Type* supertype) const;

    // Primitive type helpers
    bool is_bool() const { return name_ == "bool" || name_ == "up:bool"; }
    bool is_int() const { return name_ == "int" || name_ == "up:int" || name_ == "integer" || name_ == "up:integer"; }
    bool is_real() const { return name_ == "real" || name_ == "up:real"; }
    bool is_object() const { return !is_bool() && !is_int() && !is_real(); }

private:
    std::string name_;
    const Type* parent_ = nullptr;
    std::string parent_name_;
};

} // namespace bp
