#include "dimension.hpp"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace bp {

double Dimension::distance(const std::string& a, const std::string& b) const {
    return a == b ? 0.0 : 1.0; // discrete metric: any dimension satisfies it
}

double Dimension::numeric_distance(const std::string& a, const std::string& b) {
    char* end_a = nullptr;
    char* end_b = nullptr;
    const double value_a = std::strtod(a.c_str(), &end_a);
    const double value_b = std::strtod(b.c_str(), &end_b);
    const bool parsed_a = end_a != a.c_str() && *end_a == '\0' && !a.empty();
    const bool parsed_b = end_b != b.c_str() && *end_b == '\0' && !b.empty();
    if (!parsed_a || !parsed_b) {
        return a == b ? 0.0 : 1.0;
    }
    return std::fabs(value_a - value_b);
}

void Dimension::require_encoder(const Encoder& encoder, const std::string& dimension_name,
                                std::initializer_list<const char*> supported) {
    std::string supported_names;
    for (const char* name : supported) {
        if (encoder.name() == name) return;
        if (!supported_names.empty()) supported_names += ", ";
        supported_names += name;
    }
    throw std::invalid_argument(
        "The '" + dimension_name + "' dimension does not know how to encode itself for "
        "encoder '" + encoder.name() + "'. Supported encoders: " + supported_names);
}

// ---------------------------------------------------------------------------
// Resources / functions file parser
// ---------------------------------------------------------------------------

std::vector<RangeEntry> parse_range_file(const std::string& path, const std::string& keyword) {
    std::ifstream input(path);
    if (!input) {
        throw std::invalid_argument("Cannot open file: " + path);
    }
    std::stringstream buffer;
    buffer << input.rdbuf();
    const std::string content = buffer.str();

    std::vector<RangeEntry> entries;
    std::unordered_map<std::string, size_t> position_of;

    size_t pos = 0;
    auto skip_whitespace = [&]() {
        while (pos < content.size() && std::isspace(static_cast<unsigned char>(content[pos]))) ++pos;
    };
    auto expect = [&](char c) {
        skip_whitespace();
        if (pos >= content.size() || content[pos] != c) {
            throw std::invalid_argument("Malformed entry in " + path + ": expected '" +
                                        std::string(1, c) + "'");
        }
        ++pos;
    };
    auto read_token = [&]() -> std::string {
        skip_whitespace();
        size_t start = pos;
        int parenthesis_depth = 0;
        while (pos < content.size()) {
            char c = content[pos];
            if (c == '(') { ++parenthesis_depth; ++pos; continue; }
            if (c == ')') {
                if (parenthesis_depth == 0) break;
                --parenthesis_depth; ++pos; continue;
            }
            if (std::isspace(static_cast<unsigned char>(c)) && parenthesis_depth == 0) break;
            ++pos;
        }
        return content.substr(start, pos - start);
    };

    const std::string entry_keyword = ":" + keyword;
    while (true) {
        skip_whitespace();
        if (pos >= content.size()) break;
        expect('(');
        std::string head = read_token();
        if (head != entry_keyword) {
            throw std::invalid_argument("Malformed entry in " + path + ": expected '" +
                                        entry_keyword + "', found '" + head + "'");
        }
        RangeEntry entry;
        entry.name = read_token();
        try {
            entry.min = std::stol(read_token());
            entry.max = std::stol(read_token());
            entry.delta = std::stol(read_token());
        } catch (const std::exception&) {
            throw std::invalid_argument("Malformed numeric field in " + path + " for entry '" +
                                        entry.name + "'");
        }
        expect(')');

        auto seen = position_of.find(entry.name);
        if (seen != position_of.end()) {
            entries[seen->second] = entry; // keep the original position, take the latest values
        } else {
            position_of[entry.name] = entries.size();
            entries.push_back(entry);
        }
    }

    if (entries.empty()) {
        throw std::invalid_argument("No (" + entry_keyword + " ...) entries found in " + path);
    }
    return entries;
}

} // namespace bp
