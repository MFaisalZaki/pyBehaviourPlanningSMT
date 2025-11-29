import argparse
import os
import sys
import json
import time

import unified_planning as up
import subprocess
import tempfile
from itertools import chain
from subprocess import SubprocessError
from copy import deepcopy
from unified_planning.io import PDDLReader, PDDLWriter
from unified_planning.shortcuts import CompilationKind
from unified_planning.shortcuts import OneshotPlanner, AnytimePlanner, OperatorKind
from unified_planning.engines import PlanGenerationResultStatus as ResultsStatus

from behaviour_planning.over_domain_models.smt.shortcuts import GoalPredicatesOrderingSMT, MakespanOptimalCostSMT, ResourceCountSMT, UtilityValueSMT
from behaviour_planning.over_domain_models.smt.shortcuts import ForbidBehaviourIterativeSMT

from behaviour_planning.over_domain_models.smt.fbi.planner.planner import ForbidBehaviourIterativeSMT

def arg_parser():
    parser = argparse.ArgumentParser(description="Generate SLURM tasks for running experiments.")
    parser.add_argument('--taskfile', type=str, required=True, help='Path to the task file.')
    parser.add_argument('--outputdir', type=str, required=True, help='Directory to store output files.')
    return parser

def add_utility_values(task):
    from unified_planning.model.walkers.free_vars import FreeVarsExtractor
    vars = next(map(lambda expr: FreeVarsExtractor().get(expr), task.goals), None)
    if vars is None: return {}
    goals = {g: (i+1)*2 for i, g in enumerate(vars)}
    task.add_quality_metric(up.model.metrics.Oversubscription(goals, task.environment))
    return goals

def construct_results_file(taskdetails, task, plans, bspace):
    task_writer = PDDLWriter(task)
    resultsfile = {
        'plans': [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour.replace("\n","")}' for p in plans],
        'diversity-scores': {
            'behaviour-count': len(set(p.behaviour for p in plans))
        },
        'info' : {
            'domain' : os.path.basename(os.path.dirname(taskdetails['domainfile'])) + '/' + os.path.basename(taskdetails['domainfile']),
            'problem': os.path.basename(taskdetails['problemfile']),
            'planner': taskdetails['planner'],
            'tag' : taskdetails['planner'],
            'planning-type': taskdetails['planning-type'],
            'k': taskdetails['k-plans'],
            'q': taskdetails['q']
        },
    }
    return resultsfile

def select_plans_using_bspace(taskdetails, dims, planlist, compilation_list, is_oversubscription_planning):
    from behaviour_planning.over_domain_models.smt.bss.behaviour_count.behaviour_count import BehaviourCountSMT
    bspace_cfg = {
        "encoder": "seq",
        "solver-timeout-ms": 600000,
        "solver-memorylimit-mb": 16000,
        "dims": dims,
        "run-plan-validation": False,
        "disable-after-goal-state-actions": False,
        "select-k": taskdetails['k-plans']
    }
    bspace = BehaviourCountSMT(taskdetails['domainfile'], taskdetails['problemfile'], bspace_cfg, planlist, is_oversubscription_planning, compilation_list)
    return bspace, bspace.selected_plans(taskdetails['k-plans'])


def run_fbi(taskdetails, dims, compilation_list):
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    k = taskdetails['k-plans']
    q = taskdetails['q']

    base_planner_cfg = {}

    if taskdetails['planning-type'] == 'numerical':
        base_planner_cfg = {
            "planner-name": "SMTPlanner",
            "encoder": "EncoderForall", 
            "upper-bound": 100, 
            "search-strategy": "SMTSearch", 
            "configuration": "forall", 
            "run-validation": False,
            "compilationlist": list(map(lambda e: (e[0], str(e[1]).replace('CompilationKind.', '')), compilation_list))
        }
    else:
        base_planner_cfg = {
            "planner-name": "symk-opt",
            "symk_search_time_limit": "900s"
        }

    _params = {
        "fbi-planner-type": "ForbidBehaviourIterativeSMT",
        "base-planner-cfg": base_planner_cfg,
        "bspace-cfg": {
            "quality-bound-factor" : q,
            "encoder": "seq",
            "solver-timeout-ms": 600000,
            "solver-memorylimit-mb": 16000,
            "dims": [] if 'naive' in taskdetails['planner'] else dims,
            "compliation-list": compilation_list,
            "run-plan-validation": False,
            "disable-after-goal-state-actions": False
        }
    }

    # If the planning task is oversubscription, we add the utility dimension by default.
    _goals  = add_utility_values(task) if taskdetails['planning-type'] == 'oversubscription' else {}
    planner = ForbidBehaviourIterativeSMT(task, _params['bspace-cfg'], _params['base-planner-cfg'])
    plans   = planner.plan(k)
    bspace  = planner.bspace
    if 'naive' in taskdetails['planner']:
        task_writer = PDDLWriter(task)
        _plans_str = [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' for p in plans]
        bspace, select_plans = select_plans_using_bspace(taskdetails, dims, _plans_str, compilation_list, taskdetails['planning-type'] == 'oversubscription')
        plans = list(chain.from_iterable(bspace.selected_plans_list.values()))

    results = construct_results_file(taskdetails, task, plans, bspace)
    return results | {'logs': planner.log_msg} | {'oversubscription-goals': {str(g): u for g, u in _goals.items()}}

def run_fi(taskdetails, dims, compilation_list):
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)

    cmd  = [sys.executable]
    cmd += ["-m"]
    cmd += ["forbiditerative.plan"]
    cmd += ["--planner"]
    cmd += ["extended_unordered_topq"]
    cmd += ["--domain"]
    cmd += [taskdetails['domainfile']]
    cmd += ["--problem"]
    cmd += [taskdetails['problemfile']]
    cmd += ["--number-of-plans"]
    cmd += [str(taskdetails['k-plans'])]
    # cmd += ["1000"]
    cmd += ["--quality-bound"]
    cmd += [str(taskdetails['q'])]
    cmd += ["--symmetries"]
    cmd += ["--use-local-folder"]
    cmd += ["--clean-local-folder"]
    cmd += ["--suppress-planners-output"]
    cmd += ["--overall-time-limit"]
    cmd += ["1800"]

    fienv = os.environ.copy()
    fienv['FI_PLANNER_RUNS'] = tmpdir
    logs = []
    try:
        output = subprocess.check_output(cmd, env=fienv, cwd=tmpdir)
    except SubprocessError as e:
        logs.append(str(e))
        return {}
    
    planlist = []
    found_plans = os.path.join(tmpdir, 'found_plans', 'done')
    if not os.path.exists(found_plans): return {}
    for plan in os.listdir(found_plans):
        with open(os.path.join(found_plans, plan), 'r') as f:
            plan = f.read()
            if not plan in planlist: planlist.append(plan)
    
    bspace, selected_plans = select_plans_using_bspace(taskdetails, dims, planlist, compilation_list, False)
    
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    results = construct_results_file(taskdetails, task, selected_plans, bspace)
    task_writer = PDDLWriter(task)
    all_plans = [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour.replace("\n","")}' for p in chain.from_iterable(bspace.selected_plans_list.values())]
    return results | {'logs': logs + bspace.bspace.log_msg, 'all-plans': all_plans}

