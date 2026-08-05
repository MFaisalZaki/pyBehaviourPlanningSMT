"""
Tutorial 6: Writing your own dimension.

The five built-in dimensions are not special: each is a small C++ class
implementing a two-method contract. Since the move to the C++ core, dimensions
live in behaviour_planning_smt/cpp/src/bss rather than in Python, so adding one
means writing ~40 lines of C++ and rebuilding. This tutorial walks through the
pieces; it prints the recipe and there is nothing else to run.

The pay-off of the C++ move is that the encoding, the dimension constraints and
the forbid-behaviour loop all run inside one solver process, so a custom
dimension automatically benefits from the same incremental solving as the
built-ins.

The contract (see cpp/src/bss/dimension.hpp)
--------------------------------------------

A dimension subclasses bp::Dimension and provides two things:

 1. its constructor appends constraints to `formula_` that tie some Z3
    variables to the plan structure -- this is the __encode__ of the old
    Python DimensionConstructorSMT contract;

 2. `evaluate(model)` returns the behaviour of the found plan along this
    dimension: a Z3 expression pinning the dimension's variables to their
    model values, plus a printable string -- this is the old `expr`.

The expression returned by evaluate() is what makes a behaviour: the planner
ANDs one per dimension, then forbids that conjunction to force the next plan
into a different part of the space. So it has to *identify* the behaviour, not
merely describe it.

The encoder handed to the constructor (bp::BoundedSeqEncoder) exposes the same
handles the old Python encoder did:

    encoder.action_vars_at(t)           one bool per action at step t
    encoder.action_vars_matching(name)  every step var of actions whose grounded
                                        name contains `name`
    encoder.goal_predicate_vars()       goal conjunct i at states 1..N
    encoder.fluent_var_at_last_state(n) a grounded fluent at the final state
    encoder.horizon_expr()              the horizon variable
    encoder.size()                      the number of state layers (N + 1)

Worked example: an action-count dimension
-----------------------------------------

The old Python tutorial built an 'ac' dimension counting how many actions of a
given prefix a plan uses, so plans that drive around a lot and plans that drive
as little as possible count as different behaviours. The C++ version is:

    class ActionCountDimension : public Dimension {
    public:
        ActionCountDimension(const BoundedSeqEncoder& encoder, const std::string& prefix)
            : Dimension("ac") {
            z3::context& ctx = encoder.ctx();
            z3::expr_vector terms(ctx);
            for (const z3::expr& var : encoder.action_vars_matching(prefix)) {
                terms.push_back(z3::ite(var, ctx.int_val(1), ctx.int_val(0)));
            }
            count_ = ctx.int_const("ac");
            formula_.push_back(*count_ == z3::sum(terms));
        }

        BehaviourValue evaluate(const z3::model& model) const override {
            z3::expr value = model.eval(*count_, true);
            return {*count_ == value, value.get_decimal_string(0)};
        }

    private:
        std::optional<z3::expr> count_;
    };

Wiring it up takes three edits:

 1. declare the class in cpp/src/bss/dimension.hpp and implement it in
    cpp/src/bss/dimensions.cpp (or a new .cpp added to CMakeLists.txt);

 2. teach the behaviour space to build it: add a branch for the new name in
    BehaviourSpace's constructor (cpp/src/bss/behaviour_space.cpp), reading
    the dimension's argument from the DimensionSpec;

 3. accept the name on the command line: add it to the valid names in
    cpp/src/config/cli_parser.cpp, and map it in the Python wrapper's
    _dimension_arguments (behaviour_planning_smt/planner_wrapper.py).

Then rebuild and use it like any built-in dimension:

    python build.py
    dims = [['ac', 'navigate'], ['cb', {'quality-bound': 1.5}]]

A dimension does not have to be an integer count. 'go' pins a vector of
ordering variables and 'fn' pins one box per numeric fluent, both returning a
conjunction from evaluate(). Anything the encoder can talk about and
evaluate() can pin down works as a dimension, and two plans that agree on
every dimension count as the same behaviour, so your dimension composes with
the built-ins for free.

This dimension is all the planner needs. Inferring the behaviour of plans that
are already written -- replaying them against the task rather than reading them
off a solver model -- is a separate job, and a separate package:
https://github.com/MFaisalZaki/BehaviourDiversityCounter. A dimension there is
a different contract, so a new dimension that both sides should agree on has to
be written once for each.
"""

print(__doc__)
