#pragma once

#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace bp {

/**
 * @brief Fast-Downward-style plugin registry.
 *
 * Each category of extensible components (behaviour-space dimensions,
 * encoders) has one PluginRegistry singleton, keyed by the component's
 * factory type. A component registers itself by defining a static Plugin
 * object in its own translation unit:
 *
 *     static DimensionPlugin _plugin(
 *         "ac",
 *         [](const Encoder& encoder, const std::string& argument,
 *            const DimensionContext&) -> std::unique_ptr<Dimension> {
 *             return std::make_unique<ActionCountDimension>(encoder, argument);
 *         },
 *         "counts the plan's actions whose grounded name contains ARG");
 *
 * The registrar runs during static initialization, so adding a plugin is one
 * new .cpp file plus a CMakeLists.txt entry — nothing else in the code base
 * needs editing, and the component becomes addressable by name from the
 * command line.
 */
template <typename Factory>
class PluginRegistry {
public:
    struct Entry {
        Factory factory;
        std::string documentation;
    };

    static PluginRegistry& instance() {
        static PluginRegistry registry;
        return registry;
    }

    void register_plugin(const std::string& name, Factory factory,
                         const std::string& documentation) {
        if (entries_.count(name)) {
            throw std::logic_error("Duplicate plugin registration: " + name);
        }
        entries_.emplace(name, Entry{std::move(factory), documentation});
    }

    bool contains(const std::string& name) const { return entries_.count(name) > 0; }

    const Entry& get(const std::string& name) const {
        auto it = entries_.find(name);
        if (it == entries_.end()) {
            std::string known;
            for (const auto& [known_name, _] : entries_) {
                if (!known.empty()) known += ", ";
                known += known_name;
            }
            throw std::invalid_argument("Unknown plugin '" + name +
                                        "'. Registered plugins: " + known);
        }
        return it->second;
    }

    /// Registered names with their documentation, sorted by name.
    std::vector<std::pair<std::string, std::string>> list() const {
        std::vector<std::pair<std::string, std::string>> result;
        result.reserve(entries_.size());
        for (const auto& [name, entry] : entries_) {
            result.emplace_back(name, entry.documentation);
        }
        return result;
    }

private:
    PluginRegistry() = default;
    std::map<std::string, Entry> entries_; // ordered, for stable listings
};

/**
 * @brief Self-registration handle: constructing one registers a factory.
 */
template <typename Factory>
class Plugin {
public:
    Plugin(const std::string& name, Factory factory, const std::string& documentation) {
        PluginRegistry<Factory>::instance().register_plugin(name, std::move(factory),
                                                            documentation);
    }
};

} // namespace bp