def run_symk(taskdetails, dims, compilation_list):
    tmpdir = os.path.join(taskdetails['sandbox-dir'], 'tmp', taskdetails['filename'].replace('.json',''))
    os.makedirs(tmpdir, exist_ok=True)
    task = PDDLReader().parse_problem(taskdetails['domainfile'], taskdetails['problemfile'])
    k = taskdetails['k-plans']
    q = taskdetails['q']

    planlist = []
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmpdirname:        
        with OneshotPlanner(name="symk-opt") as planner:
            result = planner.solve(task)
            plan = result.plan
            assert plan is not None, "No plan found by symk"
            cost_bound = int(len(plan.actions) * q)

    _osp_task = deepcopy(task)
    _goals  = {}
    if taskdetails['planning-type'] == 'oversubscription':
        _goals  = add_utility_values(_osp_task) 
        _osp_task.goals.clear()
    # now remove the hard goals then generate k plans with different utilities.
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmpdirname:        
        with AnytimePlanner(name='symk', params={"symk_search_time_limit": "1800",
                                                 "plan_cost_bound": 
                                                 cost_bound, "number_of_plans": k}) as planner:
            for i, result in enumerate(planner.get_solutions(_osp_task)):
                if result.status == ResultsStatus.INTERMEDIATE:
                    planlist.append(result.plan) if i < k else None
    
    planlist = list(filter(lambda p: len(p.actions) > 0, planlist))

    task_writer = PDDLWriter(_osp_task)
    plansstr    = [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' for p in planlist]
    bspace, selected_plans = select_plans_using_bspace(taskdetails, dims, plansstr, compilation_list, True)
    results = construct_results_file(taskdetails, _osp_task, selected_plans, bspace)
    return results | {'logs': bspace.bspace.log_msg} | {'oversubscription-goals': {str(g): u for g, u in _goals.items()}}

def solve(taskname, args):

    env = up.environment.get_environment()
    env.error_used_name = False
    env.credits_stream  = None

    with open(args.taskfile, 'r') as f:
        taskdetails = json.load(f)
    
    compilation_list  = [["up_quantifiers_remover", CompilationKind.QUANTIFIERS_REMOVING]]
    compilation_list += [["up_disjunctive_conditions_remover", CompilationKind.DISJUNCTIVE_CONDITIONS_REMOVING]]
    compilation_list += [["up_grounder", CompilationKind.GROUNDING]] if 'numerical' in taskdetails['planning-type'] else [["fast-downward-reachability-grounder", CompilationKind.GROUNDING]]

    dims = []

    if taskdetails['planning-type'] == 'oversubscription':
        dims = [
            [MakespanOptimalCostSMT, {"cost-bound-factor": taskdetails['q']}],
            [UtilityValueSMT, {}]
        ]
    else:
        dims = [
            [GoalPredicatesOrderingSMT, {}],
            [MakespanOptimalCostSMT, {"cost-bound-factor": taskdetails['q']}]
        ]
        dims += [[ResourceCountSMT, taskdetails['resources']]] if taskdetails['resources'] is not None and os.path.exists(taskdetails['resources']) else []

    ret_details = {}
    start_time = time.time()
    match taskdetails['planner']:
        case 'fbi-smt-naive' | 'fbi-smt':
            ret_details = run_fbi(taskdetails,  dims, compilation_list)
        case 'fi-bc':
            ret_details = run_fi(taskdetails,   dims, compilation_list)
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

def main():
    args = arg_parser().parse_args()
    sandbox_dir = os.path.dirname(args.outputdir)
    taskname = os.path.basename(args.taskfile).replace('.json','')
    errorsdir = os.path.join(sandbox_dir, 'errors')
    os.makedirs(errorsdir, exist_ok=True)
    
    # # for dev only
    # solve(taskname, args)

    try:
        solve(taskname, args)
    except Exception as e:
        with open(os.path.join(errorsdir, f'{taskname}_error.log'), 'a') as f:
            f.write(str(e) + '\n')

if __name__ == "__main__":
    main()