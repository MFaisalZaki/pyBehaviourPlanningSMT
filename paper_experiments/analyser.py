import os
import json
import statistics
import argparse

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from scipy import stats
from itertools import combinations, chain
from collections import defaultdict, Counter
from copy import deepcopy
from utilities import getkeyvalue

import os

planner_name_map = {
    'symk': r'$\mathrm{SymK}$',
    'fi-bc': r'$\mathrm{FI_{bdc}}$',
    'fbi-smt': r'$\mathrm{FBI_{SMT}}$',
    'fbi-smt-naive': r'$\mathrm{FBI_{SMT}^{naive}}$',
}

color_map = {
    r'$\mathrm{FBI_{SMT}}$':         '#1f77b4',  # blue
    r'$\mathrm{FBI_{SMT}^{naive}}$': '#d62728',  # red
    r'$\mathrm{FI_{bdc}}$':          '#2ca02c',  # green
    r'$\mathrm{SymK}$':              '#9467bd',  # purple
}

plt.rcParams.update({
    'font.size': 16,
    'axes.titlesize': 16,
    'axes.labelsize': 16,
    'xtick.labelsize': 16,
    'ytick.labelsize': 16,
    'legend.fontsize': 16,
    'figure.titlesize': 16,
    'mathtext.default': 'regular',
    'font.family': 'serif',
    'mathtext.fontset': 'cm'
})


def arg_parser():
    parser = argparse.ArgumentParser(description="Generate SLURM tasks for running experiments.")
    parser.add_argument('--sandbox-dir', type=str, required=True, help='Path to the task file.')
    parser.add_argument('--outputdir', type=str, required=True, help='Directory to store output files.')
    return parser


def read_raw_results(resultsdir):
    ret_results = list()
    for file in map(lambda x: os.path.join(resultsdir, x), os.listdir(resultsdir)):
        if not file.endswith('.json'): continue
        with open(file, 'r') as f:
            data = json.load(f)
        
        # now we need to skip the files that have the following conditions:
        # 1. number of plans is less than the number of k
        # 2. if there are no plans key.
        # 3. if the execution time is zero.
        k_value = getkeyvalue(data, 'k')
        plans   = getkeyvalue(data, 'plans')
        execution_time = getkeyvalue(data, 'total-time-seconds')
        if plans is None: continue
        if len(plans) < k_value: continue
        if execution_time is None or execution_time == 0: continue

        _processed_entry = {
            'q': getkeyvalue(data, 'q'),
            'k': k_value,
            'domain': getkeyvalue(data, 'domain'),
            'instance': getkeyvalue(data, 'problem'),
            'planner': getkeyvalue(data, 'tag'),
            'plans': plans,
            'behaviour-count': getkeyvalue(data, 'behaviour-count'),
            'execution-time': execution_time
        }
        ret_results.append(_processed_entry)
    return ret_results

