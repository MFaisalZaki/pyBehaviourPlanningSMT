import os
import json
import statistics

from scipy import stats
from itertools import combinations 
from collections import defaultdict

from utilities import getkeyvalue

import os

def read_bc_results(directory):
    # list files in the directory
    instances = list()
    for file in map(lambda x: os.path.join(directory, x), os.listdir(directory)):
        if not file.endswith('.json'): continue
        with open(file, 'r') as f:
            data = json.load(f)
        plannername = getkeyvalue(data, 'tag')
        if plannername is None: continue
        q_value = getkeyvalue(data, 'q')
        k_value = getkeyvalue(data, 'k')
        domain_problem = f"{getkeyvalue(data, 'domain')}-{getkeyvalue(data, 'problem')}"
        planner_tag = getkeyvalue(data, 'tag')
        behaviour_count = getkeyvalue(data, 'behaviour-count')
        instances.append(
            {
                'q': q_value,
                'k': k_value,
                'domain-problem': domain_problem,
                'planner': planner_tag,
                'behaviour-count': behaviour_count
            }
        )
    return instances

def read_coverage_results(directory):
    # list files in the directory
    instances = list()
    for file in map(lambda x: os.path.join(directory, x), os.listdir(directory)):
        if not file.endswith('.json'): continue
        with open(file, 'r') as f:
            data = json.load(f)
        plannername = getkeyvalue(data, 'tag')
        if plannername is None: continue
        q_value = getkeyvalue(data, 'q')
        k_value = getkeyvalue(data, 'k')
        domain_problem = f"{getkeyvalue(data, 'domain')}-{getkeyvalue(data, 'problem')}"
        planner_tag = getkeyvalue(data, 'tag')
        plan_len = len(getkeyvalue(data, 'plans'))
        instances.append({
            'q': q_value,
            'k': k_value,
            'domain-problem': domain_problem,
            'planner': planner_tag,
            'plan-len': plan_len
        })
    return instances

instancesdir = os.path.join(os.path.dirname(__file__), '..', '..', 'sandbox-classical-behaviour-count-exp/score-dump-results')
solvedinstancesdir = os.path.join(os.path.dirname(__file__), '..', '..', 'sandbox-classical-behaviour-count-exp/dump-results')

instancesdir = '/Users/mustafafaisal/Developer/pyBehaviourPlanningSMT/sandbox-benchmark-numerical/resultsdir'
solvedinstancesdir = '/Users/mustafafaisal/Developer/pyBehaviourPlanningSMT/sandbox-benchmark-numerical/resultsdir'

c_values = [2, 3]  # we only consider pairs and triplets of planners for comparison
solvedinstance = read_coverage_results(solvedinstancesdir)
instances      = read_bc_results(instancesdir)

# # this is simple, we need to contruct a summary of those results.
# # Uncomment for classical only.
q_values = set(e['q'] for e in instances)
k_values = set(e['k'] for e in instances)
planners = set(e['planner'] for e in solvedinstance)


coverage_results = defaultdict(dict)
for q in sorted(q_values):
    coverage_results[q] = defaultdict(dict)
    for k in sorted(k_values):
        coverage_results[q][k] = defaultdict(dict)
        for planner in planners:
            if planner in ['fi-none']:
                coverage = len(list(filter(lambda e: e['q'] == q and e['k'] == k and e['planner'] == planner and k <= e['plan-len'], solvedinstance)))
            else:
                coverage = len(list(filter(lambda e: e['q'] == q and e['planner'] == planner and k <= e['plan-len'], solvedinstance)))
            coverage_results[q][k][planner] = coverage

# save this coverage result
dumpdir = os.path.join(solvedinstancesdir, '..', 'analysis-run')
os.makedirs(dumpdir, exist_ok=True)
with open(os.path.join(dumpdir, 'coverage.json'), 'w') as f:
    json.dump(coverage_results, f, indent=4)

# now we need to compute the behaviour count statistics.
all_planners = set(e['planner'] for e in instances)
q_values = set(e['q'] for e in instances)
k_values = set(e['k'] for e in instances)
planners = set(e['planner'] for e in instances)


for c in c_values:
    for q in sorted(q_values):
        for k in sorted(k_values):
            for planners in combinations(all_planners, c):
                if len(planners) < 2: continue
                planners_instances = [list(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner, instances)) for planner in planners]
                if any(len(p_instances) < 2 for p_instances in planners_instances): continue
                common_instances = set.intersection(*[set(map(lambda e: e['domain-problem'], p_instances)) for p_instances in planners_instances])
                if len(common_instances) < 2: continue
                filtered_instances_per_planner = [list(sorted(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner and x['domain-problem'] in common_instances, instances), key=lambda k:k['domain-problem'])) for planner in planners]
                assert all(len(f_instances) == len(filtered_instances_per_planner[0]) for f_instances in filtered_instances_per_planner)
                samples_per_planner = [list(map(lambda e:e['behaviour-count'], f_instances)) for f_instances in filtered_instances_per_planner]
                results_dict = {f'{planner}-samples': samples for planner, samples in zip(planners, samples_per_planner)}
                for planner, samples in zip(planners, samples_per_planner):
                    results_dict[f'{planner}-bc'] = sum(samples)
                if c == 2:
                    results_dict['p-value'] = round(stats.ttest_rel(*samples_per_planner).pvalue, 3)
                elif c == 3:
                    results_dict['p-value'] = round(stats.f_oneway(*samples_per_planner).pvalue, 3)
                results_dict['common-instances-count'] = len(common_instances)
                results_dict['common-instances'] = list(common_instances)

                # dump this to file
                dumpdir = os.path.join(instancesdir, '..', 'analysis-run', f"{c}-{q}-{k}-{'-'.join(planners)}.json")
                os.makedirs(os.path.dirname(dumpdir), exist_ok=True)
                with open(dumpdir, 'w') as f:
                    json.dump(results_dict, f, indent=4)
pass