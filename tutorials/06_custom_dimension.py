"""
Tutorial 6: Writing your own dimension.

Dimensions are plugins, in the style of Fast Downward's plugin system: each
one is a self-contained C++ file that registers itself under a short name
during static initialization, and the planner builds whatever --dim names ask
for through that registry. The built-ins are not special — 'go', 'cb', 'ru',
'uv' and 'fn' are plugins too, one file each under
behaviour_planning_smt/cpp/src/bss/dimensions/.

This tutorial dissects the bundled example plugin and then runs it: 'ac'
counts how many actions of a given name fragment a plan uses, so plans that
drive around a lot and plans that drive as little as possible count as
different behaviours.

Run with: python tutorials/06_custom_dimension.py

The contract (cpp/src/bss/dimension.hpp)
----------------------------------------

A dimension subclasses bp::Dimension and provides two things:

 1. its constructor appends constraints to `formula_` that tie some Z3
    variables to the plan structure;

 2. `evaluate(model)` returns the behaviour of the found plan along this
    dimension: a Z3 expression pinning the dimension's variables to their
    model values, plus a printable string.

The expression returned by evaluate() is what makes a behaviour: the planner
ANDs one per dimension, then forbids that conjunction to force the next plan
into a different part of the space. So it has to *identify* the behaviour,
not merely describe it.

Dimensions receive the active encoder (cpp/src/encoders/encoder.hpp) and it
is the dimension's responsibility to know which encoders it supports: read
encoder.name() and place the encodings accordingly. Guard with
require_encoder(...) so unsupported combinations fail with a clear error --
or branch per encoder the way the 'cb' dimension does, since how you count
cost depends on the encoder's execution semantics. The encoder hands you the
same handles the old Python encoder did:

    encoder.action_vars_at(t)           one bool per action at step t
    encoder.action_vars_matching(name)  every step var of actions whose
                                        grounded name contains `name`
    encoder.goal_predicate_vars()       goal conjunct i at states 1..N
    encoder.fluent_var_at_last_state(n) a grounded fluent at the final state
    encoder.horizon_expr()              the horizon variable
    encoder.size()                      the number of state layers (N + 1)

The example plugin (cpp/src/bss/dimensions/action_count.cpp)
------------------------------------------------------------

The whole plugin is one file: the class, and a registrar that makes it
addressable as 'ac'. The core of it:

    class ActionCountDimension : public Dimension {
    public:
        ActionCountDimension(const Encoder& encoder, const std::string& fragment)
            : Dimension("ac") {
            require_encoder(encoder, "ac", {"seq"});
            z3::context& ctx = encoder.ctx();
            std::vector<z3::expr> flags;
            for (const z3::expr& var : encoder.action_vars_matching(fragment)) {
                flags.push_back(z3::ite(var, ctx.int_val(1), ctx.int_val(0)));
            }
            count_var_ = ctx.int_const(("ac-" + fragment).c_str());
            formula_.push_back(*count_var_ == sum_vec(ctx, flags));
        }

        BehaviourValue evaluate(const z3::model& model) const override {
            z3::expr value = model.eval(*count_var_, true);
            return {*count_var_ == value, value.get_decimal_string(0)};
        }
    };

    static DimensionPlugin _ac_plugin(
        "ac",
        [](const Encoder& encoder, const std::string& argument,
           const DimensionContext&) -> std::unique_ptr<Dimension> {
            return std::make_unique<ActionCountDimension>(encoder, argument);
        },
        "action count (example plugin): ...");

Adding your own dimension is the same recipe:

 1. copy action_count.cpp to a new file under cpp/src/bss/dimensions/ and
    rename the class, the registered name and the encoding;
 2. add the file to cpp/CMakeLists.txt (the plugins section at the end of
    the source list);
 3. rebuild with `python build.py`.

Nothing else needs editing: the registrar puts the dimension into
`bp_planner --list-dimensions`, the CLI accepts `--dim yourname:arg`, and the
Python wrapper passes unknown dimension names straight through, with a string
additional-info becoming the argument. Encoders extend the same way through
EncoderPlugin (see cpp/src/encoders/seq_encoder.cpp), selected with the
`encoder` option.

Below, the example plugin runs like any built-in dimension.
"""

import os
from unified_planning.io import PDDLReader
from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner

pddls_dir = os.path.join(os.path.dirname(__file__), 'pddls', 'classical-rovers')
task = PDDLReader().parse_problem(os.path.join(pddls_dir, 'domain.pddl'),
                                  os.path.join(pddls_dir, 'p03.pddl'))

# A string additional-info becomes the dimension's argument: here the action
# name fragment to count. 'cb' at 1.5x leaves room for plans that differ in
# how much they navigate.
dims  = []
dims += [['ac', 'navigate']]
dims += [['cb', {"quality-bound": 1.5}]]

planner = ForbiddenBehaviorSMTPlanner(task, dims)
plans   = planner.plan(4)
print(f'\nGot {len(plans)} plans.')

for i, plan in enumerate(plans):
    print(f'Plan {i+1}: {len(plan.actions)} actions | '
          f'navigate actions: {plan.behaviour_attr["ac"]}')

# Inferring the behaviour of plans that are already written -- replaying them
# against the task rather than reading them off a solver model -- is a separate
# job, and a separate package:
# https://github.com/MFaisalZaki/BehaviourDiversityCounter. A dimension there is
# a different contract, so a new dimension that both sides should agree on has
# to be written once for each.
