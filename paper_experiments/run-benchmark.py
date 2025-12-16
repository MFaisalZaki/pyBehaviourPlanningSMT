import argparse
import os
import sys
import json
import time

import unified_planning as up
import subprocess
import tempfile

import renamer

from itertools import chain
from subprocess import SubprocessError
from copy import deepcopy
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.shortcuts import CompilationKind, Compiler
from unified_planning.shortcuts import OneshotPlanner, AnytimePlanner, OperatorKind
from unified_planning.engines import PlanGenerationResultStatus as ResultsStatus

from utilities import construct_results_file, add_utility_values

# from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, ResourceCountSMT, UtilityValueSMT, FunctionsSMT
# from behaviour_planning.over_domain_models.smt.shortcuts import ForbidBehaviourIterativeSMT

# from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import BehaviourCountSimulator
# from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_counter_simulator import GoalPredicatesOrderingSimulator, MakespanOptimalCostSimulator, ResourceCountSimulator, UtilityValueSimulator, FunctionsSimulator

# from behaviour_planning.over_domain_models.smt.fbi.planner.planner import ForbidBehaviourIterativeSMT


def arg_parser():
    parser = argparse.ArgumentParser(description="Generate SLURM tasks for running experiments.")
    parser.add_argument('--taskfile', type=str, required=True, help='Path to the task file.')
    parser.add_argument('--outputdir', type=str, required=True, help='Directory to store output files.')
    return parser

def select_k_plans(task, k, dims, planlist):
    from behaviour_planning_smt.bss.behaviour_diversity_count import BehaviourDiversityCount
    bspace = BehaviourDiversityCount(task, planlist, dims)
    return bspace, bspace.optimise(k)

def run_fbi(taskdetails, dims):
    from behaviour_planning_smt.fbi.planner import ForbiddenBehaviorSMTPlanner
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    k = taskdetails['k-plans']
    q = taskdetails['q']
    _goals  = add_utility_values(task) if taskdetails['planning-type'] == 'oversubscription' else {}
    planner = ForbiddenBehaviorSMTPlanner(task, dims)
    plans   = planner.plan(k)
    bspace, selected_plans = select_k_plans(task, k-1, dims, plans)
    results = construct_results_file(taskdetails, task, selected_plans)
    return results | {'oversubscription-goals': {str(g): u for g, u in _goals.items()}}


def solve(taskname, args):

    env = up.environment.get_environment()
    env.error_used_name = False
    env.credits_stream  = None

    with open(args.taskfile, 'r') as f:
        taskdetails = json.load(f)
    
    # TODO: Run a task renamer compilation to avoid the issue triggered by the mismatch between action names due 
    # the difference in - and _.
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)
    # read the task, then rename it and then write it back.
    # 
    # renamed_task   = renamer.Renamer().compile(_original_task).problem
    compilation_list  = []
    if not taskdetails['planning-type'] == 'numerical':
        compilation_list += [["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING]]
        compilation_list += [["up_disjunctive_conditions_remover", CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING]]
    # Apply these compilations and write the problem to a file to deal with with -,_ mistmatch.

    _original_task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    names = [name for name, _ in compilation_list]
    compilationkinds = [kind for _, kind in compilation_list]
    with Compiler(names=names, compilation_kinds=compilationkinds) as compiler:
        compiled_task = compiler.compile(_original_task)

    _task_writer   = PDDLWriter(compiled_task.problem)
    renamed_domainfile  = os.path.join(tmpdir, 'renamed-domain.pddl')
    renamed_problemfile = os.path.join(tmpdir, 'renamed-problem.pddl')
    _task_writer.write_domain(renamed_domainfile)
    _task_writer.write_problem(renamed_problemfile)

    taskdetails['domainfile-name']  = taskdetails['domainfile']
    taskdetails['problemfile-name'] = taskdetails['problemfile']

    taskdetails['domainfile']  = renamed_domainfile
    taskdetails['problemfile'] = renamed_problemfile

    compilation_list += [["up_grounder", CompilationKind.GROUNDING]] if 'numerical' in taskdetails['planning-type'] else [["fast-downward-reachability-grounder", CompilationKind.GROUNDING]]

    dims = []

    if taskdetails['planning-type'] == 'oversubscription':
        _goals = add_utility_values(compiled_task.problem)
        dims = [
            ['cb', {"quality-bound": taskdetails['q']}],
            ['uv', {"utility-goals": _goals}]
        ]
    else:
        dims = [
            ['go', {}],
            ['cb', {"quality-bound": taskdetails['q']}]
        ]
        if taskdetails['resources'] is not None and os.path.exists(taskdetails['resources']):
            # I hate this but we have no saying in this.
            # make sure to rename the resouces details.
            with open(taskdetails['resources'], 'r') as f:
                resource_content = f.read()
            resource_content = resource_content.replace('-', '_')
            with open(taskdetails['resources'], 'w') as f:
                f.write(resource_content)

            if taskdetails['planning-type'] == 'numerical':
                dims += [['fn', taskdetails['resources']]]
            else:
                dims += [['ru', taskdetails['resources']]]

    ret_details = {}
    start_time = time.time()
    match taskdetails['planner']:
        case 'fbi-smt-naive' | 'fbi-smt':
            ret_details = run_fbi(taskdetails, dims)
        case 'fi-bc':
            ret_details = run_fi(taskdetails, dims)
        case 'symk':
            ret_details = run_symk(taskdetails, dims, compilation_list)
        case _:
            assert False, f"Unknown planning type {taskdetails['planning-type']}"
    end_time = time.time()
    ret_details['total-time-seconds'] = end_time - start_time

    outputpath = os.path.join(args.outputdir, f'{taskname}-results.json')
    if len(ret_details) == 0: return
    with open(outputpath, 'w') as f:
        json.dump(ret_details, f, indent=4)
    
    # delete created files.
    if os.path.exists(taskdetails['domainfile']):
        # delete the dir 
        import shutil
        shutil.rmtree(os.path.dirname(taskdetails['domainfile']))

def main():
    args = arg_parser().parse_args()
    sandbox_dir = os.path.dirname(args.outputdir)
    taskname = os.path.basename(args.taskfile).replace('.json','')
    errorsdir = os.path.join(sandbox_dir, 'errors')
    os.makedirs(errorsdir, exist_ok=True)
    os.makedirs(args.outputdir, exist_ok=True)
    
    # # for dev only
    solve(taskname, args)

    try:
        solve(taskname, args)
    except Exception as e:
        with open(os.path.join(errorsdir, f'{taskname}_error.log'), 'a') as f:
            f.write(str(e) + '\n')

if __name__ == "__main__":
    main()