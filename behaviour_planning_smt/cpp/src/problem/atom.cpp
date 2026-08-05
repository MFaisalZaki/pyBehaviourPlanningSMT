// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "atom.hpp"
#include <stdexcept>

namespace bp {

Atom::Atom(const pb::Atom& pb_atom) {
    switch (pb_atom.content_case()) {
        case pb::Atom::kSymbol:
            value_ = pb_atom.symbol();
            break;
        case pb::Atom::kInt:
            value_ = pb_atom.int_();
            break;
        case pb::Atom::kReal:
            value_ = Real(pb_atom.real());
            break;
        case pb::Atom::kBoolean:
            value_ = pb_atom.boolean();
            break;
        default:
            value_ = std::string("");
            break;
    }
}

std::string Atom::to_string() const {
    return std::visit([](const auto& value) -> std::string {
        if constexpr (std::is_same_v<std::decay_t<decltype(value)>, std::string>) {
            return value;
        } else if constexpr (std::is_same_v<std::decay_t<decltype(value)>, int64_t>) {
            return std::to_string(value);
        } else if constexpr (std::is_same_v<std::decay_t<decltype(value)>, Real>) {
            return value.to_string();
        } else if constexpr (std::is_same_v<std::decay_t<decltype(value)>, bool>) {
            return value ? "true" : "false";
        }
        return "";
    }, value_);
}

} // namespace bp