def generate_summary_tables(raw_results):
    q_values      = set(e['q'] for e in raw_results)
    k_values      = set(e['k'] for e in raw_results)
    planners_tags = set(e['planner'] for e in raw_results)

    # The return table should have the following structure.
    # q, k, (coverage) planners, (execution time) planners (common instance), (behaviour count) planners

    _coverage_details = defaultdict(lambda: defaultdict(dict))
    _behaviour_count_details = defaultdict(lambda: defaultdict(dict))
    _execution_time_details = defaultdict(lambda: defaultdict(dict))
    _planner_details = defaultdict(lambda: defaultdict(dict))

    _coverage_values = Counter((e['q'], e['k'], e['planner']) for e in raw_results)

    for q in sorted(q_values):
        for k in sorted(k_values):
            # do these results per pairs.
            for i in range(2, len(planners_tags)+1):
                for planners in combinations(planners_tags, i):
                    _planner_details[q][k] = {planner: list(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner, raw_results)) for planner in planners}

                    # del the plans to save space. 
                    for planner in planners:
                        for entry in _planner_details[q][k][planner]:
                            if not 'plans' in entry: continue
                            del entry['plans']
                            # entry['plans'] = '-PLAN-DELIMITER-'.join(entry['plans'])

                    planners_results = {planner: list(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner, raw_results)) for planner in planners}
                    planners_key = '-PLANNER-'.join(planners_results.keys())
                    # Step 1 compute coverage by counting the number of instances solved by each planner
                    _coverage_details[q][k][planners_key] = {p:_coverage_values[(q,k,p)] for p in planners}
                    # {
                    #     planner: len(planners_results[planner]) for planner in planners
                    # }

                    _execution_time_details[q][k][planners_key]   = {}
                    _execution_time_details[q][k][planners_key] |= {
                        f'{planner}-mean': round(statistics.mean([e['execution-time'] for e in planners_results[planner]]), 3) if len([e['execution-time'] for e in planners_results[planner]]) > 2 else -1 for planner in planners 
                    }
                    _execution_time_details[q][k][planners_key] |= {
                        f'{planner}-std': round(statistics.stdev([e['execution-time'] for e in planners_results[planner]]), 3) if len([e['execution-time'] for e in planners_results[planner]]) > 2 else -1 for planner in planners
                    }
                    _execution_time_details[q][k][planners_key] |= {
                        f'{planner}-max': round(max([e['execution-time'] for e in planners_results[planner]]), 3) if len([e['execution-time'] for e in planners_results[planner]]) > 2 else -1 for planner in planners
                    }
                    _execution_time_details[q][k][planners_key] |= {
                        f'{planner}-min': round(min([e['execution-time'] for e in planners_results[planner]]), 3) if len([e['execution-time'] for e in planners_results[planner]]) > 2 else -1 for planner in planners
                    }

                    common_instances_per_planner = [set( f"{e['domain']}-{e['instance']}" for e in filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner, raw_results)) for planner in planners]
                    common_instances_per_planner = set.intersection(*common_instances_per_planner)

                    fitlered_planners_results = {
                        planner: sorted(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner and f"{x['domain']}-{x['instance']}" in common_instances_per_planner, raw_results), key = lambda x: f"{x['domain']}-{x['instance']}") for planner in planners
                    }

                    _behaviour_count_details[q][k][planners_key] = {}
                    _behaviour_count_details[q][k][planners_key] |= {
                        f'{planner}': sum([e['behaviour-count'] for e in fitlered_planners_results[planner]]) for planner in planners
                    }

                    # compute statistical significance.
                    bc_values = [[e['behaviour-count'] for e in fitlered_planners_results[planner]] for planner in fitlered_planners_results.keys()]
                    p_value = round(stats.ttest_rel(*bc_values).pvalue, 3) if len(planners) == 2 else round(stats.f_oneway(*bc_values).pvalue, 3)
                    
                    _behaviour_count_details[q][k][planners_key] |= {
                        'common-instances-count': len(common_instances_per_planner),
                        'common-instances': [f'{e["domain"]}-{e["instance"]}' for e in sorted(filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planners[0] and f"{x['domain']}-{x['instance']}" in common_instances_per_planner, raw_results), key = lambda x: f"{x['domain']}-{x['instance']}")],
                        'p-value': str(p_value),
                        'statistical-test': 'ttest' if len(planners) == 2 else 'anova',
                        'is-significant': str(p_value < 0.05),
                        'raw-values': {
                            planner: [e['behaviour-count'] for e in fitlered_planners_results[planner]] for planner in planners
                        }

                    }

    return {
        'coverage': _coverage_details,
        'behaviour-count': _behaviour_count_details,
        'execution-time': _execution_time_details,
        'planner-details': _planner_details
    }


