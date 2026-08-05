#pragma once

#include "problem.hpp"

namespace bp {

/**
 * @brief Remove delete-then-set effects, following PDDL's add-after-delete semantics.
 *
 * If an action both deletes and adds the same boolean fluent, the delete effect
 * is dropped. This mirrors pypmt's DeleteThenSetRemover, which the Python
 * implementation applied before encoding, and lifts the usual restriction of
 * state-based encodings on actions that delete and add the same fluent.
 *
 * @return the number of delete effects removed.
 */
size_t normalize_delete_then_set(Problem& problem);

} // namespace bp
