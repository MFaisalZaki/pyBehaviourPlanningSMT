"""bpbench: benchmark harness for pyBehaviourPlanningSMT.

Runs the FBI diverse planner (with its diversity-indicator plugins) against
ForbidIterative baselines that generate a plan pool and extract a diverse
subset, with BehaviourDiversityCounter as the common judge of every returned
plan set. The stages, experiment layout and sandbox structure follow the
aspbench harness of ASPPlanners
(https://github.com/MFaisalZaki/ASPPlanners/tree/main/benchmarks).
"""

__version__ = "0.1.0"