def generate_plots(resutls, dumpdir):
    os.makedirs(dumpdir, exist_ok=True)

    # step one plot violin's for behaviour count.
    # This one is tricky we need to plot the common instances not the whole thing.
    # for now let's plot them all to get the code working and then we can refine it later.
    planner_names = set()
    for q, q_values in resutls['planner-details'].items():
        planners_groups = defaultdict(list)
        for k, k_values in q_values.items():
            planner_names.update(set(planner_name_map[planner] for planner in k_values.keys()))
            
            common_instances_per_planner = [set( f"{e['domain']}-{e['instance']}" for e in filter(lambda x: x['q'] == q and x['k'] == k and x['planner'] == planner, chain.from_iterable(k_values.values()))) for planner in k_values.keys()]
            common_instances_per_planner = set.intersection(*common_instances_per_planner)
            
            filterd_details = deepcopy(k_values)
            for planner in k_values.keys():
                filterd_details[planner] = list(filter(lambda x: f"{x['domain']}-{x['instance']}" in common_instances_per_planner, k_values[planner]))

            planners_groups[f'k={k}'] = list(chain.from_iterable([(planner_name_map[planner], d['behaviour-count']) for d in details] for planner, details in filterd_details.items()))

        sorted_order = sorted(planner_names)
        fig, axes = plt.subplots(1, len(planners_groups), figsize=(20, 5), sharey=False)
        # Plot each group in a subplot
        for ax, (group_name, planners) in zip(axes, planners_groups.items()):
            df = pd.DataFrame(planners, columns=['Planner', 'Value'])
            _sorted_order = [p for p in sorted_order if p in set(e[0] for e in planners)]
            sns.violinplot(x='Planner', y='Value', data=df, ax=ax, palette=color_map, order=_sorted_order, cut=0, inner='box')
            ax.set_title(group_name, fontsize=25)
            ax.set_xlabel('')
            ax.grid(True)
            # Adjust x-axis labels to prevent overlapping
            ax.tick_params(axis='x', labelsize=20)
            ax.tick_params(axis='y', labelsize=25)
            plt.setp(ax.get_xticklabels(), ha='center')

        # Styling
        axes[0].set_ylabel("Behaviour diversity count", fontsize=23)
        for ax in axes[1:]:
            ax.set_ylabel("")

        plt.tight_layout()
        plt.savefig(os.path.join(dumpdir, f'violin-bdc-{q}-{k}.pdf'), bbox_inches='tight', dpi=600)

def remove_noisy_entries(raw_results):
    # So a noisy entry is an entry that did not appear in pervious k values for the same q, domain, instance, and planner.
    to_remove_instances = set()
    q_values = sorted(set(e['q'] for e in raw_results))
    k_values = sorted(set(e['k'] for e in raw_results))
    planners_tags = set(e['planner'] for e in raw_results)
    for q in sorted(q_values):
        for idx, k in enumerate(k_values, start=1):
            for planner in planners_tags:
                # we need to diff the instance between this k and previous k values.
                if k_values.index(k) == 0: continue
                current_k_instances = set((e['domain'], e['instance']) for e in filter(lambda x: x['q'] == q and x['k'] == k                             and x['planner'] == planner, raw_results))
                k_minus_1_instances = set((e['domain'], e['instance']) for e in filter(lambda x: x['q'] == q and x['k'] == k_values[k_values.index(k)-1] and x['planner'] == planner, raw_results))
                diff = current_k_instances - k_minus_1_instances
                if len(diff) == 0: continue
                to_remove_instances.update(set(map(lambda x: (q, x[0], x[1]), diff)))    
    cleaned_results = list(filter(lambda x: (x['q'], x['domain'], x['instance']) not in to_remove_instances, raw_results))
    return cleaned_results

def main():
    args = arg_parser().parse_args()
    resultsdir = os.path.join(args.sandbox_dir, 'resultsdir')
    errorsdir = os.path.join(args.sandbox_dir, 'errors')
    slurmdumps = os.path.join(args.sandbox_dir, 'slurm-dumps')
    outputdir = args.outputdir

    raw_results = read_raw_results(resultsdir)
    raw_results = remove_noisy_entries(raw_results)


    stats_table = generate_summary_tables(raw_results)


    generate_plots(stats_table, os.path.join(outputdir, 'plots'))

    with open(os.path.join(outputdir, 'summary_tables.json'), 'w') as f:
        json.dump(stats_table, f, indent=4)

    pass



if __name__ == "__main__":
    main()